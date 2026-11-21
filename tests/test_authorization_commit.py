"""Authorization Commit: no barrier command before the decision is durable.

docs/architecture.md, "Authorization commit". The opener in these tests
plays the barrier: when it is called it reads the database through a *separate
connection* and checks that the session claim, the access decision and the
REQUESTED gate command are already committed. A "power cut" is an exception
thrown from the opener; the lane sweeper must then report the command as
INTERRUPTED instead of losing or repeating it.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.application.entry_lane import EntryLaneController
from app.application.exit_lane import ExitLaneController
from app.db import Base
from app.domain.parking_engine import LanePolicy, PASSAGE_WAIT
from app.domain.recognition import CONF_HIGH, NormalizedRecognitionEvent
from app.models import AccessDecision, Camera, Gate, GateCommandRecord, Lane, ParkingSession, Site, Tariff
from app.services import lane_sweeper
from app.services.gates import GateCommandResult

RULES = {
    "currency": "TZS", "day_start": "00:00:00", "day_end": "23:59:59",
    "free_day_seconds": 2700, "free_night_seconds": 2700,
    "day_block_seconds": 2700, "night_block_seconds": 2700,
    "day_block_fee": 1000, "night_block_fee": 1000,
    "daily_wrap_fee": 34000, "over_1000_subtract": 1000,
}
OPEN_LANE = LanePolicy(receipt_required_before_open=False, passage_sensing=PASSAGE_WAIT)
NO_TIMEOUTS = {"passage_timeout_seconds": 0, "stranded_entry_minutes": 0}


class PowerCut(BaseException):
    """The process dies while the barrier command is in flight."""


@pytest.fixture()
def Session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'lane.db'}", connect_args={"check_same_thread": False})
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
        db.commit()
    yield factory
    engine.dispose()


def _event(plate: str, event_id: str) -> NormalizedRecognitionEvent:
    return NormalizedRecognitionEvent(
        event_id=event_id, site_id=1, camera_id=100, lane_id=10, occurred_at="2026-11-18T08:00:00+00:00",
        provider="FASTALPR", plate_raw=plate, plate_normalized=plate, confidence=0.97, bbox=None,
        vehicle_detected=True, image_ref="", plate_crop_ref="", confidence_class=CONF_HIGH, accepted=True,
    )


class Barrier:
    """Checks durable state from another connection, then answers or dies."""

    def __init__(self, factory, *, ok: bool = True, die: bool = False):
        self.factory = factory
        self.ok = ok
        self.die = die
        self.seen: list[dict] = []

    async def __call__(self, db, gate, cameras, reason, session, side, command_uuid=""):
        with self.factory() as other:
            command = other.scalar(select(GateCommandRecord).where(GateCommandRecord.command_uuid == command_uuid))
            visit = other.get(ParkingSession, session.id)
            decision = other.scalar(
                select(AccessDecision).where(AccessDecision.session_id == session.id)
                .order_by(AccessDecision.id.desc())
            )
            self.seen.append({
                "command_state": command.state if command else None,
                "command_side": command.side if command else None,
                "claim": (visit.open_command_uuid if side == "ENTRY" else visit.exit_open_command_uuid),
                "decision": decision.outcome if decision else None,
                "decision_uuid": (decision.extra or {}).get("command_uuid") if decision else None,
            })
        if self.die:
            raise PowerCut()
        return GateCommandResult(ok=self.ok, simulated=True, message="OPEN" if self.ok else "relay timeout", timestamp="t")


def _enter(db, factory, plate="T100AAA", **barrier):
    lane = Barrier(factory, **barrier)
    out = asyncio.run(EntryLaneController(opener=lane).submit(
        db, _event(plate, f"in-{plate}"), gate=db.get(Gate, 1), camera=db.get(Camera, 100), policy=OPEN_LANE))
    return out, lane


def _commands(db) -> list[GateCommandRecord]:
    return list(db.scalars(select(GateCommandRecord).order_by(GateCommandRecord.id)))


def test_entry_decision_and_command_are_committed_before_the_barrier_moves(Session):
    with Session() as db:
        out, lane = _enter(db, Session)
        assert out["barrier_command_accepted"] is True
        seen = lane.seen[0]
        assert seen["command_state"] == "REQUESTED" and seen["command_side"] == "ENTRY"
        assert seen["claim"] and seen["decision"] == "ENTRY_AUTHORIZED" and seen["decision_uuid"] == seen["claim"]
        [command] = _commands(db)
        assert command.state == "ACCEPTED" and command.ok and command.completed_at is not None
        decisions = db.scalars(select(AccessDecision).where(AccessDecision.lane_direction == "ENTRY")).all()
        assert [d.outcome for d in decisions] == ["ENTRY_AUTHORIZED"]       # one decision, finalized in place
        assert decisions[0].reason == "entry complete"


def test_entry_barrier_failure_is_recorded_on_the_same_decision(Session):
    with Session() as db:
        out, _ = _enter(db, Session, ok=False)
        assert out["reason"] == "gate_unavailable"
        [command] = _commands(db)
        assert command.state == "FAILED" and not command.ok
        outcomes = [d.outcome for d in db.scalars(select(AccessDecision))]
        assert outcomes == ["GATE_UNAVAILABLE"]


def test_power_cut_during_entry_command_is_reported_not_lost(Session):
    with Session() as db:
        with pytest.raises(PowerCut):
            _enter(db, Session, die=True)
    with Session() as db:                                   # "after the restart"
        [command] = _commands(db)
        assert command.state == "REQUESTED"
        visit = db.scalar(select(ParkingSession).where(ParkingSession.plate == "T100AAA"))
        assert visit.open_command_uuid == command.command_uuid and visit.closed_at is None
        later = datetime.now(timezone.utc) + timedelta(minutes=5)
        counts = lane_sweeper.sweep_once(db, now=later, cfg=NO_TIMEOUTS)
        assert counts["gate_interrupted"] == 1
        db.refresh(command)
        assert command.state == "INTERRUPTED" and command.completed_at is not None
        flag = db.scalar(select(AccessDecision).where(AccessDecision.outcome == "GATE_COMMAND_INTERRUPTED"))
        assert flag is not None and flag.session_id == visit.id and flag.gate_id == 1
        assert lane_sweeper.sweep_once(db, now=later, cfg=NO_TIMEOUTS)["gate_interrupted"] == 0


def test_a_command_in_flight_is_not_interrupted(Session):
    with Session() as db:
        with pytest.raises(PowerCut):
            _enter(db, Session, die=True)
        assert lane_sweeper.sweep_once(db, cfg=NO_TIMEOUTS)["gate_interrupted"] == 0
        assert _commands(db)[0].state == "REQUESTED"


def test_operator_retry_after_interruption_reuses_the_command(Session):
    with Session() as db:
        with pytest.raises(PowerCut):
            _enter(db, Session, die=True)
        lane_sweeper.sweep_once(db, now=datetime.now(timezone.utc) + timedelta(minutes=5), cfg=NO_TIMEOUTS)
        visit = db.scalar(select(ParkingSession).where(ParkingSession.plate == "T100AAA"))
        lane = Barrier(Session)
        out = asyncio.run(EntryLaneController(opener=lane).retry_gate(
            db, visit, policy=OPEN_LANE, gate=db.get(Gate, 1), camera=db.get(Camera, 100),
            command_uuid=visit.open_command_uuid))
        assert out["barrier_command_accepted"] is True
        assert lane.seen[0]["command_state"] == "REQUESTED"            # re-armed and committed first
        [command] = _commands(db)                                       # still one logical command
        assert command.state == "ACCEPTED"


def _exit(db, factory, plate="T100AAA", **barrier):
    lane = Barrier(factory, **barrier)
    out = asyncio.run(ExitLaneController(opener=lane).submit_plate(
        db, plate=plate, event_id=f"out-{plate}", site_id=1, gate=db.get(Gate, 2), camera=db.get(Camera, 200),
        lane_id=20, policy=OPEN_LANE))
    return out, lane


def test_exit_decision_and_command_are_committed_before_the_barrier_moves(Session):
    with Session() as db:
        _enter(db, Session)
        out, lane = _exit(db, Session)                       # inside the free period: nothing to pay
        assert out["barrier_command_accepted"] is True
        seen = lane.seen[0]
        assert seen["command_state"] == "REQUESTED" and seen["command_side"] == "EXIT"
        assert seen["claim"] and seen["decision"] == "EXIT_AUTHORIZED" and seen["decision_uuid"] == seen["claim"]
        exit_command = _commands(db)[-1]
        assert exit_command.state == "ACCEPTED" and exit_command.side == "EXIT"
        exits = db.scalars(select(AccessDecision).where(AccessDecision.lane_direction == "EXIT")).all()
        assert [d.outcome for d in exits] == ["EXIT_AUTHORIZED"]


def test_power_cut_during_exit_command_is_reported(Session):
    with Session() as db:
        _enter(db, Session)
        with pytest.raises(PowerCut):
            _exit(db, Session, die=True)
    with Session() as db:
        exit_command = _commands(db)[-1]
        assert exit_command.side == "EXIT" and exit_command.state == "REQUESTED"
        counts = lane_sweeper.sweep_once(db, now=datetime.now(timezone.utc) + timedelta(minutes=5), cfg=NO_TIMEOUTS)
        assert counts["gate_interrupted"] == 1
        flag = db.scalar(select(AccessDecision).where(AccessDecision.outcome == "GATE_COMMAND_INTERRUPTED"))
        assert flag.lane_direction == "EXIT"


def test_pulse_gate_commits_the_request_before_touching_hardware(Session):
    """Manual opens and lane controllers without an injected opener go through
    _pulse_gate: it must make the REQUESTED row durable first."""
    from app.services import simulation

    seen: list[str | None] = []

    class Hardware:
        async def open(self, gate, cameras, reason, *, side, dry_run, led_text):
            with Session() as other:
                row = other.scalar(select(GateCommandRecord))
                seen.append(row.state if row else None)
            return GateCommandResult(ok=True, simulated=True, message="OPEN", timestamp="t")

    with Session() as db, patch.object(simulation, "controller", lambda: Hardware()):
        result = asyncio.run(simulation._pulse_gate(
            db, db.get(Gate, 1), [db.get(Camera, 100)], reason="manual open", side="ENTRY",
            led_text="", automatic=False,
        ))
        assert result.ok
        assert seen == ["REQUESTED"]
        [command] = _commands(db)
        assert command.state == "ACCEPTED" and command.side == "ENTRY" and command.command_uuid


# ---------------------------------------------------------------- shadow mode
# SITE-PC01 runs Zirp beside the existing system with developer "gate opening"
# switched off. Every authorized exit ended as GATE_UNAVAILABLE and the visit
# stayed open: no visit closed after 29 Oct and the dashboard showed no exits.

def test_shadow_mode_records_an_authorized_exit(Session, monkeypatch):
    monkeypatch.setattr("app.services.developer.gate_opening_enabled", lambda db: False)
    with Session() as db:
        _enter(db, Session)
        out, _lane = _exit(db, Session, ok=False)
        assert out["ok"] is True and out["reason"] == "shadow_exit" and out["barrier_opened"] is False
        visit = db.scalar(select(ParkingSession))
        assert visit.status == "CLOSED" and visit.exit_time is not None
        outcomes = [d.outcome for d in db.scalars(select(AccessDecision).where(
            AccessDecision.lane_direction == "EXIT").order_by(AccessDecision.id))]
        assert outcomes == ["EXIT_RECORDED_SHADOW", "SUPERVISED_CLOSE"]


def test_with_gate_control_on_a_failed_barrier_keeps_the_visit_open(Session, monkeypatch):
    monkeypatch.setattr("app.services.developer.gate_opening_enabled", lambda db: True)
    with Session() as db:
        _enter(db, Session)
        out, _lane = _exit(db, Session, ok=False)
        assert out["reason"] == "gate_unavailable"
        assert db.scalar(select(ParkingSession)).status != "CLOSED"


# ------------------------------------------- re-entry after an exit decision
# SITE-PC01, 21 Nov: 86 arriving cars in 3 hours got no visit because their
# previous visit was left open at an exit ("Open visit already exists").

def _age_visit(db, minutes=30):
    visit = db.scalar(select(ParkingSession).where(ParkingSession.status != "CLOSED"))
    past = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    visit.updated_at = past
    visit.created_at = min(visit.created_at or past, past)
    db.commit()
    return visit


def _enter_again(db, factory, plate="T100AAA"):
    """A later arrival: a new camera event after the lane emptied."""
    from app.services import lane_stay

    lane_stay.reset()
    lane = Barrier(factory)
    return asyncio.run(EntryLaneController(opener=lane).submit(
        db, _event(plate, f"in-again-{plate}"), gate=db.get(Gate, 1), camera=db.get(Camera, 100), policy=OPEN_LANE))


def test_car_entering_again_after_an_unfinished_exit_gets_a_new_visit(Session, monkeypatch):
    monkeypatch.setattr("app.services.developer.gate_opening_enabled", lambda db: True)
    with Session() as db:
        _enter(db, Session)
        _exit(db, Session, ok=False)                         # allowed, barrier answer lost
        old = _age_visit(db)
        assert old.lifecycle == "AUTHORIZED"
        out = _enter_again(db, Session)
        assert out.get("created_session") is True, out
        visits = db.scalars(select(ParkingSession).order_by(ParkingSession.id)).all()
        assert [v.status for v in visits][0] == "CLOSED" and len(visits) == 2
        outcomes = [d.outcome for d in db.scalars(select(AccessDecision).order_by(AccessDecision.id))]
        assert "PREVIOUS_VISIT_CLOSED" in outcomes


def test_a_recent_exit_decision_is_left_alone(Session, monkeypatch):
    monkeypatch.setattr("app.services.developer.gate_opening_enabled", lambda db: True)
    with Session() as db:
        _enter(db, Session)
        _exit(db, Session, ok=False)
        out = _enter_again(db, Session)                      # seconds later: same car, still there
        assert out.get("created_session") is not True
        assert db.scalar(select(ParkingSession)).status != "CLOSED"


def test_a_visit_never_seen_at_an_exit_still_needs_an_operator(Session):
    with Session() as db:
        _enter(db, Session)
        _age_visit(db, minutes=90)
        out = _enter_again(db, Session)
        assert out.get("reason") == "duplicate" and out.get("created_session") is not True


def test_unpaid_visit_seen_at_exit_is_closed_with_the_amount_written_off(Session, monkeypatch):
    monkeypatch.setattr("app.services.developer.gate_opening_enabled", lambda db: True)
    with Session() as db:
        _enter(db, Session)
        visit = db.scalar(select(ParkingSession))
        visit.entry_time = datetime.now(timezone.utc) - timedelta(hours=3)   # past the free period
        db.commit()
        out, _lane = _exit(db, Session)
        assert db.scalar(select(ParkingSession)).lifecycle == "DENIED_PAYMENT_REQUIRED", out
        _age_visit(db)
        again = _enter_again(db, Session)
        assert again.get("created_session") is True
        closing = db.scalar(select(AccessDecision).where(AccessDecision.outcome == "SUPERVISED_CLOSE"))
        assert float((closing.extra or {}).get("written_off") or 0) > 0
