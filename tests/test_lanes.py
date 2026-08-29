from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import PropertyMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api_main import app, ensure_roles
from app.config import Settings
from app.db import Base, get_db
from app.models import Camera, Role, User, UserRole, VehicleCapture
from app.security import hash_password
from app.services.captures import persist_event

JPEG = b"\xff\xd8\xff\xd9"
CROP = b"\xff\xd8\xff\xdb\xff\xd9"


class LaneViewTests(unittest.TestCase):
    def setUp(self):
        self.media = Path(tempfile.mkdtemp(prefix="smartpark-media-"))
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
        self._media_patch = patch.object(Settings, "media_dir", new_callable=PropertyMock, return_value=self.media)
        self._media_patch.start()

    def tearDown(self):
        self._media_patch.stop()
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()
        shutil.rmtree(self.media, ignore_errors=True)

    def test_lane_view_has_entry_and_exit(self):
        seeded = self.client.post("/cameras/seed-site", headers=self.headers, json={})
        self.assertEqual(seeded.status_code, 200, seeded.text)
        lanes = self.client.get("/lanes", headers=self.headers).json()
        self.assertEqual({row["name"] for row in lanes}, {"1#", "2#"})
        lane1 = next(row for row in lanes if row["name"] == "1#")
        view = self.client.get(f"/lanes/{lane1['id']}/view", headers=self.headers)
        self.assertEqual(view.status_code, 200, view.text)
        body = view.json()
        self.assertEqual(body["gate"]["name"], "1#")
        self.assertEqual(body["entry"]["camera"]["name"], "1# Entry")
        self.assertEqual(body["exit"]["camera"]["name"], "1# Exit")
        self.assertIsNone(body["entry"]["snapshot_url"])
        self.assertIsNone(body["exit"]["snapshot_url"])
        self.assertEqual(len(body["sides"]), 2)
        overview = self.client.get("/lanes/overview", headers=self.headers)
        self.assertEqual(overview.status_code, 200, overview.text)
        self.assertEqual(len(overview.json()["lanes"]), 2)
        self.assertIsNone(body["entry"]["last"])
        self.assertIsNone(body["exit"]["last"])

    def test_persist_snapshot_crop_and_characters(self):
        self.client.post("/cameras/seed-site", headers=self.headers, json={})
        with self.Session() as db:
            camera = db.scalar(select(Camera).where(Camera.name == "1# Entry"))
            first = persist_event(
                db,
                camera,
                jpeg=JPEG,
                crop=CROP,
                capture={"image_id": 41, "plate": "T123ABC", "score": 92, "plate_box": [10, 20, 80, 50]},
            )
            self.assertIsNotNone(first)
            second = persist_event(
                db,
                camera,
                jpeg=JPEG,
                crop=CROP,
                capture={"image_id": 41, "plate": "T123ABC", "score": 92},
            )
            self.assertEqual(second.id, first.id)
            count = db.scalar(select(func.count()).select_from(VehicleCapture).where(VehicleCapture.camera_id == camera.id))
            self.assertEqual(count, 1)
            self.assertTrue((self.media / first.snapshot_path).is_file())
            self.assertTrue((self.media / first.crop_path).is_file())
            gate_id = camera.gate_id

        view = self.client.get(f"/lanes/{gate_id}/view", headers=self.headers).json()
        last = view["entry"]["last"]
        self.assertEqual(last["plate"], "T123ABC")
        self.assertEqual(last["characters"], "T 1 2 3 A B C")
        self.assertTrue(last["snapshot_url"].startswith("/media/snapshots/"))
        self.assertTrue(last["crop_url"].startswith("/media/crops/"))
        snap = self.client.get(last["snapshot_url"], headers=self.headers)
        crop = self.client.get(last["crop_url"], headers=self.headers)
        self.assertEqual(snap.status_code, 200, snap.text)
        self.assertEqual(crop.status_code, 200, crop.text)
        self.assertEqual(snap.content[:2], b"\xff\xd8")
        listed = self.client.get(f"/captures?gate_id={gate_id}", headers=self.headers).json()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["lane_direction"], "ENTRY")

    def test_fastalpr_fills_empty_native_capture(self):
        self.client.post("/cameras/seed-site", headers=self.headers, json={})
        with self.Session() as db:
            camera = db.scalar(select(Camera).where(Camera.name == "1# Entry"))
            empty = persist_event(
                db, camera, jpeg=JPEG, crop=CROP,
                capture={"image_id": 77, "plate": "", "score": 0, "have_vehicle": True},
            )
            self.assertEqual(empty.plate, "")
            filled = persist_event(
                db, camera, jpeg=JPEG, crop=CROP,
                capture={
                    "image_id": 77, "plate": "T349DLG", "score": 0.88,
                    "bbox": {"x1": 10, "y1": 20, "x2": 80, "y2": 50},
                    "source": "fastalpr",
                },
            )
            self.assertEqual(filled.id, empty.id)
            self.assertEqual(filled.plate, "T349DLG")
            self.assertEqual(filled.bbox["source"], "fastalpr")
