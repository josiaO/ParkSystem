from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import AsyncMock, PropertyMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api_main import app, ensure_roles
from app.config import Settings
from app.core.fusion import resolve_readings
from app.core.plate import (
    assess_plate, correct_ocr_confusions, is_empty_scene_ocr, normalize_plate, plate_similarity,
)
from app.db import Base, get_db
from app.models import Role, User, UserRole
from app.security import hash_password
from app.services.camera_lpr import (
    DVCAM_QY, QY_SDK_PORT, choose_overlay_box, native_confidence, native_from_sdk_capture, csf_from_contrast,
)
from app.services.presence import PresenceWatch
from app.services.alpr import (
    DETECTOR_ONNX, OCR_CONFIG, OCR_ONNX, clean_ocr_text, ensure_alpr_model_cache, recognize_bytes, status as alpr_status,
)


class PlateFusionTests(unittest.TestCase):
    def test_tanzania_plates_from_camera_logs(self):
        self.assertEqual(normalize_plate("T 285 DQP"), "T285DQP")
        self.assertEqual(normalize_plate("T 349 DLG"), "T349DLG")
        self.assertEqual(csf_from_contrast(918), 0.918)
        self.assertEqual(native_confidence(91), 0.91)
        self.assertEqual(native_confidence(0.91), 0.91)
        hit = native_from_sdk_capture({
            "plate": "T 285 DQP", "score": 91, "plate_box": [807, 303, 866, 354],
            "image_width": 1280, "image_height": 720,
        })
        self.assertEqual(hit["plate"], "T285DQP")
        self.assertAlmostEqual(hit["confidence"], 0.91)
        self.assertEqual(hit["bbox"]["x1"], 807)
        self.assertEqual(hit["image_width"], 1280)

    def test_tanzania_shape_does_not_invent_65_percent_confidence(self):
        from app.services.alpr import _apply_country_profile, _tz_plate_score
        from app.config import settings

        plate, score = _apply_country_profile("T285DQP", 0.30)
        self.assertEqual(plate, "T285DQP")
        self.assertAlmostEqual(score, 0.30)
        self.assertAlmostEqual(_tz_plate_score("T285DQP", 0.30), 0.30)
        self.assertNotAlmostEqual(score, 0.65)
        with patch.object(settings, "alpr_country", "tanzania"), patch.object(settings, "plate_validation", "TZ"):
            plate, score = _apply_country_profile("T285DQP", 0.30)
        self.assertEqual(plate, "T285DQP")
        self.assertAlmostEqual(score, 0.30, places=2)

    def test_overlay_prefers_native_uslpbox(self):
        native = native_from_sdk_capture({"plate": "T285DQP", "score": 90, "plate_box": [10, 20, 80, 50], "image_width": 640, "image_height": 480})
        local = {"plate": "T285DQP", "bbox": {"x1": 1, "y1": 2, "x2": 3, "y2": 4}, "source": "fastalpr"}
        box = choose_overlay_box(native, local)
        self.assertEqual(box["x1"], 10)
        self.assertEqual(box["label"], "T285DQP")
        self.assertEqual(box["image_width"], 640)

    def test_empty_scene_zc_is_not_a_plate(self):
        from types import SimpleNamespace
        from app.services.alpr import accept_ocr_plate, plate_box_ok

        self.assertTrue(is_empty_scene_ocr("ZC"))
        self.assertTrue(is_empty_scene_ocr("ZC1234"))
        self.assertFalse(is_empty_scene_ocr("T277ECR"))
        self.assertFalse(is_empty_scene_ocr("T793ECA"))
        self.assertFalse(accept_ocr_plate("ZC1234", 0.91))
        self.assertFalse(accept_ocr_plate("ZC", 0.99))
        self.assertTrue(accept_ocr_plate("T277ECR", 0.88))
        tall = SimpleNamespace(x1=10, y1=10, x2=40, y2=200)
        plate = SimpleNamespace(x1=100, y1=200, x2=260, y2=245)
        self.assertFalse(plate_box_ok(tall, 640, 480))
        self.assertTrue(plate_box_ok(plate, 640, 480))

    def test_empty_lane_does_not_run_second_clahe_detect(self):
        import numpy as np
        from types import SimpleNamespace
        from app.services import alpr as alpr_mod

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        seen = {"detect": 0, "clahe": 0}

        class FakeDet:
            def predict(self, img):
                seen["detect"] += 1
                return []

        engine = SimpleNamespace(detector=FakeDet(), ocr=SimpleNamespace(predict=lambda crop: None))
        with patch.object(alpr_mod, "fastalpr_installed", return_value=True), \
             patch.object(alpr_mod, "_load_engine", return_value=engine), \
             patch.object(alpr_mod, "_boost_contrast", side_effect=lambda img: seen.__setitem__("clahe", seen["clahe"] + 1) or img):
            hits, meta = alpr_mod.recognize_bgr(frame, crop_source="")
        self.assertEqual(hits, [])
        self.assertEqual(seen["detect"], 1)
        self.assertEqual(seen["clahe"], 0)
        self.assertTrue(meta["ok"])

    def test_hits_from_detections_drop_zc_and_non_plate_boxes(self):
        import numpy as np
        from types import SimpleNamespace
        from app.services.alpr import _hits_from_detections

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        ghost = SimpleNamespace(bounding_box=SimpleNamespace(x1=10, y1=10, x2=40, y2=200), confidence=0.9)
        zc = SimpleNamespace(bounding_box=SimpleNamespace(x1=100, y1=200, x2=260, y2=245), confidence=0.9)
        real = SimpleNamespace(bounding_box=SimpleNamespace(x1=300, y1=220, x2=460, y2=265), confidence=0.9)
        texts = ["ZC1234", "T277ECR"]

        class FakeOcr:
            def predict(self, crop):
                return SimpleNamespace(text=texts.pop(0), confidence=0.88)

        engine = SimpleNamespace(ocr=FakeOcr())
        hits = _hits_from_detections(engine, frame, [ghost, zc, real])
        self.assertEqual([hit.plate_normalized for hit in hits], ["T277ECR"])

    def test_crop_then_ocr_uses_padded_plate_not_full_frame(self):
        import numpy as np
        from types import SimpleNamespace
        from app.services.alpr import _predict_crop_then_ocr

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        bbox = SimpleNamespace(x1=100, y1=200, x2=220, y2=240)
        detection = SimpleNamespace(bounding_box=bbox)
        ocr = SimpleNamespace(text="T285DQP____", confidence=0.91)
        seen = {}

        class FakeOcr:
            def predict(self, crop):
                seen["crop_shape"] = tuple(crop.shape[:2])
                seen["crop_w"] = crop.shape[1]
                return ocr

        class FakeDet:
            def predict(self, img):
                seen["full_shape"] = tuple(img.shape[:2])
                return [detection]

        engine = SimpleNamespace(detector=FakeDet(), ocr=FakeOcr())
        hits = _predict_crop_then_ocr(engine, frame)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].plate_normalized, "T285DQP")
        self.assertEqual(seen["full_shape"], (480, 640))
        # OCR must see a plate crop (padded+upscaled), not the full 640-wide frame.
        self.assertLess(seen["crop_w"], 640)
        self.assertGreaterEqual(seen["crop_w"], 300)

    def test_native_plate_crop_can_skip_detector(self):
        from io import BytesIO
        from types import SimpleNamespace
        from PIL import Image
        from app.services import alpr as alpr_mod

        buf = BytesIO()
        Image.new("RGB", (180, 55), (220, 220, 220)).save(buf, format="JPEG")
        seen = {}

        class FakeOcr:
            def predict(self, crop):
                seen["shape"] = tuple(crop.shape[:2])
                return SimpleNamespace(text="T285DQP____", confidence=[0.95] * 7)

        fake_engine = SimpleNamespace(ocr=FakeOcr())
        with patch.object(alpr_mod, "fastalpr_installed", return_value=True), \
             patch.object(alpr_mod, "_load_engine", return_value=fake_engine):
            result = alpr_mod.recognize_plate_crop_bytes(buf.getvalue(), camera_label="native")

        self.assertTrue(result["ok"])
        self.assertEqual(result["pipeline"], "crop_ocr")
        self.assertEqual(result["best"]["plate"], "T285DQP")
        self.assertGreaterEqual(seen["shape"][1], 300)

    def test_clean_ocr_strips_fast_plate_padding(self):
        self.assertEqual(clean_ocr_text("T285DQP____"), "T285DQP")
        self.assertEqual(normalize_plate(clean_ocr_text("T_285_DQP")), "T285DQP")
        self.assertEqual(clean_ocr_text("T 349 DLG"), "T349DLG")

    def test_decode_alpr_image_does_not_upscale_entire_small_frame(self):
        from io import BytesIO
        from PIL import Image
        from app.services.alpr import decode_alpr_image

        img = Image.new("RGB", (320, 240), (40, 40, 40))
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85)
        bgr = decode_alpr_image(buf.getvalue())
        # Detection handles its own input resize. SmartPark only enlarges the
        # detected plate crop, avoiding wasted work on the entire vehicle frame.
        self.assertEqual(tuple(bgr.shape[:2]), (240, 320))
        self.assertEqual(bgr.shape[2], 3)

    def test_normalize_strips_separators(self):
        self.assertEqual(normalize_plate("t 123 abc"), "T123ABC")
        self.assertEqual(normalize_plate(None), "")

    def test_similarity(self):
        self.assertEqual(plate_similarity("T123ABC", "T123ABC"), 1.0)
        self.assertGreater(plate_similarity("T123ABC", "T123ABD"), 0.7)
        self.assertEqual(plate_similarity("", "T123"), 0.0)

    def test_fuse_agrees(self):
        decision = resolve_readings(native_plate="T123ABC", native_confidence=0.8, local_plate="t-123-abc", local_confidence=0.9)
        self.assertEqual(decision.resolved_plate, "T123ABC")
        self.assertEqual(decision.method, "AGREED")
        self.assertFalse(decision.needs_review)

    def test_fuse_prefers_strong_local(self):
        decision = resolve_readings(native_plate="T123ABC", native_confidence=0.5, local_plate="T123ABD", local_confidence=0.92)
        self.assertEqual(decision.resolved_plate, "T123ABD")
        self.assertEqual(decision.method, "LOCAL_SELECTED")
        self.assertTrue(decision.needs_review)

    def test_fuse_local_only_mode(self):
        decision = resolve_readings(native_plate="NATIVE1", native_confidence=0.99, local_plate="LOCAL1", local_confidence=0.4, mode="LOCAL")
        self.assertEqual(decision.resolved_plate, "LOCAL1")
        self.assertTrue(decision.needs_review)

    def test_low_confidence_single_frame_is_held(self):
        decision = resolve_readings(native_plate="", native_confidence=0, local_plate="T285DQP", local_confidence=0.41)
        self.assertEqual(decision.resolved_plate, "T285DQP")
        self.assertTrue(decision.needs_review)
        self.assertIn("single-frame", decision.reason)

    def test_disagreement_keeps_both_plates(self):
        decision = resolve_readings(native_plate="T285DQP", native_confidence=0.91, local_plate="T285D0P", local_confidence=0.91)
        self.assertTrue(decision.disagreed)
        self.assertEqual(decision.native_plate, "T285DQP")
        self.assertEqual(decision.local_plate, "T285D0P")
        self.assertTrue(decision.needs_review)

    def test_hard_plates_and_garbage(self):
        self.assertEqual(normalize_plate(""), "")
        self.assertEqual(normalize_plate("!!!"), "")
        self.assertFalse(assess_plate("STOP")["likely"])
        self.assertFalse(assess_plate("AB")["likely"])
        self.assertFalse(assess_plate("")["likely"])
        self.assertTrue(assess_plate("T285DQP")["likely"])
        self.assertTrue(assess_plate("123456")["likely"])
        self.assertTrue(assess_plate("ABCDE")["likely"])
        self.assertTrue(assess_plate("123", policy="AE")["likely"])
        self.assertFalse(assess_plate("ZC")["likely"])
        self.assertFalse(assess_plate("ZC123")["likely"])
        self.assertFalse(assess_plate("ZCABC")["likely"])
        self.assertEqual(assess_plate("ZC1234")["likelihood"], "EMPTY_SCENE_OCR")
        self.assertTrue(assess_plate("T277ECR")["likely"])
        fixed = correct_ocr_confusions("T28SDQP", policy="TZ")
        self.assertEqual(fixed["plate"], "T285DQP")
        self.assertTrue(fixed["corrected"])
        neutral = correct_ocr_confusions("T28SDQP")
        self.assertEqual(neutral["plate"], "T28SDQP")
        self.assertFalse(neutral["corrected"])

    def test_local_consensus_skips_single_frame_hold(self):
        decision = resolve_readings(
            native_plate="", native_confidence=0, local_plate="T285DQP", local_confidence=0.8, local_consensus=True,
        )
        self.assertEqual(decision.resolved_plate, "T285DQP")
        self.assertFalse(decision.needs_review)

    def test_recognize_bytes_never_invents_plates(self):
        with patch("app.services.alpr.fastalpr_installed", return_value=False):
            result = recognize_bytes(b"\xff\xd8fake", camera_label="192.168.1.49")
        self.assertFalse(result["ok"])
        self.assertEqual(result["backend"], "none")
        self.assertEqual(result["plates"], [])
        self.assertIn("not substituting simulated plates", result["detail"])

    def test_windows_kit_lists_fastalpr(self):
        text = (ROOT / "packaging" / "windows" / "requirements-windows.txt").read_text()
        self.assertIn("fast-alpr", text)
        self.assertIn("pillow", text)
        self.assertIn("onnxruntime", text)
        kit = (ROOT / "packaging" / "make_windows_kit.sh").read_text()
        self.assertIn("yolo-v9-t-384-license-plates-end2end.onnx", kit)
        self.assertIn("models/fastalpr", kit)

    def test_ensure_alpr_model_cache_copies_bundled_files(self):
        import tempfile
        from app.services import alpr as alpr_mod
        src = Path(tempfile.mkdtemp())
        (src / "detector").mkdir()
        (src / "ocr").mkdir()
        (src / "detector" / DETECTOR_ONNX).write_bytes(b"det")
        (src / "ocr" / OCR_ONNX).write_bytes(b"ocr")
        (src / "ocr" / OCR_CONFIG).write_text("ok")
        fake_home = Path(tempfile.mkdtemp())
        with patch.object(alpr_mod, "bundled_alpr_dir", return_value=src):
            with patch.object(Path, "home", return_value=fake_home):
                info = ensure_alpr_model_cache()
        self.assertTrue(info["detector"])
        self.assertTrue(info["ocr"])
        self.assertTrue(Path(info["detector_path"]).is_file())
        self.assertEqual(Path(info["detector_path"]).read_bytes(), b"det")


class AlprApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

        def override_get_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        with self.Session() as db:
            ensure_roles(db)
            admin_role = db.scalar(select(Role).where(Role.name == "Admin"))
            user = User(username="admin", full_name="Test Admin", password_hash=hash_password("correct-horse"))
            db.add(user)
            db.flush()
            db.add(UserRole(user_id=user.id, role_id=admin_role.id))
            db.commit()
        self.client = TestClient(app)
        token = self.client.post("/auth/login", json={"username": "admin", "password": "correct-horse"}).json()["token"]
        self.headers = {"Authorization": f"Bearer {token}"}
        self.media = Path(tempfile.mkdtemp(prefix="smartpark-alpr-"))
        self._media_patch = patch.object(Settings, "media_dir", new_callable=PropertyMock, return_value=self.media)
        self._media_patch.start()

    def tearDown(self):
        self._media_patch.stop()
        shutil.rmtree(self.media, ignore_errors=True)
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_alpr_status(self):
        with patch("app.api_main.alpr_status", return_value=alpr_status()):
            res = self.client.get("/alpr/status", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn(body["backend"], {"fastalpr", "none"})
        self.assertIn("installed", body)
        self.assertIn(body["country"], {None, ""})
        self.assertEqual(body["camera"]["camera_type"], DVCAM_QY)
        self.assertEqual(body["camera"]["sdk_port"], QY_SDK_PORT)
        self.assertEqual(body["camera"]["picture_port"], 40000)
        self.assertIn("OcxConfig.ocx", body["camera"]["official_config"]["ui"])
        self.assertEqual(body["camera"]["local_engine"]["name"], "fastalpr")
        self.assertTrue(body["camera"]["local_engine"]["vendor_independent"])
        self.assertFalse(body["camera"]["parking_requires_ocxconfig"])
        self.assertNotIn("parkwatch", body)

    def test_coil_rising_edge_debounces(self):
        watch = PresenceWatch(debounce_seconds=0.0, hold_seconds=4.0)
        first = watch.observe(9, True, source="api")
        self.assertTrue(first.rising)
        self.assertTrue(first.occupied)
        held = watch.observe(9, True, source="api")
        self.assertFalse(held.rising)
        left = watch.observe(9, False, source="api")
        self.assertTrue(left.falling)
        again = watch.observe(9, True, source="api")
        self.assertTrue(again.rising)

    def test_gpio_scan_learns_the_pin_that_changes(self):
        watch = PresenceWatch(debounce_seconds=0.0, hold_seconds=4.0)
        watch.observe(4, False, source="gpio", index=1, value=0)
        watch.observe(4, False, source="gpio", index=2, value=0)
        idle = watch.observe(4, False, source="gpio", index=3, value=0)
        self.assertFalse(idle.rising)
        self.assertIsNone(watch.learned_index(4))
        hit = watch.observe(4, True, source="gpio", index=3, value=1)
        self.assertTrue(hit.rising)
        self.assertEqual(watch.learned_index(4), 3)
        self.assertTrue(watch.occupied(4))

    def test_fuse_endpoint(self):
        res = self.client.post("/alpr/fuse", headers=self.headers, json={
            "native_plate": "T123ABC",
            "native_confidence": 0.81,
            "local_plate": "T123ABC",
            "local_confidence": 0.88,
        })
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["method"], "AGREED")
        self.assertEqual(res.json()["resolved_plate"], "T123ABC")

    def test_camera_alpr_uses_live_frame(self):
        created = self.client.post("/cameras", headers=self.headers, json={
            "name": "ALPR Cam", "ip_address": "192.168.1.49",
        })
        cam_id = created.json()["id"]
        grabbed = {"ok": True, "jpeg": b"\xff\xd8fake", "url_redacted": "rtsp://192.168.1.49/av0_0"}
        recognized = {
            "ok": True, "backend": "fastalpr", "plates": [{"plate": "T123ABC", "confidence": 0.91}],
            "count": 1, "best": {"plate": "T123ABC", "confidence": 0.91, "bbox": {"x1": 10, "y1": 20, "x2": 120, "y2": 50}}, "detail": "1 plate(s)",
        }
        with patch("app.api_main.live_snapshot", new=AsyncMock(return_value=grabbed)):
            with patch("app.api_main.recognize_frame", return_value=recognized):
                with patch("app.api_main._native_capture_for_camera", new=AsyncMock(return_value={
                    "plate": "T123ABC", "confidence": 0.80, "source": "qy_Net_RegImageRecvEx",
                })):
                    res = self.client.post(f"/cameras/{cam_id}/alpr/recognize", headers=self.headers)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["best"]["plate"], "T123ABC")
        self.assertEqual(res.json()["camera_id"], cam_id)
        self.assertEqual(res.json()["fusion"]["method"], "LOCAL_SELECTED")
        self.assertEqual(res.json()["fusion"]["resolved_plate"], "T123ABC")
        self.assertEqual(res.json()["last_car"]["plate"], "T123ABC")
        self.assertTrue(res.json()["last_car"]["snapshot_url"])

    def test_camera_alpr_no_frame(self):
        created = self.client.post("/cameras", headers=self.headers, json={
            "name": "Dead Cam", "ip_address": "192.168.1.50",
        })
        cam_id = created.json()["id"]
        with patch("app.api_main.live_snapshot", new=AsyncMock(return_value={"ok": False, "error": "no live JPEG"})):
            res = self.client.post(f"/cameras/{cam_id}/alpr/recognize", headers=self.headers)
        self.assertEqual(res.status_code, 409)

    def test_upload_refuses_simulation(self):
        with patch("app.api_main.recognize_frame", return_value={
            "ok": False, "backend": "none", "plates": [],
            "detail": "FastALPR is not installed — not substituting simulated plates",
        }):
            res = self.client.post(
                "/alpr/recognize",
                headers=self.headers,
                files={"file": ("frame.jpg", b"\xff\xd8fake", "image/jpeg")},
            )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["plates"], [])
        self.assertEqual(res.json()["backend"], "none")


if __name__ == "__main__":
    unittest.main()
