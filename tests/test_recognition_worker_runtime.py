from __future__ import annotations

import asyncio
import json
import multiprocessing
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domain.events import from_recognition_dict
from app.models import Camera
from app.recognition_worker import PlateTrack, _camera_rows, _infer_camera, _worker_ready, note_reading
from app.services.modules import apply_profile
from app.services.queues import SQLiteOutbox
from app.services.site_policy import save_site_policy


def _produce(path: str, count: int) -> None:
    box = SQLiteOutbox(Path(path))
    for number in range(count):
        box.enqueue("PlateRecognized", {"number": number})


class ProcessOutboxTests(unittest.TestCase):
    def test_concurrent_producer_and_ack_preserve_every_event(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "outbox.sqlite3"
            box = SQLiteOutbox(path)
            process = multiprocessing.get_context("spawn").Process(target=_produce, args=(str(path), 50))
            process.start()
            acknowledged = set()
            try:
                while process.is_alive():
                    for row in box.pending():
                        self.assertNotIn(row["id"], acknowledged)
                        acknowledged.add(row["id"])
                        box.ack(row["id"])
                    process.join(0.01)
                process.join(10)
                self.assertEqual(process.exitcode, 0)
                for row in box.pending():
                    self.assertNotIn(row["id"], acknowledged)
                    acknowledged.add(row["id"])
                    box.ack(row["id"])
                self.assertEqual(len(acknowledged), 50)
                self.assertEqual(box.depth(), 0)
            finally:
                if process.is_alive():
                    process.terminate()
                    process.join()

    def test_legacy_import_is_not_replayed_after_ack_or_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            legacy = Path(folder) / "old.jsonl"
            legacy.write_text(json.dumps({"id": "old", "kind": "plate-event", "payload": {"plate": "ABC1"}, "ts": 1}) + "\n")
            path = Path(folder) / "queue.sqlite3"
            box = SQLiteOutbox(path, legacy_path=legacy)
            self.assertEqual(box.pending()[0]["id"], "old")
            box.ack("old")
            self.assertEqual(SQLiteOutbox(path, legacy_path=legacy).pending(), [])
            self.assertTrue(legacy.exists())

    def test_malformed_legacy_event_is_not_silently_dropped(self):
        with tempfile.TemporaryDirectory() as folder:
            legacy = Path(folder) / "old.jsonl"
            legacy.write_text('{invalid}\n')
            with self.assertRaises(json.JSONDecodeError):
                SQLiteOutbox(Path(folder) / "queue.sqlite3", legacy_path=legacy)


class CameraSelectionTests(unittest.TestCase):
    def test_dead_or_stale_worker_releases_ownership(self):
        fresh = {"ok": True, "cameras": [{"camera_id": 1, "state": "READY", "last_frame_at": time.time(), "last_inference_at": time.time()}]}
        with patch("app.recognition_worker.worker_health", return_value=fresh):
            self.assertTrue(_worker_ready(1))
            self.assertFalse(_worker_ready(2))
            fresh["cameras"][0]["last_frame_at"] -= 30
            self.assertFalse(_worker_ready(1))
        with patch("app.recognition_worker.worker_health", return_value={"ok": False}):
            self.assertFalse(_worker_ready(1))

    def test_modes_module_and_persisted_site_policy(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine)
        try:
            with factory() as db:
                apply_profile(db, "LPR_ONLY")
                save_site_policy(db, {"plate_validation": "TZ"})
                for number, mode in enumerate(("FASTALPR_ONLY", "NATIVE_ONLY", "HYBRID", "VIDEO_ONLY"), 1):
                    db.add(Camera(name=f"cam-{number}", ip_address="127.0.0.1", recognition_mode=mode, adapter_id="rtsp"))
                db.commit()
            with patch("app.db.SessionLocal", factory), patch("app.services.flags.media_mtx_for_camera", return_value=True):
                rows = _camera_rows()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["plate_policy"]["plate_validation"], "TZ")
                with factory() as db:
                    row = db.get(Camera, 1)
                    row.enabled = False
                    db.commit()
                self.assertEqual(_camera_rows(), [])
        finally:
            engine.dispose()

    def test_consensus_expires_and_does_not_join_different_visits(self):
        track = PlateTrack()
        self.assertFalse(note_reading(track, "ABC123", 0))
        self.assertFalse(note_reading(track, "ABC123", 30))
        self.assertTrue(note_reading(track, "ABC123", 30.2))
        self.assertFalse(note_reading(track, "ABC123", 30.4))

    def test_continuously_visible_plate_does_not_republish_after_hold(self):
        track = PlateTrack()
        self.assertFalse(note_reading(track, "ABC123", 0))
        self.assertTrue(note_reading(track, "ABC123", .2))
        for second in range(1, 60):
            self.assertFalse(note_reading(track, "ABC123", float(second)))

    def test_outbox_contract_preserves_recognition_evidence(self):
        event = from_recognition_dict({"event_id": "capture-1", "occurred_at": "2026-09-30T12:00:00Z", "normalized_plate": "ABC123", "validation_result": {"valid": True}, "bbox": {"x1": 1}})
        self.assertEqual(event["event_id"], event["payload"]["event_id"])
        self.assertEqual(event["occurred_at"], event["payload"]["occurred_at"])
        self.assertEqual(event["payload"]["bbox"], {"x1": 1})


class WorkerRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_inference_skips_frames_and_closes_decoder(self):
        from app.config import settings

        decoded = []
        inferred = []
        closed = asyncio.Event()
        done = asyncio.Event()
        stop = asyncio.Event()
        received_policy = []
        first_inference = asyncio.Event()
        burst_decoded = asyncio.Event()

        async def stream(*args, **kwargs):
            try:
                number = 0
                while True:
                    number += 1
                    decoded.append(number)
                    yield b"\xff\xd8" + str(number).encode()
                    if number == 1:
                        await first_inference.wait()
                    elif number == 10:
                        burst_decoded.set()
                    await asyncio.sleep(0 if number <= 10 else 0.005)
            finally:
                closed.set()

        async def infer(frame):
            inferred.append(int(frame["jpeg"][2:]))
            received_policy.append(frame["plate_policy"])
            if len(inferred) == 1:
                first_inference.set()
                await burst_decoded.wait()
            await asyncio.sleep(0.06)
            if len(inferred) >= 3:
                done.set()
            return {"event_id": "event123", "normalized_plate": "ABC123", "camera_id": 1, "confidence": .9}

        stats = {}
        provider = type("Provider", (), {"process": staticmethod(infer)})()
        with patch("app.infrastructure.media.registry.get_detect_endpoint", AsyncMock(return_value={"provider": "MEDIAMTX", "rtsp": "rtsp://127.0.0.1:8554/cam1_detect"})), \
             patch("app.services.media_gateway.LocalMediaGateway.ffmpeg_jpeg_stream", stream), \
             patch("app.infrastructure.recognition.recognition_provider_for", return_value=provider), \
             patch("app.recognition_worker._publish_frame") as publish, \
             patch.object(settings, "detect_fps", 30):
            task = asyncio.create_task(_infer_camera({"id": 1, "plate_policy": {"plate_validation": "TZ"}}, stop, stats))
            try:
                await asyncio.wait_for(done.wait(), 2)
            finally:
                stop.set()
                await asyncio.wait_for(task, 2)
        self.assertTrue(closed.is_set())
        self.assertGreater(inferred[1] - inferred[0], 1)
        self.assertLess(len(inferred), len(decoded))
        self.assertGreater(stats["frame_buffer"]["dropped"], 0)
        self.assertEqual(received_policy[0], {"plate_validation": "TZ"})
        publish.assert_called_once()

    async def test_provider_moves_blocking_model_work_off_event_loop(self):
        import threading
        from app.infrastructure.recognition.fastalpr import FastALPRProvider

        caller_thread = threading.get_ident()
        model_threads = []

        def recognize(*args, **kwargs):
            model_threads.append(threading.get_ident())
            return {"ok": True}

        with patch("app.infrastructure.recognition.fastalpr.recognize_frame", recognize), \
             patch("app.infrastructure.recognition.fastalpr.local_from_fastalpr", return_value={"plate": "ABC123"}):
            result = await FastALPRProvider().process({"jpeg": b"test"})
        self.assertEqual(result["normalized_plate"], "ABC123")
        self.assertNotEqual(model_threads, [caller_thread])
