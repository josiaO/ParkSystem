"""Phase 1 parking domain engine: transitions, idempotency, site-wide sessions."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import Base
from app.domain.parking_engine import (
    ACTIVE,
    AUTHORIZED,
    CLOSED,
    DENIED_PAYMENT_REQUIRED,
    ENTRY_AUTHORIZED,
    GATE_OPEN_REQUESTED,
    InvalidTransition,
    LanePolicy,
    PASSAGE_WAIT,
    RECEIPT_TAKEN,
    SESSION_CREATED,
    apply_transition,
    can_transition,
)
from app.models import Camera, Gate, Lane, ParkingSession, Site
from app.services import parking_sessions as engine


def _engine():
    return create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)


class TransitionUnitTests(unittest.TestCase):
    def test_valid_entry_transitions(self):
        policy = LanePolicy(receipt_required_before_open=True)
        self.assertTrue(can_transition(SESSION_CREATED, "RECEIPT_PRINTING", policy))
        self.assertTrue(can_transition(RECEIPT_TAKEN, ENTRY_AUTHORIZED, policy))
        self.assertTrue(can_transition(ENTRY_AUTHORIZED, GATE_OPEN_REQUESTED, policy))
        apply_transition(RECEIPT_TAKEN, RECEIPT_TAKEN, policy)  # idempotent

    def test_invalid_entry_skips_receipt(self):
        policy = LanePolicy(receipt_required_before_open=True)
        with self.assertRaises(InvalidTransition):
            apply_transition(SESSION_CREATED, GATE_OPEN_REQUESTED, policy)
        with self.assertRaises(InvalidTransition):
            apply_transition(SESSION_CREATED, ENTRY_AUTHORIZED, policy)
        open_policy = LanePolicy(receipt_required_before_open=False)
        self.assertTrue(can_transition(SESSION_CREATED, ENTRY_AUTHORIZED, open_policy))

    def test_valid_exit_and_denied(self):
        policy = LanePolicy()
        self.assertTrue(can_transition(ACTIVE, "EXIT_VEHICLE_DETECTED", policy))
        self.assertTrue(can_transition("AUTHORIZATION_DECISION", AUTHORIZED, policy))
        self.assertTrue(can_transition("AUTHORIZATION_DECISION", DENIED_PAYMENT_REQUIRED, policy))
        self.assertFalse(can_transition(DENIED_PAYMENT_REQUIRED, "EXIT_GATE_OPEN_REQUESTED", policy))

    def test_passage_fallback_allows_open_to_active(self):
        wait = LanePolicy(passage_sensing=PASSAGE_WAIT)
        self.assertFalse(can_transition(GATE_OPEN_REQUESTED, ACTIVE, wait))
        fallback = LanePolicy()
        self.assertTrue(can_transition(GATE_OPEN_REQUESTED, ACTIVE, fallback))


class ParkingEnginePersistenceTests(unittest.TestCase):
    def _seed(self, db):
        db.add(Site(id=1, name="Site"))
        g1 = Gate(id=1, name="North", site_id=1)
        g2 = Gate(id=2, name="South", site_id=1)
        db.add_all([g1, g2])
        db.flush()
        db.add_all([
            Lane(id=10, gate_id=1, name="North Entry", direction="ENTRY"),
            Lane(id=11, gate_id=1, name="North Exit", direction="EXIT"),
            Lane(id=20, gate_id=2, name="South Entry", direction="ENTRY"),
            Lane(id=21, gate_id=2, name="South Exit", direction="EXIT"),
            Camera(id=100, name="N-In", ip_address="10.0.0.1", site_id=1, gate_id=1),
            Camera(id=101, name="S-Out", ip_address="10.0.0.2", site_id=1, gate_id=2),
        ])
        db.commit()

    def setUp(self):
        self.engine = _engine()
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        with self.Session() as db:
            self._seed(db)

    def tearDown(self):
        self.engine.dispose()

    def test_duplicate_entry_event_one_session(self):
        policy = LanePolicy(receipt_required_before_open=True)
        with self.Session() as db:
            a, created = engine.start_entry(
                db, plate="T111AAA", event_id="evt-1", lane_id=10, camera_id=100, gate_id=1, policy=policy,
            )
            b, created2 = engine.start_entry(
                db, plate="T111AAA", event_id="evt-1", lane_id=10, camera_id=100, gate_id=1, policy=policy,
            )
            self.assertTrue(created)
            self.assertFalse(created2)
            self.assertEqual(a.id, b.id)
            self.assertEqual(db.scalar(select(ParkingSession).where(ParkingSession.plate == "T111AAA")).id, a.id)

    def test_same_vehicle_event_twice_different_id_reuses_open(self):
        with self.Session() as db:
            a, _ = engine.start_entry(db, plate="T222BBB", event_id="e-a", lane_id=10, gate_id=1)
            b, created = engine.start_entry(db, plate="T222BBB", event_id="e-b", lane_id=20, gate_id=2)
            self.assertFalse(created)
            self.assertEqual(a.id, b.id)
            self.assertEqual(a.entry_lane_id, 10)

    def test_duplicate_receipt_taken(self):
        policy = LanePolicy(receipt_required_before_open=True)
        with self.Session() as db:
            row, _ = engine.start_entry(db, plate="T333CCC", event_id="e3", lane_id=10, policy=policy)
            once = engine.mark_receipt_taken(db, row, policy=policy)
            twice = engine.mark_receipt_taken(db, once, policy=policy)
            self.assertEqual(once.id, twice.id)
            self.assertEqual(twice.lifecycle, RECEIPT_TAKEN)
            self.assertIsNotNone(twice.receipt_taken_at)

    def test_receipt_required_rejects_gate_before_taken(self):
        policy = LanePolicy(receipt_required_before_open=True)
        with self.Session() as db:
            row, _ = engine.start_entry(db, plate="T444DDD", event_id="e4", lane_id=10, policy=policy)
            with self.assertRaises(InvalidTransition):
                engine.request_entry_open(db, row, command_uuid="cmd-1", policy=policy)

    def test_gate_command_retry_same_uuid(self):
        policy = LanePolicy(receipt_required_before_open=False)
        with self.Session() as db:
            row, _ = engine.start_entry(db, plate="T555EEE", event_id="e5", lane_id=10, policy=policy)
            row = engine.advance(db, row, ENTRY_AUTHORIZED, policy=policy)
            first = engine.request_entry_open(db, row, command_uuid="open-9", policy=policy)
            second = engine.request_entry_open(db, first, command_uuid="open-9", policy=policy)
            self.assertEqual(first.id, second.id)
            self.assertEqual(second.open_command_uuid, "open-9")
            self.assertEqual(second.lifecycle, GATE_OPEN_REQUESTED)

    def test_duplicate_exit_event_does_not_close_twice(self):
        policy = LanePolicy()
        with self.Session() as db:
            row, _ = engine.start_entry(db, plate="T666FFF", event_id="in-6", lane_id=10, gate_id=1, policy=policy)
            row = engine.complete_casual_entry(db, row, policy=policy)
            self.assertEqual(row.lifecycle, ACTIVE)
            first, outcome = engine.start_exit(
                db, plate="T666FFF", event_id="out-6", lane_id=21, gate_id=2, camera_id=101, paid=True, policy=policy,
            )
            self.assertEqual(outcome, AUTHORIZED)
            first = engine.complete_authorized_exit(db, first, policy=policy, command_uuid="x-1")
            self.assertEqual(first.status, "CLOSED")
            closed_at = first.closed_at
            again, again_outcome = engine.start_exit(
                db, plate="T666FFF", event_id="out-6", lane_id=21, paid=True, policy=policy,
            )
            self.assertEqual(again.id, first.id)
            self.assertEqual(again.closed_at, closed_at)
            self.assertIn(again_outcome, {CLOSED, AUTHORIZED, "EXIT_GATE_OPEN_REQUESTED", "EXIT_VEHICLE_PASSED"})

    def test_site_wide_entry_a_exit_b(self):
        policy = LanePolicy()
        with self.Session() as db:
            row, _ = engine.start_entry(
                db, plate="T777GGG", event_id="in-n", site_id=1, lane_id=10, gate_id=1, camera_id=100, policy=policy,
            )
            row = engine.complete_casual_entry(db, row, policy=policy)
            out, outcome = engine.start_exit(
                db, plate="T777GGG", event_id="out-s", site_id=1, lane_id=21, gate_id=2, camera_id=101, paid=True, policy=policy,
            )
            self.assertEqual(outcome, AUTHORIZED)
            self.assertEqual(out.entry_lane_id, 10)
            self.assertEqual(out.exit_lane_id, 21)
            out = engine.complete_authorized_exit(db, out, policy=policy, command_uuid="boom-s")
            self.assertEqual(out.status, "CLOSED")
            self.assertEqual(out.entry_lane_id, 10)
            self.assertEqual(out.exit_lane_id, 21)

    def test_one_gate_deployment(self):
        policy = LanePolicy()
        with self.Session() as db:
            row, _ = engine.start_entry(db, plate="T888HHH", event_id="og-in", lane_id=10, gate_id=1, policy=policy)
            row = engine.complete_casual_entry(db, row, policy=policy)
            out, outcome = engine.start_exit(
                db, plate="T888HHH", event_id="og-out", lane_id=11, gate_id=1, paid=True, policy=policy,
            )
            self.assertEqual(outcome, AUTHORIZED)
            out = engine.complete_authorized_exit(db, out, policy=policy)
            self.assertEqual(out.entry_lane_id, 10)
            self.assertEqual(out.exit_lane_id, 11)

    def test_multi_gate_two_vehicles(self):
        policy = LanePolicy()
        with self.Session() as db:
            a, _ = engine.start_entry(db, plate="T010AAA", event_id="a-in", lane_id=10, gate_id=1, policy=policy)
            b, _ = engine.start_entry(db, plate="T020BBB", event_id="b-in", lane_id=20, gate_id=2, policy=policy)
            self.assertNotEqual(a.id, b.id)
            a = engine.complete_casual_entry(db, a, policy=policy)
            b = engine.complete_casual_entry(db, b, policy=policy)
            self.assertEqual(a.lifecycle, ACTIVE)
            self.assertEqual(b.lifecycle, ACTIVE)

    def test_unpaid_exit_denied(self):
        policy = LanePolicy()
        with self.Session() as db:
            row, _ = engine.start_entry(db, plate="T999III", event_id="pay-in", lane_id=10, policy=policy)
            row = engine.complete_casual_entry(db, row, policy=policy)
            row.amount_due = 1000
            row.amount_paid = 0
            db.commit()
            out, outcome = engine.start_exit(db, plate="T999III", event_id="pay-out", paid=False, policy=policy)
            self.assertEqual(outcome, DENIED_PAYMENT_REQUIRED)
            with self.assertRaises(InvalidTransition):
                engine.complete_authorized_exit(db, out, policy=policy)

    def test_two_lanes_simultaneous_different_plates(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        path = Path(tmp) / "concurrent.db"
        file_engine = create_engine(
            f"sqlite:///{path}", connect_args={"check_same_thread": False, "timeout": 30},
        )
        Base.metadata.create_all(file_engine)
        FileSession = sessionmaker(bind=file_engine, autoflush=False, expire_on_commit=False)
        with FileSession() as db:
            self._seed(db)
        policy = LanePolicy()

        def enter(plate, event_id, lane_id, gate_id):
            with FileSession() as db:
                row, created = engine.start_entry(
                    db, plate=plate, event_id=event_id, lane_id=lane_id, gate_id=gate_id, policy=policy,
                )
                return row.id, created, plate

        with ThreadPoolExecutor(max_workers=2) as pool:
            futs = [
                pool.submit(enter, "T100AAA", "sim-a", 10, 1),
                pool.submit(enter, "T200BBB", "sim-b", 20, 2),
            ]
            results = [f.result() for f in as_completed(futs)]
        ids = {r[0] for r in results}
        self.assertEqual(len(ids), 2)
        self.assertTrue(all(r[1] for r in results))
        file_engine.dispose()

    def test_two_lanes_same_plate_one_session(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        path = Path(tmp) / "race.db"
        file_engine = create_engine(
            f"sqlite:///{path}", connect_args={"check_same_thread": False, "timeout": 30},
        )
        Base.metadata.create_all(file_engine)
        FileSession = sessionmaker(bind=file_engine, autoflush=False, expire_on_commit=False)
        with FileSession() as db:
            self._seed(db)
        policy = LanePolicy()

        def enter(lane_id, gate_id, event_id):
            with FileSession() as db:
                row, created = engine.start_entry(
                    db, plate="T300CCC", event_id=event_id, lane_id=lane_id, gate_id=gate_id, policy=policy,
                )
                return row.id, created

        with ThreadPoolExecutor(max_workers=2) as pool:
            futs = [pool.submit(enter, 10, 1, "race-1"), pool.submit(enter, 20, 2, "race-2")]
            results = [f.result() for f in as_completed(futs)]
        ids = {r[0] for r in results}
        self.assertEqual(len(ids), 1)
        created_flags = [r[1] for r in results]
        self.assertEqual(sum(1 for c in created_flags if c), 1)
        file_engine.dispose()

    def test_passage_wait_does_not_close_on_open_command(self):
        policy = LanePolicy(passage_sensing=PASSAGE_WAIT)
        with self.Session() as db:
            row, _ = engine.start_entry(db, plate="T400DDD", event_id="pw-in", lane_id=10, policy=policy)
            row = engine.advance(db, row, ENTRY_AUTHORIZED, policy=policy)
            row = engine.request_entry_open(db, row, command_uuid="pw-open", policy=policy)
            self.assertEqual(row.lifecycle, GATE_OPEN_REQUESTED)
            self.assertEqual(row.status, "ACTIVE")
            row = engine.mark_vehicle_passed(db, row, policy=policy)
            self.assertEqual(row.lifecycle, ACTIVE)

    def test_engine_does_not_import_hardware(self):
        text = Path(engine.__file__).read_text()
        self.assertNotIn("from app.services.gates", text)
        self.assertNotIn("from app.services.hvx_client", text)
        self.assertNotIn("hardware.printers", text)
        self.assertNotIn("from app.services.receipts", text)


if __name__ == "__main__":
    unittest.main()
