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
from app.infrastructure.hardware.printers import ReceiptDocument, list_system_printers, printer_adapter, render_a4_png


def _doc() -> ReceiptDocument:
    return ReceiptDocument(
        site_name="SmartPark",
        plate="T000TST",
        entry_time="01 Jan 2026 12:00",
        entry_gate="1#",
        public_reference="ABC",
        public_url="/p/ABC",
        payment_instructions="Pay at the kiosk.",
        body_text="SmartPark\nPARKING ENTRY\nPlate: T000TST\n",
        qr_payload="/p/ABC",
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

    def test_system_adapter_without_name_is_file_only(self):
        adapter = printer_adapter("system", printer_name="")
        self.assertEqual(adapter.id, "system")
        result = asyncio.run(adapter.print_receipt(_doc()))
        self.assertTrue(result.ok)
        self.assertTrue(result.simulated)
        self.assertTrue(result.path)
        self.assertTrue(Path(result.path).is_file())
