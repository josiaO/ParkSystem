"""Component 1: media acquisition stays bounded, fresh, and isolated per camera."""

from __future__ import annotations

import asyncio
import json
import threading
import time
import unittest
from unittest.mock import AsyncMock, patch

from app.infrastructure.media.diagnostics import FAIL, PASS, scrub, summarize_samples, verdict_for
from app.infrastructure.media.service import MediaService
from app.services.media_gateway import CameraLiveSpec, CameraMediaSession, LocalMediaGateway
from app.services.queues import VIDEO_FRAMES

JPEG = b"\xff\xd8" + b"LIVE" + b"\xff\xd9"


def _spec(camera_id: int, *, handle: int | None = None, need_detect: bool = False) -> CameraLiveSpec:
    return CameraLiveSpec(
        id=camera_id,
        ip=f"10.0.0.{camera_id}",
        username="operator",
        password="secret-pass",
        rtsp_url="",
        sdk_handle=handle,
        need_detect=need_detect,
    )


class AcquisitionContractTests(unittest.TestCase):
    def test_latest_frame_replaces_stale_and_stays_bounded(self):
        gw = LocalMediaGateway()
        for i in range(50):
            gw.publish(1, JPEG + bytes([i % 255]), source="sdk")
        row = gw.session(1)
        self.assertIsInstance(row, CameraMediaSession)
        self.assertEqual(row.live.depth(), 1)
        self.assertEqual(row.detect.depth(), 1)
        self.assertLessEqual(row.live.depth(), 1)
        self.assertEqual(row.live.latest().seq, 50)
        self.assertEqual(row.live.dropped, 49)
        self.assertEqual(VIDEO_FRAMES.maxsize, 1)
        self.assertEqual(gw.peek_live(1).camera_id, 1)

    def test_one_camera_does_not_change_another(self):
        gw = LocalMediaGateway()
        gw.publish(1, JPEG + b"a", source="sdk")
        gw.publish(2, JPEG + b"b", source="sdk")
        gw.publish(1, JPEG + b"c", source="sdk")
        self.assertTrue(gw.peek_live(2).jpeg.endswith(b"b"))
        self.assertEqual(gw.session(2).frames_changed, 1)
        self.assertEqual(gw.session(1).frames_changed, 2)
        self.assertEqual(gw.session(2).duplicate_frames, 0)

    def test_repeated_frame_is_not_fresh(self):
        gw = LocalMediaGateway()
        gw.publish(1, JPEG, source="sdk", url="sdk://handle/1")
        fresh = gw.session(1).last_fresh_frame_at
        time.sleep(0.02)
        gw.publish(1, JPEG, source="sdk", url="sdk://handle/1")
        row = gw.session(1)
        self.assertEqual(row.duplicate_frames, 1)
        self.assertEqual(row.frames_changed, 1)
        self.assertEqual(row.last_fresh_frame_at, fresh)
        self.assertGreater(row.last_received_at, fresh)
        row.last_fresh_frame_at = time.monotonic() - 10
        row.last_frame_received_at = row.last_fresh_frame_at
        health = gw.health_sync(1)
        self.assertTrue(health["frozen"])
        self.assertFalse(health["ok"])
        self.assertGreater(health["live_frame_age_ms"], 1000)
        self.assertLess(health["last_received_age_ms"], 1000)
        self.assertEqual(health["queue_depth"], 1)

    def test_restart_affects_only_the_failed_camera(self):
        gw = LocalMediaGateway()
        gw.publish(1, JPEG + b"a", source="sdk")
        gw.publish(2, JPEG + b"b", source="sdk")
        gw.session(1).child_pids.add(111)
        gw.session(2).child_pids.add(222)
        with patch("app.services.media_gateway._kill_pid") as kill, \
                patch("app.services.media_gateway.reconnect_for") as policy:
            policy.return_value.record_failure.return_value = 0.01
            self.assertTrue(gw.restart_decoder(1))
            self.assertFalse(gw.restart_decoder(1))
        kill.assert_called_once_with(111)
        self.assertNotIn(111, gw.session(1).child_pids)
        self.assertIn(222, gw.session(2).child_pids)
        self.assertEqual(gw.session(1).decoder_restarts, 1)
        self.assertEqual(gw.session(2).decoder_restarts, 0)
        self.assertEqual(gw.session(2).reconnects, 0)
        self.assertTrue(gw.peek_live(2).jpeg.endswith(b"b"))

    def test_releasing_a_viewer_keeps_detect(self):
        gw = LocalMediaGateway()
        spec = _spec(3, handle=3, need_detect=True)
        gw.acquire_detect(spec)
        gw.acquire_live(spec)
        gw.release_live(3)
        row = gw.session(3)
        self.assertEqual(row.viewers, 0)
        self.assertGreaterEqual(row.detect_consumers, 1)
        self.assertTrue(row.wanted())
        gw.stop_producer(3)
        self.assertIsNotNone(gw.session(3))
        self.assertTrue(gw.session(3).wanted())

    def test_slow_detect_reader_does_not_stall_live_publish(self):
        gw = LocalMediaGateway()
        stop = False

        def reader() -> None:
            while not stop:
                gw.peek_detect(1)
                time.sleep(0.01)

        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        started = time.perf_counter()
        try:
            for i in range(40):
                gw.publish(1, JPEG + bytes([i]), source="sdk")
        finally:
            stop = True
            thread.join(timeout=1)
        self.assertLess(time.perf_counter() - started, 0.3)
        self.assertEqual(gw.session(1).live.depth(), 1)
        self.assertEqual(gw.peek_live(1).seq, 40)

    def test_credentials_are_redacted(self):
        gw = LocalMediaGateway()
        gw.publish(1, JPEG, source="rtsp", url="rtsp://operator:secret-pass@10.0.0.8/av0_1")
        text = json.dumps(gw.health_sync(1))
        self.assertNotIn("secret-pass", text)
        self.assertIn("********", text)
        leaked = scrub({"password": "secret-pass", "url": "rtsp://operator:secret-pass@10.0.0.8/live"})
        self.assertNotIn("password", leaked)
        self.assertNotIn("secret-pass", json.dumps(leaked))

    def test_media_service_hides_the_source(self):
        gw = LocalMediaGateway()
        service = MediaService(gw)
        service.register_camera(8, {
            "ip": "10.0.0.8",
            "username": "operator",
            "password": "secret-pass",
            "sdk_handle": None,
            "need_detect": False,
            "rtsp_url": "",
        })
        gw.publish(8, JPEG, source="sdk", url="sdk://handle/8")
        sample = service.latest_detect_frame(8)
        self.assertIsNotNone(sample)
        self.assertEqual(sample.camera_id, 8)
        self.assertEqual(sample.jpeg, JPEG)
        self.assertGreater(sample.seq, 0)
        self.assertGreaterEqual(sample.age_ms(), 0)
        self.assertEqual(sample.source, "sdk")
        health = service.health(8)
        self.assertIn("live_frame_age_ms", health)
        self.assertEqual(service.evidence_frame(8).seq, sample.seq)
        service.stop(8)

    def test_repeated_sdk_jpeg_stays_connected(self):
        asyncio.run(self._repeated_sdk_jpeg_stays_connected())

    async def _repeated_sdk_jpeg_stays_connected(self):
        gw = LocalMediaGateway()
        counter = {"n": 0}

        async def live_jpeg(handle: int) -> bytes:
            if int(handle) == 1:
                return JPEG
            counter["n"] = (counter["n"] + 1) % 200
            return b"\xff\xd8" + bytes([counter["n"]]) + b"\xff\xd9"

        from types import SimpleNamespace

        fake_settings = SimpleNamespace(
            stale_stream_seconds=0.05,
            live_sdk_interval_seconds=0.01,
            detect_fps=5.0,
            live_idle_seconds=30.0,
            stream_read_timeout_seconds=3.0,
        )
        with patch("app.services.media_gateway.HVXHostClient") as host_cls, \
                patch("app.services.media_gateway.settings", fake_settings), \
                patch("app.services.circuit.ReconnectPolicy.record_failure", return_value=0.01):
            host_cls.return_value.live_jpeg = AsyncMock(side_effect=live_jpeg)
            gw.ensure_producer(_spec(1, handle=1, need_detect=True))
            gw.ensure_producer(_spec(1, handle=1, need_detect=True))
            gw.ensure_producer(_spec(2, handle=2, need_detect=True))
            await asyncio.sleep(0.05)
            names = [task.get_name() for task in asyncio.all_tasks()]
            self.assertEqual(names.count("media-1"), 1)
            self.assertEqual(names.count("media-2"), 1)
            await asyncio.sleep(0.45)
            frozen = gw.session(1)
            healthy = gw.session(2)
            try:
                self.assertEqual(frozen.reconnects, 0)
                self.assertEqual(frozen.decoder_restarts, 0)
                self.assertGreater(frozen.duplicate_frames, 0)
                self.assertGreater(frozen.frames_arrived, 1)
                self.assertEqual(healthy.reconnects, 0)
                self.assertGreater(healthy.frames_changed, 1)
                self.assertEqual(healthy.live.depth(), 1)
            finally:
                gw.stop_all()

    def test_missing_sdk_jpeg_reconnects_only_that_camera(self):
        asyncio.run(self._missing_sdk_jpeg_reconnects_only_that_camera())

    async def _missing_sdk_jpeg_reconnects_only_that_camera(self):
        gw = LocalMediaGateway()
        seen = {"n": 0}
        counter = {"n": 0}

        async def live_jpeg(handle: int) -> bytes:
            if int(handle) == 1:
                seen["n"] += 1
                return JPEG if seen["n"] == 1 else b""
            counter["n"] = (counter["n"] + 1) % 200
            return b"\xff\xd8" + bytes([counter["n"]]) + b"\xff\xd9"

        from types import SimpleNamespace

        fake_settings = SimpleNamespace(
            stale_stream_seconds=0.05,
            live_sdk_interval_seconds=0.01,
            detect_fps=5.0,
            live_idle_seconds=30.0,
            stream_read_timeout_seconds=3.0,
        )
        with patch("app.services.media_gateway.HVXHostClient") as host_cls, \
                patch("app.services.media_gateway.settings", fake_settings), \
                patch("app.services.circuit.ReconnectPolicy.record_failure", return_value=0.01):
            host_cls.return_value.live_jpeg = AsyncMock(side_effect=live_jpeg)
            gw.ensure_producer(_spec(1, handle=1, need_detect=True))
            gw.ensure_producer(_spec(2, handle=2, need_detect=True))
            await asyncio.sleep(0.5)
            stalled = gw.session(1)
            healthy = gw.session(2)
            try:
                self.assertGreaterEqual(stalled.reconnects, 1)
                self.assertLess(stalled.reconnects, 15)
                self.assertEqual(healthy.reconnects, 0)
                self.assertGreater(healthy.frames_changed, 1)
            finally:
                gw.stop_all()


class CameraLabVerdictTests(unittest.TestCase):
    def test_fresh_samples_pass_and_frozen_samples_fail(self):
        fresh = summarize_samples([
            {"camera_id": 1, "source": "sdk", "sdk": True, "connection_state": "STREAMING",
             "frames_received": 10, "frames_changed": 10, "duplicate_frames": 0,
             "frames_dropped_live": 0, "live_frame_age_ms": 40, "detect_frame_age_ms": 80,
             "queue_depth": 1, "detect_queue_depth": 1, "child_pids": [], "reconnects": 0,
             "decoder_restarts": 0, "frozen": False, "frame_interval_p95_ms": 120},
            {"camera_id": 1, "source": "sdk", "sdk": True, "connection_state": "STREAMING",
             "frames_received": 40, "frames_changed": 40, "duplicate_frames": 0,
             "frames_dropped_live": 1, "live_frame_age_ms": 80, "detect_frame_age_ms": 90,
             "queue_depth": 1, "detect_queue_depth": 1, "child_pids": [], "reconnects": 0,
             "decoder_restarts": 0, "frozen": False, "frame_interval_p95_ms": 140},
        ], name="Entry")
        state, _reasons = verdict_for(fresh, duration_s=60)
        self.assertEqual(state, PASS)
        self.assertEqual(fresh["adapter"], "hvx-sdk")

        frozen = summarize_samples([
            {"camera_id": 3, "source": "sdk", "connection_state": "STREAMING",
             "frames_received": 1, "frames_changed": 1, "duplicate_frames": 0,
             "live_frame_age_ms": 10, "queue_depth": 1, "detect_queue_depth": 0,
             "child_pids": [], "reconnects": 0, "decoder_restarts": 0, "frozen": False},
            {"camera_id": 3, "source": "sdk", "connection_state": "DEGRADED",
             "frames_received": 30, "frames_changed": 1, "duplicate_frames": 29,
             "live_frame_age_ms": 4000, "queue_depth": 1, "detect_queue_depth": 0,
             "child_pids": [], "reconnects": 2, "decoder_restarts": 2, "frozen": True},
        ])
        state, reasons = verdict_for(frozen, duration_s=30)
        self.assertEqual(state, FAIL)
        self.assertTrue(any("fresh" in reason or "age" in reason or "repeating" in reason for reason in reasons))

    def test_lab_refuses_to_attach_when_site_service_is_down(self):
        from tools.camera_lab import main

        code = main(["--camera", "1", "--duration", "1", "--url", "http://127.0.0.1:9", "--password", "secret-pass"])
        self.assertEqual(code, 1)


class LabOutputTests(unittest.TestCase):
    def test_down_service_message_does_not_print_the_password(self):
        from io import StringIO
        from unittest.mock import patch as patch_stdout

        from tools.camera_lab import main

        buf = StringIO()
        with patch_stdout("sys.stdout", buf):
            main(["--all", "--duration", "5", "--url", "http://127.0.0.1:9", "--password", "secret-pass"])
        text = buf.getvalue()
        self.assertIn(FAIL, text)
        self.assertNotIn("secret-pass", text)
