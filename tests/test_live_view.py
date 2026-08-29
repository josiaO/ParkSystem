from __future__ import annotations

import unittest
from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api_main import app, ensure_roles
from app.db import Base, get_db, set_session_factory
from app.models import Role, User, UserRole
from app.security import hash_password
from app.services.alpr import bbox_dict
from app.services.preview import media_path, remember_frame, stop_live_pumps, take_latest_jpeg


JPEG = b"\xff\xd8\xff\xd9"


class _Box:
    x1, y1, x2, y2 = 10, 20, 80, 50


class LiveViewTests(unittest.TestCase):
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
        set_session_factory(self.Session)
        self._pump_patch = patch("app.api_main.start_live_pump")
        self._pump_patch.start()
        self._preview_pump = patch("app.services.preview.start_live_pump")
        self._preview_pump.start()
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
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"}

    def tearDown(self):
        self._pump_patch.stop()
        self._preview_pump.stop()
        stop_live_pumps()
        set_session_factory(None)
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def _camera(self):
        return self.client.post("/cameras", headers=self.headers, json={
            "name": "Live Cam", "ip_address": "192.168.1.49",
        }).json()

    def test_take_latest_jpeg_drops_stacked_frames(self):
        first = b"\xff\xd8" + b"AAAA" + b"\xff\xd9"
        second = b"\xff\xd8" + b"BBBB" + b"\xff\xd9"
        latest, rest = take_latest_jpeg(b"xx" + first + second + b"\xff")
        self.assertEqual(latest, second)
        self.assertEqual(rest, b"\xff")
        none, leftover = take_latest_jpeg(b"\xff\xd8incomplete")
        self.assertEqual(none, b"")
        self.assertEqual(leftover, b"\xff\xd8incomplete")

    def test_bbox_dict(self):
        self.assertEqual(bbox_dict(_Box()), {"x1": 10, "y1": 20, "x2": 80, "y2": 50})
        self.assertIsNone(bbox_dict(None))

    def test_media_path_rejects_traversal(self):
        self.assertIsNone(media_path("crops", "../secrets.txt"))
        self.assertIsNone(media_path("not-a-kind", "a.jpg"))

    def test_snapshot_requires_auth(self):
        cam = self._camera()
        self.assertEqual(self.client.get(f"/cameras/{cam['id']}/snapshot.jpg").status_code, 401)

    def test_snapshot_jpeg_and_query_token(self):
        cam = self._camera()
        grabbed = {"ok": True, "jpeg": JPEG, "url": "rtsp://192.168.1.49/av0_0", "url_redacted": "rtsp://192.168.1.49/av0_0"}
        with patch("app.api_main.snapshot_for_camera", new=AsyncMock(return_value=grabbed)):
            res = self.client.get(f"/cameras/{cam['id']}/snapshot.jpg", headers=self.headers)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.headers["content-type"], "image/jpeg")
        self.assertEqual(res.content, JPEG)
        with patch("app.api_main.snapshot_for_camera", new=AsyncMock(return_value=grabbed)):
            via_query = self.client.get(f"/cameras/{cam['id']}/snapshot.jpg?access_token={self.token}")
        self.assertEqual(via_query.status_code, 200)
        listed = self.client.get(f"/cameras/{cam['id']}", headers=self.headers).json()
        self.assertEqual(listed["status"], "VIDEO_CONNECTED")

    def test_snapshot_uses_cached_jpeg_without_extra_grab(self):
        cam = self._camera()
        remember_frame(cam["id"], JPEG)
        with patch("app.api_main.snapshot_for_camera", new=AsyncMock(side_effect=AssertionError("should not grab"))) as grab:
            res = self.client.get(f"/cameras/{cam['id']}/snapshot.jpg", headers=self.headers)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.content, JPEG)
        self.assertIn("no-store", res.headers.get("cache-control", "").lower())
        grab.assert_not_called()

    def test_live_watch_and_unwatch(self):
        cam = self._camera()
        watch = self.client.post(f"/cameras/{cam['id']}/live/watch", headers=self.headers)
        self.assertEqual(watch.status_code, 200, watch.text)
        self.assertGreaterEqual(watch.json()["viewers"], 1)
        unwatch = self.client.post(f"/cameras/{cam['id']}/live/unwatch", headers=self.headers)
        self.assertEqual(unwatch.status_code, 200, unwatch.text)

    def test_preview_json(self):
        cam = self._camera()
        grabbed = {"ok": True, "jpeg": JPEG, "url": "rtsp://x", "url_redacted": "rtsp://x"}
        with patch("app.api_main.snapshot_for_camera", new=AsyncMock(return_value=grabbed)):
            res = self.client.get(f"/cameras/{cam['id']}/preview", headers=self.headers)
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertTrue(body["live"])
        self.assertIn("/snapshot.jpg", body["snapshot_url"])
        self.assertIn("/live.mjpeg", body["live_url"])
        self.assertIn("live_source", body)
        self.assertIn("live_fps", body)

    def test_live_mjpeg(self):
        cam = self._camera()
        remember_frame(cam["id"], JPEG)

        async def fake_parts(_id):
            yield b"--smartparkframe\r\nContent-Type: image/jpeg\r\n\r\n" + JPEG + b"\r\n"

        with patch("app.api_main.mjpeg_from_cache", new=fake_parts):
            res = self.client.get(f"/cameras/{cam['id']}/live.mjpeg", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertIn("multipart/x-mixed-replace", res.headers["content-type"])
        self.assertIn("no-cache", res.headers.get("cache-control", "").lower())
        self.assertIn(JPEG, res.content)

    def test_media_missing(self):
        res = self.client.get("/media/crops/missing.jpg", headers=self.headers)
        self.assertEqual(res.status_code, 404)

    def test_generic_ip_camera_connects_video_not_sdk(self):
        cam = self.client.post("/cameras", headers=self.headers, json={
            "name": "Dahua Entry", "ip_address": "10.0.0.50", "adapter_id": "dahua",
        }).json()
        self.assertEqual(cam["adapter_id"], "dahua")
        self.assertFalse(cam["native_plates"])
        self.assertEqual(cam["plate_engine"], "fastalpr")
        jpeg = b"\xff\xd8\xff\xd9"
        with patch(
            "app.infrastructure.hardware.cameras.rtsp.grab_http_snapshot",
            new=AsyncMock(return_value={
                "ok": True,
                "jpeg": jpeg,
                "url": "http://10.0.0.50/cgi-bin/snapshot.cgi",
                "url_redacted": "http://10.0.0.50/cgi-bin/snapshot.cgi",
                "source": "http",
            }),
        ):
            res = self.client.post(f"/cameras/{cam['id']}/sdk/connect", headers=self.headers, json={})
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["status"], "VIDEO_CONNECTED")
        self.assertIsNone(body["sdk_handle"])
        self.assertFalse(body["native_plates"])
        self.assertEqual(body["plate_engine"], "fastalpr")
        self.assertTrue(body["sdk_result"]["connected"])
        self.assertFalse(body["sdk_result"].get("sdk_login"))
        self.assertNotIn("jpeg", body["sdk_result"])

    def test_onvif_connect_is_not_sdk_connected(self):
        cam = self.client.post("/cameras", headers=self.headers, json={
            "name": "ONVIF Stub", "ip_address": "10.0.0.51", "adapter_id": "onvif",
        }).json()
        res = self.client.post(f"/cameras/{cam['id']}/sdk/connect", headers=self.headers, json={})
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertNotEqual(body["status"], "SDK_CONNECTED")
        self.assertIsNone(body["sdk_handle"])
        self.assertFalse((body.get("sdk_result") or {}).get("connected"))

    def test_import_discovered_ip_cameras_connects_fastalpr_path(self):
        jpeg = b"\xff\xd8\xff\xd9"
        with patch(
            "app.infrastructure.hardware.cameras.rtsp.grab_http_snapshot",
            new=AsyncMock(return_value={
                "ok": True,
                "jpeg": jpeg,
                "url": "http://10.0.0.88/cgi-bin/snapshot.cgi",
                "url_redacted": "http://10.0.0.88/cgi-bin/snapshot.cgi",
                "source": "http",
            }),
        ):
            res = self.client.post("/cameras/import-discovered", headers=self.headers, json={
                "username": "admin",
                "password": "secret",
                "connect": True,
                "cameras": [{"ip_address": "10.0.0.88", "adapter_id": "hikvision", "name": "Hik Entry"}],
            })
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(len(body["created"]), 1)
        created = body["created"][0]
        self.assertEqual(created["adapter_id"], "hikvision")
        self.assertEqual(created["username"], "admin")
        self.assertFalse(created["native_plates"])
        connected = body["connected"][0]
        self.assertEqual(connected["status"], "VIDEO_CONNECTED")
        self.assertIsNone(connected["sdk_handle"])
        listed = {row["ip_address"]: row for row in self.client.get("/cameras", headers=self.headers).json()}
        self.assertEqual(listed["10.0.0.88"]["plate_engine"], "fastalpr")

    def test_hvx_connect_falls_back_to_video_when_sdk_port_closed(self):
        cam = self.client.post("/cameras", headers=self.headers, json={
            "name": "Browser Cam", "ip_address": "10.0.0.90", "adapter_id": "hvx",
        }).json()
        jpeg = b"\xff\xd8\xff\xd9"

        async def probe(ip, port, timeout=1.0):
            return int(port) != 30000

        with patch("app.api_main.tcp_open", new=probe):
            with patch(
                "app.infrastructure.hardware.cameras.rtsp.grab_http_snapshot",
                new=AsyncMock(return_value={
                    "ok": True,
                    "jpeg": jpeg,
                    "url": "http://10.0.0.90/cgi-bin/snapshot.cgi",
                    "url_redacted": "http://10.0.0.90/cgi-bin/snapshot.cgi",
                    "source": "http",
                }),
            ):
                res = self.client.post(f"/cameras/{cam['id']}/sdk/connect", headers=self.headers, json={})
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["status"], "VIDEO_CONNECTED")
        self.assertEqual(body["adapter_id"], "rtsp")
        self.assertIsNone(body["sdk_handle"])
        self.assertEqual(body["plate_engine"], "fastalpr")

    def test_snapshot_uses_sdk_jpeg_without_ffmpeg(self):
        cam = self._camera()
        with self.Session() as db:
            from app.models import Camera, CameraStatus
            row = db.get(Camera, cam["id"])
            row.status = CameraStatus.SDK_CONNECTED.value
            row.sdk_handle = 7
            db.commit()
        jpeg = b"\xff\xd8\xff\xd9"
        with patch("app.services.preview.HVXHostClient") as hvx:
            hvx.return_value.live_jpeg = AsyncMock(return_value=jpeg)
            hvx.return_value.capture_jpeg = AsyncMock(return_value=jpeg)
            with patch("app.services.preview.grab_http_snapshot", new=AsyncMock(return_value={"ok": False})):
                with patch("app.services.preview.grab_camera_frame", new=AsyncMock(return_value={"ok": False, "error": "ffmpeg is not installed"})):
                    res = self.client.get(f"/cameras/{cam['id']}/snapshot.jpg", headers=self.headers)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.content, jpeg)


if __name__ == "__main__":
    unittest.main()
