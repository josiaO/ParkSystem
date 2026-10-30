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
from app.models import Node, NodeGateAssignment, Role, User, UserRole
from app.security import hash_password
from app.services.node_scope import (
    camera_active_on_this_installation,
    camera_in_recognition_scope,
    camera_visible_in_management,
    reset_recognition_scope,
    set_recognition_gate_id,
)
from app.services.preview import stop_live_pumps


class NodeScopeTests(unittest.TestCase):
    def test_production_owner_assignment_persists_entry_and_exit_only(self):
        from app.config import settings
        from app.services.node_scope import describe_recognition_scope
        with patch.object(settings, "deployment_profile", "PRODUCTION"), patch.object(settings, "recognition_gate_id", None), patch.object(settings, "recognition_all_gates_enabled", False):
            with self.Session() as db:
                self.assertEqual(describe_recognition_scope(db)["mode"], "unassigned")
            response = self.client.put("/runtime/recognition-owner", headers=self.headers, json={"gate_id": self.gate1["id"]})
            self.assertEqual(response.status_code, 200, response.text)
            reset_recognition_scope()
            with self.Session() as db:
                scope = describe_recognition_scope(db)
                self.assertEqual({row["id"] for row in scope["cameras"]}, {self.cam1e["id"], self.cam1x["id"]})
                self.assertFalse(camera_in_recognition_scope(self.cam2e, db=db))
            from app.recognition_worker import _camera_rows
            with patch("app.db.SessionLocal", self.Session), patch("app.services.flags.media_mtx_for_camera", return_value=True), patch("app.recognition_worker._software_camera", return_value=True):
                self.assertEqual({row["id"] for row in _camera_rows()}, {self.cam1e["id"], self.cam1x["id"], self.cam2e["id"]})
            response = self.client.post("/runtime/recognition-scope", headers=self.headers, json={"gate_id": self.gate2["id"]})
            self.assertEqual(response.status_code, 409)
            response = self.client.get("/runtime/recognition-scope", headers=self.headers)
            self.assertEqual(response.json()["gate_id"], self.gate1["id"])

    def test_owner_assignment_rejects_all_gates_unknown_gate_and_env_override(self):
        from app.config import settings
        for gate_id, expected in ((None, 422), (-1, 422), (999999, 404)):
            response = self.client.put("/runtime/recognition-owner", headers=self.headers, json={"gate_id": gate_id})
            self.assertEqual(response.status_code, expected, response.text)
        with patch.object(settings, "recognition_gate_id", self.gate1["id"]):
            response = self.client.put("/runtime/recognition-owner", headers=self.headers, json={"gate_id": self.gate2["id"]})
            self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.put("/runtime/recognition-owner", json={"gate_id": self.gate1["id"]}).status_code, 401)

    def test_database_assignment_overrides_stale_process_local_selection(self):
        from app.models import SiteSetting
        from app.services.node_scope import recognition_gate_id
        set_recognition_gate_id(self.gate1["id"])
        with self.Session() as db:
            db.add(SiteSetting(key="node", value={"recognition_gate_id": self.gate2["id"]}))
            db.commit()
        with self.Session() as db:
            self.assertEqual(recognition_gate_id(db), self.gate2["id"])

    def test_operator_cannot_reassign_production_owner(self):
        with self.Session() as db:
            role = db.scalar(select(Role).where(Role.name == "Operator"))
            user = User(username="operator", full_name="Operator", password_hash=hash_password("operator-pass"))
            db.add(user)
            db.flush()
            db.add(UserRole(user_id=user.id, role_id=role.id))
            db.commit()
        token = self.client.post("/auth/login", json={"username": "operator", "password": "operator-pass"}).json()["token"]
        response = self.client.put("/runtime/recognition-owner", headers={"Authorization": f"Bearer {token}"}, json={"gate_id": self.gate1["id"]})
        self.assertEqual(response.status_code, 403, response.text)

    def test_human_admin_token_keeps_central_permissions_on_edge_pc(self):
        """Human RBAC is independent from the physical computer role."""
        from unittest.mock import patch

        with patch("app.security._processing_node_installation", return_value=True), \
             patch("app.services.node_scope.deployment_role", return_value="EDGE_NODE"):
            me = self.client.get("/auth/me", headers=self.headers)
            self.assertEqual(me.status_code, 200, me.text)

            for path in ("/users", "/roles", "/modules", "/settings/site"):
                response = self.client.get(path, headers=self.headers) if path != "/settings/site" else self.client.patch(path, headers=self.headers, json={})
                self.assertNotEqual(response.status_code, 403, f"{path}: {response.text}")

            setup = self.client.get("/auth/setup")
            self.assertEqual(setup.status_code, 200, setup.text)

    def test_camera_response_never_exposes_secret_store_reference(self):
        response = self.client.get("/cameras", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        for camera in response.json():
            self.assertNotIn("credentials_ref", camera)
            self.assertNotIn("password_secret", camera)

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

    def test_clearing_scope_does_not_invent_a_production_gate(self):
        self.client.post("/runtime/recognition-scope", headers=self.headers, json={"gate_id": self.gate1["id"]})
        body = self.client.post("/runtime/recognition-scope", headers=self.headers, json={"gate_id": None})
        self.assertIsNone(body.json()["gate_id"])
        with self.Session() as db:
            from app.config import settings
            with patch.object(settings, "deployment_profile", "PRODUCTION"), patch.object(settings, "recognition_all_gates_enabled", False):
                self.assertFalse(camera_in_recognition_scope(self.cam2e, db=db))

    def test_unassigned_site_server_can_list_cameras_for_commissioning(self):
        from app.config import settings

        with patch.object(settings, "deployment_profile", "PRODUCTION"), \
             patch.object(settings, "recognition_gate_id", None), \
             patch.object(settings, "recognition_all_gates_enabled", False), \
             patch("app.services.node_scope.site_server_can_manage_unassigned_cameras", return_value=True):
            with self.Session() as db:
                self.assertTrue(camera_visible_in_management(self.cam1e, db=db))
                self.assertTrue(camera_visible_in_management(self.cam2e, db=db))
            response = self.client.get("/cameras", headers=self.headers)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual({row["id"] for row in response.json()}, {self.cam1e["id"], self.cam1x["id"], self.cam2e["id"]})

    def test_site_server_management_stays_global_after_gate_assignment(self):
        """A server-side gate test must not hide another lane's registry rows."""
        from app.config import settings

        with patch.object(settings, "deployment_profile", "PRODUCTION"), \
             patch.object(settings, "recognition_gate_id", self.gate1["id"]), \
             patch.object(settings, "recognition_all_gates_enabled", False), \
             patch("app.services.node_scope.site_server_can_manage_unassigned_cameras", return_value=True):
            response = self.client.get("/cameras", headers=self.headers)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(
                {row["id"] for row in response.json()},
                {self.cam1e["id"], self.cam1x["id"], self.cam2e["id"]},
            )
            # The Site Server owns every local producer; only an EDGE_NODE
            # applies the selected gate as a hardware boundary.
            by_id = {row["id"]: row for row in response.json()}
            self.assertTrue(by_id[self.cam1e["id"]]["stream_allowed"])
            self.assertTrue(by_id[self.cam2e["id"]]["stream_allowed"])

    def test_site_server_releases_gate_owned_by_active_edge_node(self):
        """The central registry stays visible, but the server hardware must stay idle."""
        from app.config import settings

        with self.Session() as db:
            node = Node(node_id="edge-1", site_id=1, name="Remote lane", node_type="EDGE_NODE", status="ACTIVE")
            db.add(node)
            db.flush()
            db.add(NodeGateAssignment(node_id=node.id, gate_id=self.gate1["id"], enabled=True))
            db.commit()
            with patch.object(settings, "deployment_profile", "PRODUCTION"), \
                 patch("app.services.node_scope.deployment_role", return_value="SITE_SERVER"):
                self.assertFalse(camera_active_on_this_installation(self.cam1e, db=db))
                self.assertTrue(camera_active_on_this_installation(self.cam2e, db=db))
                self.assertTrue(camera_visible_in_management(self.cam1e, db=db))

        with patch("app.services.node_scope.deployment_role", return_value="SITE_SERVER"):
            response = self.client.get("/cameras", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        by_id = {row["id"]: row for row in response.json()}
        self.assertFalse(by_id[self.cam1e["id"]]["stream_allowed"])
        self.assertTrue(by_id[self.cam2e["id"]]["stream_allowed"])

    def test_edge_node_cannot_manage_central_node_registry(self):
        with patch("app.services.node_scope.deployment_role", return_value="EDGE_NODE"):
            response = self.client.get("/nodes", headers=self.headers)
        self.assertEqual(response.status_code, 403, response.text)

    def test_unassigned_edge_node_stays_hidden_and_fail_closed(self):
        from app.config import settings

        with patch.object(settings, "deployment_profile", "PRODUCTION"), \
             patch.object(settings, "recognition_gate_id", None), \
             patch.object(settings, "recognition_all_gates_enabled", False), \
             patch("app.services.node_scope.site_server_can_manage_unassigned_cameras", return_value=False):
            with self.Session() as db:
                self.assertFalse(camera_visible_in_management(self.cam1e, db=db))
            response = self.client.get("/cameras", headers=self.headers)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json(), [])

    def test_unassigned_processing_node_never_defaults_to_all_cameras(self):
        """A fresh node must not inherit the server's camera scope."""
        from app.config import settings

        with patch.object(settings, "deployment_profile", "DEVELOPMENT"), \
             patch.object(settings, "recognition_gate_id", None), \
             patch.object(settings, "recognition_all_gates_enabled", True), \
             patch("app.services.node_scope.deployment_role", return_value="EDGE_NODE"):
            with self.Session() as db:
                self.assertFalse(camera_in_recognition_scope(self.cam1e, db=db))
                self.assertFalse(camera_in_recognition_scope(self.cam1x, db=db))
                self.assertFalse(camera_visible_in_management(self.cam1e, db=db))
            response = self.client.get("/cameras", headers=self.headers)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json(), [])

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

    def test_shared_database_keeps_assignments_per_computer(self):
        from app.config import settings
        from app.services.node_scope import recognition_gate_id

        with self.Session() as db:
            with patch.object(settings, "node_id", "lane-server"):
                set_recognition_gate_id(self.gate1["id"], db)
            reset_recognition_scope()
            with patch.object(settings, "node_id", "lane-client"):
                set_recognition_gate_id(self.gate2["id"], db)
            reset_recognition_scope()
            with patch.object(settings, "node_id", "lane-server"):
                self.assertEqual(recognition_gate_id(db), self.gate1["id"])
            with patch.object(settings, "node_id", "lane-client"):
                self.assertEqual(recognition_gate_id(db), self.gate2["id"])

    def test_viewing_another_gate_is_rejected_without_changing_assignment(self):
        set_recognition_gate_id(self.gate1["id"])
        from app.config import settings
        with patch.object(settings, "deployment_profile", "PRODUCTION"), patch.object(settings, "recognition_all_gates_enabled", False), patch("app.services.node_scope.deployment_role", return_value="EDGE_NODE"):
            response = self.client.get(f"/cameras/{self.cam2e['id']}/live/endpoint", headers=self.headers)
        self.assertEqual(response.status_code, 403, response.text)
        from app.services.node_scope import recognition_gate_id
        self.assertEqual(recognition_gate_id(), self.gate1["id"])

    def test_all_media_boundaries_reject_another_nodes_camera(self):
        """A node must fail closed before it opens a foreign camera producer."""
        from app.config import settings

        set_recognition_gate_id(self.gate1["id"])
        foreign = self.cam2e["id"]
        with patch.object(settings, "deployment_profile", "PRODUCTION"), patch.object(settings, "recognition_all_gates_enabled", False), patch("app.services.node_scope.deployment_role", return_value="EDGE_NODE"):
            requests = [
                self.client.get(f"/cameras/{foreign}/streams", headers=self.headers),
                self.client.get(f"/cameras/{foreign}/snapshot.jpg", headers=self.headers),
                self.client.get(f"/cameras/{foreign}/preview", headers=self.headers),
                self.client.post(f"/cameras/{foreign}/live/viewer-state", headers=self.headers, json={"transport": "MJPEG"}),
                self.client.post(f"/cameras/{foreign}/live/watch", headers=self.headers),
                self.client.post(f"/cameras/{foreign}/live/whep", headers=self.headers, content=b""),
                self.client.post(f"/cameras/{foreign}/rtsp/probe", headers=self.headers),
            ]
        self.assertTrue(all(response.status_code == 403 for response in requests), [response.status_code for response in requests])

    def test_processing_node_can_only_add_and_manage_its_assigned_gate(self):
        """Shared PostgreSQL is the site registry; local node control is gate-scoped."""
        from app.config import settings

        with patch.object(settings, "deployment_profile", "PRODUCTION"), \
             patch.object(settings, "recognition_gate_id", None), \
             patch("app.services.node_scope.deployment_role", return_value="EDGE_NODE"):
            response = self.client.post("/cameras", headers=self.headers, json={
                "name": "Node camera", "ip_address": "192.168.1.200",
            })
            self.assertEqual(response.status_code, 409, response.text)

            response = self.client.put("/runtime/recognition-owner", headers=self.headers, json={"gate_id": self.gate1["id"]})
            self.assertEqual(response.status_code, 200, response.text)
            created = self.client.post("/cameras", headers=self.headers, json={
                "name": "Node camera", "ip_address": "192.168.1.200",
            })
            self.assertEqual(created.status_code, 200, created.text)
            self.assertEqual(created.json()["gate_id"], self.gate1["id"])

            foreign = self.client.get(f"/cameras/{self.cam2e['id']}", headers=self.headers)
            self.assertEqual(foreign.status_code, 403, foreign.text)
            central = self.client.post("/gates", headers=self.headers, json={"name": "Central-only"})
            self.assertEqual(central.status_code, 200, central.text)

    def test_site_server_can_still_manage_foreign_camera_records(self):
        """The central server keeps global registry access after a lane is assigned."""
        from app.config import settings

        with patch.object(settings, "deployment_profile", "PRODUCTION"), \
             patch("app.services.node_scope.deployment_role", return_value="SITE_SERVER"):
            response = self.client.get(f"/cameras/{self.cam2e['id']}", headers=self.headers)
            self.assertEqual(response.status_code, 200, response.text)

    def test_out_of_scope_media_sync_unregisters_local_path(self):
        from app.config import settings
        from app.models import Camera
        from app.services.mediamtx_sources import sync_camera

        with patch.object(settings, "deployment_profile", "PRODUCTION"), patch.object(settings, "recognition_all_gates_enabled", False), patch("app.services.node_scope.deployment_role", return_value="EDGE_NODE"):
            with self.Session() as db:
                set_recognition_gate_id(self.gate1["id"], db)
                camera = db.get(Camera, self.cam2e["id"])
                with patch("app.infrastructure.media.registry.unregister_camera_source") as unregister, \
                     patch("app.infrastructure.media.registry.register_camera_source") as register:
                    result = sync_camera(camera, db=db)
        self.assertFalse(result["registered"])
        self.assertIn("outside", result["reason"])
        unregister.assert_called_once_with(self.cam2e["id"])
        register.assert_not_called()


if __name__ == "__main__":
    unittest.main()
