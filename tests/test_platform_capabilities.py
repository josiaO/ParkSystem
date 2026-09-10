from __future__ import annotations

import unittest
from pathlib import Path
import sys
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api_main import app, ensure_roles
from app.db import Base, get_db
from app.services import platform_capabilities as plat
from app.services.health import ready


class PlatformCapabilitiesTests(unittest.TestCase):
    def test_snapshot_marks_web_supported(self):
        snap = plat.platform_snapshot()
        self.assertTrue(snap["web_supported"])
        self.assertIn(snap["recommended_client"], {"desktop", "web"})
        self.assertIn(snap["recommended_camera_adapter"], {"hvx", "rtsp"})

    def test_non_windows_recommends_web_and_rtsp(self):
        with patch.object(plat, "system_name", return_value="Linux"):
            self.assertFalse(plat.hvx_host_supported())
            self.assertEqual(plat.recommended_client(), "web")
            self.assertEqual(plat.recommended_camera_adapter(), "rtsp")
            snap = plat.platform_snapshot()
            self.assertFalse(snap["desktop_supported"])
            self.assertIn("Windows-only", snap["note"])

    def test_windows_recommends_desktop_and_hvx(self):
        with patch.object(plat, "system_name", return_value="Windows"):
            self.assertTrue(plat.hvx_host_supported())
            self.assertEqual(plat.recommended_client(), "desktop")
            self.assertEqual(plat.recommended_camera_adapter(), "hvx")


class PlatformReadyApiTests(unittest.TestCase):
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
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_auth_setup_includes_platform(self):
        body = self.client.get("/auth/setup").json()
        self.assertIn("platform", body)
        self.assertTrue(body["platform"]["web_supported"])
        self.assertIn("recommended_camera_adapter", body)

    def test_ready_without_hvx_on_linux(self):
        # This CI/dev host is non-Windows: missing HVX must still be ready for web mode.
        if plat.is_windows():
            self.skipTest("Windows requires HVX for ready=ready")
        payload = ready()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ready")
        self.assertFalse(payload["hvx_host"]["required"])
        self.assertIn("platform", payload)
        self.assertEqual(payload["platform"]["recommended_client"], "web")


if __name__ == "__main__":
    unittest.main()
