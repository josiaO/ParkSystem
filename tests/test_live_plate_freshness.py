"""Regression tests for stale live plate state and native callback freshness."""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, PropertyMock, patch

from app.services import preview


class LivePlateFreshnessTests(unittest.TestCase):
    def tearDown(self):
        preview._state.clear()

    def test_last_car_expires_from_live_lane(self):
        with patch("app.services.preview.time.monotonic", return_value=10.0):
            preview.remember_last_car(1, {"plate": "T285DQP"})
        with patch("app.services.preview.time.monotonic", return_value=12.0):
            self.assertEqual(preview.fresh_last_car(1, max_age_seconds=4), {"plate": "T285DQP"})
        with patch("app.services.preview.time.monotonic", return_value=15.0):
            self.assertIsNone(preview.fresh_last_car(1, max_age_seconds=4))
            self.assertEqual(preview.get_state(1).last_car, {})

    def test_fastalpr_result_expires_from_live_lane(self):
        with patch("app.services.preview.time.monotonic", return_value=20.0):
            preview.remember_alpr(2, {"best": {"plate": "T111AAA"}})
        with patch("app.services.preview.time.monotonic", return_value=22.0):
            self.assertIsNotNone(preview.fresh_alpr(2, max_age_seconds=4))
        with patch("app.services.preview.time.monotonic", return_value=25.0):
            self.assertIsNone(preview.fresh_alpr(2, max_age_seconds=4))


class CameraReadOnLiveLaneTests(unittest.TestCase):
    def tearDown(self):
        preview._state.clear()

    def test_camera_callback_stays_on_the_live_lane(self):
        from pathlib import Path
        import tempfile
        from PIL import Image
        from io import BytesIO
        from app.api_main import _show_camera_read

        image = BytesIO()
        Image.new("RGB", (80, 24), "white").save(image, format="JPEG")
        jpeg = image.getvalue()
        from app.config import Settings
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(Settings, "media_dir", new_callable=PropertyMock, return_value=Path(folder)), \
             patch("app.services.preview.time.monotonic", return_value=50.0):
            _show_camera_read(
                7, plate="T545DJZ", confidence=0.9, jpeg=jpeg, crop=jpeg,
                overlay={"x1": 10, "y1": 4, "x2": 70, "y2": 20, "image_width": 80, "image_height": 24},
            )
            shown = preview.fresh_last_car(7, max_age_seconds=45)
            self.assertEqual(shown["plate"], "T545DJZ")
            self.assertTrue(str(shown["crop_url"]).split("?")[0].endswith("crops/live-7.jpg"))
            self.assertEqual(preview.held_plate_box(7)["x2"], 70)
            self.assertTrue((Path(folder) / "crops" / "live-7.jpg").is_file())


class NativeCaptureFreshnessTests(unittest.IsolatedAsyncioTestCase):
    async def test_stale_vendor_last_capture_is_not_a_current_plate(self):
        from app.api_main import _native_capture_for_camera

        camera = SimpleNamespace(sdk_handle=44)
        old = {
            "last_capture": {
                "image_id": 1,
                "plate": "T999OLD",
                "score": 99,
                "captured_at_epoch": 100.0,
            }
        }
        with patch("app.api_main.HVXHostClient.state", AsyncMock(return_value=old)), \
             patch("app.api_main.time.time", return_value=110.0), \
             patch("app.api_main.settings.live_plate_fresh_seconds", 4.0):
            body = await _native_capture_for_camera(camera)
        self.assertFalse(body.get("plate"))

    async def test_fresh_vendor_capture_is_returned(self):
        from app.api_main import _native_capture_for_camera

        camera = SimpleNamespace(sdk_handle=44)
        fresh = {
            "last_capture": {
                "image_id": 2,
                "plate": "T285DQP",
                "score": 95,
                "captured_at_epoch": 100.0,
            }
        }
        with patch("app.api_main.HVXHostClient.state", AsyncMock(return_value=fresh)), \
             patch("app.api_main.time.time", return_value=102.0), \
             patch("app.api_main.settings.live_plate_fresh_seconds", 4.0):
            body = await _native_capture_for_camera(camera)
        self.assertEqual(body.get("plate"), "T285DQP")


if __name__ == "__main__":
    unittest.main()
