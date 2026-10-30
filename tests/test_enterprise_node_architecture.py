from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.api_main import app
from app.db import Base, get_db
from app.deployment import EDGE_NODE, OPERATOR_CLIENT, SITE_SERVER, DeploymentConfig, central_server_base_url, local_node_runtime_url
from app.models import Gate, Node, NodeGateAssignment, Site
from app.services.node_authorization import NodePrincipal, assigned_gate_ids, hash_node_credential, node_owns_gate
from app.security import processing_node_permissions


def test_deployment_separates_central_and_local_planes():
    edge = DeploymentConfig(role=EDGE_NODE, server_base_url="http://192.168.1.240:8760", server_bind_port=8760)
    assert not edge.is_site_server
    assert edge.runs_local_gate_runtime
    assert edge.uses_remote_site_server
    assert central_server_base_url(edge) == "http://192.168.1.240:8760"
    assert local_node_runtime_url(edge) == "http://127.0.0.1:8760"

    server = DeploymentConfig(role=SITE_SERVER, server_bind_port=8760)
    assert server.is_site_server
    assert central_server_base_url(server) == "http://127.0.0.1:8760"
    assert local_node_runtime_url(server) == "http://127.0.0.1:8760"

    workstation = DeploymentConfig(role=OPERATOR_CLIENT, server_base_url="http://server:8760")
    assert not workstation.runs_local_gate_runtime
    assert local_node_runtime_url(workstation) == ""


def test_human_permissions_are_not_filtered_by_installation_role():
    permissions = {"users.manage", "sessions.view", "payments.view", "*"}
    with patch("app.services.node_scope.is_processing_node", return_value=True):
        assert processing_node_permissions(permissions) == permissions


def test_node_assignment_is_independent_from_human_roles():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        site = Site(name="Test")
        db.add(site)
        db.flush()
        gate_a = Gate(name="Gate A", site_id=site.id)
        gate_b = Gate(name="Gate B", site_id=site.id)
        db.add_all([gate_a, gate_b])
        db.flush()
        node = Node(node_id="gate-a-01", site_id=site.id, name="Gate A node", credential_hash="hash")
        db.add(node)
        db.flush()
        db.add(NodeGateAssignment(node_id=node.id, gate_id=gate_a.id))
        db.commit()

        principal = NodePrincipal(node_pk=node.id, node_id=node.node_id, site_id=site.id)
        assert assigned_gate_ids(db, principal) == {gate_a.id}
        assert node_owns_gate(db, principal, gate_a.id)
        assert not node_owns_gate(db, principal, gate_b.id)

    engine.dispose()


def test_node_auth_and_config_are_assignment_scoped():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        site = Site(name="Test")
        db.add(site)
        db.flush()
        owned = Gate(name="Owned", site_id=site.id)
        foreign = Gate(name="Foreign", site_id=site.id)
        db.add_all([owned, foreign])
        db.flush()
        node = Node(
            node_id="edge-auth-01",
            site_id=site.id,
            name="Edge auth",
            credential_hash=hash_node_credential("node-secret-123456"),
        )
        db.add(node)
        db.flush()
        db.add(NodeGateAssignment(node_id=node.id, gate_id=owned.id))
        db.commit()
        owned_id = owned.id

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        auth = client.post("/node/auth", json={"node_id": "edge-auth-01", "credential": "node-secret-123456"})
        assert auth.status_code == 200, auth.text
        headers = {"Authorization": f"Bearer {auth.json()['token']}"}
        config = client.get("/node/config", headers=headers)
        assert config.status_code == 200, config.text
        assert config.json()["node"]["assigned_gate_ids"] == [owned_id]
        assert client.get("/node/me", headers=headers).status_code == 200
        assert client.get("/node/me", headers={"Authorization": "Bearer invalid"}).status_code == 401
        client.close()
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
