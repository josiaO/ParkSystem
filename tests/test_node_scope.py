"""This PC processes one selected gate (entry+exit), not every lane."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]

from app.api_main import app, ensure_roles
from app.db import Base, get_db, set_session_factory
from app.models import Role, User, UserRole
from app.security import hash_password
from app.services.node_scope import (
    camera_in_recognition_scope,
    reset_recognition_scope,
    set_recognition_gate_id,
)
from app.services.preview import stop_live_pumps


class NodeScopeTests(unittest.TestCase):
    def setUp(self):
        reset_recognition_scope()
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
        self.gate1 = self.client.post("/gates", headers=self.headers, json={"name": "1#"}).json()
        self.gate2 = self.client.post("/gates", headers=self.headers, json={"name": "2#"}).json()
        self.cam1e = self.client.post("/cameras", headers=self.headers, json={
            "name": "1# Entry", "ip_address": "192.168.1.144", "gate_id": self.gate1["id"], "lane_direction": "ENTRY",
        }).json()
        self.cam1x = self.client.post("/cameras", headers=self.headers, json={
            "name": "1# Exit", "ip_address": "192.168.1.145", "gate_id": self.gate1["id"], "lane_direction": "EXIT",
        }).json()
        self.cam2e = self.client.post("/cameras", headers=self.headers, json={
            "name": "2# Entry", "ip_address": "192.168.1.49", "gate_id": self.gate2["id"], "lane_direction": "ENTRY",
        }).json()

    def tearDown(self):
        reset_recognition_scope()
        stop_live_pumps()
        set_session_factory(None)
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_selecting_gate_1_excludes_gate_2_cameras(self):
        body = self.client.post(
            "/runtime/recognition-scope",
            headers=self.headers,
            json={"gate_id": self.gate1["id"]},
        )
        self.assertEqual(body.status_code, 200, body.text)
        payload = body.json()
        self.assertEqual(payload["mode"], "gate")
        self.assertEqual(payload["gate_id"], self.gate1["id"])
        ids = {row["id"] for row in payload["cameras"]}
        self.assertEqual(ids, {self.cam1e["id"], self.cam1x["id"]})
        self.assertTrue(camera_in_recognition_scope(self.cam1e, db=None))
        set_recognition_gate_id(self.gate1["id"])
        self.assertTrue(camera_in_recognition_scope(self.cam1e))
        self.assertTrue(camera_in_recognition_scope(self.cam1x))
        self.assertFalse(camera_in_recognition_scope(self.cam2e))

    def test_all_cameras_processes_every_gate(self):
        self.client.post("/runtime/recognition-scope", headers=self.headers, json={"gate_id": self.gate1["id"]})
        body = self.client.post("/runtime/recognition-scope", headers=self.headers, json={"gate_id": None})
        self.assertEqual(body.json()["mode"], "all")
        self.assertTrue(camera_in_recognition_scope(self.cam2e))

    def test_zx5188_is_not_a_bundled_plate(self):
        hits = []
        for path in (ROOT / "app").rglob("*"):
            if path.suffix.lower() not in {".py", ".html", ".json", ".txt", ".md"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "ZX5188" in text.replace(" ", "").upper():
                hits.append(str(path))
        self.assertEqual(hits, [])

    def test_drain_does_not_replay_host_last_capture(self):
        text = (ROOT / "app" / "api_main.py").read_text(encoding="utf-8")
        drain = text.split("async def _drain_camera_events", 1)[1].split("async def _poll_coil_and_read", 1)[0]
        self.assertNotIn('state.get("last_capture")', drain)
        self.assertIn("Do not replay last_capture", drain)

    def test_env_pin_blocks_ui_override(self):
        with patch("app.services.node_scope.env_recognition_gate_id", return_value=self.gate1["id"]):
            res = self.client.post(
                "/runtime/recognition-scope",
                headers=self.headers,
                json={"gate_id": self.gate2["id"]},
            )
        self.assertEqual(res.status_code, 409)


if __name__ == "__main__":
    unittest.main()
