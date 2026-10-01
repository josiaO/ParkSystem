"""Phase 6: authoritative exit orchestration and QR fallback."""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.application.exit_lane import ExitLaneController
from app.db import Base
from app.domain.parking_engine import CLOSED, EXIT_GATE_OPEN_REQUESTED, LanePolicy, PASSAGE_WAIT
from app.infrastructure.hardware.qr_scanners import HidKeyboardQrScanner
from app.infrastructure.payments.ledger import record_succeeded_payment
from app.models import AccessPlan, Camera, Gate, Lane, ParkingSession, RegisteredVehicle, Site, Tariff
from app.services.gates import GateCommandResult
from app.services.parking_sessions import complete_casual_entry, start_entry


class FakeOpener:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.calls: list[tuple] = []

    async def __call__(self, db, gate, cameras, reason, session, side, command_uuid=""):
        self.calls.append((gate.id, session.id, side, command_uuid))
        return GateCommandResult(
            ok=self.ok,
            simulated=True,
            message="OPEN" if self.ok else "relay offline",
            timestamp="t",
        )


class ExitLaneTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        with self.Session() as db:
            db.add(Site(id=1, name="Site", currency="TZS"))
            db.add_all([
                Gate(id=1, name="North", site_id=1),
                Gate(id=2, name="South", site_id=1),
            ])
            db.flush()
            db.add_all([
                Lane(id=10, gate_id=1, name="North Entry", direction="ENTRY"),
                Lane(id=20, gate_id=2, name="South Exit", direction="EXIT"),
                Camera(id=100, name="Entry", ip_address="10.0.0.1", site_id=1, gate_id=1, lane_id=10, lane_direction="ENTRY"),
                Camera(id=200, name="Exit", ip_address="10.0.0.2", site_id=1, gate_id=2, lane_id=20, lane_direction="EXIT"),
            ])
            rules = {
                "currency": "TZS",
                "day_start": "00:00:00",
                "day_end": "23:59:59",
                "free_day_seconds": 2700,
                "free_night_seconds": 2700,
                "day_block_seconds": 2700,
                "night_block_seconds": 2700,
                "day_block_fee": 1000,
                "night_block_fee": 1000,
                "daily_wrap_fee": 34000,
                "over_1000_subtract": 1000,
            }
            db.add(Tariff(site_id=1, name="Car1", car_type="Car1", currency="TZS", rules=rules, active=True))
            db.commit()

    def tearDown(self):
        self.engine.dispose()

    def _active(self, db, plate: str, entry_time: datetime) -> ParkingSession:
        row, created = start_entry(
            db,
            plate=plate,
            event_id=f"entry-{plate}",
            site_id=1,
            gate_id=1,
            lane_id=10,
            camera_id=100,
            policy=LanePolicy(),
        )
        self.assertTrue(created)
        row.entry_time = entry_time
        db.commit()
        row = complete_casual_entry(db, row, policy=LanePolicy())
        return row

    def test_free_period_exit_opens_and_closes(self):
        async def run():
            now = datetime(2026, 10, 1, 12, 20, tzinfo=timezone.utc)
            opener = FakeOpener()
            ctrl = ExitLaneController(opener=opener)
            with self.Session() as db:
                row = self._active(db, "T100AAA", now - timedelta(minutes=20))
                out = await ctrl.submit_plate(
                    db, plate=row.plate, event_id="exit-free", site_id=1,
                    gate=db.get(Gate, 2), camera=db.get(Camera, 200), lane_id=20, at=now,
                )
                self.assertTrue(out["barrier_opened"])
                self.assertFalse(out["pay_required"])
                db.refresh(row)
                self.assertEqual(row.lifecycle, CLOSED)
                self.assertEqual(row.entry_gate_id, 1)
                self.assertEqual(row.exit_gate_id, 2)
                self.assertEqual(len(opener.calls), 1)

        asyncio.run(run())

    def test_unpaid_exit_is_denied(self):
        async def run():
            now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
            opener = FakeOpener()
            ctrl = ExitLaneController(opener=opener)
            with self.Session() as db:
                row = self._active(db, "T200BBB", now - timedelta(minutes=60))
                out = await ctrl.submit_plate(
                    db, plate=row.plate, event_id="exit-unpaid", site_id=1,
                    gate=db.get(Gate, 2), camera=db.get(Camera, 200), lane_id=20, at=now,
                )
                self.assertTrue(out["pay_required"])
                self.assertFalse(out["barrier_opened"])
                self.assertGreater(out["financial"]["due"], 0)
                self.assertEqual(len(opener.calls), 0)
                db.refresh(row)
                self.assertNotEqual(row.lifecycle, CLOSED)

        asyncio.run(run())

    def test_paid_exit_re_evaluates_previous_denial(self):
        async def run():
            now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
            opener = FakeOpener()
            ctrl = ExitLaneController(opener=opener)
            with self.Session() as db:
                row = self._active(db, "T300CCC", now - timedelta(minutes=60))
                denied = await ctrl.submit_plate(
                    db, plate=row.plate, event_id="exit-denied", site_id=1,
                    gate=db.get(Gate, 2), camera=db.get(Camera, 200), lane_id=20, at=now,
                )
                self.assertTrue(denied["pay_required"])
                db.refresh(row)
                due = float(row.amount_due)
                record_succeeded_payment(
                    db, row, amount=due, method="KIOSK_CASH", provider_id="kiosk_manual",
                    idempotency_key="cash-T300CCC",
                )
                allowed = await ctrl.submit_plate(
                    db, plate=row.plate, event_id="exit-paid", site_id=1,
                    gate=db.get(Gate, 2), camera=db.get(Camera, 200), lane_id=20,
                    at=now + timedelta(minutes=1),
                )
                self.assertTrue(allowed["barrier_opened"])
                self.assertFalse(allowed["pay_required"])
                db.refresh(row)
                self.assertEqual(row.lifecycle, CLOSED)

        asyncio.run(run())

    def test_gate_failure_keeps_session_open(self):
        async def run():
            now = datetime(2026, 10, 1, 12, 10, tzinfo=timezone.utc)
            ctrl = ExitLaneController(opener=FakeOpener(ok=False))
            with self.Session() as db:
                row = self._active(db, "T400DDD", now - timedelta(minutes=10))
                out = await ctrl.submit_plate(
                    db, plate=row.plate, event_id="exit-gate-fail", site_id=1,
                    gate=db.get(Gate, 2), camera=db.get(Camera, 200), lane_id=20, at=now,
                )
                self.assertFalse(out["barrier_opened"])
                self.assertEqual(out["reason"], "gate_unavailable")
                db.refresh(row)
                self.assertNotEqual(row.lifecycle, CLOSED)

        asyncio.run(run())

    def test_wait_for_passage_does_not_close_on_open(self):
        async def run():
            now = datetime(2026, 10, 1, 12, 10, tzinfo=timezone.utc)
            ctrl = ExitLaneController(opener=FakeOpener())
            policy = LanePolicy(passage_sensing=PASSAGE_WAIT)
            with self.Session() as db:
                row = self._active(db, "T500EEE", now - timedelta(minutes=10))
                out = await ctrl.submit_plate(
                    db, plate=row.plate, event_id="exit-pass", site_id=1,
                    gate=db.get(Gate, 2), camera=db.get(Camera, 200), lane_id=20,
                    at=now, policy=policy,
                )
                self.assertTrue(out["barrier_opened"])
                db.refresh(row)
                self.assertEqual(row.lifecycle, EXIT_GATE_OPEN_REQUESTED)
                done = await ctrl.vehicle_passed(db, row, policy=policy)
                self.assertEqual(done["session"]["lifecycle"], CLOSED)

        asyncio.run(run())

    def test_same_qr_is_exit_fallback(self):
        async def run():
            now = datetime(2026, 10, 1, 12, 10, tzinfo=timezone.utc)
            ctrl = ExitLaneController(opener=FakeOpener())
            with self.Session() as db:
                row = self._active(db, "T600FFF", now - timedelta(minutes=10))
                scan = f"https://pay.example/s/{row.public_token}"
                parsed = HidKeyboardQrScanner.parse(scan)
                self.assertIsNotNone(parsed)
                out = await ctrl.submit_qr(
                    db, raw_scan=scan, event_id="qr-exit", site_id=1,
                    gate=db.get(Gate, 2), camera=db.get(Camera, 200), lane_id=20, at=now,
                )
                self.assertTrue(out["barrier_opened"])
                self.assertFalse(out["pay_required"])

        asyncio.run(run())

    def test_subscriber_exits_without_fee(self):
        async def run():
            now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
            ctrl = ExitLaneController(opener=FakeOpener())
            with self.Session() as db:
                plan = AccessPlan(site_id=1, name="Staff", kind="STAFF", auto_open=True)
                db.add(plan)
                db.flush()
                db.add(RegisteredVehicle(site_id=1, plate="T700VIP", plan_id=plan.id, enabled=True))
                db.commit()
                row = self._active(db, "T700VIP", now - timedelta(hours=4))
                row.parker_kind = "STAFF"
                db.commit()
                out = await ctrl.submit_plate(
                    db, plate=row.plate, event_id="vip-exit", site_id=1,
                    gate=db.get(Gate, 2), camera=db.get(Camera, 200), lane_id=20, at=now,
                )
                self.assertTrue(out["barrier_opened"])
                self.assertEqual(out["financial"]["due"], 0)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
