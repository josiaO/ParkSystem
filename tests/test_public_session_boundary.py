"""Public Driver projections and evidence stay bound to one visit."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import Base
from app.models import Gate, ParkingSession, VehicleCapture
from app.services.fee_engine import load_active_rules
from app.services.kiosk_lookup import capture_for_session
from app.services.public_pay import public_session_payload
from app.services.simulation import quote_session


class PublicSessionBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_driver_projection_contains_no_internal_session_identifiers(self):
        with self.Session() as db:
            db.add(Gate(id=1, site_id=1, name="Gate A"))
            row = ParkingSession(
                site_id=1,
                plate="T123ABC",
                gate_id=1,
                entry_gate_id=1,
                camera_id=7,
                status="CLOSED",
                amount_due=2000,
                amount_paid=0,
                currency="TZS",
                public_token="opaque-token",
                entry_event_id="entry-1",
                visit_id="visit-1",
            )
            db.add(row)
            db.commit()
            db.refresh(row)

            body = public_session_payload(db, row)

        for forbidden in ("session", "session_id", "gate_id", "camera_id", "visit_id", "vehicle_id", "access_plan_id"):
            self.assertNotIn(forbidden, body)
        self.assertEqual(body["entry_gate"], "Gate A")
        self.assertEqual(body["payment_status"], "UNPAID")
        self.assertFalse(body["can_exit"])

    def test_evidence_resolution_keeps_event_visit_identity(self):
        with self.Session() as db:
            first = ParkingSession(
                site_id=1, plate="T123ABC", camera_id=7, status="CLOSED",
                public_token="first-token", entry_event_id="event-1", visit_id="visit-1",
            )
            second = ParkingSession(
                site_id=1, plate="T123ABC", camera_id=7, status="CLOSED",
                public_token="second-token", entry_event_id="event-2", visit_id="visit-2",
            )
            db.add_all([first, second])
            db.flush()
            first_capture = VehicleCapture(
                camera_id=7, plate="T123ABC", event_id="event-1", visit_id="visit-1",
                snapshot_path="snapshots/first.jpg", crop_path="crops/first.jpg",
            )
            second_capture = VehicleCapture(
                camera_id=7, plate="T123ABC", event_id="event-2", visit_id="visit-2",
                snapshot_path="snapshots/second.jpg", crop_path="crops/second.jpg",
            )
            db.add_all([first_capture, second_capture])
            db.commit()

            resolved = capture_for_session(db, first)

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.event_id, "event-1")
        self.assertEqual(resolved.snapshot_path, "snapshots/first.jpg")

    def test_evidence_resolution_can_use_persisted_entry_image_identity(self):
        with self.Session() as db:
            row = ParkingSession(
                site_id=1, plate="T123ABC", camera_id=7, status="ACTIVE",
                public_token="image-ref-token", entry_event_id="legacy-event",
                entry_image_ref="/media/snapshots/entry.jpg",
            )
            db.add(row)
            db.flush()
            capture = VehicleCapture(
                camera_id=7, plate="T123ABC", event_id="new-event",
                snapshot_path="snapshots/entry.jpg", crop_path="crops/entry.jpg",
            )
            db.add(capture)
            db.commit()

            resolved = capture_for_session(db, row)

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.snapshot_path, "snapshots/entry.jpg")

    def test_mobile_payment_projection_includes_visit_bound_vehicle_photos(self):
        with self.Session() as db:
            row = ParkingSession(
                site_id=1,
                plate="T123ABC",
                camera_id=7,
                status="CLOSED",
                public_token="photo-token",
                entry_event_id="photo-event",
                visit_id="photo-visit",
                amount_due=2000,
                amount_paid=0,
                currency="TZS",
            )
            db.add(row)
            db.flush()
            db.add(VehicleCapture(
                camera_id=7,
                plate="T123ABC",
                event_id="photo-event",
                visit_id="photo-visit",
                snapshot_path="snapshots/photo.jpg",
                crop_path="crops/photo.jpg",
            ))
            db.commit()

            body = public_session_payload(db, row)

        self.assertEqual(body["snapshot_url"], "/p/photo-token/snapshot.jpg")
        self.assertEqual(body["crop_url"], "/p/photo-token/crop.jpg")
        self.assertIn("photo", body["image_note"].lower())

    def test_tariff_lookup_handles_legacy_missing_site_id(self):
        with self.Session() as db:
            rules = load_active_rules(db, site_id=None)

        self.assertEqual(rules["currency"], "TZS")

    def test_quote_handles_partial_legacy_tariff_snapshot(self):
        with self.Session() as db:
            row = ParkingSession(
                site_id=1,
                plate="T123ABC",
                status="ACTIVE",
                tariff_rules={"day_block_seconds": None, "day_block_fee": None},
            )
            db.add(row)
            db.flush()
            quote = quote_session(db, row, persist=False)

        self.assertIn("due", quote)


if __name__ == "__main__":
    unittest.main()

