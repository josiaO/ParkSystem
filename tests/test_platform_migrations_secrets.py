"""§11/§12 platform slice: Alembic runner, site-scoped constraints, SecretStore, redaction."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api_main import app, ensure_roles
from app.db import Base, get_db, set_session_factory
from app.infrastructure import secrets as secret_mod
from app.migrations.runner import current_revision, head_revision, upgrade_to_head
from app.models import AccessPlan, Camera, Gate, RegisteredVehicle, Role, Site, Tariff, User, UserRole
from app.security import hash_password
from app.services import redaction
from app.services.secrets_migration import migrate_plaintext_secrets


LEGACY_SQL = [
    "CREATE TABLE sites (id INTEGER NOT NULL, name VARCHAR(160) NOT NULL, timezone VARCHAR(80) NOT NULL, "
    "locale VARCHAR(20) NOT NULL, currency VARCHAR(8) NOT NULL, enabled BOOLEAN NOT NULL, PRIMARY KEY (id))",
    "CREATE TABLE gates (id INTEGER NOT NULL, name VARCHAR(120) NOT NULL, mode VARCHAR(30) NOT NULL, "
    "enabled BOOLEAN NOT NULL, physical_control_verified BOOLEAN NOT NULL, site_id INTEGER, zone_id INTEGER, "
    "PRIMARY KEY (id), UNIQUE (name))",
    "CREATE TABLE cameras (id INTEGER NOT NULL, name VARCHAR(120) NOT NULL, ip_address VARCHAR(64) NOT NULL, "
    "sdk_port INTEGER NOT NULL, username VARCHAR(120) NOT NULL, password_secret VARCHAR(300) NOT NULL, "
    "gate_id INTEGER, lane_direction VARCHAR(20) NOT NULL, rtsp_url TEXT NOT NULL, status VARCHAR(30) NOT NULL, "
    "sdk_handle INTEGER, last_error TEXT NOT NULL, last_seen_at DATETIME, enabled BOOLEAN NOT NULL, "
    "PRIMARY KEY (id), UNIQUE (name), FOREIGN KEY(gate_id) REFERENCES gates (id))",
    "CREATE INDEX ix_cameras_ip_address ON cameras (ip_address)",
    "CREATE TABLE tariffs (id INTEGER NOT NULL, name VARCHAR(80) NOT NULL, car_type VARCHAR(40) NOT NULL, "
    "currency VARCHAR(8) NOT NULL, source VARCHAR(200) NOT NULL, rules JSON, active BOOLEAN NOT NULL, "
    "created_at DATETIME NOT NULL, PRIMARY KEY (id), UNIQUE (name))",
    "CREATE TABLE access_plans (id INTEGER NOT NULL, name VARCHAR(80) NOT NULL, kind VARCHAR(40) NOT NULL, "
    "auto_open BOOLEAN NOT NULL, print_receipt BOOLEAN NOT NULL, enabled BOOLEAN NOT NULL, notes TEXT NOT NULL, "
    "PRIMARY KEY (id), UNIQUE (name))",
    "CREATE TABLE registered_vehicles (id INTEGER NOT NULL, plate VARCHAR(32) NOT NULL, owner_name VARCHAR(160) NOT NULL, "
    "plan_id INTEGER, enabled BOOLEAN NOT NULL, valid_from DATETIME, valid_until DATETIME, notes TEXT NOT NULL, "
    "created_at DATETIME NOT NULL, PRIMARY KEY (id), FOREIGN KEY(plan_id) REFERENCES access_plans (id))",
    "CREATE UNIQUE INDEX ix_registered_vehicles_plate ON registered_vehicles (plate)",
    "CREATE TABLE users (id INTEGER NOT NULL, username VARCHAR(80) NOT NULL, full_name VARCHAR(160) NOT NULL, "
    "password_hash VARCHAR(255) NOT NULL, status VARCHAR(20) NOT NULL, created_at DATETIME NOT NULL, PRIMARY KEY (id))",
    "CREATE TABLE vehicle_captures (id INTEGER NOT NULL, camera_id INTEGER, gate_id INTEGER, lane_direction VARCHAR(20) NOT NULL, "
    "plate VARCHAR(32) NOT NULL, plate_raw VARCHAR(32) NOT NULL, confidence NUMERIC(6, 3) NOT NULL, image_id INTEGER NOT NULL, "
    "snapshot_path VARCHAR(260) NOT NULL, crop_path VARCHAR(260) NOT NULL, bbox JSON, created_at DATETIME NOT NULL, PRIMARY KEY (id))",
    "INSERT INTO gates (id, name, mode, enabled, physical_control_verified) VALUES (7, '1#', 'COMMISSIONING', 1, 0)",
    "INSERT INTO cameras (id, name, ip_address, sdk_port, username, password_secret, lane_direction, rtsp_url, status, "
    "last_error, enabled) VALUES (3, 'Entry', '192.168.1.10', 30000, 'admin', 'legacy-pass', 'ENTRY', '', 'UNKNOWN', '', 1)",
    "INSERT INTO registered_vehicles (id, plate, owner_name, enabled, notes, created_at) "
    "VALUES (1, 'T123ABC', 'Owner', 1, '', '2026-01-01 00:00:00')",
]


class AlembicRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _engine(self, name: str):
        return create_engine(f"sqlite:///{Path(self.tmp.name) / name}")

    def test_fresh_database_is_created_and_stamped_at_head(self):
        engine = self._engine("fresh.db")
        summary = upgrade_to_head(engine)
        self.assertEqual(summary["mode"], "fresh")
        self.assertEqual(current_revision(engine), head_revision())
        self.assertIn("cameras", inspect(engine).get_table_names())
        self.assertEqual(upgrade_to_head(engine)["mode"], "upgrade")

    def test_pre_alembic_sqlite_is_adopted_and_site_scoped(self):
        engine = self._engine("legacy.db")
        with engine.begin() as conn:
            for stmt in LEGACY_SQL:
                conn.exec_driver_sql(stmt)
        summary = upgrade_to_head(engine)
        self.assertEqual(summary["mode"], "adopt")
        self.assertIn("cameras.adapter_id", summary["legacy_fixups"])
        self.assertIn("vehicle_captures.source", summary["legacy_fixups"])
        self.assertEqual(current_revision(engine), head_revision())

        insp = inspect(engine)
        for table, column in (("gates", "name"), ("cameras", "name"), ("tariffs", "name"),
                              ("access_plans", "name"), ("registered_vehicles", "plate")):
            cols = {c["name"] for c in insp.get_columns(table)}
            self.assertIn("site_id", cols, table)
            uniques = insp.get_unique_constraints(table)
            self.assertEqual([u["column_names"] for u in uniques], [["site_id", column]], table)
        self.assertIn("credentials_ref", {c["name"] for c in insp.get_columns("cameras")})
        self.assertFalse(any(i["unique"] for i in insp.get_indexes("registered_vehicles")))
        self.assertIn("ai_review", {c["name"] for c in insp.get_columns("vehicle_captures")})  # 0003

        with engine.connect() as conn:
            self.assertEqual(conn.execute(text("SELECT site_id FROM gates WHERE id=7")).scalar(), 1)
            self.assertEqual(conn.execute(text("SELECT site_id, password_secret FROM cameras WHERE id=3")).first(), (1, "legacy-pass"))
            self.assertEqual(conn.execute(text("SELECT id FROM sites WHERE id=1")).scalar(), 1)

        Session = sessionmaker(bind=engine)
        with Session() as db:
            db.add(Site(id=2, name="Second"))
            db.add(Gate(name="1#", site_id=2))
            db.add(RegisteredVehicle(plate="T123ABC", site_id=2))
            db.commit()
            self.assertEqual(db.scalar(select(Gate).where(Gate.id == 7)).site_id, 1)
            db.add(Gate(name="1#"))  # default site again -> conflict
            with self.assertRaises(IntegrityError):
                db.commit()
        self.assertEqual(upgrade_to_head(engine)["mode"], "upgrade")

    def test_legacy_module_is_frozen(self):
        from app.migrations import legacy
        self.assertNotIn("credentials_ref", [c for cols in legacy.LEGACY_TABLES.values() for c, _ in cols])
        self.assertNotIn("site_id", [c for c, _ in legacy.LEGACY_TABLES["cameras"]])


class SiteScopedModelTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)

    def tearDown(self):
        self.engine.dispose()

    def test_names_are_unique_per_site_not_globally(self):
        with self.Session() as db:
            db.add_all([Site(id=1, name="A"), Site(id=2, name="B")])
            db.add_all([
                Camera(name="Entry", ip_address="10.0.0.1"), Camera(name="Entry", ip_address="10.0.0.2", site_id=2),
                Tariff(name="Car1"), Tariff(name="Car1", site_id=2),
                AccessPlan(name="Staff"), AccessPlan(name="Staff", site_id=2),
            ])
            db.commit()
            self.assertEqual(db.scalar(select(Camera).where(Camera.ip_address == "10.0.0.1")).site_id, 1)
            db.add(Camera(name="Entry", ip_address="10.0.0.3"))
            with self.assertRaises(IntegrityError):
                db.commit()


class SecretStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        redaction.forget_all_secrets()

    def tearDown(self):
        secret_mod.set_secret_store(None)
        redaction.forget_all_secrets()
        self.tmp.cleanup()

    def test_file_store_round_trip_is_private(self):
        store = secret_mod.FileSecretStore(Path(self.tmp.name) / "secrets")
        ref = secret_mod.new_ref("camera")
        self.assertTrue(secret_mod.is_ref(ref))
        store.put(ref, "rtsp-pass")
        self.assertEqual(store.get(ref), "rtsp-pass")
        path = store._path(ref)
        if os.name == "posix":
            self.assertEqual(oct(path.stat().st_mode & 0o777), "0o600")
        store.delete(ref)
        self.assertFalse(store.exists(ref))
        with self.assertRaises(secret_mod.SecretStoreError):
            store.get(ref)
        with self.assertRaises(secret_mod.SecretStoreError):
            store.put("../etc/passwd", "x")

    def test_camera_password_property_uses_external_store(self):
        secret_mod.set_secret_store(secret_mod.MemorySecretStore())
        cam = Camera(name="C", ip_address="1.2.3.4", password_secret="hunter22")
        self.assertEqual(cam._password_secret, "")
        self.assertTrue(cam.credentials_ref.startswith("camera:"))
        self.assertEqual(cam.password_secret, "hunter22")
        first_ref = cam.credentials_ref
        cam.password_secret = "rotated!"
        self.assertEqual(cam.credentials_ref, first_ref)  # ref is stable across rotation
        self.assertEqual(cam.password_secret, "rotated!")
        self.assertTrue(cam.has_password())
        # the raw value is now a registered secret for redaction
        self.assertNotIn("rotated!", redaction.redact_text("camera failed with rotated! in body"))

    def test_db_backend_keeps_legacy_column(self):
        secret_mod.set_secret_store(secret_mod.DatabaseSecretStore())
        cam = Camera(name="C", ip_address="1.2.3.4", password_secret="plain")
        self.assertEqual(cam._password_secret, "plain")
        self.assertFalse(cam.credentials_ref)
        self.assertEqual(cam.password_secret, "plain")

    def test_startup_migration_moves_plaintext_rows(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        secret_mod.set_secret_store(secret_mod.DatabaseSecretStore())
        with Session() as db:
            db.add(Site(id=1, name="A"))
            db.add(Camera(name="Legacy", ip_address="1.1.1.1", password_secret="old-plain"))
            db.commit()
        secret_mod.set_secret_store(secret_mod.MemorySecretStore())
        with Session() as db:
            summary = migrate_plaintext_secrets(db)
            self.assertEqual(summary["moved"], 1)
            cam = db.scalar(select(Camera))
            self.assertEqual(cam._password_secret, "")
            self.assertTrue(cam.credentials_ref)
            self.assertEqual(cam.password_secret, "old-plain")
            self.assertEqual(migrate_plaintext_secrets(db)["moved"], 0)
        engine.dispose()

    def test_db_rollback_still_reads_moved_credentials(self):
        root = Path(self.tmp.name) / "secrets"
        file_store = secret_mod.FileSecretStore(root)
        ref = file_store.put(secret_mod.new_ref("camera"), "moved-pass")
        secret_mod.set_secret_store(secret_mod.DatabaseSecretStore())
        with patch.object(secret_mod.settings.__class__, "data_dir", property(lambda _s: Path(self.tmp.name))), \
                patch("platform.system", return_value="Linux"):
            self.assertEqual(secret_mod.resolve_secret(ref, fallback=""), "moved-pass")
            self.assertEqual(secret_mod.resolve_secret(ref, fallback="column-wins"), "column-wins")
            self.assertEqual(secret_mod.resolve_secret("camera:" + "0" * 32, fallback=""), "")

    def test_backend_selection(self):
        with patch.object(secret_mod.settings, "secrets_backend", "auto"), patch("platform.system", return_value="Windows"):
            self.assertEqual(secret_mod.configured_backend(), "dpapi")
        with patch.object(secret_mod.settings, "secrets_backend", "auto"), patch("platform.system", return_value="Linux"):
            self.assertEqual(secret_mod.configured_backend(), "db")
        with patch.object(secret_mod.settings, "secrets_backend", "dpapi"), patch("platform.system", return_value="Linux"):
            self.assertEqual(secret_mod.configured_backend(), "file")
        with patch.object(secret_mod.settings, "secrets_backend", "bogus"):
            self.assertEqual(secret_mod.configured_backend(), "db")


class RedactionTests(unittest.TestCase):
    def setUp(self):
        redaction.forget_all_secrets()

    def tearDown(self):
        redaction.forget_all_secrets()

    def test_patterns(self):
        out = redaction.redact_text("rtsp://admin:S3cret!@10.0.0.5:554/live failed; api_key=FLWSECK_TEST-abcdef0123456789-X token: abc")
        self.assertNotIn("S3cret!", out)
        self.assertIn("rtsp://admin:***@10.0.0.5:554/live", out)
        self.assertNotIn("FLWSECK_TEST-abcdef0123456789-X", out)
        self.assertIn("token: ***", out)
        self.assertEqual(redaction.redact_text("AIzaSyA1234567890abcdefghijklmnop"), "***")

    def test_registered_and_settings_secrets(self):
        redaction.register_secret("very-secret-value")
        redaction.register_secret("admin")  # too common, never registered
        self.assertEqual(redaction.redact_text("x very-secret-value y"), "x *** y")
        self.assertEqual(redaction.redact_text("admin"), "admin")
        with patch("app.config.settings.flutterwave_secret_key", "FLWSECK_TEST-zzzz1111yyyy2222-X"):
            self.assertNotIn("zzzz1111", redaction.redact_text("key FLWSECK_TEST-zzzz1111yyyy2222-X here"))

    def test_redact_obj_masks_keys_but_keeps_identifiers(self):
        body = {
            "password": "x", "api_key": "k", "secret_hash": "h", "checksum": "c", "pin": "1234",
            "phone": "+255712345678", "customer_phone": "255712345678",
            "credentials_ref": "camera:abc123", "idempotency_key": "mobile:tx-1", "public_token": "tok",
            "active_mobile_provider": "simulated", "token_cached": True, "webhook_secret_configured": True,
            "rtsp_url": "rtsp://u:p@h/x", "nested": [{"authorization": "Bearer abc"}], "mapping": {"a": 1},
            "blob": b"\x00\x01",
        }
        out = redaction.redact_obj(body)
        for key in ("password", "api_key", "secret_hash", "checksum", "pin"):
            self.assertEqual(out[key], "***", key)
        self.assertEqual(out["phone"], "*********678")
        self.assertEqual(out["credentials_ref"], "camera:abc123")
        self.assertEqual(out["idempotency_key"], "mobile:tx-1")
        self.assertEqual(out["public_token"], "tok")
        self.assertEqual(out["active_mobile_provider"], "simulated")
        self.assertIs(out["token_cached"], True)
        self.assertEqual(out["rtsp_url"], "rtsp://u:***@h/x")
        self.assertEqual(out["nested"][0]["authorization"], "***")
        self.assertEqual(out["mapping"], {"a": 1})
        self.assertEqual(out["blob"], "<2 bytes>")

    def test_logging_filter(self):
        redaction.register_secret("log-secret-123")
        log = logging.getLogger("smartpark.test.redaction")
        log.propagate = False
        records: list[str] = []

        class Sink(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        sink = Sink()
        log.addHandler(sink)
        redaction.install_logging_redaction(log)
        try:
            log.warning("camera %s failed: %s", "rtsp://a:b@h/", "log-secret-123 password=xyz")
        finally:
            log.removeHandler(sink)
        self.assertEqual(len(records), 1)
        self.assertNotIn("a:b@", records[0])
        self.assertNotIn("log-secret-123", records[0])
        self.assertIn("password=***", records[0])


class PlatformApiTests(unittest.TestCase):
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
        set_session_factory(self.Session)
        secret_mod.set_secret_store(secret_mod.MemorySecretStore())
        redaction.forget_all_secrets()
        with self.Session() as db:
            ensure_roles(db)
            db.add(Site(id=1, name="A"))
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
        set_session_factory(None)
        secret_mod.set_secret_store(None)
        redaction.forget_all_secrets()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_camera_create_stores_ref_and_never_returns_password(self):
        res = self.client.post("/cameras", json={
            "name": "Cam A", "ip_address": "10.0.0.9", "adapter_id": "rtsp", "username": "admin",
            "password": "TopSecretPw1", "rtsp_url": "rtsp://admin:TopSecretPw1@10.0.0.9/live",
        }, headers=self.headers)
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertNotIn("TopSecretPw1", res.text)
        self.assertTrue(body["credentials_ref"].startswith("camera:"))
        self.assertTrue(body["password_configured"])
        self.assertEqual(body["site_id"], 1)
        with self.Session() as db:
            cam = db.scalar(select(Camera))
            self.assertEqual(cam._password_secret, "")
            self.assertEqual(cam.password_secret, "TopSecretPw1")
            ref = cam.credentials_ref
        self.assertTrue(secret_mod.secret_store().exists(ref))
        res = self.client.delete(f"/cameras/{body['id']}", headers=self.headers)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertFalse(secret_mod.secret_store().exists(ref))

    def test_duplicate_camera_name_still_conflicts_within_site(self):
        for _ in range(2):
            res = self.client.post("/cameras", json={"name": "Dup", "ip_address": "10.0.0.1", "adapter_id": "rtsp"}, headers=self.headers)
        self.assertEqual(res.status_code, 409, res.text)

    def test_diagnostics_bundle_is_redacted(self):
        self.client.post("/cameras", json={
            "name": "Cam B", "ip_address": "10.0.0.8", "adapter_id": "rtsp", "username": "admin",
            "password": "DiagSecret99", "rtsp_url": "rtsp://admin:DiagSecret99@10.0.0.8/live",
        }, headers=self.headers)
        res = self.client.get("/health/diagnostics", headers=self.headers)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertNotIn("DiagSecret99", res.text)
        body = res.json()
        self.assertEqual(body["secret_store"]["backend"], "memory")
        self.assertIn("schema", body)
        self.assertEqual(body["cameras"][0]["rtsp_url"], "rtsp://admin:***@10.0.0.8/live")
        self.assertTrue(body["cameras"][0]["password_configured"])
        self.assertNotIn("password_secret", body["cameras"][0])
        res = self.client.get("/health/diagnostics")
        self.assertEqual(res.status_code, 401)

    def test_http_exception_detail_is_redacted(self):
        # Force a 404 whose detail embeds a credential URL through the public route surface.
        from fastapi import HTTPException
        from app.api_main import _redacted_http_exception
        import asyncio

        exc = HTTPException(400, "cannot reach rtsp://admin:Hidden42@10.0.0.3/live")
        response = asyncio.run(_redacted_http_exception(None, exc))
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("Hidden42", response.body.decode())
        self.assertIn("rtsp://admin:***@10.0.0.3/live", response.body.decode())


if __name__ == "__main__":
    unittest.main()
