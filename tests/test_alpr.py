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
from app.core.plate import normalize_plate, plate_similarity
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

    def test_overlay_prefers_native_uslpbox(self):
        native = native_from_sdk_capture({"plate": "T285DQP", "score": 90, "plate_box": [10, 20, 80, 50], "image_width": 640, "image_height": 480})
        local = {"plate": "T285DQP", "bbox": {"x1": 1, "y1": 2, "x2": 3, "y2": 4}, "source": "fastalpr"}
        box = choose_overlay_box(native, local)
        self.assertEqual(box["x1"], 10)
        self.assertEqual(box["label"], "T285DQP")
        self.assertEqual(box["image_width"], 640)

    def test_clean_ocr_strips_fast_plate_padding(self):
        self.assertEqual(clean_ocr_text("T285DQP____"), "T285DQP")
        self.assertEqual(normalize_plate(clean_ocr_text("T_285_DQP")), "T285DQP")
        self.assertEqual(clean_ocr_text("T 349 DLG"), "T349DLG")

    def test_decode_alpr_image_scales_small_photos(self):
        from io import BytesIO
        from PIL import Image
        from app.services.alpr import decode_alpr_image

        img = Image.new("RGB", (320, 240), (40, 40, 40))
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85)
        bgr = decode_alpr_image(buf.getvalue())
        self.assertGreaterEqual(min(bgr.shape[0], bgr.shape[1]), 720)
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

    def test_fuse_local_only_mode(self):
        decision = resolve_readings(native_plate="NATIVE1", native_confidence=0.99, local_plate="LOCAL1", local_confidence=0.4, mode="LOCAL")
        self.assertEqual(decision.resolved_plate, "LOCAL1")

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
        self.assertEqual(body["country"], "Tanzania")
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
            "count": 1, "best": {"plate": "T123ABC", "confidence": 0.91}, "detail": "1 plate(s)",
        }
        with patch("app.api_main.live_snapshot", new=AsyncMock(return_value=grabbed)):
            with patch("app.api_main.recognize_bytes", return_value=recognized):
                with patch("app.api_main._native_capture_for_camera", new=AsyncMock(return_value={
                    "plate": "T123ABC", "confidence": 0.80, "source": "qy_Net_RegImageRecvEx",
                })):
                    res = self.client.post(f"/cameras/{cam_id}/alpr/recognize", headers=self.headers)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["best"]["plate"], "T123ABC")
        self.assertEqual(res.json()["camera_id"], cam_id)
        self.assertEqual(res.json()["fusion"]["method"], "AGREED")
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
        with patch("app.api_main.recognize_bytes", return_value={
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
