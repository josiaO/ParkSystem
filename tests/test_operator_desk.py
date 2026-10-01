"""QR desk lookup, tariff form, reports, backup, and bulk vehicle registration."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api_main import app, ensure_roles
from app.db import Base, get_db
from app.models import ParkingSession, Role, User, UserRole
from app.security import hash_password
from app.services.kiosk_lookup import extract_receipt_token
from app.services.preview import release_live


class OperatorDeskTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

        def override_get_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        with self.Session() as db:
            ensure_roles(db)
            from app.services.modules import apply_profile
            apply_profile(db, "PARKING_PRO")
            admin_role = db.scalar(select(Role).where(Role.name == "Admin"))
            user = User(username="admin", full_name="Test Admin", password_hash=hash_password("correct-horse"))
            db.add(user)
            db.flush()
            db.add(UserRole(user_id=user.id, role_id=admin_role.id))
            db.commit()
        self.client = TestClient(app)
        token = self.client.post("/auth/login", json={"username": "admin", "password": "correct-horse"}).json()["token"]
        self.headers = {"Authorization": f"Bearer {token}"}

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def _open(self, plate="T100ABC", hours_ago=0):
        created = self.client.post("/sessions", headers=self.headers, json={"plate": plate}).json()
        with self.Session() as db:
            row = db.get(ParkingSession, created["id"])
            row.public_token = f"tok-{plate}"
            if hours_ago:
                row.entry_time = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
            db.commit()
        return created["id"]

    def test_qr_text_extracts_token(self):
        self.assertEqual(extract_receipt_token("http://192.168.1.10:8760/p/abc123"), "abc123")
        self.assertEqual(extract_receipt_token("/p/abc123/qr.png"), "abc123")
        self.assertEqual(extract_receipt_token("abc123"), "abc123")

    def test_lookup_by_scanned_url_shows_time_and_blocks_free_payment(self):
        sid = self._open()
        found = self.client.get("/sessions/lookup", headers=self.headers, params={"q": "http://site/p/tok-T100ABC"})
        self.assertEqual(found.status_code, 200, found.text)
        body = found.json()
        self.assertEqual(body["session_id"], sid)
        self.assertIn("duration_label", body)
        self.assertFalse(body["payable"])
        self.assertIn("does not have a fee", body["pay_blocked_reason"])
        refused = self.client.post(f"/sessions/{sid}/pay", headers=self.headers, json={"method": "KIOSK_CASH"})
        self.assertEqual(refused.status_code, 409, refused.text)

    def test_payable_visit_can_be_settled_once(self):
        sid = self._open(plate="T200DEF", hours_ago=3)
        found = self.client.get("/sessions/lookup", headers=self.headers, params={"q": "T200DEF"})
        self.assertTrue(found.json()["payable"], found.text)
        paid = self.client.post("/p/tok-T200DEF/kiosk-pay", headers=self.headers, json={"method": "KIOSK_CASH"})
        self.assertEqual(paid.status_code, 200, paid.text)
        self.assertTrue(paid.json()["paid"])
        self.assertFalse(paid.json()["payable"])
        page = self.client.get("/p/tok-T200DEF")
        self.assertIn("Time inside", page.text)
        self.assertIn("disabled", page.text)

    def test_tariff_form_round_trip(self):
        saved = self.client.patch("/fees/tariff", headers=self.headers, json={
            "day_block_fee": 1500,
            "free_day_minutes": 20,
            "day_start": "06:00",
        })
        self.assertEqual(saved.status_code, 200, saved.text)
        editor = saved.json()["editor"]
        self.assertEqual(editor["day_block_fee"], 1500)
        self.assertEqual(editor["free_day_minutes"], 20)
        self.assertEqual(editor["day_start"], "06:00")
        again = self.client.get("/fees/tariff", headers=self.headers)
        self.assertEqual(again.json()["editor"]["day_block_fee"], 1500)

    def test_bulk_vehicles_with_season_dates(self):
        result = self.client.post("/vehicles/bulk", headers=self.headers, json={"vehicles": [
            {"plate": "T300AAA", "owner_name": "Amina", "valid_from": "2026-09-01T00:00:00Z", "valid_until": "2026-10-01T00:00:00Z"},
            {"plate": "T300BBB", "owner_name": "Baraka", "valid_from": "2026-09-26T00:00:00Z"},
        ]})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(len(result.json()["created"]), 2)
        listed = self.client.get("/vehicles", headers=self.headers).json()
        plates = {row["plate"]: row for row in listed}
        self.assertTrue(plates["T300AAA"]["valid_from"].startswith("2026-09-01"))
        removed = self.client.post("/vehicles/bulk-delete", headers=self.headers, json={
            "ids": [plates["T300AAA"]["id"], plates["T300BBB"]["id"]],
        })
        self.assertEqual(removed.json()["deleted"], [plates["T300AAA"]["id"], plates["T300BBB"]["id"]])
        self.assertEqual(self.client.get("/vehicles", headers=self.headers).json(), [])

    def test_report_and_offline_backup(self):
        self._open(plate="T400CCC", hours_ago=3)
        self.client.post("/p/tok-T400CCC/kiosk-pay", headers=self.headers, json={"method": "KIOSK_CASH"})
        today = datetime.now(timezone.utc).date().isoformat()
        report = self.client.get("/reports/summary", headers=self.headers, params={"start": today, "end": today})
        self.assertEqual(report.status_code, 200, report.text)
        body = report.json()
        self.assertGreaterEqual(body["collected"], 1)
        self.assertTrue(body["sections"])
        kinds = {item["id"] for item in body["reports"]}
        self.assertTrue({"overview", "payments", "outstanding", "daily", "operators", "accuracy", "exceptions", "seasons"} <= kinds)
        exported = self.client.get("/reports/export.csv", headers=self.headers, params={"kind": "daily", "start": today, "end": today})
        self.assertEqual(exported.status_code, 200, exported.text)
        self.assertIn("Day", exported.text)
        csv = self.client.get("/reports/payments.csv", headers=self.headers, params={"start": today, "end": today})
        self.assertIn("Session", csv.text)
        self.assertIn("Amount", csv.text)

    def test_outstanding_and_plate_accuracy_reports(self):
        sid = self._open(plate="T500EEE", hours_ago=2)
        with self.Session() as db:
            from app.models import ParkingSession, VehicleCapture
            row = db.get(ParkingSession, sid)
            row.amount_due = 2500
            row.amount_paid = 0
            row.status = "OPEN"
            db.add(VehicleCapture(
                plate="T500EEE",
                plate_raw="T500EEE",
                confidence=0.6,
                bbox={
                    "native_plate": "T500EEE",
                    "local_plate": "T50OEEE",
                    "needs_review": True,
                    "fusion": {"native_plate": "T500EEE", "local_plate": "T50OEEE", "disagreed": True},
                },
            ))
            db.commit()
        today = datetime.now(timezone.utc).date().isoformat()
        report = self.client.get("/reports/summary", headers=self.headers, params={"start": today, "end": today})
        self.assertEqual(report.status_code, 200, report.text)
        body = report.json()
        owing = next(item for item in body["reports"] if item["id"] == "outstanding")
        self.assertTrue(any(row["plate"] == "T500EEE" and row["remaining"] == 2500 for row in owing["rows"]))
        self.assertGreaterEqual(body["accuracy"]["disagreed"], 1)
        self.assertGreaterEqual(body["accuracy"]["held"], 1)
        status = self.client.get("/backup", headers=self.headers)
        self.assertTrue(status.json()["offline_due"])
        downloaded = self.client.get("/backup/download", headers=self.headers)
        self.assertEqual(downloaded.status_code, 200, downloaded.text)
        self.assertIn("CREATE TABLE", downloaded.text)
        after = self.client.get("/backup", headers=self.headers).json()
        self.assertFalse(after["offline_due"])
        self.assertIsNotNone(after["last_offline_at"])

    def test_hiding_a_camera_does_not_release_detection(self):
        from unittest.mock import patch
        with patch("app.services.preview.gateway") as gateway:
            gateway.session.return_value = None
            release_live(7)
            gateway.release_detect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
