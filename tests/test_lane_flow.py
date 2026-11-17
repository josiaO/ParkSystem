"""Visits keep moving on lanes without passage sensors; stranded entries expire."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.application.entry_lane import EntryLaneController
from app.application.exit_lane import ExitLaneController
from app.db import Base
from app.domain.parking_engine import (
    ACTIVE, CLOSED, ENTRY_CANCELLED, EXIT_GATE_OPEN_REQUESTED, GATE_OPEN_REQUESTED, LanePolicy, PASSAGE_WAIT, SESSION_CREATED,
)
from app.domain.recognition import CONF_HIGH, NormalizedRecognitionEvent
from app.infrastructure.hardware.receipt_printers import SimulatedKioskPrinter
from app.models import AccessDecision, AccessPlan, Camera, Gate, Lane, ParkingSession, RegisteredVehicle, Site, Tariff
from app.services import lane_sweeper
from app.services.gates import GateCommandResult

RULES = {
    "currency": "TZS", "day_start": "00:00:00", "day_end": "23:59:59",
    "free_day_seconds": 2700, "free_night_seconds": 2700,
    "day_block_seconds": 2700, "night_block_seconds": 2700,
    "day_block_fee": 1000, "night_block_fee": 1000,
    "daily_wrap_fee": 34000, "over_1000_subtract": 1000,
}
WAIT = LanePolicy(passage_sensing=PASSAGE_WAIT)
CFG = {"passage_timeout_seconds": 60, "stranded_entry_minutes": 15}


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
            Lane(id=10, gate_id=1, name="N Entry", direction="ENTRY"),
            Lane(id=20, gate_id=2, name="S Exit", direction="EXIT"),
            Camera(id=100, name="Entry", ip_address="10.0.0.1", site_id=1, gate_id=1, lane_id=10, lane_direction="ENTRY"),
            Camera(id=200, name="Exit", ip_address="10.0.0.2", site_id=1, gate_id=2, lane_id=20, lane_direction="EXIT"),
        ])
        db.add(Tariff(site_id=1, name="Car1", car_type="Car1", currency="TZS", rules=RULES, active=True))
        plan = AccessPlan(site_id=1, name="Staff", kind="STAFF", enabled=True)
        db.add(plan)
        db.flush()
        db.add(RegisteredVehicle(site_id=1, plate="T500REG", plan_id=plan.id, enabled=True))
        db.commit()
    yield factory
    engine.dispose()


class Opener:
    async def __call__(self, db, gate, cameras, reason, session, side, command_uuid=""):
        return GateCommandResult(ok=True, simulated=True, message="OPEN", timestamp="t")


def _event(plate, event_id, camera_id=100, lane_id=10):
    return NormalizedRecognitionEvent(
        event_id=event_id, site_id=1, camera_id=camera_id, lane_id=lane_id, occurred_at="2026-11-17T08:00:00+00:00",
        provider="FASTALPR", plate_raw=plate, plate_normalized=plate, confidence=0.97, bbox=None,
        vehicle_detected=True, image_ref="", plate_crop_ref="", confidence_class=CONF_HIGH, accepted=True,
    )


def _entered_waiting_for_passage(db):
    asyncio.run(EntryLaneController(opener=Opener()).submit(
        db, _event("T500REG", "e1"), gate=db.get(Gate, 1), camera=db.get(Camera, 100), policy=WAIT))
    row = db.scalar(select(ParkingSession).where(ParkingSession.plate == "T500REG"))
    assert row.lifecycle == GATE_OPEN_REQUESTED
    return row


def _age(db, row, seconds):
    row.updated_at = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    db.commit()


def test_exit_read_completes_an_entry_still_waiting_for_passage(Session):
    with Session() as db:
        _entered_waiting_for_passage(db)
        out = asyncio.run(ExitLaneController(opener=Opener()).submit_plate(
            db, plate="T500REG", event_id="x1", site_id=1, gate=db.get(Gate, 2), camera=db.get(Camera, 200),
            lane_id=20, policy=WAIT))
        assert out.get("reason") != "visit_incomplete" and out["barrier_command_accepted"] is not False
        row = db.scalar(select(ParkingSession).where(ParkingSession.plate == "T500REG"))
        assert row.lifecycle == EXIT_GATE_OPEN_REQUESTED


def test_incomplete_visit_at_exit_asks_an_operator_instead_of_raising(Session):
    policy = LanePolicy(receipt_required_before_open=True, print_receipt_on_entry=True, passage_sensing=PASSAGE_WAIT)
    with Session() as db, patch("app.application.entry_lane.settings", SimpleNamespace(deployment_profile="PRODUCTION")):
        asyncio.run(EntryLaneController(printer=SimulatedKioskPrinter(), opener=Opener()).submit(
            db, _event("T501CAS", "e1"), gate=db.get(Gate, 1), camera=db.get(Camera, 100), policy=policy))
        out = asyncio.run(ExitLaneController(opener=Opener()).submit_plate(
            db, plate="T501CAS", event_id="x1", site_id=1, gate=db.get(Gate, 2), camera=db.get(Camera, 200),
            lane_id=20, policy=policy))
        assert out["reason"] == "visit_incomplete" and out["assistance_required"] and out["barrier_opened"] is False


def test_sweeper_assumes_passage_after_the_timeout_only(Session):
    with Session() as db:
        row = _entered_waiting_for_passage(db)
        _age(db, row, 30)
        assert lane_sweeper.sweep_once(db, cfg=CFG)["entry_passage_assumed"] == 0
        _age(db, row, 90)
        assert lane_sweeper.sweep_once(db, cfg=CFG)["entry_passage_assumed"] == 1
        db.refresh(row)
        assert row.lifecycle == ACTIVE
        assert db.scalar(select(AccessDecision).where(AccessDecision.outcome == "PASSAGE_ASSUMED")) is not None


def test_sweeper_closes_an_exit_left_waiting_for_passage(Session):
    with Session() as db:
        _entered_waiting_for_passage(db)
        asyncio.run(ExitLaneController(opener=Opener()).submit_plate(
            db, plate="T500REG", event_id="x1", site_id=1, gate=db.get(Gate, 2), camera=db.get(Camera, 200),
            lane_id=20, policy=WAIT))
        row = db.scalar(select(ParkingSession).where(ParkingSession.plate == "T500REG"))
        _age(db, row, 120)
        assert lane_sweeper.sweep_once(db, cfg=CFG)["exit_passage_assumed"] == 1
        db.refresh(row)
        assert row.lifecycle == CLOSED and row.status == "CLOSED"


def test_stranded_entry_expires_and_frees_the_plate(Session):
    policy = LanePolicy(receipt_required_before_open=True, print_receipt_on_entry=True, passage_sensing=PASSAGE_WAIT)
    with Session() as db, patch("app.application.entry_lane.settings", SimpleNamespace(deployment_profile="PRODUCTION")):
        ctrl = EntryLaneController(printer=SimulatedKioskPrinter(), opener=Opener())
        asyncio.run(ctrl.submit(db, _event("T502STR", "e1"), gate=db.get(Gate, 1), camera=db.get(Camera, 100), policy=policy))
        row = db.scalar(select(ParkingSession).where(ParkingSession.plate == "T502STR"))
        assert row.lifecycle == SESSION_CREATED
        _age(db, row, 5 * 60)
        assert lane_sweeper.sweep_once(db, cfg=CFG)["entry_expired"] == 0
        _age(db, row, 20 * 60)
        assert lane_sweeper.sweep_once(db, cfg=CFG)["entry_expired"] == 1
        db.refresh(row)
        assert row.lifecycle == ENTRY_CANCELLED and row.status == "CLOSED"
        again = asyncio.run(ctrl.submit(db, _event("T502STR", "e2"), gate=db.get(Gate, 1), camera=db.get(Camera, 100), policy=policy))
        assert again["created_session"] is True


def test_zero_disables_the_timeouts(Session):
    with Session() as db:
        row = _entered_waiting_for_passage(db)
        _age(db, row, 10_000)
        assert lane_sweeper.sweep_once(db, cfg={"passage_timeout_seconds": 0, "stranded_entry_minutes": 0}) == {
            "entry_passage_assumed": 0, "exit_passage_assumed": 0, "entry_expired": 0}
