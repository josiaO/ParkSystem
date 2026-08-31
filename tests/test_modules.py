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
from app.domain.events import EVENT_PLATE_RECOGNIZED, plate_recognized, from_recognition_dict
from app.domain.modules import DEPLOYMENT_PROFILES, MODULES, PROFILE_LPR_ONLY, PROFILE_PARKING_LITE
from app.infrastructure.payments import list_payment_providers, payment_provider_for
from app.models import Gate, Role, SiteSetting, User, UserRole
from app.security import hash_password, user_permissions
from app.services.modules import (
    apply_profile,
    enabled_set,
    ensure_modules_initialized,
    is_enabled,
    list_modules,
    navigation_items,
    save_config,
    set_enabled,
    validate_enablement,
)
from app.services.topology import create_lane, ensure_default_site, site_topology, sync_gate_lanes_from_cameras


class ModuleRegistryTests(unittest.TestCase):
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
            user = User(username="admin", full_name="Admin", password_hash=hash_password("pass"))
            db.add(user)
            db.flush()
            db.add(UserRole(user_id=user.id, role_id=admin_role.id))
            db.commit()
        self.client = TestClient(app)
        token = self.client.post("/auth/login", json={"username": "admin", "password": "pass"}).json()["token"]
        self.headers = {"Authorization": f"Bearer {token}"}

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_default_profile_enables_parking_modules(self):
        with self.Session() as db:
            cfg = ensure_modules_initialized(db)
        self.assertEqual(cfg["profile"], PROFILE_PARKING_LITE)
        self.assertIn("parking.sessions", cfg["enabled"])
        self.assertIn("payments.core", cfg["enabled"])

    def test_lpr_profile_has_no_parking_or_payments(self):
        with self.Session() as db:
            cfg = apply_profile(db, PROFILE_LPR_ONLY)
        enabled = set(cfg["enabled"])
        self.assertIn("recognition.alpr", enabled)
        self.assertNotIn("parking.sessions", enabled)
        self.assertNotIn("payments.core", enabled)
        self.assertNotIn("access.gates", enabled)

    def test_dependency_validation_rejects_orphans(self):
        errors = validate_enablement({"parking.sessions"})
        self.assertTrue(any("requires" in e for e in errors))

    def test_security_without_gates(self):
        with self.Session() as db:
            cfg = apply_profile(db, "SECURITY")
        enabled = set(cfg["enabled"])
        self.assertIn("security.watchlists", enabled)
        self.assertNotIn("access.gates", enabled)

    def test_parking_without_payments_optional(self):
        with self.Session() as db:
            cfg = apply_profile(db, PROFILE_PARKING_LITE)
            enabled = [m for m in cfg["enabled"] if m != "payments.core" and m != "payments.kiosk"]
            # removing payments should fail if parking still expects tariff chain — keep sessions only subset
            enabled = [m for m in enabled if not m.startswith("payments.")]
            errors = validate_enablement(set(enabled))
            self.assertFalse(errors)

    def test_navigation_requires_module_and_permission(self):
        with self.Session() as db:
            apply_profile(db, PROFILE_LPR_ONLY)
            user = db.scalar(select(User).where(User.username == "admin"))
            nav = navigation_items(db, user_permissions(user))
        pages = {row["page"] for row in nav}
        self.assertIn("cameras", pages)
        self.assertNotIn("payments", pages)
        self.assertNotIn("sessions", pages)

    def test_truncated_preset_config_is_repaired(self):
        with self.Session() as db:
            ensure_modules_initialized(db)
            from app.models import SiteSetting
            row = db.get(SiteSetting, "modules")
            row.value = {
                "profile": PROFILE_PARKING_LITE,
                "enabled": ["core.sites", "core.identity"],
                "onboarding_completed": True,
            }
            db.commit()
            cfg = ensure_modules_initialized(db)
        self.assertIn("camera.management", cfg["enabled"])
        self.assertIn("parking.sessions", cfg["enabled"])
        self.assertIn("payments.core", cfg["enabled"])

    def test_api_modules_and_topology(self):
        mods = self.client.get("/modules", headers=self.headers)
        self.assertEqual(mods.status_code, 200)
        body = mods.json()
        self.assertGreaterEqual(len(body["modules"]), len(MODULES))
        topo = self.client.get("/topology", headers=self.headers)
        self.assertEqual(topo.status_code, 200)
        self.assertIn("gates", topo.json())

    def test_onboarding_apply_use_case(self):
        r = self.client.post(
            "/onboarding/step",
            headers=self.headers,
            json={"step": 1, "use_case": "LPR", "activate": True},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["profile"], PROFILE_LPR_ONLY)

    def test_onboarding_full_wizard_steps(self):
        status = self.client.get("/onboarding/status", headers=self.headers)
        self.assertEqual(status.status_code, 200)
        body = status.json()
        self.assertEqual(len(body["steps"]), 8)
        self.assertTrue(body["optional_module_choices"])

        r1 = self.client.post(
            "/onboarding/step",
            headers=self.headers,
            json={"step": 2, "use_case": "PARKING"},
        )
        self.assertEqual(r1.status_code, 200)

        r2 = self.client.post(
            "/onboarding/step",
            headers=self.headers,
            json={
                "step": 3,
                "topology": {"preset": "1in1out"},
                "site": {"name": "Wizard Site", "timezone": "UTC", "currency": "USD"},
            },
        )
        self.assertEqual(r2.status_code, 200)
        topo = self.client.get("/topology", headers=self.headers).json()
        self.assertGreaterEqual(topo["counts"]["gates"], 1)
        self.assertGreaterEqual(topo["counts"]["lanes"], 2)

        r4 = self.client.post(
            "/onboarding/step",
            headers=self.headers,
            json={"step": 5, "recognition_mode": "HYBRID", "hardware": {"reviewed": True}},
        )
        self.assertEqual(r4.status_code, 200)

        r5 = self.client.post(
            "/onboarding/step",
            headers=self.headers,
            json={
                "step": 6,
                "optional_modules": ["parking.sessions", "parking.tariffs", "payments.core"],
            },
        )
        self.assertEqual(r5.status_code, 200)
        self.assertIn("parking.sessions", r5.json()["enabled"])

        r8 = self.client.post(
            "/onboarding/step",
            headers=self.headers,
            json={"step": 8, "health_ok": True, "activate": True},
        )
        self.assertEqual(r8.status_code, 200)
        self.assertTrue(r8.json()["onboarding_completed"])

    def test_me_includes_navigation(self):
        me = self.client.get("/auth/me", headers=self.headers).json()
        self.assertIn("navigation", me)
        self.assertIn("modules", me)


class TopologyTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_multi_gate_topology(self):
        with self.Session() as db:
            ensure_default_site(db)
            for i in range(3):
                db.add(Gate(name=f"Gate-{i}", enabled=True))
            db.commit()
            for i in range(7):
                create_lane(db, name=f"Lane-{i}", gate_id=1 + (i % 3), direction="ENTRY" if i % 2 == 0 else "EXIT")
            body = site_topology(db)
        self.assertEqual(body["counts"]["gates"], 3)
        self.assertEqual(body["counts"]["lanes"], 7)

    def test_zero_gate_lpr_topology(self):
        with self.Session() as db:
            ensure_default_site(db)
            body = site_topology(db)
        self.assertEqual(body["counts"]["gates"], 0)

    def test_sync_lanes_from_legacy_cameras(self):
        with self.Session() as db:
            gate = Gate(name="1#", enabled=True)
            db.add(gate)
            db.commit()
            from app.models import Camera

            db.add(Camera(name="Entry cam", ip_address="10.0.0.1", gate_id=gate.id, lane_direction="ENTRY"))
            db.add(Camera(name="Exit cam", ip_address="10.0.0.2", gate_id=gate.id, lane_direction="EXIT"))
            db.commit()
            created = sync_gate_lanes_from_cameras(db)
            body = site_topology(db)
        self.assertGreaterEqual(created, 2)
        self.assertGreaterEqual(body["counts"]["lanes"], 2)


class EventContractTests(unittest.TestCase):
    def test_plate_recognized_shape(self):
        event = plate_recognized(
            site_id=1,
            camera_id=2,
            plate_text_raw="T 285 DQP",
            plate_text_normalized="T285DQP",
            recognition_provider="FASTALPR",
            confidence=0.93,
        )
        self.assertEqual(event["kind"], EVENT_PLATE_RECOGNIZED)
        payload = event["payload"]
        self.assertEqual(payload["plate_text_normalized"], "T285DQP")
        self.assertEqual(payload["recognition_provider"], "FASTALPR")

    def test_bridge_from_legacy_recognition_dict(self):
        bridged = from_recognition_dict({
            "camera_id": 4,
            "raw_plate": "abc-1",
            "normalized_plate": "ABC1",
            "source": "HVX_NATIVE",
            "confidence": 0.88,
        })
        self.assertEqual(bridged["kind"], EVENT_PLATE_RECOGNIZED)


class AdapterRegistryTests(unittest.TestCase):
    def test_payment_provider_registry(self):
        self.assertIn("kiosk_manual", list_payment_providers())
        provider = payment_provider_for("kiosk_manual")
        self.assertEqual(provider.id, "kiosk_manual")


class DocsExistTests(unittest.TestCase):
    def test_module_docs_tree(self):
        root = ROOT / "docs"
        for path in (
            "modules/OVERVIEW.md",
            "modules/DEPENDENCY-GRAPH.md",
            "modules/MODULE-REGISTRY.md",
            "onboarding/DEPLOYMENT-PROFILES.md",
            "development/MODULE-CONTRACTS.md",
        ):
            self.assertTrue((root / path).is_file(), path)


if __name__ == "__main__":
    unittest.main()
