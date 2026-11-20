"""Regression tests for defects found in the November 2026 production audit.

See docs/audit-2026-11.md. Each test names the defect it proves fixed.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import (
    MANUAL_SOURCE_GATE,
    AlertDelivery,
    Camera,
    Gate,
    GateCommandRecord,
    Lane,
    ManualOpenEvent,
    Site,
    User,
)
from app.services import alerts, manual_open
from app.services.gates import GateCommandResult
from app.services.latest_frame import LatestFrameBuffer


@pytest.fixture()
def Session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        db.add(Site(id=1, name="Site", currency="TZS"))
        db.add(Gate(id=2, name="2#", site_id=1))
        db.flush()
        db.add_all([
            Lane(id=21, gate_id=2, name="2# Exit", direction="EXIT"),
            Camera(id=4, name="2# Exit", ip_address="10.0.0.50", site_id=1, gate_id=2, lane_id=21,
                   lane_direction="EXIT"),
            User(id=7, username="cashier", full_name="Cashier A", password_hash="x"),
        ])
        db.commit()
    manual_open.boom_watch.reset()
    manual_open._boom_index_cache.clear()
    yield factory
    engine.dispose()


# ------------------------------------------------------------ frame freshness

def test_latest_frame_take_never_returns_an_older_frame_later():
    """Defect: take() popped the newest and left older frames queued, so the
    next take() returned a frame older than one already consumed."""
    buf = LatestFrameBuffer("audit", maxsize=3)
    for n in range(3):
        buf.put(f"f{n}".encode())
    newest = buf.take()
    assert newest is not None and newest.jpeg == b"f2"
    assert buf.take() is None, "older frames must be dropped, not handed out after a newer one"
    assert buf.dropped == 2 and buf.depth() == 0


# ------------------------------------------------------ duplicate gate pulses

def test_accepted_command_uuid_is_not_pulsed_twice(Session):
    """Defect: re-sending a command UUID that was already ACCEPTED (a replay or
    retry) physically pulsed the barrier again."""
    from app.services import simulation

    calls: list[str] = []

    class Hardware:
        async def open(self, gate, cameras, reason, *, side, dry_run, led_text):
            calls.append(reason)
            return GateCommandResult(ok=True, simulated=False, message="OPEN", timestamp="t")

    with Session() as db:
        db.add(GateCommandRecord(command_uuid="cmd-1", gate_id=2, reason="exit T1", automatic=True,
                                 dry_run=False, ok=True, state="ACCEPTED", side="EXIT"))
        db.commit()
        with patch.object(simulation, "controller", lambda: Hardware()):
            result = asyncio.run(simulation._pulse_gate(
                db, db.get(Gate, 2), [db.get(Camera, 4)], reason="exit T1", side="EXIT",
                led_text="", automatic=True, command_uuid="cmd-1",
            ))
        assert calls == [], "an accepted command must not reach the barrier again"
        assert result.ok and "duplicate" in result.message
        rows = list(db.scalars(select(GateCommandRecord)))
        assert len(rows) == 1 and rows[0].state == "ACCEPTED"


def test_failed_command_uuid_can_still_be_retried(Session):
    """The guard must not block an operator retry of a FAILED command."""
    from app.services import simulation

    calls: list[str] = []

    class Hardware:
        async def open(self, gate, cameras, reason, *, side, dry_run, led_text):
            calls.append(reason)
            return GateCommandResult(ok=True, simulated=False, message="OPEN", timestamp="t")

    with Session() as db:
        db.add(GateCommandRecord(command_uuid="cmd-2", gate_id=2, reason="exit T2", automatic=True,
                                 dry_run=False, ok=False, state="FAILED", side="EXIT"))
        db.commit()
        with patch.object(simulation, "controller", lambda: Hardware()), \
                patch("app.services.simulation.should_pulse_physical", lambda **kw: True):
            result = asyncio.run(simulation._pulse_gate(
                db, db.get(Gate, 2), [db.get(Camera, 4)], reason="exit T2", side="EXIT",
                led_text="", automatic=True, command_uuid="cmd-2",
            ))
        assert calls == ["exit T2"] and result.ok
        assert db.scalar(select(GateCommandRecord)).state == "ACCEPTED"


# ------------------------------------------------------- manual-open alerts

def _recipients(db):
    alerts.save_alert_settings(db, {"recipients": [{"channel": "sms", "to": "0712345678", "name": "Manager"}]})


def test_alert_lost_between_event_commit_and_queueing_is_recovered(Session):
    """Defect: a failure/crash after the manual-open event commit but before
    alert rows were queued left alert_status=NONE forever: nobody was told."""
    now = datetime.now(timezone.utc)
    with Session() as db:
        _recipients(db)
        with patch.object(alerts, "queue_for_event", side_effect=RuntimeError("db blip")):
            event = manual_open.record_manual_open(
                db, source=MANUAL_SOURCE_GATE, gate=db.get(Gate, 2), side="EXIT", user=db.get(User, 7),
                reason="driver asked", command_ok=True, at=now - timedelta(minutes=1),
            )
        assert event.alert_status == "NONE"
        assert db.scalars(select(AlertDelivery)).all() == []
        event_id = event.id

    sent: list[int] = []
    counts = alerts.deliver_due_once(Session, sender=lambda db, d, e: sent.append(e.id) or "ok", now=now + timedelta(seconds=5))
    assert counts["sent"] == 1 and sent == [event_id]
    with Session() as db:
        assert db.get(ManualOpenEvent, event_id).alert_status == "SENT"
    # Swept once only.
    assert alerts.deliver_due_once(Session, sender=lambda *a: "ok", now=now + timedelta(seconds=10))["sent"] == 0


def test_fresh_unqueued_event_is_left_to_its_own_writer(Session):
    """The sweep waits a grace period so it does not race record_manual_open."""
    now = datetime.now(timezone.utc)
    with Session() as db:
        _recipients(db)
        db.add(ManualOpenEvent(source=MANUAL_SOURCE_GATE, gate_id=2, side="EXIT", lane_label="2# Exit",
                               command_ok=True, alert_status="NONE", created_at=now))
        db.commit()
        assert alerts.queue_unqueued_events(db, now=now) == 0


def test_opted_out_event_is_never_swept(Session):
    now = datetime.now(timezone.utc)
    with Session() as db:
        _recipients(db)
        event = manual_open.record_manual_open(
            db, source=MANUAL_SOURCE_GATE, gate=db.get(Gate, 2), side="EXIT", user=db.get(User, 7),
            reason="test", command_ok=True, at=now - timedelta(minutes=5), queue_alerts=False,
        )
        assert event.alert_status == "SKIPPED"
        assert alerts.queue_unqueued_events(db, now=now) == 0


# ------------------------------------------------------- Tanzanian plates

@pytest.mark.parametrize("ocr, expected", [
    ("7843ADF", "T843ADF"),   # TestingData/I0105082026002824.jpg: bolt over the T
    ("T843ADF", "T843ADF"),
    ("T8B2ADF", "T883ADF"),   # digit position B -> 8 (pre-existing rule)
    ("78321ADF", "78321ADF"),  # not the TZ shape: left alone
    ("7832AD", "7832AD"),
])
def test_tz_profile_restores_a_leading_t_read_as_7(ocr, expected):
    from app.services import alpr

    assert alpr._fix_tz_ocr_plate(ocr) == expected


# ------------------------------------------- PostgreSQL races (disposable DB)
#
# Run with ZIRP_TEST_POSTGRES_URL pointing at a THROWAWAY database: the tests
# drop and create every table. Never point this at a site database.

PG_URL = __import__("os").environ.get("ZIRP_TEST_POSTGRES_URL", "")


@pytest.fixture()
def PgSession():
    if not PG_URL:
        pytest.skip("ZIRP_TEST_POSTGRES_URL not set (needs a disposable PostgreSQL database)")
    engine = create_engine(PG_URL, pool_size=12, max_overflow=4)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        db.add(Site(id=1, name="Site", currency="TZS"))
        db.flush()
        db.add(Gate(id=2, name="2#", site_id=1))
        db.commit()
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def _parallel(n, fn):
    import threading

    barrier = threading.Barrier(n)
    results, errors = [], []

    def run(i):
        try:
            barrier.wait(timeout=10)
            results.append(fn(i))
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(repr(exc))

    threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    return results, errors


def test_pg_replayed_provider_payment_is_recorded_once(PgSession):
    """8 simultaneous webhook/poll deliveries of one ClickPesa transaction."""
    from app.domain.parking_engine import LanePolicy
    from app.infrastructure.payments.ledger import paid_total, record_succeeded_payment
    from app.models import ParkingSession, PaymentTransaction
    from app.services.parking_sessions import start_entry

    with PgSession() as db:
        row, _ = start_entry(db, plate="T123ABC", event_id="e-1", site_id=1, gate_id=2, policy=LanePolicy())
        session_id = row.id

    def deliver(i):
        with PgSession() as db:
            row = db.get(ParkingSession, session_id)
            out = record_succeeded_payment(
                db, row, amount=2000, method="MOBILE", provider_id="clickpesa",
                idempotency_key=f"mobile:tx-1-{i % 2}",  # two different keys, one provider txn
                provider_transaction_id="clickpesa:CP-0001",
            )
            return out["duplicate"]

    results, errors = _parallel(8, deliver)
    assert errors == []
    assert results.count(False) == 1, results
    with PgSession() as db:
        rows = db.scalars(select(PaymentTransaction).where(PaymentTransaction.session_id == session_id)).all()
        assert len(rows) == 1
        assert paid_total(db, session_id) == 2000


def test_pg_racing_gate_answers_keep_one_command_row(PgSession):
    from app.services.decisions import record_gate_command

    def answer(i):
        with PgSession() as db:
            row = record_gate_command(db, gate=db.get(Gate, 2), session=None, reason="exit", automatic=True,
                                      dry_run=False, ok=bool(i % 2), message=f"try {i}",
                                      command_uuid="cmd-race", side="EXIT")
            return row.state

    results, errors = _parallel(8, answer)
    assert errors == []
    with PgSession() as db:
        rows = db.scalars(select(GateCommandRecord)).all()
        assert len(rows) == 1
        assert rows[0].state == "ACCEPTED", "an accepted answer is never downgraded by a racing failure"
