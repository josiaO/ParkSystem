"""The public payments tunnel may only reach the narrow payment surface."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api_main import app, ensure_roles
from app.config import settings
from app.db import Base, get_db
from app.models import ParkingSession, VehicleCapture
from app.services import public_ingress


class PublicIngressPolicyTests(unittest.TestCase):
    def test_public_paths(self):
        for path in ("/p/abc", "/s/abc", "/p/abc/status", "/api/public/payment-intents", "/api/public/payment-status/abc",
                     "/api/webhooks/flutterwave", "/api/webhooks/clickpesa", "/health"):
            self.assertTrue(public_ingress.is_public_path(path), path)
        for path in ("/", "/cameras", "/cameras/1/live.mjpeg", "/gates/1/open", "/media/gateway", "/auth/login",
                     "/payments", "/payments/health", "/sessions", "/api/publicx", "/hvx", "/docs"):
            self.assertFalse(public_ingress.is_public_path(path), path)
        self.assertTrue(public_ingress.is_public_path("/p/abc", "GET"))
        self.assertTrue(public_ingress.is_public_path("/api/public/payment-intents", "POST"))
        self.assertFalse(public_ingress.is_public_path("/p/abc/pay", "POST"))
        self.assertFalse(public_ingress.is_public_path("/p/abc/kiosk-pay", "POST"))
        self.assertFalse(public_ingress.is_public_path("/api/public/payment-status/abc", "POST"))

    def test_no_ingress_hosts_means_no_restriction(self):
        with patch.object(settings, "public_ingress_hosts", ""):
            self.assertTrue(public_ingress.request_allowed("/cameras", {"host": "pay.example.com"}))

    def test_host_matching_uses_forwarded_host_and_strips_port(self):
        with patch.object(settings, "public_ingress_hosts", "pay.example.com, Pay2.Example.com"):
            self.assertFalse(public_ingress.request_allowed("/cameras", {"host": "pay.example.com:443"}))
            self.assertFalse(public_ingress.request_allowed("/cameras", {"host": "127.0.0.1:8760",
                                                                          "x-forwarded-host": "pay2.example.com"}))
            self.assertTrue(public_ingress.request_allowed("/cameras", {"host": "127.0.0.1:8760"}))
            self.assertTrue(public_ingress.request_allowed("/api/webhooks/flutterwave", {"host": "pay.example.com"}))

    def test_rate_limiter_is_bounded_by_route_family_without_token_keys(self):
        public_ingress.reset_rate_limiter()
        key = ("198.51.100.10", "payment-intent")
        for _ in range(10):
            self.assertTrue(public_ingress._rate_limiter.allow(key, limit=10, window_seconds=60))
        self.assertFalse(public_ingress._rate_limiter.allow(key, limit=10, window_seconds=60))
        public_ingress.reset_rate_limiter()


class PublicIngressMiddlewareTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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
            from app.services.modules import apply_profile
            apply_profile(db, "PARKING_PRO")
            db.commit()
        self._patch = patch.object(settings, "public_ingress_hosts", "pay.example.com")
        self._patch.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self._patch.stop()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_admin_and_camera_apis_are_invisible_on_public_host(self):
        for path in ("/cameras", "/gates", "/auth/login", "/media/gateway", "/payments", "/docs", "/openapi.json"):
            res = self.client.get(path, headers={"host": "pay.example.com"})
            self.assertEqual(res.status_code, 404, path)
            self.assertEqual(res.json(), {"detail": "Not Found"})
        res = self.client.post("/auth/login", json={"username": "admin", "password": "x"},
                               headers={"host": "pay.example.com"})
        self.assertEqual(res.status_code, 404)

    def test_public_surface_still_served_on_public_host(self):
        res = self.client.get("/api/public/payment-status/nope", headers={"host": "pay.example.com"})
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["detail"], "Receipt not found")  # reached the route, not the guard
        hook = self.client.post("/api/webhooks/flutterwave", content=b"{}", headers={"host": "pay.example.com"})
        self.assertEqual(hook.status_code, 401)  # reached the handler: unsigned webhook rejected
        health = self.client.get("/health", headers={"host": "pay.example.com"})
        self.assertEqual(health.status_code, 200)

    def test_public_payment_photo_endpoint_serves_the_visit_bound_snapshot(self):
        import shutil
        import tempfile
        from unittest.mock import PropertyMock
        from app.config import Settings

        media = Path(tempfile.mkdtemp(prefix="smartpark-public-media-"))
        try:
            (media / "snapshots").mkdir(parents=True)
            photo = b"\xff\xd8\xff\xd9"
            (media / "snapshots" / "entry.jpg").write_bytes(photo)
            with patch.object(Settings, "media_dir", new_callable=PropertyMock, return_value=media):
                with self.Session() as db:
                    row = ParkingSession(
                        site_id=1,
                        plate="T123ABC",
                        camera_id=7,
                        status="CLOSED",
                        public_token="photo-route-token",
                        entry_event_id="photo-route-event",
                    )
                    db.add(row)
                    db.flush()
                    db.add(VehicleCapture(
                        camera_id=7,
                        plate="T123ABC",
                        event_id="photo-route-event",
                        snapshot_path="snapshots/entry.jpg",
                    ))
                    db.commit()

                res = self.client.get(
                    "/p/photo-route-token/snapshot.jpg",
                    headers={"host": "pay.example.com"},
                )
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.content, photo)
            self.assertEqual(res.headers.get("content-type"), "image/jpeg")
        finally:
            shutil.rmtree(media, ignore_errors=True)

    def test_lan_host_is_unrestricted(self):
        res = self.client.get("/cameras", headers={"host": "127.0.0.1:8760"})
        self.assertNotEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
