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
from app.services.cache import TtlCache
from app.services.circuit import CircuitBreaker, ReconnectPolicy, BACKOFF_STEPS
from app.services.dedup import EventDeduper
from app.services.ocr_policy import NATIVE_ONLY, LOCAL_ONLY, should_run_local
from app.services.preview import CameraLiveSpec, acquire_live, live_metrics, release_live, remember_frame, stop_live_pumps, viewers_for
from app.services.queues import BoundedQueue, DurableOutbox
from app.services.runtime import READY_CORE, set_startup_state, startup_state


JPEG = b"\xff\xd8\xff\xd9"


class QueueAndCircuitTests(unittest.TestCase):
    def test_video_queue_keeps_newest(self):
        q = BoundedQueue("video", maxsize=1, overflow="drop_oldest")
        self.assertTrue(q.put("old"))
        self.assertTrue(q.put("new"))
        self.assertEqual(q.get(), "new")
        self.assertEqual(q.dropped, 1)

    def test_parking_queue_never_drops(self):
        q = BoundedQueue("parking", maxsize=2, overflow="reject")
        self.assertTrue(q.put(1))
        self.assertTrue(q.put(2))
        self.assertFalse(q.put(3))
        self.assertEqual(q.depth(), 2)
        snap = q.snapshot()
        self.assertTrue(snap["alert"])

    def test_outbox_survives_ack(self):
        dest = Path("/tmp/smartpark-outbox-test.jsonl")
        dest.write_text("", encoding="utf-8")
        box = DurableOutbox(dest)
        item_id = box.enqueue("plate-event", {"plate": "T123ABC"})
        self.assertEqual(len(box.pending()), 1)
        box.ack(item_id)
        self.assertEqual(box.pending(), [])
        dest.unlink(missing_ok=True)

    def test_circuit_opens_and_half_opens(self):
        br = CircuitBreaker("x", failure_threshold=2, reset_seconds=0.05)
        self.assertTrue(br.allow())
        br.failure()
        br.failure()
        self.assertEqual(br.state, "OPEN")
        self.assertFalse(br.allow())
        time.sleep(0.06)
        self.assertTrue(br.allow())
        self.assertEqual(br.state, "HALF_OPEN")
        br.success()
        self.assertEqual(br.state, "CLOSED")

    def test_reconnect_backoff_caps(self):
        policy = ReconnectPolicy()
        policy.stagger = 0
        waits = [policy.record_failure("down") for _ in range(8)]
        self.assertGreaterEqual(waits[0], BACKOFF_STEPS[0])
        self.assertLessEqual(waits[-1], BACKOFF_STEPS[-1] * 1.5)
        self.assertFalse(policy.ready())
        policy.record_success()
        self.assertTrue(policy.ready())

    def test_ttl_cache(self):
        cache = TtlCache(ttl_seconds=0.05, maxsize=4)
        cache.set("a", 1)
        self.assertEqual(cache.get("a"), 1)
        time.sleep(0.06)
        self.assertIsNone(cache.get("a"))

    def test_event_dedup(self):
        d = EventDeduper(window_seconds=1.0)
        self.assertFalse(d.seen(camera_id=1, plate="T1", image_id=9))
        self.assertTrue(d.seen(camera_id=1, plate="T1", image_id=9))

    def test_native_ocr_skips_fastalpr(self):
        with patch("app.services.ocr_policy.alpr_mode", return_value=NATIVE_ONLY):
            self.assertFalse(should_run_local(native_plate="T123ABC", native_confidence=0.9))
            self.assertTrue(should_run_local(native_plate="T123ABC", explicit=True))
            self.assertFalse(should_run_local(native_plate="", native_confidence=0.0))
            self.assertTrue(should_run_local(native_plate="", presence=True))
            self.assertTrue(should_run_local(native_plate="", native_plates=False))
            self.assertTrue(should_run_local(native_plate="T123ABC", native_confidence=0.99, native_plates=False))

    def test_local_only_always_runs(self):
        with patch("app.services.ocr_policy.alpr_mode", return_value=LOCAL_ONLY):
            self.assertTrue(should_run_local(native_plate="T123ABC", native_confidence=0.99))


class HealthApiTests(unittest.TestCase):
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
        self._pump_patch = patch("app.services.preview.start_live_pump")
        self._pump_patch.start()
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
        stop_live_pumps()
        set_session_factory(None)
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_health_live_unauthenticated(self):
        res = self.client.get("/health/live")
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertTrue(body["ok"])
        self.assertIn("process", body)
        self.assertIn("pid", body["process"])

    def test_health_ready_and_details(self):
        set_startup_state(READY_CORE)
        ready = self.client.get("/health/ready")
        self.assertEqual(ready.status_code, 200, ready.text)
        self.assertTrue(ready.json()["ok"])
        details = self.client.get("/health/details", headers=self.headers)
        self.assertEqual(details.status_code, 200, details.text)
        body = details.json()
        self.assertIn("queues", body)
        self.assertIn("cameras", body)
        self.assertEqual(startup_state(), READY_CORE)

    def test_live_viewers_and_metrics(self):
        spec = CameraLiveSpec(id=42, ip="127.0.0.1", username="a", password="b", rtsp_url="", sdk_handle=None)
        remember_frame(42, JPEG, source="sdk")
        acquire_live(spec)
        self.assertEqual(viewers_for(42), 1)
        rows = {row["camera_id"]: row for row in live_metrics()}
        self.assertEqual(rows[42]["viewers"], 1)
        self.assertEqual(rows[42]["queue_depth"], 1)
        release_live(42)
        self.assertEqual(viewers_for(42), 0)


if __name__ == "__main__":
    unittest.main()
