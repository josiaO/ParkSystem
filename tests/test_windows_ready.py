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
from app.config import settings
from app.db import Base, get_db
from app.models import Camera, CameraStatus, Role, User, UserRole
from app.security import hash_password
from app.services.bootstrap import effective_bootstrap_password, ensure_bootstrap_admin, setup_status
from app.services.hvx_client import HVXHostUnavailable
from app.services.site_cameras import KNOWN_SITE_CAMERAS


class WindowsReadyTests(unittest.TestCase):
    def test_existing_recognition_path_saves_and_serves_snapshot_and_plate_crop(self):
        from io import BytesIO
        from tempfile import TemporaryDirectory
        from types import SimpleNamespace
        from PIL import Image
        from app.models import VehicleCapture
        from app.services.preview import remember_frame
        from app.services import preview
        from app.services.presence import PresenceWatch
        from app.services.recognition_runtime import runtime
        runtime.reset()
        self.addCleanup(runtime.reset)
        preview._state.clear()
        self.addCleanup(preview._state.clear)
        presence = patch("app.api_main.coil_watch", PresenceWatch())
        presence.start()
        self.addCleanup(presence.stop)
        headers = self._login_admin()
        camera = self.client.post("/cameras", headers=headers, json={"name": "Recognition camera", "ip_address": "10.44.8.23", "adapter_id": "ipcam"}).json()
        runtime.lane(camera["id"]).visit.reset()
        frame = BytesIO()
        Image.new("RGB", (640, 360), "white").save(frame, format="JPEG")
        remember_frame(camera["id"], frame.getvalue())
        detection = SimpleNamespace(bounding_box=SimpleNamespace(x1=120, y1=110, x2=300, y2=155), confidence=.95)
        engine = SimpleNamespace(detector=SimpleNamespace(predict=lambda frame: [detection]),
                                 ocr=SimpleNamespace(predict=lambda frame: SimpleNamespace(text="T123ABC", confidence=.96)))
        with TemporaryDirectory() as folder, patch("app.config.default_data_dir", return_value=Path(folder)), \
             patch("app.services.alpr.fastalpr_installed", return_value=True), \
             patch("app.services.alpr._load_engine", return_value=engine), \
             patch("app.services.modules.is_enabled", side_effect=lambda module, db: module != "parking.sessions"), \
             patch("app.services.ai_review.schedule_capture_review"):
            response = self.client.post(f"/cameras/{camera['id']}/presence", headers=headers)
            self.assertEqual(response.status_code, 200, response.text)
            evidence = response.json()["last_car"]
            self.assertEqual(evidence["plate"], "T123ABC")
            for field in ("snapshot_url", "crop_url"):
                image = self.client.get(evidence[field], headers=headers)
                self.assertEqual(image.status_code, 200, image.text[:100])
                self.assertTrue(image.content.startswith(b"\xff\xd8"))
            snapshot = Image.open(BytesIO(self.client.get(evidence["snapshot_url"], headers=headers).content))
            crop = Image.open(BytesIO(self.client.get(evidence["crop_url"], headers=headers).content))
            self.assertLess(crop.width, snapshot.width)
            self.assertLess(crop.height, snapshot.height)
            with self.Session() as db:
                captures = list(db.scalars(select(VehicleCapture)).all())
                self.assertEqual(len(captures), 1)
                captures[0].snapshot_path = captures[0].snapshot_path.replace("/", "\\")
                captures[0].crop_path = captures[0].crop_path.replace("/", "\\")
                db.commit()
            response = self.client.get(f"/cameras/{camera['id']}/plates", headers=headers)
            saved = response.json()["evidence"]
            for field in ("snapshot_url", "crop_url"):
                self.assertNotIn("\\", saved[field])
                image = self.client.get(saved[field], headers=headers)
                self.assertEqual(image.status_code, 200)
                self.assertTrue(image.content.startswith(b"\xff\xd8"))

    def test_last_evidence_is_available_after_vehicle_presence_clears(self):
        from app.models import VehicleCapture
        from app.services.recognition_runtime import runtime
        headers = self._login_admin()
        response = self.client.post("/cameras", headers=headers, json={"name": "Evidence camera", "ip_address": "10.44.8.23"})
        camera_id = response.json()["id"]
        with self.Session() as db:
            db.add(VehicleCapture(camera_id=camera_id, plate="T123ABC", snapshot_path=r"snapshots\car.jpg", crop_path=r"crops\plate.jpg"))
            db.commit()
        runtime.lane(camera_id).visit.reset()
        with patch("app.api_main._native_capture_for_camera", new=AsyncMock(return_value={})), \
             patch("app.api_main.coil_watch.occupied", return_value=False):
            response = self.client.get(f"/cameras/{camera_id}/plates", headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["clear_last_car"])
        self.assertFalse(body["vehicle_present"])
        self.assertIsNone(body["current_plate"])
        self.assertEqual(body["evidence"]["snapshot_url"], "/media/snapshots/car.jpg")
        self.assertEqual(body["evidence"]["crop_url"], "/media/crops/plate.jpg")

    def test_confirmed_production_seed_is_editable_and_preserves_existing_cameras(self):
        headers = self._login_admin()
        with patch.object(settings, "deployment_profile", "PRODUCTION"):
            for confirmation in (False, "true", 1):
                response = self.client.post("/cameras/seed-site", headers=headers, json={"confirm_test_data": confirmation})
                self.assertEqual(response.status_code, 409)
            response = self.client.post("/cameras/seed-site", headers=headers, json={"confirm_test_data": True})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(len(response.json()["created"]), 4)
            camera_id = response.json()["created"][0]["id"]
            gate = self.client.post("/gates", headers=headers, json={"name": "Warehouse West"}).json()
            with self.Session() as db:
                camera = db.get(Camera, camera_id)
                camera.name = "Admin configured exit"
                camera.gate_id = gate["id"]
                camera.lane_direction = "EXIT"
                camera.controller_ip = "10.44.8.60"
                db.commit()
            for profile in ("DEVELOPMENT", "PRODUCTION"):
                with patch.object(settings, "deployment_profile", profile):
                    repeated = self.client.post("/cameras/seed-site", headers=headers, json={"confirm_test_data": True})
                self.assertEqual(repeated.status_code, 200, repeated.text)
                self.assertEqual(repeated.json()["created"], [])
                self.assertTrue(all(not row["updated"] for row in repeated.json()["skipped"]))
            saved = next(row for row in self.client.get("/cameras", headers=headers).json() if row["id"] == camera_id)
            self.assertEqual(saved["name"], "Admin configured exit")
            self.assertEqual(saved["gate_id"], gate["id"])
            self.assertEqual(saved["lane_direction"], "EXIT")
            self.assertEqual(saved["controller_ip"], "10.44.8.60")
            with self.Session() as db:
                camera = db.get(Camera, camera_id)
                camera.ip_address = "10.44.8.23"
                db.commit()
            saved = next(row for row in self.client.get("/cameras", headers=headers).json() if row["id"] == camera_id)
            self.assertEqual(saved["ip_address"], "10.44.8.23")

    def test_production_never_seeds_or_invents_camera_addresses(self):
        headers = self._login_admin()
        from app.services.site_cameras import camera_spec_for_ip, load_site_lanes, site_controller_ips
        with patch.object(settings, "deployment_profile", "PRODUCTION"):
            response = self.client.post("/cameras/seed-site", headers=headers, json={})
            self.assertEqual(response.status_code, 409)
            self.assertEqual(load_site_lanes(), ())
            self.assertEqual(site_controller_ips(), ())
            spec = camera_spec_for_ip("192.168.1.144")
            self.assertEqual(spec["name"], "Camera 192.168.1.144")
            self.assertEqual(spec["gate_name"], "")
            self.assertEqual(spec["controller_ip"], "")
            with patch("app.api_main.HVXHostClient") as host, patch("app.api_main.probe_ips", new=AsyncMock(return_value={})) as probe:
                host.return_value.discover = AsyncMock(return_value={"ok": True, "ips": []})
                discovered = self.client.get("/cameras/discover", headers=headers)
                self.assertEqual(discovered.json()["cameras"], [])
                self.assertEqual(probe.call_args.args[0], [])
            with patch("app.api_main._discover_cameras", new=AsyncMock(return_value={"cameras": []})):
                response = self.client.post("/cameras/import-discovered", headers=headers, json={"connect": False})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["created"], [])
            self.assertEqual(self.client.get("/cameras", headers=headers).json(), [])
            self.assertEqual(self.client.get("/gates", headers=headers).json(), [])

    def test_production_discovery_uses_real_addresses_and_preserves_admin_metadata(self):
        headers = self._login_admin()
        with patch.object(settings, "deployment_profile", "PRODUCTION"):
            gate = self.client.post("/gates", headers=headers, json={"name": "Warehouse West"}).json()
            camera = self.client.post("/cameras", headers=headers, json={"name": "Replacement exit", "ip_address": "10.44.8.23", "lane_direction": "EXIT", "gate_id": gate["id"], "controller_ip": "10.44.8.60"}).json()
            with patch("app.api_main.HVXHostClient") as host, patch("app.api_main.probe_ips", new=AsyncMock(return_value={"10.44.8.23": True})) as probe:
                host.return_value.discover = AsyncMock(return_value={"ok": True, "ips": ["10.44.8.24"]})
                response = self.client.get("/cameras/discover", headers=headers)
                self.assertEqual({row["ip_address"] for row in response.json()["cameras"]}, {"10.44.8.23", "10.44.8.24"})
                self.assertEqual(set(probe.call_args.args[0]), {"10.44.8.23", "10.44.8.24"})
            response = self.client.post("/cameras/import-discovered", headers=headers, json={"ips": ["10.44.8.23"], "connect": False})
            self.assertEqual(response.status_code, 200, response.text)
            saved = self.client.get("/cameras", headers=headers).json()[0]
            self.assertEqual(saved["id"], camera["id"])
            self.assertEqual(saved["name"], "Replacement exit")
            self.assertEqual(saved["lane_direction"], "EXIT")
            self.assertEqual(saved["controller_ip"], "10.44.8.60")
            self.assertEqual(saved["gate_id"], gate["id"])

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

    def _login_admin(self, password="correct-horse"):
        with self.Session() as db:
            if db.scalar(select(User).where(User.username == "admin")) is None:
                admin_role = db.scalar(select(Role).where(Role.name == "Admin"))
                user = User(username="admin", full_name="Test Admin", password_hash=hash_password(password))
                db.add(user)
                db.flush()
                db.add(UserRole(user_id=user.id, role_id=admin_role.id))
                db.commit()
        token = self.client.post("/auth/login", json={"username": "admin", "password": password}).json()["token"]
        return {"Authorization": f"Bearer {token}"}

    def test_bootstrap_creates_admin_once(self):
        with self.Session() as db:
            self.assertTrue(ensure_bootstrap_admin(db))
            self.assertFalse(ensure_bootstrap_admin(db))
            status = setup_status(db)
        password = effective_bootstrap_password()
        self.assertTrue(status["ready"])
        self.assertEqual(status["username"], settings.bootstrap_username)
        self.assertEqual(status["password"], password)
        self.assertGreaterEqual(len(password), 12)
        login = self.client.post("/auth/login", json={
            "username": settings.bootstrap_username,
            "password": password,
        })
        self.assertEqual(login.status_code, 200, login.text)

    def test_auth_setup_endpoint(self):
        res = self.client.get("/auth/setup")
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["username"], "admin")
        self.assertTrue(body["password"])
        self.assertNotEqual(body["password"], "SmartPark1!")
        self.assertIn(body["username"], body["hint"])
        self.assertTrue(body["ready"])

    def test_setup_hides_default_password_when_admin_already_exists(self):
        headers = self._login_admin("correct-horse")
        self.assertEqual(self.client.get("/auth/me", headers=headers).status_code, 200)
        body = self.client.get("/auth/setup").json()
        self.assertEqual(body["username"], "admin")
        self.assertEqual(body["password"], "")
        self.assertFalse(body["bootstrap_password_ok"])
        self.assertIn("already has an admin", body["hint"])

    def test_seed_site_adds_four_cameras(self):
        headers = self._login_admin()
        first = self.client.post("/cameras/seed-site", headers=headers, json={})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(len(first.json()["created"]), 4)
        self.assertEqual(first.json()["created"][0]["sdk_port"], 30000)
        self.assertEqual(first.json()["created"][0]["status"], CameraStatus.DISCOVERED.value)
        second = self.client.post("/cameras/seed-site", headers=headers, json={})
        self.assertEqual(len(second.json()["created"]), 0)
        self.assertEqual(len(second.json()["skipped"]), 4)
        listed = self.client.get("/cameras", headers=headers).json()
        self.assertEqual({row["ip_address"] for row in listed}, {row["ip_address"] for row in KNOWN_SITE_CAMERAS})
        self.assertEqual(
            {row["ip_address"] for row in listed},
            {"192.168.1.144", "192.168.1.145", "192.168.1.49", "192.168.1.50"},
        )
        self.assertEqual(
            {row["controller_ip"] for row in listed},
            {"192.168.1.61", "192.168.1.69", "192.168.1.65", "192.168.1.67"},
        )
        self.assertEqual(
            {row["display_ip"] for row in listed},
            {"192.168.1.62", "192.168.1.70", "192.168.1.66", "192.168.1.68"},
        )
        self.assertEqual({row["name"] for row in listed}, {"1# Entry", "1# Exit", "2# Entry", "2# Exit"})
        lane1 = [row for row in listed if row["gate_name"] == "1#"]
        self.assertEqual({row["ip_address"] for row in lane1}, {"192.168.1.144", "192.168.1.145"})
        entry = next(row for row in lane1 if row["lane_direction"] == "ENTRY")
        self.assertEqual(entry["name"], "1# Entry")
        self.assertEqual(entry["side"], "Entry")
        self.assertEqual(entry["lane_name"], "1#")
        self.assertEqual(entry["controller_ip"], "192.168.1.61")
        self.assertEqual(entry["display_ip"], "192.168.1.62")
        exit_side = next(row for row in listed if row["name"] == "2# Exit")
        self.assertEqual(exit_side["display_ip"], "192.168.1.68")
        self.assertNotEqual(exit_side["display_ip"], "192.168.1.43")
        self.assertEqual(len(first.json()["gates"]), 2)
        gates = self.client.get("/gates", headers=headers).json()
        self.assertEqual({row["name"] for row in gates}, {"1#", "2#"})

    def test_discover_does_not_mark_sdk_connected(self):
        headers = self._login_admin()
        probed = {row["ip_address"]: True for row in KNOWN_SITE_CAMERAS}
        with patch("app.api_main.HVXHostClient") as hvx:
            hvx.return_value.discover = AsyncMock(side_effect=HVXHostUnavailable("host down"))
            with patch("app.api_main.probe_ips", new=AsyncMock(return_value=probed)):
                res = self.client.get("/cameras/discover", headers=headers)
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["sdk_port"], 30000)
        self.assertEqual(len(body["cameras"]), 4)
        for row in body["cameras"]:
            self.assertTrue(row["tcp_open"])
            self.assertTrue(row["reachable"])
            self.assertFalse(row["already_added"])
            self.assertNotEqual(row.get("camera_status"), CameraStatus.SDK_CONNECTED.value)
        self.assertIn("not SDK_CONNECTED", body["note"])

    def test_discover_lan_ip_cameras_are_not_sdk_connected(self):
        headers = self._login_admin()
        probed = {row["ip_address"]: True for row in KNOWN_SITE_CAMERAS}
        generic = [{
            "ip": "10.0.0.77",
            "sdk_open": False,
            "http_open": True,
            "rtsp_open": True,
            "vendor": "dahua",
            "kind": "dahua",
            "adapter_id": "dahua",
        }]
        with patch("app.api_main.HVXHostClient") as hvx:
            hvx.return_value.discover = AsyncMock(side_effect=HVXHostUnavailable("host down"))
            with patch("app.api_main.probe_ips", new=AsyncMock(return_value=probed)):
                with patch("app.api_main.scan_lan_devices", new=AsyncMock(return_value=generic)):
                    res = self.client.get("/cameras/discover?scan_lan=true", headers=headers)
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertTrue(body["scan_lan"])
        by_ip = {row["ip_address"]: row for row in body["cameras"]}
        self.assertEqual(by_ip["192.168.1.144"]["adapter_id"], "hvx")
        self.assertEqual(by_ip["192.168.1.144"]["plate_engine"], "native")
        dahua = by_ip["10.0.0.77"]
        self.assertEqual(dahua["adapter_id"], "dahua")
        self.assertEqual(dahua["plate_engine"], "fastalpr")
        self.assertTrue(dahua["reachable"])
        self.assertNotEqual(dahua.get("camera_status"), CameraStatus.SDK_CONNECTED.value)
        self.assertIn("not SDK_CONNECTED", body["note"])

    def test_connect_all_uses_hvx_login(self):
        headers = self._login_admin()
        self.assertEqual(self.client.post("/cameras/seed-site", headers=headers, json={}).status_code, 200)
        with patch("app.api_main.tcp_open", new=AsyncMock(return_value=True)):
            with patch("app.infrastructure.hardware.cameras.hvx.HVXHostClient") as hvx:
                hvx.return_value.connect = AsyncMock(return_value={
                    "connected": True, "handle": 11, "connect_rc": 0, "connect_rc_name": "DC_NO_ERROR",
                })
                res = self.client.post("/cameras/sdk/connect-all", headers=headers, json={})
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["connected"], 4)
        self.assertEqual(body["attempted"], 4)
        self.assertEqual(body.get("skipped") or 0, 0)
        self.assertIn("camera IPs only", body["note"])
        listed = self.client.get("/cameras", headers=headers).json()
        self.assertEqual(
            {row["ip_address"] for row in listed},
            {"192.168.1.144", "192.168.1.145", "192.168.1.49", "192.168.1.50"},
        )
        self.assertTrue(all(row["status"] == CameraStatus.SDK_CONNECTED.value for row in listed))
        self.assertTrue(all(row["sdk_handle"] == 11 for row in listed))

    def test_connect_all_skips_unreachable_camera(self):
        headers = self._login_admin()
        self.assertEqual(self.client.post("/cameras/seed-site", headers=headers, json={}).status_code, 200)

        async def probe(ip, port, timeout=1.0):
            return ip != "192.168.1.145"

        with patch("app.api_main.tcp_open", new=probe):
            with patch("app.infrastructure.hardware.cameras.hvx.HVXHostClient") as hvx:
                hvx.return_value.connect = AsyncMock(return_value={
                    "connected": True, "handle": 7, "connect_rc": 0, "connect_rc_name": "DC_NO_ERROR",
                })
                res = self.client.post("/cameras/sdk/connect-all", headers=headers, json={})
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["connected"], 3)
        self.assertEqual(body["skipped"], 1)
        self.assertEqual(body["attempted"], 4)
        listed = {row["ip_address"]: row for row in self.client.get("/cameras", headers=headers).json()}
        self.assertEqual(listed["192.168.1.145"]["status"], CameraStatus.SDK_FAILED.value)
        self.assertIn("skipped", listed["192.168.1.145"]["last_error"].lower())
        self.assertEqual(listed["192.168.1.144"]["status"], CameraStatus.SDK_CONNECTED.value)

    def test_preview_shows_native_plate_without_fastalpr(self):
        headers = self._login_admin()
        cam_id = self.client.post("/cameras", headers=headers, json={
            "name": "1# Entry", "ip_address": "192.168.1.144", "recognition_mode": "NATIVE_ONLY",
        }).json()["id"]
        with self.Session() as db:
            camera = db.get(Camera, cam_id)
            camera.status = CameraStatus.SDK_CONNECTED.value
            camera.sdk_handle = 4
            db.commit()
        grabbed = {"ok": False, "error": "No live JPEG"}
        native = {"plate": "T285DQP", "confidence": 0.91, "source": "qy_Net_RegImageRecvEx", "have_vehicle": True}
        with patch("app.api_main.snapshot_for_camera", new=AsyncMock(return_value=grabbed)):
            with patch("app.api_main._native_capture_for_camera", new=AsyncMock(return_value=native)):
                preview = self.client.get(f"/cameras/{cam_id}/preview", headers=headers)
                plates = self.client.get(f"/cameras/{cam_id}/plates", headers=headers)
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.json()["native"]["plate"], "T285DQP")
        self.assertEqual(preview.json()["resolved_plate"], "T285DQP")
        self.assertEqual(plates.status_code, 200)
        self.assertEqual(plates.json()["fusion"]["resolved_plate"], "T285DQP")

    def test_dry_run_open_uses_gpio_board_and_led(self):
        headers = self._login_admin()
        self.assertEqual(self.client.post("/cameras/seed-site", headers=headers, json={}).status_code, 200)
        gates = self.client.get("/gates", headers=headers).json()
        gate_id = next(row["id"] for row in gates if row["name"] == "1#")
        res = self.client.post(f"/gates/{gate_id}/open", headers=headers, json={
            "reason": "commissioning", "dry_run": True, "side": "ENTRY",
        })
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["simulated"])
        self.assertEqual(len(body["actuators"]), 1)
        row = body["actuators"][0]
        self.assertTrue(row["gpio"]["dry_run"])
        self.assertTrue(row["board"]["dry_run"])
        self.assertEqual(row["board"]["ip"], "192.168.1.61")
        self.assertEqual(row["led"]["ip"], "192.168.1.62")
        self.assertEqual(row["led"]["text"], "WELCOME")

    def test_open_without_side_does_not_pulse_both_barriers(self):
        headers = self._login_admin()
        self.assertEqual(self.client.post("/cameras/seed-site", headers=headers, json={}).status_code, 200)
        gates = self.client.get("/gates", headers=headers).json()
        gate_id = next(row["id"] for row in gates if row["name"] == "1#")
        res = self.client.post(f"/gates/{gate_id}/open", headers=headers, json={
            "reason": "commissioning", "dry_run": True,
        })
        self.assertEqual(res.status_code, 409, res.text)
        self.assertIn("ENTRY or EXIT", res.json()["detail"])

    def test_dry_run_open_exit_uses_exit_board_and_led(self):
        headers = self._login_admin()
        self.assertEqual(self.client.post("/cameras/seed-site", headers=headers, json={}).status_code, 200)
        gates = self.client.get("/gates", headers=headers).json()
        gate_id = next(row["id"] for row in gates if row["name"] == "1#")
        res = self.client.post(f"/gates/{gate_id}/open", headers=headers, json={
            "reason": "commissioning", "dry_run": True, "side": "EXIT",
        })
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(len(body["actuators"]), 1)
        row = body["actuators"][0]
        self.assertEqual(row["board"]["ip"], "192.168.1.69")
        self.assertEqual(row["led"]["ip"], "192.168.1.70")
        self.assertEqual(row["led"]["text"], "THANKYOU")

    def test_car1_fee_quote_endpoint(self):
        headers = self._login_admin()
        tariff = self.client.get("/fees/tariff", headers=headers)
        self.assertEqual(tariff.status_code, 200, tariff.text)
        self.assertEqual(tariff.json()["name"], "Car1")
        quote = self.client.post("/fees/quote", headers=headers, json={
            "entry_time": "2026-08-25T10:00:00+00:00",
            "exit_time": "2026-08-25T10:45:01+00:00",
            "car_type": "Car1",
        })
        self.assertEqual(quote.status_code, 200, quote.text)
        self.assertEqual(quote.json()["due"], 1000)

    def test_printer_status_and_registered_vehicles_endpoints(self):
        headers = self._login_admin()
        printer = self.client.get("/printers/status", headers=headers)
        self.assertEqual(printer.status_code, 200, printer.text)
        self.assertEqual(printer.json()["adapter_id"], "simulated")
        listed = self.client.get("/vehicles", headers=headers)
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json(), [])
        missing = self.client.post("/cameras/1/snapshot/capture", headers=headers)
        self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main()
