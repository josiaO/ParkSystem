"""Recognition consumes local MediaMTX. It does not own the camera."""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.recognition_decoder import decoder_command, require_local_mediamtx


class LocalEndpointTests(unittest.TestCase):
    def test_only_local_mediamtx_is_accepted(self):
        self.assertEqual(
            require_local_mediamtx("rtsp://127.0.0.1:8554/cam1_detect"),
            "rtsp://127.0.0.1:8554/cam1_detect",
        )
        for url in (
            "rtsp://192.168.1.49:554/stream",
            "rtsp://127.0.0.1:554/cam1",
            "http://127.0.0.1:8554/cam1",
            "rtsp://127.0.0.1:8554",
        ):
            with self.assertRaises(ValueError):
                require_local_mediamtx(url)

    def test_command_decodes_without_transcoding(self):
        with patch("app.services.recognition_decoder.ffmpeg_bin", return_value="ffmpeg"):
            cmd = decoder_command("rtsp://localhost:8554/cam2", sample_fps=3, scale=960)
        self.assertEqual(cmd[0], "ffmpeg")
        self.assertIn("tcp", cmd)
        self.assertIn("fps=3,scale=960:-2", cmd)
        self.assertIn("mjpeg", cmd)
        self.assertNotIn("libx264", cmd)
        self.assertNotIn("192.168.1.49", " ".join(cmd))


class DecoderLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_decoder_is_reaped_when_the_lane_stops(self):
        class Stream:
            def __init__(self, chunks):
                self._chunks = list(chunks)

            async def read(self, _n=0):
                if self._chunks:
                    return self._chunks.pop(0)
                return b""

        class Proc:
            def __init__(self):
                self.pid = 4242
                self.returncode = None
                self.stdout = Stream([b"\xff\xd8\xff\xd9", b""])
                self.stderr = Stream([b""])
                self.terminated = False

            def terminate(self):
                self.terminated = True
                self.returncode = 0

            def kill(self):
                self.returncode = -9

            async def wait(self):
                self.returncode = 0
                return 0

        proc = Proc()

        async def fake_exec(*_cmd, **_kwargs):
            return proc

        from app.services.recognition_decoder import iter_jpegs

        with patch("app.services.recognition_decoder.ffmpeg_bin", return_value="ffmpeg"), \
             patch("app.services.recognition_decoder.asyncio.create_subprocess_exec", fake_exec):
            pids = []
            agen = iter_jpegs("rtsp://127.0.0.1:8554/cam1_detect", sample_fps=3, on_pid=pids.append)
            frame = await agen.__anext__()
            self.assertEqual(frame, b"\xff\xd8\xff\xd9")
            self.assertEqual(pids, [4242])
            await agen.aclose()
        self.assertTrue(proc.terminated)



    async def test_partial_bytes_cannot_keep_a_broken_stream_alive(self):
        from app.config import settings
        from app.services.recognition_decoder import RecognitionDecoder
        from unittest.mock import Mock

        async def incomplete(*args):
            await asyncio.sleep(.005)
            return b"incomplete"

        proc = SimpleNamespace(
            pid=123, returncode=None,
            stdout=SimpleNamespace(read=incomplete), stderr=None,
            terminate=Mock(), kill=Mock(), wait=AsyncMock(return_value=0),
        )
        with patch("app.services.recognition_decoder.ffmpeg_bin", return_value="ffmpeg"), \
             patch("app.services.recognition_decoder.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)), \
             patch.object(settings, "stream_read_timeout_seconds", .03):
            decoder = RecognitionDecoder()
            frames = decoder.frames("rtsp://localhost:8554/cam1", sample_fps=3)
            with self.assertRaises(TimeoutError):
                await asyncio.wait_for(anext(frames), .3)
            proc.terminate.assert_called_once()
            self.assertIsNone(decoder.pid)


class RoiAndCropTests(unittest.TestCase):
    def test_roi_boxes_are_translated_back_to_the_full_frame(self):
        numpy = __import__("numpy")
        from app.services.alpr import _roi_crop, _shift_detections

        image = numpy.zeros((100, 200, 3), dtype=numpy.uint8)
        view, dx, dy = _roi_crop(image, "0.10,0.20,0.90,0.80")
        self.assertEqual((dx, dy), (20, 20))
        self.assertEqual(view.shape[:2], (60, 160))
        detection = SimpleNamespace(
            bounding_box=SimpleNamespace(x1=1, y1=2, x2=30, y2=12),
            confidence=0.9,
        )
        shifted = _shift_detections([detection], dx, dy)
        box = shifted[0].bounding_box
        self.assertEqual((box.x1, box.y1, box.x2, box.y2), (21, 22, 50, 32))
        full, full_dx, full_dy = _roi_crop(image, "off")
        self.assertEqual((full_dx, full_dy), (0, 0))
        self.assertEqual(full.shape[:2], (100, 200))

    def test_ocr_is_called_with_the_plate_crop(self):
        numpy = __import__("numpy")
        from app.services.alpr import _hits_from_detections

        image = numpy.zeros((80, 200, 3), dtype=numpy.uint8)
        seen = []

        class Ocr:
            def predict(self, crop):
                seen.append(crop.shape)
                return SimpleNamespace(text="", confidence=0.1)

        engine = SimpleNamespace(ocr=Ocr())
        detection = SimpleNamespace(
            bounding_box=SimpleNamespace(x1=20, y1=40, x2=120, y2=60),
            confidence=0.9,
        )
        _hits_from_detections(engine, image, [detection], save_crops=False)
        self.assertEqual(len(seen), 1)
        self.assertNotEqual(tuple(seen[0][:2]), (80, 200))


class LaneBehaviorTests(unittest.IsolatedAsyncioTestCase):
    async def test_confirmed_plate_pauses_ocr_and_departure_clears_it(self):
        from app.config import settings
        from app.recognition_worker import _infer_camera
        from app.services.recognition_runtime import runtime

        runtime.reset()
        published = []
        inferred = []
        phase = {"plate": "T123ABC", "present": True}
        stop = asyncio.Event()

        async def stream(*_args, **_kwargs):
            number = 0
            while not stop.is_set():
                number += 1
                yield b"\xff\xd8" + str(number).encode()
                await asyncio.sleep(0.01)

        async def infer(frame):
            inferred.append(frame["jpeg"])
            plate = phase["plate"] if phase["present"] else ""
            return {
                "event_id": "event1",
                "ok": bool(plate),
                "normalized_plate": plate,
                "confidence": 0.95 if plate else 0.0,
                "camera_id": 7,
            }

        def present(_jpeg, detect_roi=None):
            return phase["present"]

        provider = type("Provider", (), {"process": staticmethod(infer)})()
        stats = {"started_at": 0}
        with patch("app.infrastructure.media.registry.get_detect_endpoint", AsyncMock(return_value={"provider": "MEDIAMTX", "rtsp": "rtsp://127.0.0.1:8554/cam7_detect"})), \
             patch("app.services.recognition_decoder.iter_jpegs", stream), \
             patch("app.services.alpr.plate_still_present", present), \
             patch("app.infrastructure.recognition.recognition_provider_for", return_value=provider), \
             patch("app.recognition_worker._publish_frame", side_effect=lambda event, _jpeg: published.append(event["normalized_plate"])), \
             patch.object(settings, "recognition_sample_fps", 20), \
             patch.object(settings, "recognition_departure_check_seconds", 0.02), \
             patch.object(settings, "recognition_absence_reset_seconds", 0.05):
            task = asyncio.create_task(_infer_camera({"id": 7, "plate_policy": {}}, stop, stats))
            try:
                for _ in range(100):
                    if published:
                        break
                    await asyncio.sleep(0.02)
                self.assertEqual(published, ["T123ABC"])
                paused_at = len(inferred)
                last_progress = stats["last_inference_at"]
                await asyncio.sleep(0.15)
                self.assertEqual(len(inferred), paused_at)
                self.assertTrue(stats.get("ocr_paused"))
                self.assertGreater(stats["last_inference_at"], last_progress)
                self.assertGreater(runtime.lane(7).last_frame_at, 0)
                phase["present"] = False
                saw_clear = False
                for _ in range(150):
                    if stats.get("last_plate") == "":
                        saw_clear = True
                        break
                    await asyncio.sleep(0.02)
                self.assertTrue(saw_clear)
                self.assertEqual(published, ["T123ABC"])
                phase["present"] = True
                phase["plate"] = "T999XYZ"
                for _ in range(150):
                    if "T999XYZ" in published:
                        break
                    await asyncio.sleep(0.02)
                self.assertEqual(published, ["T123ABC", "T999XYZ"])
                await asyncio.sleep(0.15)
                self.assertEqual(published, ["T123ABC", "T999XYZ"])
            finally:
                stop.set()
                await asyncio.wait_for(task, 2)
                runtime.reset()

    async def test_one_decoder_failure_does_not_stop_the_other_lane(self):
        from app.recognition_worker import _infer_camera
        from app.services.recognition_runtime import runtime

        runtime.reset()
        stop = asyncio.Event()

        async def endpoint(camera_id):
            return {"provider": "MEDIAMTX", "rtsp": f"rtsp://127.0.0.1:8554/cam{camera_id}_detect"}

        async def stream(url, **_kwargs):
            if url.endswith("cam2_detect"):
                raise RuntimeError("decoder down")
            while not stop.is_set():
                yield b"\xff\xd8ok"
                await asyncio.sleep(0.01)

        async def infer(_frame):
            return {"ok": True, "normalized_plate": "", "confidence": 0, "event_id": "event2"}

        provider = type("Provider", (), {"process": staticmethod(infer)})()
        good = {"started_at": 0}
        bad = {"started_at": 0}
        with patch("app.infrastructure.media.registry.get_detect_endpoint", endpoint), \
             patch("app.services.recognition_decoder.iter_jpegs", stream), \
             patch("app.infrastructure.recognition.recognition_provider_for", return_value=provider):
            good_task = asyncio.create_task(_infer_camera({"id": 1}, stop, good))
            bad_task = asyncio.create_task(_infer_camera({"id": 2}, stop, bad))
            try:
                for _ in range(50):
                    if good.get("last_frame_at") and int(bad.get("reconnects") or 0) >= 1:
                        break
                    await asyncio.sleep(0.02)
                self.assertTrue(good.get("last_frame_at"))
                self.assertGreaterEqual(int(bad.get("reconnects") or 0), 1)
                self.assertEqual(int(good.get("reconnects") or 0), 0)
            finally:
                stop.set()
                await asyncio.gather(good_task, bad_task, return_exceptions=True)
                runtime.reset()

    async def test_worker_refuses_a_physical_camera_url(self):
        from app.recognition_worker import _infer_camera

        called = []

        async def stream(*_args, **_kwargs):
            called.append(1)
            yield b"\xff\xd8"

        stats = {}
        with patch("app.infrastructure.media.registry.get_detect_endpoint", AsyncMock(return_value={"provider": "MEDIAMTX", "rtsp": "rtsp://192.168.1.49:554/live"})), \
             patch("app.services.recognition_decoder.iter_jpegs", stream):
            await _infer_camera({"id": 4}, asyncio.Event(), stats)
        self.assertEqual(called, [])
        self.assertEqual(stats["state"], "DEGRADED")


class UnconfirmedVisitTests(unittest.IsolatedAsyncioTestCase):
    async def test_missed_read_before_consensus_does_not_pause_ocr(self):
        from app.config import settings
        from app.recognition_worker import _infer_camera
        from app.services.recognition_runtime import runtime

        runtime.reset()
        stop = asyncio.Event()
        reads = []
        published = []

        async def stream(*args, **kwargs):
            while not stop.is_set():
                yield b"\xff\xd8frame"
                await asyncio.sleep(0.01)

        async def infer(frame):
            reads.append(1)
            plate = "" if len(reads) == 2 else "ABC123"
            return {"ok": bool(plate), "normalized_plate": plate, "confidence": .9}

        with patch("app.infrastructure.media.registry.get_detect_endpoint", AsyncMock(return_value={"provider": "MEDIAMTX", "rtsp": "rtsp://localhost:8554/cam8"})), \
             patch("app.services.recognition_decoder.iter_jpegs", stream), \
             patch("app.infrastructure.recognition.recognition_provider_for", return_value=SimpleNamespace(process=infer)), \
             patch("app.services.alpr.plate_still_present", return_value=True), \
             patch("app.recognition_worker._publish_frame", side_effect=lambda *args: published.append(1)), \
             patch.object(settings, "recognition_sample_fps", 20):
            task = asyncio.create_task(_infer_camera({"id": 8}, stop, {}))
            try:
                for _ in range(100):
                    if published:
                        break
                    await asyncio.sleep(.02)
                self.assertGreaterEqual(len(reads), 3)
                self.assertEqual(published, [1])
                await asyncio.sleep(.1)
            finally:
                stop.set()
                await asyncio.wait_for(task, 2)
                runtime.reset()
