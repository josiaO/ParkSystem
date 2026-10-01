"""Regression tests for fail-closed parking hardware and site isolation."""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db import Base
from app.domain.receipt_engine import CAP_PAPER_STATUS, CAP_TAKEN_SENSOR
from app.infrastructure.hardware.printers import EscPosPrinterAdapter, ReceiptDocument
from app.infrastructure.hardware.receipt_printers import HardwareReceiptPrinter
from app.models import AccessPlan, Camera, Gate, RegisteredVehicle, Site
from app.services.access import lookup_entitlement
from app.services.gates import PhysicalGateController


def _receipt() -> ReceiptDocument:
    return ReceiptDocument(
        site_name="Test",
        plate="T123ABC",
        entry_time="2026-10-01 10:00",
        entry_gate="Entry",
        public_reference="ABCD-2345",
        public_url="/s/token",
        payment_instructions="Keep receipt",
        body_text="receipt",
        qr_payload="/s/token",
    )


class GateAuthorityTests(unittest.TestCase):
    def test_led_success_does_not_count_as_barrier_open(self):
        gate = Gate(id=1, name="Gate A")
        camera = Camera(id=1, name="Entry", ip_address="10.0.0.1", lane_direction="ENTRY", enabled=True)

        async def run():
            with patch("app.services.gates._gpio_pulse", new=AsyncMock(return_value={"ok": False})), \
                 patch("app.services.gates.send_board_command", new=AsyncMock(return_value=SimpleNamespace(ok=False))), \
                 patch("app.services.gates.send_led_text", new=AsyncMock(return_value=SimpleNamespace(ok=True))):
                return await PhysicalGateController().open(gate, [camera], "test", side="ENTRY")

        result = asyncio.run(run())
        self.assertFalse(result.ok)
        self.assertIn("no barrier actuator succeeded", result.message)
        self.assertIn("display updated", result.message)

    def test_gpio_success_is_barrier_success(self):
        gate = Gate(id=1, name="Gate A")
        camera = Camera(id=1, name="Entry", ip_address="10.0.0.1", lane_direction="ENTRY", enabled=True)

        async def run():
            with patch("app.services.gates._gpio_pulse", new=AsyncMock(return_value={"ok": True})), \
                 patch("app.services.gates.send_board_command", new=AsyncMock(return_value=SimpleNamespace(ok=False))), \
                 patch("app.services.gates.send_led_text", new=AsyncMock(return_value=SimpleNamespace(ok=False))):
                return await PhysicalGateController().open(gate, [camera], "test", side="ENTRY")

        self.assertTrue(asyncio.run(run()).ok)


class PrinterSafetyTests(unittest.TestCase):
    def test_configured_escpos_send_failure_is_not_success(self):
        adapter = EscPosPrinterAdapter()

        async def run():
            with patch.object(settings, "printer_escpos_host", "127.0.0.1"), \
                 patch("app.infrastructure.hardware.printers._send_tcp", side_effect=OSError("offline")):
                return await adapter.print_receipt(_receipt())

        result = asyncio.run(run())
        self.assertFalse(result.ok)
        self.assertEqual(result.status, "FAILED")
        self.assertFalse(result.simulated)

    def test_generic_hardware_printer_does_not_claim_unmeasured_sensors(self):
        printer = HardwareReceiptPrinter("simulated")
        self.assertNotIn(CAP_PAPER_STATUS, printer.capabilities)
        self.assertNotIn(CAP_TAKEN_SENSOR, printer.capabilities)


class SiteScopedEntitlementTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)

    def tearDown(self):
        self.engine.dispose()

    def test_same_plate_can_have_different_entitlement_by_site(self):
        with self.Session() as db:
            db.add_all([Site(id=1, name="A"), Site(id=2, name="B")])
            p1 = AccessPlan(id=1, site_id=1, name="Staff A", kind="STAFF", auto_open=True)
            p2 = AccessPlan(id=2, site_id=2, name="Visitor B", kind="VISITOR", auto_open=False)
            db.add_all([p1, p2])
            db.flush()
            db.add_all([
                RegisteredVehicle(site_id=1, plate="T123ABC", owner_name="A", plan_id=1, enabled=True),
                RegisteredVehicle(site_id=2, plate="T123ABC", owner_name="B", plan_id=2, enabled=True),
            ])
            db.commit()

            a = lookup_entitlement(db, "T123ABC", site_id=1)
            b = lookup_entitlement(db, "T123ABC", site_id=2)
            self.assertEqual(a.owner_name, "A")
            self.assertEqual(a.kind, "STAFF")
            self.assertEqual(b.owner_name, "B")
            self.assertEqual(b.kind, "VISITOR")


if __name__ == "__main__":
    unittest.main()
