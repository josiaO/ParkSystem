"""FastALPR plate engine: ParkWatch-style read, swap, and retrain pack."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import Settings
from app.infrastructure.recognition.engines import (
    active_engine_id,
    list_engines,
    recognize_frame,
    register_engine,
)
from app.infrastructure.recognition.engines import registry as engine_registry
from app.infrastructure.recognition.engines.training import apply_model_pack, record_correction, training_status
from app.services.ocr_policy import LOCAL_ONLY, alpr_mode, should_run_local, software_ocr_enabled


class PlateEngineTests(unittest.TestCase):
    def test_default_mode_reads_in_software(self):
        self.assertEqual(Settings().alpr_mode, "FASTALPR_ONLY")
        self.assertEqual(Settings().alpr_engine, "fastalpr")
        self.assertEqual(alpr_mode(), LOCAL_ONLY)
        self.assertTrue(should_run_local(native_plate="T123ABC", native_confidence=0.99, presence=True))
        self.assertFalse(should_run_local(native_plate="T123ABC", native_confidence=0.99, presence=False))
        self.assertTrue(should_run_local(native_plate="T123ABC", native_confidence=0.99, native_plates=False))

    def test_hybrid_mode_rereads_vehicle_event_even_with_strong_native_plate(self):
        from types import SimpleNamespace
        from app.services.ocr_policy import should_run_local

        camera = SimpleNamespace(recognition_mode="HYBRID", adapter_id="hvx")
        self.assertTrue(should_run_local(
            native_plate="T123ABC",
            native_confidence=0.99,
            native_plates=True,
            presence=True,
            camera=camera,
        ))

    def test_parkwatch_in_alpr_uses_fastalpr_not_camera_text(self):
        from types import SimpleNamespace

        hvx = SimpleNamespace(recognition_mode="FASTALPR_ONLY", adapter_id="hvx")
        hybrid = SimpleNamespace(recognition_mode="HYBRID", adapter_id="hvx")
        native_only = SimpleNamespace(recognition_mode="NATIVE_ONLY", adapter_id="hvx")
        self.assertTrue(software_ocr_enabled(hvx))
        self.assertTrue(software_ocr_enabled(hybrid))
        self.assertFalse(software_ocr_enabled(native_only))
        self.assertTrue(should_run_local(
            native_plate="T123ABC", native_confidence=0.99, native_plates=True, presence=True, camera=hvx,
        ))
        self.assertFalse(should_run_local(
            native_plate="T123ABC", native_confidence=0.99, native_plates=True, presence=False, camera=hvx,
        ))

    def test_hvx_fastalpr_gets_detect_jpeg_not_sdk_jpeg_poll(self):
        from types import SimpleNamespace
        from app.api_main import _live_spec

        camera = SimpleNamespace(
            id=1,
            ip_address="192.168.1.144",
            username="admin",
            password_secret="admin",
            rtsp_url="",
            sdk_handle=1,
            ffmpeg_profile="",
            rtsp_transport="",
            adapter_id="hvx",
            recognition_mode="FASTALPR_ONLY",
            stream_profiles={},
        )
        spec = _live_spec(camera)
        self.assertFalse(spec.need_detect)
        native = SimpleNamespace(**{**camera.__dict__, "recognition_mode": "NATIVE_ONLY"})
        self.assertFalse(_live_spec(native).need_detect)
        generic = SimpleNamespace(**{**camera.__dict__, "adapter_id": "rtsp", "sdk_handle": None})
        self.assertTrue(_live_spec(generic).need_detect)
        text = Path(__file__).resolve().parents[1].joinpath("app/api_main.py").read_text(encoding="utf-8")
        watch = text.split("async def _maybe_watch_local_alpr")[1].split("async def _outbox_loop")[0]
        self.assertIn("software_ocr_enabled(camera)", watch)
        self.assertNotIn("live_jpeg(handle)", watch)
        self.assertIn("adapter_has_native_plates(camera)", watch)
        self.assertIn("acquire_detect(_live_spec(camera, need_detect=True))", watch)

    def test_fastalpr_is_the_known_engine(self):
        self.assertEqual(active_engine_id(), "fastalpr")
        rows = {row["id"]: row for row in list_engines()}
        self.assertIn("fastalpr", rows)
        self.assertTrue(rows["fastalpr"]["active"])
        self.assertTrue(rows["fastalpr"]["retrainable"])
        self.assertTrue(rows["fastalpr"]["replaceable"])

    def test_recognize_frame_uses_the_active_engine(self):
        class Other:
            id = "other"
            display_name = "Other"
            version = "0"

            def describe(self):
                return {"display_name": "Other", "version": "0", "installed": True, "retrainable": False, "replaceable": True}

            def recognize_bytes(self, jpeg, *, camera_label="frame"):
                return {"ok": True, "plates": [], "best": None, "engine_id": self.id, "label": camera_label, "size": len(jpeg)}

        register_engine(Other())
        with patch("app.infrastructure.recognition.engines.registry.settings") as cfg:
            cfg.alpr_engine = "other"
            result = recognize_frame(b"jpeg-bytes", camera_label="entry")
        self.assertEqual(result["engine_id"], "other")
        self.assertEqual(result["label"], "entry")
        self.assertEqual(result["size"], 10)
        engine_registry._ENGINES.pop("other", None)

    def test_correction_log_and_model_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "media"
            pack = root / "pack"
            installed = root / "models"
            pack.mkdir()
            (pack / "detector.onnx").write_bytes(b"det")
            (pack / "ocr.onnx").write_bytes(b"ocr")
            (pack / "ocr.yaml").write_text("alphabet: ABC", encoding="utf-8")
            (pack / "manifest.json").write_text(json.dumps({
                "engine_id": "fastalpr",
                "country": "Tanzania",
                "detector_onnx": "detector.onnx",
                "ocr_onnx": "ocr.onnx",
                "ocr_config": "ocr.yaml",
            }), encoding="utf-8")
            with patch("app.infrastructure.recognition.engines.training.settings") as cfg:
                cfg.media_dir = media
                cfg.alpr_country = "Tanzania"
                media.mkdir()
                row = record_correction(image_ref="crops/a.jpg", predicted="T000AAA", corrected="T123ABC")
                self.assertEqual(row["corrected"], "T123ABC")
                self.assertEqual(training_status()["corrections"], 1)
            with patch.dict(os.environ, {"SMARTPARK_ALPR_MODEL_DIR": str(installed)}):
                with patch("app.services.alpr.unload_engine") as unload:
                    applied = apply_model_pack(str(pack))
            self.assertTrue(applied["ok"])
            self.assertTrue((installed / "detector.onnx").is_file())
            self.assertTrue((installed / "manifest.json").is_file())
            unload.assert_called_once()
            with self.assertRaises(FileNotFoundError):
                apply_model_pack(str(root / "missing"))
