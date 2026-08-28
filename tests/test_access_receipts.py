from __future__ import annotations

import unittest
from pathlib import Path
import sys
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api_main import app, ensure_roles
from app.db import Base, get_db
from app.models import Role, User, UserRole
from app.security import hash_password
from app.services.gates import GateCommandResult

OPENED = GateCommandResult(ok=True, simulated=False, message="OPEN", timestamp="t")


class AccessReceiptTests(unittest.TestCase):
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

    def _lane(self):
        gate = self.client.post("/gates", headers=self.headers, json={"name": "1#"}).json()
        self.client.post("/cameras", headers=self.headers, json={
            "name": "1# Entry", "ip_address": "192.168.1.144", "gate_id": gate["id"], "lane_direction": "ENTRY",
        })
        self.client.post("/cameras", headers=self.headers, json={
            "name": "1# Exit", "ip_address": "192.168.1.145", "gate_id": gate["id"], "lane_direction": "EXIT",
        })
        return gate

    def test_register_plate_and_auto_open(self):
        gate = self._lane()
        plans = self.client.get("/access-plans", headers=self.headers)
        self.assertEqual(plans.status_code, 200, plans.text)
        vip = next(row for row in plans.json() if row["kind"] == "VIP")
        created = self.client.post("/vehicles", headers=self.headers, json={
            "plate": "T 453 ETH", "owner_name": "Tenant", "plan_id": vip["id"],
        })
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()["plate"], "T453ETH")
        mock_ctrl = MagicMock()
        mock_ctrl.open = AsyncMock(return_value=OPENED)
        with patch("app.services.simulation.controller", return_value=mock_ctrl):
            res = self.client.post("/sim/entry", headers=self.headers, json={
                "plate": "T453ETH", "gate_id": gate["id"], "side": "ENTRY",
            })
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertTrue(body["barrier_opened"])
        self.assertEqual(body["session"]["status"], "ACTIVE")
        self.assertEqual(body["session"]["parker_kind"], "VIP")
        mock_ctrl.open.assert_awaited()

    def test_registered_exit_opens_without_payment(self):
        gate = self._lane()
        plans = self.client.get("/access-plans", headers=self.headers).json()
        vip = next(row for row in plans if row["kind"] == "VIP")
        self.client.post("/vehicles", headers=self.headers, json={"plate": "T453ETH", "plan_id": vip["id"]})
        mock_ctrl = MagicMock()
        mock_ctrl.open = AsyncMock(return_value=OPENED)
        with patch("app.services.simulation.controller", return_value=mock_ctrl):
            self.client.post("/sim/entry", headers=self.headers, json={
                "plate": "T453ETH", "gate_id": gate["id"], "side": "ENTRY",
            })
            mock_ctrl.open.reset_mock()
            exiting = self.client.post("/sim/exit", headers=self.headers, json={
                "plate": "T453ETH", "gate_id": gate["id"], "side": "EXIT",
            })
        self.assertEqual(exiting.status_code, 200, exiting.text)
        self.assertTrue(exiting.json()["opened"])
        self.assertFalse(exiting.json().get("pay_required"))
        mock_ctrl.open.assert_awaited()

    def test_printer_adapter_is_ready(self):
        status = self.client.get("/printers/status", headers=self.headers)
        self.assertEqual(status.status_code, 200, status.text)
        body = status.json()
        self.assertEqual(body["adapter_id"], "simulated")
        self.assertIn("REQUIRE_TAKEN_BEFORE_OPEN", body["policies"])
        self.assertIn("printers", body)

    def test_system_printer_stores_a4_without_device(self):
        saved = self.client.patch("/settings/parking", headers=self.headers, json={
            "printer_adapter": "system",
            "printer_name": "Missing USB Printer",
            "receipt_policy": "PRINT_AND_OPEN",
        })
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["printer_adapter"], "system")
        test = self.client.post("/printers/test", headers=self.headers, json={})
        self.assertEqual(test.status_code, 200, test.text)
        self.assertTrue(test.json().get("ok"))
        self.assertTrue(test.json().get("path"))

    def test_print_happens_before_gate_opens(self):
        gate = self._lane()
        order = []
        mock_ctrl = MagicMock()

        async def open_gate(*args, **kwargs):
            order.append("open")
            return OPENED

        mock_ctrl.open = AsyncMock(side_effect=open_gate)

        async def fake_print(document):
            order.append("print")
            from app.infrastructure.hardware.printers import PrintResult
            return PrintResult(ok=True, adapter_id="simulated", status="PRINTED", message="printed", simulated=True, path="/tmp/x")

        with patch("app.services.simulation.controller", return_value=mock_ctrl):
            with patch("app.services.receipts.printer_adapter") as adapter_fn:
                adapter = MagicMock()
                adapter.id = "simulated"
                adapter.print_receipt = AsyncMock(side_effect=fake_print)
                adapter_fn.return_value = adapter
                res = self.client.post("/sim/entry", headers=self.headers, json={
                    "plate": "T000PRT", "gate_id": gate["id"], "side": "ENTRY",
                })
        self.assertEqual(res.status_code, 200, res.text)
        self.assertTrue(res.json()["barrier_opened"])
        self.assertEqual(order, ["print", "open"])

    def test_dashboard_counts_registered_plates(self):
        self.client.post("/vehicles", headers=self.headers, json={"plate": "T111AAA"})
        dash = self.client.get("/dashboard", headers=self.headers)
        self.assertEqual(dash.status_code, 200, dash.text)
        self.assertGreaterEqual(dash.json()["registered_plates"], 1)

    def test_casual_print_and_open_by_default(self):
        gate = self._lane()
        mock_ctrl = MagicMock()
        mock_ctrl.open = AsyncMock(return_value=OPENED)
        with patch("app.services.simulation.controller", return_value=mock_ctrl):
            res = self.client.post("/sim/entry", headers=self.headers, json={
                "plate": "T000CAS", "gate_id": gate["id"], "side": "ENTRY",
            })
        self.assertTrue(res.json()["barrier_opened"])
        self.assertEqual(res.json()["session"]["status"], "ACTIVE")
        self.assertIn("PARKING ENTRY", res.json()["receipt"])
        mock_ctrl.open.assert_awaited()
        sid = res.json()["session"]["id"]
        slip = self.client.get(f"/sessions/{sid}/receipt", headers=self.headers)
        self.assertEqual(slip.status_code, 200, slip.text)
        self.assertIn("PARKING ENTRY", slip.json()["body_text"])
        txt = self.client.get(f"/sessions/{sid}/receipt.txt", headers=self.headers)
        self.assertEqual(txt.status_code, 200, txt.text)
        self.assertIn("PARKING ENTRY", txt.text)
        reprint = self.client.post(f"/sessions/{sid}/receipt", headers=self.headers, json={})
        self.assertEqual(reprint.status_code, 200, reprint.text)
        self.assertTrue((reprint.json().get("print") or {}).get("path"))

    def test_print_failure_still_opens_barrier(self):
        gate = self._lane()
        mock_ctrl = MagicMock()
        mock_ctrl.open = AsyncMock(return_value=OPENED)
        broken = MagicMock()
        broken.id = "simulated"
        broken.print_receipt = AsyncMock(side_effect=RuntimeError("printer offline"))
        with patch("app.services.simulation.controller", return_value=mock_ctrl):
            with patch("app.services.receipts.printer_adapter", return_value=broken):
                res = self.client.post("/sim/entry", headers=self.headers, json={
                    "plate": "T000NOP", "gate_id": gate["id"], "side": "ENTRY",
                })
        self.assertEqual(res.status_code, 200, res.text)
        self.assertTrue(res.json()["barrier_opened"])
        self.assertIn("PARKING ENTRY", res.json()["receipt"])
        mock_ctrl.open.assert_awaited()

    def test_kiosk_payment_writes_ledger(self):
        gate = self._lane()
        mock_ctrl = MagicMock()
        mock_ctrl.open = AsyncMock(return_value=OPENED)
        with patch("app.services.simulation.controller", return_value=mock_ctrl):
            created = self.client.post("/sim/entry", headers=self.headers, json={
                "plate": "T000PAY", "gate_id": gate["id"], "side": "ENTRY",
            }).json()
        sid = created["session"]["id"]
        from datetime import datetime, timedelta, timezone
        with self.Session() as db:
            from app.models import ParkingSession
            row = db.get(ParkingSession, sid)
            row.entry_time = datetime.now(timezone.utc) - timedelta(hours=3)
            db.commit()
        paid = self.client.post(f"/sessions/{sid}/pay", headers=self.headers, json={"method": "KIOSK_CASH"})
        self.assertEqual(paid.status_code, 200, paid.text)
        self.assertEqual(paid.json()["status"], "PAID")
        ledger = self.client.get("/payments", headers=self.headers)
        self.assertEqual(ledger.status_code, 200, ledger.text)
        rows = ledger.json()
        self.assertTrue(any(item["session_id"] == sid and item["status"] == "SUCCEEDED" for item in rows))
        dash = self.client.get("/dashboard", headers=self.headers).json()
        self.assertIn("revenue_today", dash)
        self.assertIn("entries_today", dash)


if __name__ == "__main__":
    unittest.main()
