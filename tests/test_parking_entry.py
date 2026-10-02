"""Phase 4: full simulated entry orchestration, plus SQLite datetime safety."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import sys
from unittest.mock import PropertyMock, patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.application.entry_lane import EntryLaneController
from app.config import Settings
from app.db import Base
from app.domain.parking_engine import ACTIVE, ENTRY_CANCELLED, LanePolicy
from app.domain.recognition import CONF_HIGH, CONF_LOW, NormalizedRecognitionEvent
from app.infrastructure.hardware.receipt_printers import SimulatedKioskPrinter
from app.models import AccessPlan, Camera, Gate, Lane, ParkingSession, RegisteredVehicle, Site
from app.services.access import lookup_entitlement
from app.services.gates import GateCommandResult
from app.services.parking_sessions import start_entry_from_recognition


def _engine():
    return create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)


def _event(plate: str, event_id: str, *, camera_id=100, lane_id=10, confidence=0.95, cls=CONF_HIGH, accepted=True):
    return NormalizedRecognitionEvent(
        event_id=event_id,
        site_id=1,
        camera_id=camera_id,
        lane_id=lane_id,
        occurred_at="2026-09-30T12:00:00+00:00",
        provider="FASTALPR",
        plate_raw=plate,
        plate_normalized=plate,
        confidence=confidence,
        bbox=None,
        vehicle_detected=True,
        image_ref="",
        plate_crop_ref="",
        confidence_class=cls,
        accepted=accepted,
    )


class FakeOpener:
    def __init__(self, fail_times: int = 0) -> None:
        self.calls: list[tuple] = []
        self.fail_times = fail_times

    async def __call__(self, db, gate, cameras, reason, session, side, command_uuid=""):
        self.calls.append((gate.id if gate else None, session.id if session else None, command_uuid))
        if self.fail_times > 0:
            self.fail_times -= 1
            return GateCommandResult(ok=False, simulated=True, message="controller down", timestamp="t")
        return GateCommandResult(ok=True, simulated=True, message="OPEN", timestamp="t")


class AccessDatetimeTests(unittest.TestCase):
    def setUp(self):
        self.engine = _engine()
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)

    def tearDown(self):
        self.engine.dispose()

    def test_naive_valid_from_compares_against_aware_now(self):
        with self.Session() as db:
            db.add(Site(id=1, name="Site"))
            plan = AccessPlan(name="VIP", kind="VIP", auto_open=True, print_receipt=False, site_id=1)
            db.add(plan)
            db.flush()
            db.add(RegisteredVehicle(
                plate="T111AAA",
                owner_name="Tenant",
                plan_id=plan.id,
                enabled=True,
                site_id=1,
                valid_from=datetime(2020, 1, 1, 0, 0, 0),
                valid_until=datetime(2030, 1, 1, 0, 0, 0),
            ))
            db.commit()
            hit = lookup_entitlement(db, "T111AAB")
            self.assertEqual(hit.kind, "VIP")
            self.assertTrue(hit.registered)


class EntryOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = _engine()
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        with self.Session() as db:
            db.add(Site(id=1, name="Site"))
            g1 = Gate(id=1, name="North", site_id=1)
            g2 = Gate(id=2, name="South", site_id=1)
            db.add_all([g1, g2])
            db.flush()
            db.add_all([
                Lane(id=10, gate_id=1, name="North Entry", direction="ENTRY"),
                Lane(id=20, gate_id=2, name="South Entry", direction="ENTRY"),
                Camera(id=100, name="N-In", ip_address="10.0.0.1", site_id=1, gate_id=1, lane_direction="ENTRY"),
                Camera(id=200, name="S-In", ip_address="10.0.0.2", site_id=1, gate_id=2, lane_direction="ENTRY"),
                AccessPlan(id=5, name="VIP", kind="VIP", auto_open=True, print_receipt=False, site_id=1),
            ])
            db.commit()
        self.media = Path(tempfile.mkdtemp(prefix="smartpark-entry-"))
        self._media = patch.object(Settings, "media_dir", new_callable=PropertyMock, return_value=self.media)
        self._media.start()
        self.policy = LanePolicy(receipt_required_before_open=True)

    def tearDown(self):
        self._media.stop()
        shutil.rmtree(self.media, ignore_errors=True)
        self.engine.dispose()

    def _ctrl(self, opener=None, printer=None):
        return EntryLaneController(printer=printer or SimulatedKioskPrinter(), opener=opener or FakeOpener())

    def test_normal_casual_entry(self):
        async def _run():
            opener = FakeOpener()
            printer = SimulatedKioskPrinter()
            ctrl = self._ctrl(opener, printer)
            with self.Session() as db:
                gate = db.get(Gate, 1)
                first = await ctrl.submit(db, _event("T100AAA", "e-1"), gate=gate, camera=db.get(Camera, 100), policy=self.policy)
                self.assertTrue(first["ok"])
                self.assertFalse(first["barrier_opened"])
                self.assertEqual(first["reason"], "waiting_receipt")
                row = db.get(ParkingSession, first["session"]["id"])
                printer.simulate_taken()
                done = await ctrl.confirm_receipt_taken(db, row, policy=self.policy, gate=gate, camera=db.get(Camera, 100))
                self.assertTrue(done["barrier_opened"])
                db.refresh(row)
                self.assertEqual(row.lifecycle, ACTIVE)
                self.assertEqual(row.status, "ACTIVE")
                self.assertEqual(len(opener.calls), 1)
                self.assertEqual(db.scalar(select(func.count()).select_from(ParkingSession)), 1)

        asyncio.run(_run())

    def test_duplicate_alpr_frames_one_session(self):
        async def _run():
            opener = FakeOpener()
            ctrl = self._ctrl(opener)
            with self.Session() as db:
                gate = db.get(Gate, 1)
                cam = db.get(Camera, 100)
                a = await ctrl.submit(db, _event("T200BBB", "dup-1"), gate=gate, camera=cam, policy=self.policy)
                b = await ctrl.submit(db, _event("T200BBB", "dup-1"), gate=gate, camera=cam, policy=self.policy)
                c = await ctrl.submit(db, _event("T200BBB", "dup-2"), gate=gate, camera=cam, policy=self.policy)
                self.assertEqual(a["session"]["id"], b["session"]["id"])
                self.assertEqual(a["session"]["id"], c["session"]["id"])
                self.assertTrue(b["duplicate"] or not b["created_session"])
                self.assertEqual(db.scalar(select(func.count()).select_from(ParkingSession)), 1)
                self.assertEqual(len(opener.calls), 0)

        asyncio.run(_run())

    def test_near_duplicate_ocr_on_same_lane_one_session(self):
        async def _run():
            ctrl = self._ctrl()
            with self.Session() as db:
                gate = db.get(Gate, 1)
                cam = db.get(Camera, 100)
                a = await ctrl.submit(db, _event("T285DQP", "near-1"), gate=gate, camera=cam, policy=self.policy)
                b = await ctrl.submit(db, _event("T285DOP", "near-2"), gate=gate, camera=cam, policy=self.policy)
                self.assertEqual(a["session"]["id"], b["session"]["id"])
                self.assertTrue(b["duplicate"])
                self.assertEqual(db.scalar(select(func.count()).select_from(ParkingSession)), 1)

        asyncio.run(_run())

    def test_receipt_printer_failure_does_not_open(self):
        async def _run():
            opener = FakeOpener()
            printer = SimulatedKioskPrinter()
            printer.paper_ok = False
            ctrl = self._ctrl(opener, printer)
            with self.Session() as db:
                out = await ctrl.submit(
                    db, _event("T300CCC", "p-fail"), gate=db.get(Gate, 1), camera=db.get(Camera, 100), policy=self.policy,
                )
                self.assertTrue(out["assistance_required"])
                self.assertFalse(out["barrier_opened"])
                self.assertEqual(len(opener.calls), 0)
                row = db.get(ParkingSession, out["session"]["id"])
                self.assertNotEqual(row.lifecycle, ACTIVE)

        asyncio.run(_run())

    def test_receipt_not_taken_keeps_gate_closed(self):
        async def _run():
            opener = FakeOpener()
            ctrl = self._ctrl(opener)
            with self.Session() as db:
                out = await ctrl.submit(
                    db, _event("T400DDD", "no-take"), gate=db.get(Gate, 1), camera=db.get(Camera, 100), policy=self.policy,
                )
                self.assertFalse(out["barrier_opened"])
                self.assertEqual(len(opener.calls), 0)
                row = db.get(ParkingSession, out["session"]["id"])
                self.assertEqual(row.status, "WAITING_RECEIPT")

        asyncio.run(_run())

    def test_receipt_taken_twice_one_gate_command(self):
        async def _run():
            opener = FakeOpener()
            printer = SimulatedKioskPrinter()
            ctrl = self._ctrl(opener, printer)
            with self.Session() as db:
                gate = db.get(Gate, 1)
                cam = db.get(Camera, 100)
                first = await ctrl.submit(db, _event("T500EEE", "twice"), gate=gate, camera=cam, policy=self.policy)
                row = db.get(ParkingSession, first["session"]["id"])
                printer.simulate_taken()
                await ctrl.confirm_receipt_taken(db, row, policy=self.policy, gate=gate, camera=cam)
                await ctrl.confirm_receipt_taken(db, row, policy=self.policy, gate=gate, camera=cam)
                self.assertEqual(len(opener.calls), 1)

        asyncio.run(_run())

    def test_gate_command_retry(self):
        async def _run():
            opener = FakeOpener(fail_times=1)
            printer = SimulatedKioskPrinter()
            ctrl = self._ctrl(opener, printer)
            with self.Session() as db:
                gate = db.get(Gate, 1)
                cam = db.get(Camera, 100)
                first = await ctrl.submit(db, _event("T600FFF", "retry"), gate=gate, camera=cam, policy=self.policy)
                row = db.get(ParkingSession, first["session"]["id"])
                printer.simulate_taken()
                failed = await ctrl.confirm_receipt_taken(db, row, policy=self.policy, gate=gate, camera=cam)
                self.assertEqual(failed["reason"], "gate_unavailable")
                self.assertFalse(failed["barrier_opened"])
                db.refresh(row)
                uuid = failed.get("open_command_uuid") or ""
                again = await ctrl.retry_gate(db, row, policy=self.policy, gate=gate, camera=cam, command_uuid=uuid)
                self.assertTrue(again["barrier_opened"])
                third = await ctrl.retry_gate(db, row, policy=self.policy, gate=gate, camera=cam, command_uuid=uuid)
                self.assertTrue(third.get("duplicate") or third["reason"] == "already_open")
                self.assertEqual(len(opener.calls), 2)

        asyncio.run(_run())

    def test_vehicle_leaves_before_completion(self):
        async def _run():
            opener = FakeOpener()
            ctrl = self._ctrl(opener)
            with self.Session() as db:
                gate = db.get(Gate, 1)
                cam = db.get(Camera, 100)
                first = await ctrl.submit(db, _event("T700GGG", "left"), gate=gate, camera=cam, policy=self.policy)
                row = db.get(ParkingSession, first["session"]["id"])
                left = await ctrl.vehicle_left(db, row, policy=self.policy)
                self.assertEqual(left["lifecycle"], ENTRY_CANCELLED)
                db.refresh(row)
                self.assertEqual(row.status, "CLOSED")
                self.assertEqual(len(opener.calls), 0)
                again, created = start_entry_from_recognition(
                    db, _event("T700GGG", "left-2"), gate_id=1, policy=self.policy,
                )
                self.assertTrue(created)
                self.assertNotEqual(again.id, row.id)

        asyncio.run(_run())

    def test_subscriber_entry_skips_receipt(self):
        async def _run():
            opener = FakeOpener()
            ctrl = self._ctrl(opener)
            with self.Session() as db:
                db.add(RegisteredVehicle(
                    plate="T800VIP", owner_name="VIP", plan_id=5, enabled=True, site_id=1,
                    valid_from=datetime(2020, 1, 1),
                ))
                db.commit()
                gate = db.get(Gate, 1)
                out = await ctrl.submit(
                    db, _event("T800VIP", "vip-1"), gate=gate, camera=db.get(Camera, 100), policy=self.policy,
                )
                self.assertTrue(out["barrier_opened"])
                self.assertEqual(out["session"]["parker_kind"], "VIP")
                self.assertEqual(len(opener.calls), 1)
                row = db.get(ParkingSession, out["session"]["id"])
                self.assertEqual(row.lifecycle, ACTIVE)

        asyncio.run(_run())

    def test_entry_gate_a_and_gate_b(self):
        async def _run():
            with self.Session() as db:
                a = await self._ctrl().submit(
                    db, _event("T010AAA", "ga", camera_id=100, lane_id=10),
                    gate=db.get(Gate, 1), camera=db.get(Camera, 100), policy=self.policy,
                )
                b = await self._ctrl().submit(
                    db, _event("T020BBB", "gb", camera_id=200, lane_id=20),
                    gate=db.get(Gate, 2), camera=db.get(Camera, 200), policy=self.policy,
                )
                self.assertNotEqual(a["session"]["id"], b["session"]["id"])
                self.assertEqual(a["session"]["gate_id"], 1)
                self.assertEqual(b["session"]["gate_id"], 2)
                self.assertFalse(a["barrier_opened"])
                self.assertFalse(b["barrier_opened"])

        asyncio.run(_run())

    def test_low_confidence_does_not_create_session(self):
        async def _run():
            with self.Session() as db:
                out = await self._ctrl().submit(
                    db, _event("T900LOW", "low", cls=CONF_LOW, confidence=0.2, accepted=False),
                    gate=db.get(Gate, 1), policy=self.policy,
                )
                self.assertFalse(out["ok"])
                self.assertEqual(out["reason"], "recognition_timeout")
                self.assertEqual(db.scalar(select(func.count()).select_from(ParkingSession)), 0)

        asyncio.run(_run())

    def test_no_presence_does_not_create_session(self):
        async def _run():
            with self.Session() as db:
                out = await self._ctrl().submit(
                    db, _event("T901OCC", "occ"), gate=db.get(Gate, 1), policy=self.policy, occupied=False,
                )
                self.assertEqual(out["reason"], "no_presence")
                self.assertEqual(db.scalar(select(func.count()).select_from(ParkingSession)), 0)

        asyncio.run(_run())


class SimultaneousEntryTests(unittest.TestCase):
    def test_simultaneous_entries_at_two_gates(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        path = Path(tmp) / "entry.db"
        file_engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False, "timeout": 30})
        Base.metadata.create_all(file_engine)
        FileSession = sessionmaker(bind=file_engine, autoflush=False, expire_on_commit=False)
        with FileSession() as db:
            db.add(Site(id=1, name="Site"))
            db.add_all([Gate(id=1, name="North", site_id=1), Gate(id=2, name="South", site_id=1)])
            db.flush()
            db.add_all([
                Lane(id=10, gate_id=1, name="N", direction="ENTRY"),
                Lane(id=20, gate_id=2, name="S", direction="ENTRY"),
                Camera(id=100, name="N-In", ip_address="10.0.0.1", site_id=1, gate_id=1),
                Camera(id=200, name="S-In", ip_address="10.0.0.2", site_id=1, gate_id=2),
            ])
            db.commit()
        policy = LanePolicy(receipt_required_before_open=True)
        media = Path(tmp) / "media"
        media.mkdir()

        def one(plate, event_id, gate_id, camera_id, lane_id):
            with FileSession() as db:
                with patch.object(Settings, "media_dir", new_callable=PropertyMock, return_value=media):
                    ctrl = EntryLaneController(printer=SimulatedKioskPrinter(), opener=FakeOpener())
                    return asyncio.run(ctrl.submit(
                        db, _event(plate, event_id, camera_id=camera_id, lane_id=lane_id),
                        gate=db.get(Gate, gate_id), camera=db.get(Camera, camera_id), policy=policy,
                    ))

        with ThreadPoolExecutor(max_workers=2) as pool:
            futs = [
                pool.submit(one, "T010AAA", "sim-a", 1, 100, 10),
                pool.submit(one, "T020BBB", "sim-b", 2, 200, 20),
            ]
            results = [f.result() for f in as_completed(futs)]
        ids = {row["session"]["id"] for row in results}
        self.assertEqual(len(ids), 2)
        with FileSession() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(ParkingSession)), 2)
        file_engine.dispose()
