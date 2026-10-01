"""Recognition commissioning diagnostics must be useful and side-effect free."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Camera, VehicleCapture
from app.services.recognition_commissioning import commissioning_snapshot, diagnostic_read


class RecognitionCommissioningTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        self.media = Path(tempfile.mkdtemp(prefix="smartpark-commissioning-"))

    def tearDown(self):
        import shutil

        shutil.rmtree(self.media, ignore_errors=True)
        self.engine.dispose()

    def _camera(self, db, *, adapter="rtsp", mode="FASTALPR_ONLY"):
        row = Camera(
            site_id=1,
            name="Test camera",
            ip_address="192.168.1.50",
            adapter_id=adapter,
            recognition_mode=mode,
            stream_profiles={
                "MAIN": {"uri": "rtsp://cam/main", "width": 1920, "height": 1080},
                "SUB": {"uri": "rtsp://cam/sub", "width": 640, "height": 360},
                "LIVE": {"source": "SUB"},
                "DETECT": {"source": "SUB", "ai_fps": 5},
            },
            enabled=True,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def _capture(self, db, camera, *, width=60):
        crop_rel = "crops/test.jpg"
        snap_rel = "snapshots/test.jpg"
        (self.media / "crops").mkdir(parents=True, exist_ok=True)
        (self.media / "snapshots").mkdir(parents=True, exist_ok=True)
        jpeg = b"\xff\xd8commissioning\xff\xd9"
        (self.media / crop_rel).write_bytes(jpeg)
        (self.media / snap_rel).write_bytes(jpeg)
        row = VehicleCapture(
            camera_id=camera.id,
            plate="T285DQP",
            plate_raw="T285DQP",
            confidence=.91,
            snapshot_path=snap_rel,
            crop_path=crop_rel,
            bbox={"x1": 100, "y1": 100, "x2": 100 + width, "y2": 130},
            source="fastalpr",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def test_commissioning_recommends_main_when_plate_is_too_small(self):
        with self.Session() as db:
            camera = self._camera(db)
            self._capture(db, camera, width=60)
            with patch("app.services.recognition_commissioning._worker_row", return_value={
                "owns_continuous_software_reads": True, "worker_ok": True
            }), patch("app.services.recognition_commissioning._media_row", return_value={
                "connection_state": "STREAMING",
                "live_fps": 12,
                "live_frame_age_ms": 40,
                "detect_frame_age_ms": 80,
                "ai_processed_fps": 5,
                "transport": "TCP",
                "codec": "H264",
                "reconnects": 0,
            }):
                body = commissioning_snapshot(db, camera)

        self.assertEqual(body["capture"]["capture_quality"]["quality"], "TOO_SMALL")
        self.assertEqual(body["detect_stream"]["recommended_source"], "MAIN")
        codes = {row["code"] for row in body["recommendations"]}
        self.assertIn("PLATE_TOO_SMALL", codes)
        self.assertEqual(body["recognition"]["strategy"], "CONTINUOUS_DETECT")

    def test_hvx_hybrid_is_event_verification_not_continuous_worker(self):
        with self.Session() as db:
            camera = self._camera(db, adapter="hvx", mode="HYBRID")
            self._capture(db, camera, width=145)
            with patch("app.services.recognition_commissioning._worker_row", return_value={
                "owns_continuous_software_reads": False, "worker_ok": True
            }), patch("app.services.recognition_commissioning._media_row", return_value={
                "connection_state": "STREAMING",
                "live_fps": 12,
                "live_frame_age_ms": 30,
                "detect_frame_age_ms": None,
                "ai_processed_fps": 0,
                "transport": "TCP",
                "codec": "H264",
                "reconnects": 0,
            }):
                body = commissioning_snapshot(db, camera)

        self.assertTrue(body["recognition"]["native_capable"])
        self.assertEqual(body["recognition"]["mode"], "HYBRID")
        self.assertEqual(body["recognition"]["strategy"], "EVENT_VERIFY")
        self.assertEqual(body["capture"]["capture_quality"]["quality"], "GOOD")

    def test_diagnostic_crop_read_never_writes_a_capture_or_session(self):
        with self.Session() as db:
            camera = self._camera(db)
            self._capture(db, camera, width=140)
            before = len(list(db.scalars(select(VehicleCapture)).all()))
            fake = {
                "ok": True,
                "backend": "fastalpr",
                "pipeline": "crop_ocr",
                "best": {"plate": "T285DQP", "confidence": .96},
                "plates": [{"plate": "T285DQP", "confidence": .96}],
            }
            fake_settings = SimpleNamespace(media_dir=self.media)
            with patch("app.services.recognition_commissioning.settings", fake_settings), \
                 patch("app.services.alpr.recognize_plate_crop_bytes", return_value=fake):
                result = diagnostic_read(db, camera)
            after = len(list(db.scalars(select(VehicleCapture)).all()))

        self.assertEqual(result["evidence_source"], "plate_crop")
        self.assertEqual(result["best"]["plate"], "T285DQP")
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
