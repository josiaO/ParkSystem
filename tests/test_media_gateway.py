from __future__ import annotations

import time
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

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
from app.services.ffmpeg_profiles import fallback_profile, list_profiles, normalize_profile, profile_args
from app.services.latest_frame import LatestFrameBuffer
from app.services.media_gateway import LocalMediaGateway, take_latest_jpeg
from app.services.onvif_discover import parse_media_xaddr, parse_profiles, parse_stream_uri
from app.services.preview import CameraLiveSpec, acquire_live, live_metrics, release_live, remember_frame, stop_live_pumps, viewers_for
from app.services.queues import AI_FRAMES, BoundedQueue
from app.services.stream_roles import classify_stream, hvx_profiles, profile_warnings, recommend_roles


JPEG = b"\xff\xd8" + b"LIVE" + b"\xff\xd9"


class LatestFrameTests(unittest.TestCase):
    def test_queue_stays_bounded_and_keeps_newest(self):
        buf = LatestFrameBuffer("live", maxsize=1)
        for i in range(20):
            buf.put(JPEG + bytes([i % 256]), source="rtsp")
        self.assertEqual(buf.depth(), 1)
        self.assertEqual(buf.dropped, 19)
        self.assertEqual(buf.latest().seq, 20)

    def test_backlog_20fps_producer_3fps_consumer(self):
        buf = LatestFrameBuffer("detect", maxsize=1)
        last_seq = 0
        processed = 0
        for i in range(20):
            buf.put(JPEG, source="rtsp")
            if i % 7 == 0:
                sample = buf.latest()
                self.assertIsNotNone(sample)
                self.assertGreaterEqual(sample.seq, last_seq)
                last_seq = sample.seq
                processed += 1
                self.assertLess(sample.age_ms(), 50)
        self.assertEqual(buf.depth(), 1)
        self.assertGreaterEqual(buf.dropped, 15)
        self.assertLessEqual(processed, 4)

    def test_slow_ai_does_not_grow_queue(self):
        live = LatestFrameBuffer("live", maxsize=1)
        detect = LatestFrameBuffer("detect", maxsize=1)
        for i in range(10):
            live.put(JPEG, source="sdk")
            detect.put(JPEG, source="sdk")
        time.sleep(0.05)
        self.assertEqual(live.depth(), 1)
        self.assertEqual(detect.depth(), 1)
        newest = detect.latest()
        self.assertEqual(newest.seq, 10)

    def test_take_latest_jpeg_still_drops_stacked_frames(self):
        first = b"\xff\xd8" + b"AAAA" + b"\xff\xd9"
        second = b"\xff\xd8" + b"BBBB" + b"\xff\xd9"
        latest, rest = take_latest_jpeg(b"xx" + first + second + b"\xff")
        self.assertEqual(latest, second)
        self.assertEqual(rest, b"\xff")


class StreamRoleTests(unittest.TestCase):
    def test_classify_and_recommend(self):
        self.assertEqual(classify_stream({"width": 2688, "height": 1520, "fps": 20}), "MAIN")
        self.assertEqual(classify_stream({"width": 1280, "height": 720, "fps": 10}), "SUB")
        rec = recommend_roles([
            {"uri": "rtsp://cam/main", "width": 2688, "height": 1520, "fps": 20, "codec": "h264"},
            {"uri": "rtsp://cam/sub", "width": 1280, "height": 720, "fps": 10, "codec": "h264", "gop": 10},
        ])
        self.assertEqual(rec["MAIN"]["uri"], "rtsp://cam/main")
        self.assertEqual(rec["LIVE"]["source"], "SUB")
        self.assertEqual(rec["DETECT"]["ai_fps"], 5)
        warns = profile_warnings(rec, upstream_consumers=2, smart_codec=True)
        self.assertIn("Smart codec enabled", warns)
        self.assertIn("Multiple upstream consumers", warns)

    def test_hvx_profiles_are_sdk_not_rtsp(self):
        rows = hvx_profiles(7)
        self.assertEqual(rows["MAIN"]["protocol"], "sdk")
        self.assertIn("sdk://handle/7", rows["SUB"]["uri"])

    def test_ffmpeg_profiles_are_named(self):
        names = {row["id"] for row in list_profiles()}
        self.assertEqual(names, {"COMPATIBLE", "LOW_LATENCY_LAN", "LOSSY_NETWORK", "VENDOR_SPECIAL"})
        self.assertEqual(normalize_profile("nope"), "LOW_LATENCY_LAN")
        self.assertEqual(fallback_profile("LOW_LATENCY_LAN"), "COMPATIBLE")
        args = " ".join(profile_args("LOW_LATENCY_LAN"))
        self.assertIn("nobuffer", args)
        self.assertIn("100000", args)
        compatible = " ".join(profile_args("COMPATIBLE"))
        self.assertIn("5000000", compatible)


class OnvifParseTests(unittest.TestCase):
    def test_parse_capabilities_profiles_and_uri(self):
        caps = """<Envelope><Body><GetCapabilitiesResponse>
            <Capabilities><Media><XAddr>http://10.0.0.8/onvif/media</XAddr></Media></Capabilities>
        </GetCapabilitiesResponse></Body></Envelope>"""
        self.assertEqual(parse_media_xaddr(caps), "http://10.0.0.8/onvif/media")
        profiles = """<Envelope><Body>
            <Profiles token="Profile_1"><Name>Main</Name>
              <VideoEncoderConfiguration>
                <Encoding>H264</Encoding><Width>1920</Width><Height>1080</Height>
                <FrameRateLimit>20</FrameRateLimit><GovLength>20</GovLength>
              </VideoEncoderConfiguration>
            </Profiles>
            <Profiles token="Profile_2"><Name>Sub</Name>
              <VideoEncoderConfiguration>
                <Encoding>H264</Encoding><Width>1280</Width><Height>720</Height>
                <FrameRateLimit>10</FrameRateLimit><GovLength>10</GovLength>
              </VideoEncoderConfiguration>
            </Profiles>
        </Body></Envelope>"""
        rows = parse_profiles(profiles)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["token"], "Profile_1")
        self.assertEqual(rows[0]["codec"], "h264")
        self.assertEqual(rows[0]["width"], 1920)
        uri_xml = "<Envelope><Body><MediaUri><Uri>rtsp://10.0.0.8/Streaming/Channels/101</Uri></MediaUri></Body></Envelope>"
        self.assertIn("rtsp://", parse_stream_uri(uri_xml))


class GatewayIsolationTests(unittest.TestCase):
    def test_live_and_detect_are_independent_buffers(self):
        gw = LocalMediaGateway()
        gw.publish(9, JPEG, source="sdk", url="sdk://handle/1")
        live = gw.peek_live(9)
        detect = gw.peek_detect(9)
        self.assertEqual(live.jpeg, JPEG)
        self.assertEqual(detect.jpeg, JPEG)
        gw.note_ai_sample(9, infer_ms=1000, dropped=False)
        row = gw._health_row(gw.session(9))
        self.assertEqual(row["queue_depth"], 1)
        self.assertEqual(row["detect_queue_depth"], 1)
        self.assertGreaterEqual(row["frames_sampled_ai"], 1)
        stop_live_pumps()

    def test_ai_frames_queue_is_bounded(self):
        q = BoundedQueue("ai", maxsize=1, overflow="drop_oldest")
        q.put("old")
        q.put("new")
        self.assertEqual(q.get(), "new")
        self.assertEqual(q.dropped, 1)
        self.assertEqual(AI_FRAMES.maxsize, 1)


class MediaApiTests(unittest.TestCase):
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
        self.headers = {"Authorization": f"Bearer {token}"}

    def tearDown(self):
        self._pump_patch.stop()
        self._preview_pump.stop()
        stop_live_pumps()
        set_session_factory(None)
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_camera_streams_and_decode_endpoints(self):
        cam = self.client.post("/cameras", headers=self.headers, json={
            "name": "Stream Cam", "ip_address": "10.0.0.40",
        }).json()
        self.assertIn("stream_profiles", cam)
        self.assertEqual(cam["ffmpeg_profile"], "LOW_LATENCY_LAN")
        res = self.client.get(f"/cameras/{cam['id']}/streams", headers=self.headers)
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertIsInstance(body.get("stream_profiles"), dict)
        self.assertIn("profiles", body)
        patch = self.client.patch(f"/cameras/{cam['id']}/streams", headers=self.headers, json={
            "ffmpeg_profile": "COMPATIBLE",
            "rtsp_transport": "UDP",
            "ai_fps": 5,
        })
        self.assertEqual(patch.status_code, 200, patch.text)
        self.assertEqual(patch.json()["ffmpeg_profile"], "COMPATIBLE")
        self.assertEqual(patch.json()["rtsp_transport"], "UDP")
        decode = self.client.get("/hardware/decode", headers=self.headers)
        self.assertEqual(decode.status_code, 200, decode.text)
        self.assertIn("hwaccels", decode.json())
        self.assertFalse(decode.json()["enabled"])
        gw = self.client.get("/media/gateway", headers=self.headers)
        self.assertEqual(gw.status_code, 200, gw.text)
        body = gw.json()
        self.assertIn("child_pids", body)
        self.assertIn("flags", body)
        self.assertEqual(body["flags"]["live_view_provider"], "DIRECT_LEGACY")
        self.assertEqual(body["rollback"]["live_view_provider"], ["DIRECT_LEGACY", "MEDIAMTX"])
        self.assertIn("mediamtx", body)

    def test_hidden_view_releases_viewers(self):
        spec = CameraLiveSpec(id=77, ip="127.0.0.1", username="a", password="b", rtsp_url="", sdk_handle=None)
        remember_frame(77, JPEG, source="sdk")
        acquire_live(spec)
        self.assertEqual(viewers_for(77), 1)
        release_live(77)
        self.assertEqual(viewers_for(77), 0)
        rows = {row["camera_id"]: row for row in live_metrics()}
        self.assertEqual(rows[77]["viewers"], 0)


if __name__ == "__main__":
    unittest.main()
