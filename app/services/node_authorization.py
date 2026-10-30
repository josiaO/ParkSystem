"""Central node identity and resource-scope authorization.

This module sits above camera/gate adapters. It knows which node owns a
resource, but it deliberately does not know how a camera stream or gate
driver works.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Camera, Gate, Node, NodeAuthSession, NodeGateAssignment


@dataclass(frozen=True)
class NodePrincipal:
    node_pk: int
    node_id: str
    site_id: int
    capabilities: frozenset[str] = field(default_factory=frozenset)

    @property
    def principal_type(self) -> str:
        return "node"


def _active_node(row: Node | None) -> Node:
    if row is None or row.status != "ACTIVE" or row.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Node credential revoked or unavailable")
    return row


def principal_for_node(db: Session, node_id: str | None = None) -> NodePrincipal:
    identity = str(node_id or settings.node_id or "").strip()
    row = _active_node(db.scalar(select(Node).where(Node.node_id == identity)))
    capabilities = row.capabilities if isinstance(row.capabilities, dict) else {}
    values = capabilities.get("permissions") or capabilities.get("capabilities") or []
    return NodePrincipal(
        node_pk=int(row.id),
        node_id=row.node_id,
        site_id=int(row.site_id),
        capabilities=frozenset(str(value) for value in values),
    )


def assigned_gate_ids(db: Session, principal: NodePrincipal) -> set[int]:
    rows = db.scalars(
        select(NodeGateAssignment.gate_id).where(
            NodeGateAssignment.node_id == principal.node_pk,
            NodeGateAssignment.enabled == True,  # noqa: E712
        )
    ).all()
    return {int(value) for value in rows}


def node_owns_gate(db: Session, principal: NodePrincipal, gate_id: int) -> bool:
    gate = db.get(Gate, int(gate_id))
    return bool(gate and int(gate.site_id) == principal.site_id and int(gate.id) in assigned_gate_ids(db, principal))


def node_owns_camera(db: Session, principal: NodePrincipal, camera_id: int) -> bool:
    camera = db.get(Camera, int(camera_id))
    return bool(
        camera
        and int(camera.site_id) == principal.site_id
        and camera.gate_id is not None
        and node_owns_gate(db, principal, int(camera.gate_id))
    )


def require_node_gate(db: Session, principal: NodePrincipal, gate_id: int) -> Gate:
    gate = db.get(Gate, int(gate_id))
    if gate is None:
        raise HTTPException(status_code=404, detail="Gate not found")
    if not node_owns_gate(db, principal, gate.id):
        raise HTTPException(status_code=403, detail="Node is not assigned to this gate")
    return gate


def require_node_camera(db: Session, principal: NodePrincipal, camera_id: int) -> Camera:
    camera = db.get(Camera, int(camera_id))
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    if not node_owns_camera(db, principal, camera.id):
        raise HTTPException(status_code=403, detail="Node is not assigned to this camera's gate")
    return camera


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_node_session(db: Session, node: Node, *, hours: int = 24) -> str:
    token = secrets.token_urlsafe(48)
    db.add(NodeAuthSession(
        node_id=node.id,
        token_hash=_token_hash(token),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=hours),
    ))
    node.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return token


def hash_node_credential(credential: str) -> str:
    from app.security import hash_password

    return hash_password(credential)


def verify_node_credential(credential_hash: str, credential: str) -> bool:
    from app.security import verify_password

    return bool(credential_hash) and verify_password(credential_hash, credential)


def load_node_from_token(db: Session, token: str | None) -> NodePrincipal:
    if not token:
        raise HTTPException(status_code=401, detail="Node authentication required")
    row = db.scalar(select(NodeAuthSession).where(NodeAuthSession.token_hash == _token_hash(token)))
    if row is None:
        raise HTTPException(status_code=401, detail="Node session expired")
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Node session expired")
    return principal_for_node(db, db.get(Node, row.node_id).node_id if db.get(Node, row.node_id) else "")
