"""Regression checks for the MediaMTX, plate-policy, and recognition-worker fixes."""

from __future__ import annotations

import asyncio
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.core.plate import apply_site_plate, correct_ocr_confusions
from app.recognition_worker import PlateTrack, note_reading
from app.services import mediamtx
from app.services.events import recognition_from_outbox
from app.services.latest_frame import FrameSample
from app.services.media_gateway import CameraLiveSpec
from app.services.preview import acquire_live, snapshot_for_camera


ROOT = Path(__file__).resolve().parents[1]


class MediaMTXPathTests(unittest.TestCase):
    def tearDown(self):
        mediamtx._sources.pop(3, None)
        mediamtx._sources.pop(4, None)

    def test_detect_endpoint_uses_detect_path(self):
        mediamtx._sources[3] = {"uri": "rtsp://cam/live", "detect_uri": "rtsp://cam/sub"}
        live = mediamtx.live_endpoint(3)
        detect = mediamtx.detect_endpoint(3)
        self.assertEqual(live["rtsp"], "rtsp://127.0.0.1:8554/cam3")
        self.assertEqual(detect["rtsp"], "rtsp://127.0.0.1:8554/cam3_detect")
        self.assertEqual(detect["kind"], "mediamtx-detect")
        self.assertNotEqual(live["rtsp"], detect["rtsp"])

    def test_generated_config_enables_metrics_and_omits_fake_reload(self):
        text = (ROOT / "app" / "services" / "mediamtx.py").read_text(encoding="utf-8")
        self.assertNotIn("/v3/config/paths/reload", text)
        dest = ROOT / "data" / "test-mediamtx.yml"
        dest.parent.mkdir(parents=True, exist_ok=True)
        with patch.object(mediamtx, "config_path", return_value=dest):
            mediamtx._sources[3] = {"uri": "rtsp://cam/live", "detect_uri": "rtsp://cam/sub"}
            mediamtx.write_config()
        body = dest.read_text(encoding="utf-8")
        self.assertIn("metrics: yes", body)
        self.assertIn("metricsAddress: 127.0.0.1:9998", body)
        self.assertIn("cam3_detect:", body)
        dest.unlink(missing_ok=True)

    def test_sync_paths_uses_add_not_reload(self):
        urls: list[str] = []

        class Resp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def urlopen(req, timeout=0):
            urls.append(req.full_url)
            return Resp()

        mediamtx._sources[4] = {"uri": "rtsp://cam/live", "detect_uri": "rtsp://cam/detect"}
        with patch.object(mediamtx, "running", return_value=True), patch("urllib.request.urlopen", urlopen):
            self.assertTrue(mediamtx.sync_paths())
        self.assertTrue(any(url.endswith("/v3/config/paths/add/cam4") for url in urls))
        self.assertTrue(any(url.endswith("/v3/config/paths/add/cam4_detect") for url in urls))
        self.assertFalse(any("reload" in url for url in urls))

    def test_register_source_does_not_restart_mediamtx(self):
        dest = ROOT / "data" / "test-mediamtx-register.yml"
        dest.parent.mkdir(parents=True, exist_ok=True)
        with patch.object(mediamtx, "config_path", return_value=dest), \
             patch.object(mediamtx, "running", return_value=True), \
             patch.object(mediamtx, "sync_paths", return_value=False), \
             patch.object(mediamtx, "stop") as stop, \
             patch.object(mediamtx, "start") as start:
            mediamtx.register_source(3, {"uri": "rtsp://127.0.0.1/live", "detect_uri": "rtsp://127.0.0.1/sub"})
        stop.assert_not_called()
        start.assert_not_called()
        dest.unlink(missing_ok=True)


class DesktopMediaMTXTests(unittest.TestCase):
    def test_snapshot_uses_live_cache_instead_of_ffmpeg(self):
        sample = FrameSample(jpeg=b"\xff\xd8\xff\xd9", seq=1, received_at=time.monotonic(), source="mediamtx", url="rtsp://127.0.0.1:8554/cam9")

        async def run():
            with patch("app.infrastructure.media.registry.mediamtx_live_active", return_value=True), \
                 patch("app.services.mediamtx.live_endpoint", return_value={"rtsp": "rtsp://127.0.0.1:8554/cam9"}), \
                 patch("app.services.preview.gateway.peek_live", return_value=sample), \
                 patch("app.services.frame_grab.capture_frame", new_callable=AsyncMock) as capture:
                body = await snapshot_for_camera(9, "127.0.0.1", "admin", "secret", "")
            return body, capture

        body, capture = asyncio.run(run())
        self.assertTrue(body["ok"])
        self.assertTrue(body["cached"])
        self.assertEqual(body["jpeg"], sample.jpeg)
        capture.assert_not_called()

    def test_acquire_live_starts_mediamtx_live_consumer(self):
        spec = CameraLiveSpec(id=9, ip="127.0.0.1", username="a", password="b", rtsp_url="", sdk_handle=None)
        with patch("app.infrastructure.media.registry.mediamtx_live_active", return_value=True), \
             patch("app.services.mediamtx_live.ensure_live_consumer") as live, \
             patch("app.services.mediamtx_detect.ensure_detect_consumer") as detect:
            acquire_live(spec)
        live.assert_called_once()
        detect.assert_not_called()

    def test_webrtc_flag_does_not_switch_desktop_back_to_direct_camera(self):
        from app.infrastructure.media import registry

        config = {"media_gateway_enabled": True, "live_view_provider": "MEDIAMTX", "webrtc_live_enabled": False}
        with patch.object(registry, "_migration_flags", return_value=config), \
             patch.object(registry, "_camera_enabled", return_value=True), \
             patch.object(registry.mediamtx, "running", return_value=True), \
             patch.object(registry.gateway, "get_live_endpoint", AsyncMock(return_value={"kind": "mjpeg", "path": "/cameras/9/live.mjpeg"})):
            self.assertTrue(registry.mediamtx_live_active(9))
            endpoint = asyncio.run(registry.get_live_endpoint(9))
        self.assertEqual(endpoint["provider"], "MEDIAMTX")
        self.assertEqual(endpoint["transport"], "MJPEG")
        self.assertNotIn("webrtc", endpoint)

    def test_desktop_mjpeg_failure_does_not_poll_snapshots(self):
        text = (ROOT / "app" / "desktop" / "main.py").read_text(encoding="utf-8")
        fail = text.split("def _mjpeg_fail", 1)[1].split("def _retry_mjpeg", 1)[0]
        self.assertNotIn("_snap_timer.start()", fail)
        self.assertIn("_retry_mjpeg", fail)
        self.assertIn("10054", fail)
        self.assertIn("250", fail)

    def test_desktop_mjpeg_reads_error_body_without_response_text(self):
        from types import SimpleNamespace
        from app.desktop.api import stream_http_error

        text = (ROOT / "app" / "desktop" / "main.py").read_text(encoding="utf-8")
        run = text.split("class MjpegStream", 1)[1].split("class ", 1)[0]
        self.assertIn("stream_http_error", run)
        self.assertNotIn("response.text", run)

        class StreamError(Exception):
            pass

        class FakeResponse:
            status_code = 409

            def read(self):
                return b'{"detail":"No live video yet. Connect the camera, then wait a second."}'

            @property
            def text(self):
                raise StreamError(
                    "Attempted to access streaming response content, without having called 'read()'."
                )

        message = stream_http_error(FakeResponse())
        self.assertIn("409", message)
        self.assertIn("No live video yet", message)

    def test_hvx_desktop_live_uses_sdk_jpeg_not_mediamtx_ffmpeg(self):
        spec = CameraLiveSpec(id=9, ip="127.0.0.1", username="a", password="b", rtsp_url="", sdk_handle=1)
        with patch("app.infrastructure.media.registry.mediamtx_live_active", return_value=True), \
             patch("app.services.mediamtx_live.ensure_live_consumer") as live, \
             patch("app.services.preview.gateway.ensure_producer") as prod, \
             patch("app.services.preview.start_idle_watch"):
            acquire_live(spec)
        prod.assert_called()
        live.assert_not_called()


class PlatePolicyTests(unittest.TestCase):
    def test_default_policy_does_not_apply_tanzania_positions(self):
        applied = apply_site_plate("T28SDQP", validation="NONE")
        self.assertEqual(applied["normalized_plate"], "T28SDQP")
        self.assertFalse(applied["ocr_corrected"])
        kenya = apply_site_plate("KAA1 23A", validation="NONE")
        self.assertEqual(kenya["normalized_plate"], "KAA123A")

    def test_tanzania_policy_still_corrects_digit_positions(self):
        applied = apply_site_plate("T28SDQP", validation="TZ")
        self.assertEqual(applied["normalized_plate"], "T285DQP")
        self.assertTrue(applied["ocr_corrected"])

    def test_neutral_still_matches_a_known_lookalike(self):
        fixed = correct_ocr_confusions("ABCO123", known_plates=["ABC0123"], policy="NONE")
        self.assertEqual(fixed["plate"], "ABC0123")
        self.assertEqual(fixed["reason"], "known-confusion")


class RecognitionWorkerTests(unittest.TestCase):
    def test_worker_does_not_read_the_site_service_gateway(self):
        text = (ROOT / "app" / "recognition_worker.py").read_text(encoding="utf-8")
        self.assertNotIn("peek_detect", text)
        self.assertNotIn("peek_live", text)
        self.assertNotIn("import gateway", text)
        self.assertIn("cam{id}_detect", text)
        self.assertIn("publish_recognition", text)

    def test_two_agreeing_reads_publish_once(self):
        track = PlateTrack()
        self.assertFalse(note_reading(track, "KAA123A", 10.0, confidence=0.8))
        self.assertTrue(note_reading(track, "KAA123A", 10.2, confidence=0.8))
        self.assertFalse(note_reading(track, "KAA123A", 12.0, confidence=0.8))
        self.assertFalse(note_reading(track, "KAA123A", 40.0, confidence=0.8))
        self.assertTrue(note_reading(track, "KAA123A", 40.2, confidence=0.8))

    def test_outbox_unwraps_plate_recognized(self):
        item = {
            "kind": "PlateRecognized",
            "payload": {
                "kind": "PlateRecognized",
                "payload": {"normalized_plate": "KAA123A", "camera_id": 3, "source": "FASTALPR"},
            },
        }
        body = recognition_from_outbox(item)
        self.assertEqual(body["plate"], "KAA123A")
        self.assertEqual(body["camera_id"], 3)
        self.assertIsNone(recognition_from_outbox({"kind": "other", "payload": {}}))


class CIWorkflowTests(unittest.TestCase):
    def test_github_actions_runs_compile_and_pytest(self):
        text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("python -m compileall app tools", text)
        self.assertIn("pytest -q", text)
        self.assertIn("pull_request", text)
