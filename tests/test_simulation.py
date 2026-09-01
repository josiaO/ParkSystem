from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api_main import app, ensure_roles
from app.config import Settings
from app.db import Base, engine_kwargs, get_db, set_session_factory
from app.models import ParkingSession, Role, User, UserRole
from app.security import hash_password
from app.services.gates import GateCommandResult


OPENED = GateCommandResult(ok=True, simulated=False, message="OPEN", timestamp="t")


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        self.media = Path(tempfile.mkdtemp(prefix="smartpark-sim-"))
        self._media_patch = patch.object(Settings, "media_dir", new_callable=PropertyMock, return_value=self.media)
        self._media_patch.start()

        def override_get_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        set_session_factory(self.Session)
        with self.Session() as db:
            ensure_roles(db)
            admin_role = db.scalar(select(Role).where(Role.name == "Admin"))
            operator_role = db.scalar(select(Role).where(Role.name == "Operator"))
            admin = User(username="admin", full_name="Test Admin", password_hash=hash_password("correct-horse"))
            operator = User(username="operator", full_name="Test Operator", password_hash=hash_password("correct-horse"))
            db.add(admin)
            db.add(operator)
            db.flush()
            db.add(UserRole(user_id=admin.id, role_id=admin_role.id))
            db.add(UserRole(user_id=operator.id, role_id=operator_role.id))
            db.commit()
        self.client = TestClient(app)
        token = self.client.post("/auth/login", json={"username": "admin", "password": "correct-horse"}).json()["token"]
        self.headers = {"Authorization": f"Bearer {token}"}
        op_token = self.client.post("/auth/login", json={"username": "operator", "password": "correct-horse"}).json()["token"]
        self.operator_headers = {"Authorization": f"Bearer {op_token}"}

    def tearDown(self):
        self.client.close()
        set_session_factory(None)
        self._media_patch.stop()
        shutil.rmtree(self.media, ignore_errors=True)
        app.dependency_overrides.clear()
        self.engine.dispose()

    def _lane(self):
        gate = self.client.post("/gates", headers=self.headers, json={"name": "1#"}).json()
        entry = self.client.post("/cameras", headers=self.headers, json={
            "name": "1# Entry",
            "ip_address": "192.168.1.144",
            "gate_id": gate["id"],
            "lane_direction": "ENTRY",
        }).json()
        self.client.post("/cameras", headers=self.headers, json={
            "name": "1# Exit",
            "ip_address": "192.168.1.145",
            "gate_id": gate["id"],
            "lane_direction": "EXIT",
        })
        return gate, entry

    def _age_session(self, session_id: int, hours: float = 3):
        with self.Session() as db:
            row = db.get(ParkingSession, session_id)
            row.entry_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            db.commit()

    def _require_taken(self):
        res = self.client.patch("/settings/parking", headers=self.headers, json={
            "receipt_policy": "REQUIRE_TAKEN_BEFORE_OPEN",
            "receipt_required_before_open": True,
        })
        self.assertEqual(res.status_code, 200, res.text)

    def test_sqlite_uses_nullpool_not_default_queuepool(self):
        kwargs = engine_kwargs("sqlite:///tmp/smartpark.db")
        self.assertIs(kwargs["poolclass"], NullPool)
        pg = engine_kwargs("postgresql+psycopg://u:p@localhost/smartpark")
        self.assertEqual(pg["pool_size"], 5)
        self.assertEqual(pg["max_overflow"], 5)
        self.assertLessEqual(pg["pool_timeout"], 10)

    def test_developer_role_exists(self):
        roles = {row["name"] for row in self.client.get("/roles", headers=self.headers).json()}
        self.assertIn("Developer", roles)
        self.assertIn("Admin", roles)

    def test_operator_cannot_run_simulation(self):
        gate, _ = self._lane()
        res = self.client.post("/sim/entry", headers=self.operator_headers, json={
            "plate": "T123ABC", "gate_id": gate["id"], "side": "ENTRY",
        })
        self.assertEqual(res.status_code, 403)

    def test_print_and_open_is_default_casual_entry(self):
        gate, _ = self._lane()
        mock_ctrl = MagicMock()
        mock_ctrl.open = AsyncMock(return_value=OPENED)
        with patch("app.services.simulation.controller", return_value=mock_ctrl):
            res = self.client.post("/sim/entry", headers=self.headers, json={
                "plate": "T 123 ABC", "gate_id": gate["id"], "side": "ENTRY",
            })
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertTrue(body["barrier_opened"])
        self.assertEqual(body["session"]["status"], "ACTIVE")
        self.assertTrue(body["session"]["public_token"])
        self.assertIn("latency_ms", body)
        self.assertIn("PARKING ENTRY", body["receipt"])
        mock_ctrl.open.assert_awaited()

    def test_require_taken_holds_gate_until_receipt(self):
        self._require_taken()
        gate, _ = self._lane()
        mock_ctrl = MagicMock()
        mock_ctrl.open = AsyncMock(return_value=OPENED)
        with patch("app.services.simulation.controller", return_value=mock_ctrl):
            res = self.client.post("/sim/entry", headers=self.headers, json={
                "plate": "T 123 ABC", "gate_id": gate["id"], "side": "ENTRY",
            })
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertFalse(body["barrier_opened"])
        self.assertEqual(body["session"]["status"], "WAITING_RECEIPT")
        self.assertEqual(body["session"]["receipt_status"], "PRINTED")
        mock_ctrl.open.assert_not_called()

    def test_receipt_taken_opens_barrier(self):
        self._require_taken()
        gate, _ = self._lane()
        mock_ctrl = MagicMock()
        mock_ctrl.open = AsyncMock(return_value=OPENED)
        with patch("app.services.simulation.controller", return_value=mock_ctrl):
            created = self.client.post("/sim/entry", headers=self.headers, json={
                "plate": "T123ABC", "gate_id": gate["id"], "side": "ENTRY",
            }).json()
            sid = created["session"]["id"]
            taken = self.client.post(f"/sim/sessions/{sid}/receipt-taken", headers=self.headers, json={})
        self.assertEqual(taken.status_code, 200, taken.text)
        body = taken.json()
        self.assertEqual(body["session"]["receipt_status"], "TAKEN")
        self.assertEqual(body["session"]["status"], "ACTIVE")
        self.assertTrue((body.get("barrier") or {}).get("ok"))
        mock_ctrl.open.assert_awaited()

    def test_grace_period_exit_opens_without_payment(self):
        gate, _ = self._lane()
        mock_ctrl = MagicMock()
        mock_ctrl.open = AsyncMock(return_value=OPENED)
        with patch("app.services.simulation.controller", return_value=mock_ctrl):
            created = self.client.post("/sim/entry", headers=self.headers, json={
                "plate": "T123ABC", "gate_id": gate["id"], "side": "ENTRY",
            }).json()
            self.assertTrue(created["barrier_opened"])
            mock_ctrl.open.reset_mock()
            exiting = self.client.post("/sim/exit", headers=self.headers, json={
                "plate": "T123ABC", "gate_id": gate["id"], "side": "EXIT",
            })
        self.assertEqual(exiting.status_code, 200, exiting.text)
        body = exiting.json()
        self.assertTrue(body["opened"])
        self.assertFalse(body["pay_required"])
        self.assertEqual(body["fee"]["due"], 0)
        mock_ctrl.open.assert_awaited()

    def test_unpaid_exit_stays_closed_with_pay_prompt(self):
        gate, _ = self._lane()
        mock_ctrl = MagicMock()
        mock_ctrl.open = AsyncMock(return_value=OPENED)
        with patch("app.services.simulation.controller", return_value=mock_ctrl):
            created = self.client.post("/sim/entry", headers=self.headers, json={
                "plate": "T123ABC", "gate_id": gate["id"], "side": "ENTRY",
            }).json()
            sid = created["session"]["id"]
            self._age_session(sid)
            mock_ctrl.open.reset_mock()
            exiting = self.client.post("/sim/exit", headers=self.headers, json={
                "plate": "T123ABC", "gate_id": gate["id"], "side": "EXIT",
            })
        self.assertEqual(exiting.status_code, 200, exiting.text)
        body = exiting.json()
        self.assertFalse(body["opened"])
        self.assertTrue(body["pay_required"])
        self.assertIn("Pay", body["say"])
        self.assertIn("Pay", body["message"])
        mock_ctrl.open.assert_not_called()

    def test_paid_exit_opens(self):
        gate, _ = self._lane()
        mock_ctrl = MagicMock()
        mock_ctrl.open = AsyncMock(return_value=OPENED)
        with patch("app.services.simulation.controller", return_value=mock_ctrl):
            created = self.client.post("/sim/entry", headers=self.headers, json={
                "plate": "T123ABC", "gate_id": gate["id"], "side": "ENTRY",
            }).json()
            sid = created["session"]["id"]
            self._age_session(sid)
            paid = self.client.post(f"/sim/sessions/{sid}/pay", headers=self.headers, json={})
            self.assertEqual(paid.status_code, 200, paid.text)
            self.assertEqual(paid.json()["status"], "PAID")
            mock_ctrl.open.reset_mock()
            exiting = self.client.post("/sim/exit", headers=self.headers, json={
                "plate": "T123ABC", "gate_id": gate["id"], "side": "EXIT",
            })
        self.assertEqual(exiting.status_code, 200, exiting.text)
        body = exiting.json()
        self.assertTrue(body["opened"])
        self.assertFalse(body["pay_required"])
        mock_ctrl.open.assert_awaited()

    def test_public_receipt_page(self):
        gate, _ = self._lane()
        with patch("app.services.simulation.controller") as ctrl:
            ctrl.return_value.open = AsyncMock(return_value=OPENED)
            created = self.client.post("/sim/entry", headers=self.headers, json={
                "plate": "T123ABC", "gate_id": gate["id"], "side": "ENTRY",
            }).json()
        token = created["session"]["public_token"]
        page = self.client.get(f"/p/{token}")
        self.assertEqual(page.status_code, 200)
        self.assertIn("T123ABC", page.text)

    def test_parking_settings_round_trip(self):
        res = self.client.patch("/settings/parking", headers=self.headers, json={
            "pay_prompt": "Pay now {amount} {currency}",
            "receipt_required_before_open": True,
        })
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["pay_prompt"], "Pay now {amount} {currency}")
        got = self.client.get("/settings/parking", headers=self.headers)
        self.assertEqual(got.json()["pay_prompt"], "Pay now {amount} {currency}")

    def test_image_entry_receipt_pay_then_same_image_exit(self):
        gate, _ = self._lane()
        alpr = {
            "ok": True,
            "backend": "fastalpr",
            "plates": [{"plate": "T123ABC", "confidence": 0.94}],
            "best": {"plate": "T123ABC", "confidence": 0.94, "bbox": {"x1": 10, "y1": 20, "x2": 80, "y2": 50}},
            "detail": "1 plate(s)",
        }
        jpeg = b"\xff\xd8\xff\xd9"
        mock_ctrl = MagicMock()
        mock_ctrl.open = AsyncMock(return_value=OPENED)

        def upload(side):
            return self.client.post(
                "/sim/capture",
                headers=self.headers,
                data={"gate_id": str(gate["id"]), "side": side},
                files={"file": ("car.jpg", jpeg, "image/jpeg")},
            )

        with patch("app.api_main.recognize_bytes", return_value=alpr):
            with patch("app.services.simulation.controller", return_value=mock_ctrl):
                entry = upload("ENTRY")
                self.assertEqual(entry.status_code, 200, entry.text)
                body = entry.json()
                self.assertEqual(body["action"], "ENTRY")
                self.assertTrue(body["barrier_opened"])
                self.assertIn("T123ABC", body["receipt"])
                sid = body["session"]["id"]
                mock_ctrl.open.assert_awaited()
                self._age_session(sid)
                mock_ctrl.open.reset_mock()
                unpaid = upload("EXIT")
                self.assertEqual(unpaid.status_code, 200, unpaid.text)
                self.assertTrue(unpaid.json()["pay_required"])
                self.assertFalse(unpaid.json()["opened"])
                mock_ctrl.open.assert_not_called()
                paid = self.client.post(f"/sim/sessions/{sid}/pay", headers=self.headers, json={})
                self.assertEqual(paid.status_code, 200, paid.text)
                exiting = upload("EXIT")
                self.assertEqual(exiting.status_code, 200, exiting.text)
                self.assertTrue(exiting.json()["opened"])
                mock_ctrl.open.assert_awaited()

    def test_capture_without_plate_does_not_open(self):
        gate, _ = self._lane()
        with patch("app.api_main.recognize_bytes", return_value={
            "ok": True, "backend": "fastalpr", "plates": [], "best": None, "detail": "no plate in frame",
        }):
            res = self.client.post(
                "/sim/capture",
                headers=self.headers,
                data={"gate_id": str(gate["id"]), "side": "ENTRY"},
                files={"file": ("car.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
            )
        self.assertEqual(res.status_code, 409)
        self.assertIn("no plate", res.json()["detail"].lower())
        self.assertIn("does not use the cameras", res.json()["detail"].lower())

    def test_camera_plate_event_print_and_open(self):
        from app.models import Gate
        from app.services.simulation import handle_plate_event
        import asyncio
        gate, _ = self._lane()
        mock_ctrl = MagicMock()
        mock_ctrl.open = AsyncMock(return_value=OPENED)
        with self.Session() as db:
            row = db.get(Gate, gate["id"])
            with patch("app.services.simulation.controller", return_value=mock_ctrl):
                result = asyncio.run(handle_plate_event(
                    db, plate="T999XYZ", gate=row, side="ENTRY", simulated=False, source="camera",
                ))
        self.assertTrue(result["barrier_opened"])
        self.assertEqual(result["session"]["status"], "ACTIVE")
        self.assertFalse(result["session"]["simulated"])
        mock_ctrl.open.assert_awaited()


if __name__ == "__main__":
    unittest.main()
