"""Cash top-ups, supervised close, manual entry and honest duplicate reporting."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.application.entry_lane import EntryLaneController
from app.application.exit_lane import ExitLaneController
from app.db import Base
from app.domain.parking_engine import CLOSED, InvalidTransition, LanePolicy, PASSAGE_WAIT
from app.domain.recognition import CONF_HIGH, NormalizedRecognitionEvent
from app.models import (
    AccessDecision, AccessPlan, Camera, Gate, Lane, ParkingSession, PaymentTransaction, RegisteredVehicle, Site, Tariff,
)
from app.services.gates import GateCommandResult
from app.services.parking_sessions import complete_casual_entry, manual_entry, start_entry, supervised_close
from app.services.simulation import mark_paid

RULES = {
    "currency": "TZS", "day_start": "00:00:00", "day_end": "23:59:59",
    "free_day_seconds": 2700, "free_night_seconds": 2700,
    "day_block_seconds": 2700, "night_block_seconds": 2700,
    "day_block_fee": 1000, "night_block_fee": 1000,
    "daily_wrap_fee": 34000, "over_1000_subtract": 1000,
}


@pytest.fixture()
def Session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        db.add(Site(id=1, name="Site", currency="TZS"))
        db.add_all([Gate(id=1, name="North", site_id=1), Gate(id=2, name="South", site_id=1)])
        db.flush()
        db.add_all([
            Lane(id=10, gate_id=1, name="North Entry", direction="ENTRY"),
            Lane(id=20, gate_id=2, name="South Exit", direction="EXIT"),
            Camera(id=100, name="Entry", ip_address="10.0.0.1", site_id=1, gate_id=1, lane_id=10, lane_direction="ENTRY"),
            Camera(id=200, name="Exit", ip_address="10.0.0.2", site_id=1, gate_id=2, lane_id=20, lane_direction="EXIT"),
        ])
        db.add(Tariff(site_id=1, name="Car1", car_type="Car1", currency="TZS", rules=RULES, active=True))
        db.commit()
    yield factory
    engine.dispose()


class Opener:
    def __init__(self):
        self.calls = []

    async def __call__(self, db, gate, cameras, reason, session, side, command_uuid=""):
        self.calls.append(side)
        return GateCommandResult(ok=True, simulated=True, message="OPEN", timestamp="t")


def _visit(db, plate, entered):
    row, _ = start_entry(db, plate=plate, event_id=f"e-{plate}", site_id=1, gate_id=1, lane_id=10,
                         camera_id=100, policy=LanePolicy())
    row.entry_time = entered
    db.commit()
    return complete_casual_entry(db, row, policy=LanePolicy())


def test_cash_top_up_after_grace_is_recorded_and_the_car_can_leave(Session):
    now = datetime.now(timezone.utc)
    with Session() as db:
        row = _visit(db, "T300TOP", now - timedelta(hours=3))
        paid_once = float(mark_paid(db, row, method="KIOSK_CASH").amount_paid)
        row = db.get(ParkingSession, row.id)
        row.entry_time -= timedelta(days=1)          # another day passes
        row.payment_exit_grace_until = now - timedelta(minutes=1)
        db.commit()
        denied = asyncio.run(ExitLaneController(opener=Opener()).submit_plate(
            db, plate="T300TOP", event_id="x1", site_id=1, gate=db.get(Gate, 2), camera=db.get(Camera, 200),
            lane_id=20, at=now))
        assert denied["barrier_opened"] is False
        topped = mark_paid(db, db.get(ParkingSession, row.id), method="KIOSK_CASH")
        txns = db.scalars(select(PaymentTransaction).where(PaymentTransaction.session_id == row.id)).all()
        assert len(txns) == 2 and float(topped.amount_paid) > paid_once
        opened = asyncio.run(ExitLaneController(opener=Opener()).submit_plate(
            db, plate="T300TOP", event_id="x2", site_id=1, gate=db.get(Gate, 2), camera=db.get(Camera, 200),
            lane_id=20, at=now))
        assert opened["barrier_opened"] is True


def test_double_click_on_the_same_cash_settlement_is_still_one_payment(Session):
    from app.infrastructure.payments.ledger import cash_settlement_key, record_succeeded_payment

    with Session() as db:
        row = _visit(db, "T301DBL", datetime.now(timezone.utc) - timedelta(hours=3))
        key = cash_settlement_key(row.id, 0, 3000)
        first = record_succeeded_payment(db, row, amount=3000, idempotency_key=key)
        second = record_succeeded_payment(db, row, amount=3000, idempotency_key=key)
        assert not first["duplicate"] and second["duplicate"]
        assert cash_settlement_key(row.id, 3000, 34000) != key


def test_supervised_close_records_the_write_off(Session):
    with Session() as db:
        row = _visit(db, "T302OLD", datetime.now(timezone.utc) - timedelta(days=3))
        with pytest.raises(ValueError):
            supervised_close(db, row, reason="")
        result = supervised_close(db, row, reason="car left via ParkWatch lane", user_id=None)
        assert result["session"]["lifecycle"] == CLOSED and result["written_off"] > 0
        decision = db.scalar(select(AccessDecision).where(AccessDecision.outcome == "SUPERVISED_CLOSE"))
        assert decision.extra["written_off"] == result["written_off"]
        with pytest.raises(InvalidTransition):
            supervised_close(db, db.get(ParkingSession, row.id), reason="again")
        # The plate can enter again afterwards.
        assert manual_entry(db, plate="T302OLD", site_id=1).id != row.id


def test_manual_entry_uses_the_engine_and_refuses_a_duplicate(Session):
    with Session() as db:
        row = manual_entry(db, plate="t303man", site_id=1)
        assert row.plate == "T303MAN" and row.public_token and row.tariff_rules and row.lifecycle == "ACTIVE"
        with pytest.raises(InvalidTransition):
            manual_entry(db, plate="T303MAN", site_id=1)


def _event(plate, event_id):
    return NormalizedRecognitionEvent(
        event_id=event_id, site_id=1, camera_id=100, lane_id=10, occurred_at="2026-11-17T08:00:00+00:00",
        provider="FASTALPR", plate_raw=plate, plate_normalized=plate, confidence=0.97, bbox=None,
        vehicle_detected=True, image_ref="", plate_crop_ref="", confidence_class=CONF_HIGH, accepted=True,
    )


def test_duplicate_entry_never_claims_the_barrier_opened(Session):
    policy = LanePolicy(passage_sensing=PASSAGE_WAIT)
    opener = Opener()
    with Session() as db:
        plan = AccessPlan(site_id=1, name="Staff", kind="STAFF", enabled=True)
        db.add(plan)
        db.flush()
        db.add(RegisteredVehicle(site_id=1, plate="T304DUP", plan_id=plan.id, enabled=True))
        db.commit()
        ctrl = EntryLaneController(opener=opener)
        asyncio.run(ctrl.submit(db, _event("T304DUP", "e1"), gate=db.get(Gate, 1), camera=db.get(Camera, 100), policy=policy))
        again = asyncio.run(ctrl.submit(db, _event("T304DUP", "e2"), gate=db.get(Gate, 1), camera=db.get(Camera, 100), policy=policy))
        assert again["duplicate"] and again["barrier_opened"] is False and len(opener.calls) == 1
        assert again["stale_visit"] is False            # same approach: no operator needed
        row = db.scalar(select(ParkingSession).where(ParkingSession.plate == "T304DUP"))
        row.created_at = datetime.now(timezone.utc) - timedelta(hours=5)
        db.commit()
        later = asyncio.run(ctrl.submit(db, _event("T304DUP", "e3"), gate=db.get(Gate, 1), camera=db.get(Camera, 100), policy=policy))
        assert later["stale_visit"] is True and later["assistance_required"] is True
