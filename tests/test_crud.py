from __future__ import annotations

import unittest
from pathlib import Path
import sys

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api_main import app, ensure_roles
from app.db import Base, get_db
from app.models import Role, User, UserRole
from app.security import hash_password


class CrudTests(unittest.TestCase):
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

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_camera_crud(self):
        created = self.client.post("/cameras", headers=self.headers, json={
            "name": "Gate A Entry",
            "ip_address": "192.168.1.49",
            "sdk_port": 30000,
            "username": "admin",
            "password": "cam-secret",
            "lane_direction": "ENTRY",
        })
        self.assertEqual(created.status_code, 200, created.text)
        cam_id = created.json()["id"]
        fetched = self.client.get(f"/cameras/{cam_id}", headers=self.headers)
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["name"], "Gate A Entry")
        self.assertNotIn("password_secret", fetched.json())
        updated = self.client.patch(f"/cameras/{cam_id}", headers=self.headers, json={"name": "Gate A Entry Cam"})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["name"], "Gate A Entry Cam")
        listed = self.client.get("/cameras", headers=self.headers)
        self.assertEqual(len(listed.json()), 1)
        deleted = self.client.delete(f"/cameras/{cam_id}", headers=self.headers)
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get(f"/cameras/{cam_id}", headers=self.headers).status_code, 404)

    def test_camera_duplicate_name(self):
        payload = {"name": "Cam 1", "ip_address": "10.0.0.1"}
        self.assertEqual(self.client.post("/cameras", headers=self.headers, json=payload).status_code, 200)
        dup = self.client.post("/cameras", headers=self.headers, json=payload)
        self.assertEqual(dup.status_code, 409)

    def test_gate_crud(self):
        created = self.client.post("/gates", headers=self.headers, json={"name": "Gate A", "mode": "COMMISSIONING"})
        self.assertEqual(created.status_code, 200, created.text)
        gate_id = created.json()["id"]
        self.assertEqual(self.client.get(f"/gates/{gate_id}", headers=self.headers).json()["name"], "Gate A")
        updated = self.client.patch(f"/gates/{gate_id}", headers=self.headers, json={"mode": "SHADOW", "enabled": False})
        self.assertEqual(updated.json()["mode"], "SHADOW")
        self.assertFalse(updated.json()["enabled"])
        cam = self.client.post("/cameras", headers=self.headers, json={
            "name": "Linked Cam", "ip_address": "10.0.0.2", "gate_id": gate_id,
        }).json()
        self.assertEqual(self.client.delete(f"/gates/{gate_id}", headers=self.headers).status_code, 200)
        self.assertIsNone(self.client.get(f"/cameras/{cam['id']}", headers=self.headers).json()["gate_id"])

    def test_user_crud(self):
        created = self.client.post("/users", headers=self.headers, json={
            "username": "operator1",
            "full_name": "Lane Operator",
            "password": "operator-password",
            "roles": ["Operator"],
        })
        self.assertEqual(created.status_code, 200, created.text)
        user_id = created.json()["id"]
        self.assertEqual(created.json()["roles"], ["Operator"])
        fetched = self.client.get(f"/users/{user_id}", headers=self.headers)
        self.assertEqual(fetched.json()["full_name"], "Lane Operator")
        patched = self.client.patch(f"/users/{user_id}", headers=self.headers, json={"full_name": "Gate Operator"})
        self.assertEqual(patched.json()["full_name"], "Gate Operator")
        self.assertEqual(self.client.delete(f"/users/{user_id}", headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get(f"/users/{user_id}", headers=self.headers).status_code, 404)

    def test_cannot_delete_self_or_last_admin(self):
        me = self.client.get("/auth/me", headers=self.headers).json()
        self.assertEqual(self.client.delete(f"/users/{me['id']}", headers=self.headers).status_code, 409)
        listed = self.client.get("/users", headers=self.headers).json()
        self.assertEqual(len(listed), 1)
        self.assertEqual(self.client.patch(f"/users/{me['id']}", headers=self.headers, json={"roles": ["Operator"]}).status_code, 409)

    def test_roles_list(self):
        roles = self.client.get("/roles", headers=self.headers).json()
        self.assertEqual({r["name"] for r in roles}, {"Admin", "Operator", "Developer", "Kiosk Operator"})

    def test_device_registry_projects_cameras(self):
        cam = self.client.post("/cameras", headers=self.headers, json={
            "name": "1# Entry", "ip_address": "192.168.1.144",
        }).json()
        self.assertEqual(cam["adapter_id"], "hvx")
        self.assertEqual(cam["connection_mode"], "DIRECT")
        listed = self.client.get("/devices", headers=self.headers)
        self.assertEqual(listed.status_code, 200, listed.text)
        cameras = [row for row in listed.json()["devices"] if row["device_type"] == "CAMERA"]
        self.assertEqual(cameras[0]["adapter_id"], "hvx")
        self.assertFalse(listed.json()["edge_agent"]["available"])


if __name__ == "__main__":
    unittest.main()
