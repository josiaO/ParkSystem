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
from app.models import Role, User, UserRole, UserStatus
from app.security import hash_password


class AuthTests(unittest.TestCase):
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
            locked = User(
                username="locked",
                full_name="Locked",
                password_hash=hash_password("correct-horse"),
                status=UserStatus.LOCKED.value,
            )
            db.add(locked)
            db.commit()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_root_serves_web_login(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Sign In", r.text)

    def test_login_rejects_bad_password(self):
        r = self.client.post("/auth/login", json={"username": "admin", "password": "nope"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["detail"], "Invalid username or password")

    def test_login_rejects_locked_account(self):
        r = self.client.post("/auth/login", json={"username": "locked", "password": "correct-horse"})
        self.assertEqual(r.status_code, 403)

    def test_json_login_then_me_and_cameras(self):
        r = self.client.post("/auth/login", json={"username": "admin", "password": "correct-horse"})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["token"])
        self.assertEqual(body["token"], body["access_token"])
        self.assertEqual(body["token_type"], "bearer")
        self.assertEqual(body["permissions"], ["*"])
        headers = {"Authorization": f"Bearer {body['token']}"}
        me = self.client.get("/auth/me", headers=headers)
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["username"], "admin")
        cams = self.client.get("/cameras", headers=headers)
        self.assertEqual(cams.status_code, 200)
        self.assertEqual(cams.json(), [])

    def test_oauth_form_token_login(self):
        r = self.client.post(
            "/auth/token",
            data={"username": "admin", "password": "correct-horse", "grant_type": "password"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        token = r.json()["access_token"]
        me = self.client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me.status_code, 200)

    def test_protected_routes_require_auth(self):
        self.assertEqual(self.client.get("/auth/me").status_code, 401)
        self.assertEqual(self.client.get("/cameras").status_code, 401)

    def test_logout_revokes_session(self):
        token = self.client.post("/auth/login", json={"username": "admin", "password": "correct-horse"}).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        self.assertEqual(self.client.post("/auth/logout", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/auth/me", headers=headers).status_code, 401)


if __name__ == "__main__":
    unittest.main()
