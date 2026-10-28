"""Which gate this Site Service node recognizes.

Production is one PC per gate: set SMARTPARK_RECOGNITION_GATE_ID so this
computer only processes that gate's ENTRY and EXIT cameras. Development uses
the Live Gates lane preset: pick gate 1 and gate 2 is not OCR'd or parked.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.config import settings

NODE_SETTING_KEY = "node"


def node_setting_key() -> str:
    import hashlib

    identity = str(settings.node_id).strip().lower()
    return f"node:{hashlib.sha256(identity.encode()).hexdigest()[:32]}"

_ui_gate_id: int | None = None
_ui_set = False


def reset_recognition_scope() -> None:
    """Test helper. Production code uses set_recognition_gate_id()."""
    global _ui_gate_id, _ui_set
    _ui_gate_id = None
    _ui_set = False


def env_recognition_gate_id() -> int | None:
    raw = getattr(settings, "recognition_gate_id", None)
    if raw in (None, "", 0, "0"):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def recognition_gate_id(db=None) -> int | None:
    pinned = env_recognition_gate_id()
    if pinned is not None:
        return pinned
    if db is None and _ui_set:
        return _ui_gate_id
    if db is not None:
        try:
            from app.models import Camera, SiteSetting
            row = db.get(SiteSetting, node_setting_key())
            if row is None and str(settings.resolved_database_url).startswith("sqlite"):
                row = db.get(SiteSetting, NODE_SETTING_KEY)
            raw = (row.value or {}).get("recognition_gate_id") if row and isinstance(row.value, dict) else None
            if raw not in (None, "", 0, "0"):
                return int(raw)
        except Exception:
            return None
    return None


def deployment_role() -> str:
    """Return this installation's persisted deployment role.

    The Windows launchers historically exported ``SMARTPARK_NODE_ROLE=SERVER``
    for every local service.  That legacy setting is not sufficient to decide
    ownership: an EDGE_NODE is a local camera processor but is not the central
    Site Server.  Keep the deployment file as the authoritative role and use
    the legacy setting only as a compatibility signal for older lane installs.
    """
    try:
        from app.deployment import load_deployment_config

        return str(load_deployment_config().role or "").upper()
    except Exception:
        return ""


def is_processing_node() -> bool:
    """Whether this process must have an explicit gate before touching media."""
    return deployment_role() == "EDGE_NODE" or str(getattr(settings, "node_role", "SERVER")).upper() == "CLIENT"


def camera_gate_id(camera) -> int | None:
    if camera is None:
        return None
    if isinstance(camera, dict):
        raw = camera.get("gate_id")
    else:
        raw = getattr(camera, "gate_id", None)
    if raw in (None, "", 0, "0"):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def camera_in_recognition_scope(camera=None, *, gate_id: int | None = None, db=None) -> bool:
    wanted = recognition_gate_id(db)
    if wanted is None:
        # A lane processor must never interpret a missing assignment as
        # "all cameras".  This is the safe startup state while the operator
        # selects its gate in Live Gates.
        if is_processing_node():
            return False
        return settings.deployment_profile == "DEVELOPMENT" or settings.recognition_all_gates_enabled
    cam_gate = gate_id if gate_id is not None else camera_gate_id(camera)
    return cam_gate is not None and int(cam_gate) == int(wanted)


def camera_active_on_this_installation(camera=None, *, db=None) -> bool:
    """Whether this process may start media/recognition for a camera.

    The central Site Server owns and processes the whole registry. Only an
    EDGE_NODE uses the persisted gate assignment as a local hardware boundary.
    This is intentionally separate from the UI's selected recognition scope.
    """
    if not is_processing_node():
        return True
    return camera_in_recognition_scope(camera, db=db)


def site_server_can_manage_unassigned_cameras() -> bool:
    """Return whether this installation is the central Site Server.

    The Site Server owns the camera registry, so its management view must stay
    global even after the server itself is assigned a gate for testing.  The
    gate check is deliberately kept for media, connection, and recognition;
    this function must never be used as a stream-ownership check.

    This is deliberately separate from ``settings.node_role``: an EDGE_NODE
    can also use a server database and must not gain central-management rights
    merely because that setting says ``SERVER``.
    """
    try:
        from app.deployment import SITE_SERVER

        return deployment_role() == SITE_SERVER and not is_processing_node()
    except Exception:
        return False


def camera_visible_in_management(camera=None, *, db=None) -> bool:
    """Whether a camera may appear in the configuration list.

    Recognition/media ownership remains strict.  The central Site Server may
    manage every registry record so an administrator can assign or repair a
    camera that belongs to another lane.  A processing node still sees only
    its own gate plus unassigned records during commissioning; it can save a
    new record without gaining permission to stream another node's camera.
    """
    if site_server_can_manage_unassigned_cameras():
        return True
    if is_processing_node():
        # An EDGE_NODE must not even inherit the central server's unassigned or
        # foreign rows from the shared database.  Gate names remain available
        # through the read-only gate list so the node can choose its owner.
        return camera_in_recognition_scope(camera, db=db)
    if camera_in_recognition_scope(camera, db=db):
        return True
    return camera_gate_id(camera) is None


def set_recognition_gate_id(gate_id: int | None, db=None) -> dict[str, Any]:
    """Operator/dev choice. Ignored when the process is env-pinned."""
    global _ui_gate_id, _ui_set
    if env_recognition_gate_id() is not None:
        return describe_recognition_scope(db)
    chosen: int | None = None
    if gate_id not in (None, "", 0, "0"):
        chosen = int(gate_id)
    _ui_gate_id = chosen
    _ui_set = True
    if db is not None:
        from app.models import SiteSetting
        key = node_setting_key()
        row = db.get(SiteSetting, key)
        body = dict(row.value) if row and isinstance(row.value, dict) else {}
        if chosen is not None:
            body["recognition_gate_id"] = chosen
        else:
            body["recognition_gate_id"] = None
        if row is None:
            db.add(SiteSetting(key=key, value=body))
        else:
            row.value = body
        db.commit()
    return describe_recognition_scope(db)


def describe_recognition_scope(db=None) -> dict[str, Any]:
    from app.models import Camera, Gate

    gate_id = recognition_gate_id(db)
    pinned = env_recognition_gate_id() is not None
    cameras: list[dict[str, Any]] = []
    gate_name = ""
    if db is not None:
        if gate_id is not None:
            gate = db.get(Gate, int(gate_id))
            gate_name = str(getattr(gate, "name", "") or "") if gate else f"Gate {gate_id}"
            query = select(Camera).where(Camera.enabled == True, Camera.gate_id == int(gate_id))  # noqa: E712
        else:
            query = select(Camera).where(Camera.enabled == True)  # noqa: E712
        rows = list(db.scalars(query).all())
        cameras = [
            {
                "id": int(c.id),
                "name": c.name,
                "lane_direction": str(c.lane_direction or ""),
                "gate_id": c.gate_id,
            }
            for c in rows
            if camera_in_recognition_scope(c, db=db)
        ]
    return {
        "node_id": settings.node_id,
        "node_role": settings.node_role,
        "gate_id": gate_id,
        "gate_name": gate_name,
        "mode": "gate" if gate_id is not None else ("all" if camera_in_recognition_scope(db=db) else "unassigned"),
        "deployment_profile": settings.deployment_profile,
        "pinned": pinned,
        "cameras": cameras,
        "detail": (
            f"This PC processes {gate_name or f'gate {gate_id}'} entry and exit only."
            if gate_id is not None
            else ("This PC processes every connected gate (explicit all-gates mode or development)."
                  if camera_in_recognition_scope(db=db) else "NODE NOT ASSIGNED TO GATE")
        ),
    }
