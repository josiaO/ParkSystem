from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import PropertyMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.infrastructure.hardware.printers import (
    ReceiptDocument,
    escpos_bytes,
    escpos_qr_block,
    escpos_qr_column,
    escpos_qr_native,
    escpos_qr_raster,
    list_system_printers,
    printer_adapter,
    qr_png_bytes,
    render_a4_png,
)


def _doc() -> ReceiptDocument:
    qr_png = qr_png_bytes("http://127.0.0.1:8760/p/ABC")
    return ReceiptDocument(
        site_name="SmartPark",
        plate="T000TST",
        entry_time="01 Jan 2026 12:00",
        entry_gate="1#",
        public_reference="ABC",
        public_url="http://127.0.0.1:8760/p/ABC",
        payment_instructions="Pay at the kiosk.",
        body_text="SmartPark\nPARKING ENTRY\nPlate: T000TST\n",
        qr_payload="http://127.0.0.1:8760/p/ABC",
        qr_png=qr_png,
        lines=["SmartPark"],
    )


class PrinterTests(unittest.TestCase):
    def setUp(self):
        self.media = Path(tempfile.mkdtemp(prefix="smartpark-print-"))
        self._media = patch.object(Settings, "media_dir", new_callable=PropertyMock, return_value=self.media)
        self._media.start()

    def tearDown(self):
        self._media.stop()
        import shutil
        shutil.rmtree(self.media, ignore_errors=True)
    def test_list_printers_does_not_raise(self):
        rows = list_system_printers()
        self.assertIsInstance(rows, list)

    def test_render_a4_png(self):
        png = render_a4_png(_doc())
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertGreater(len(png), 1000)

    def test_escpos_bytes_has_ticket_markers(self):
        payload = escpos_bytes(_doc())
        self.assertIn(b"PARKING ENTRY", payload)
        self.assertIn(b"T000TST", payload)
        self.assertTrue(payload.startswith(b"\x1b@"))
        self.assertIn(b"Scan QR", payload)
        self.assertTrue(b"\x1d(\x6b" in payload or b"\x1d\x76\x30" in payload or b"\x1b*" in payload)

    def test_escpos_qr_column_from_png(self):
        doc = _doc()
        if not doc.qr_png:
            self.skipTest("qrcode not installed")
        column = escpos_qr_column(doc.qr_png, max_width=256)
        self.assertTrue(column.startswith(b"\x1b3"))
        self.assertIn(b"\x1b*", column)

    def test_escpos_qr_native_contains_store_command(self):
        block = escpos_qr_native("http://example.test/p/ABC")
        self.assertIn(b"\x1d(\x6b", block)
        self.assertIn(b"http://example.test/p/ABC", block)

    def test_escpos_qr_raster_from_png(self):
        doc = _doc()
        if not doc.qr_png:
            self.skipTest("qrcode not installed")
        raster = escpos_qr_raster(doc.qr_png, max_width=256)
        self.assertTrue(raster.startswith(b"\x1d\x76\x30"))

    def test_system_adapter_without_name_is_file_only(self):
        adapter = printer_adapter("system", printer_name="")
        self.assertEqual(adapter.id, "system")
        result = asyncio.run(adapter.print_receipt(_doc()))
        self.assertTrue(result.ok)
        self.assertTrue(result.simulated)
        self.assertTrue(result.path)
        self.assertTrue(Path(result.path).is_file())

    def test_system_adapter_sends_escpos_when_printer_set(self):
        adapter = printer_adapter("system", printer_name="Thermal POS")
        with patch("app.infrastructure.hardware.printers.send_escpos_to_system_printer") as send:
            result = asyncio.run(adapter.print_receipt(_doc()))
        self.assertTrue(result.ok)
        self.assertFalse(result.simulated)
        send.assert_called_once()
        printer_name, payload = send.call_args[0]
        self.assertEqual(printer_name, "Thermal POS")
        self.assertIn(b"PARKING ENTRY", payload)
