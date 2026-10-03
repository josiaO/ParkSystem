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
    if _ui_set:
        return _ui_gate_id
    if db is not None:
        try:
            from app.models import SiteSetting
            row = db.get(SiteSetting, NODE_SETTING_KEY)
            raw = (row.value or {}).get("recognition_gate_id") if row and isinstance(row.value, dict) else None
            if raw not in (None, "", 0, "0"):
                return int(raw)
        except (TypeError, ValueError, Exception):
            return _ui_gate_id
    return None


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
        return True
    cam_gate = gate_id if gate_id is not None else camera_gate_id(camera)
    return cam_gate is not None and int(cam_gate) == int(wanted)


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
        row = db.get(SiteSetting, NODE_SETTING_KEY)
        body = dict(row.value) if row and isinstance(row.value, dict) else {}
        if chosen is None:
            body.pop("recognition_gate_id", None)
        else:
            body["recognition_gate_id"] = chosen
        if row is None:
            db.add(SiteSetting(key=NODE_SETTING_KEY, value=body))
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
        "gate_id": gate_id,
        "gate_name": gate_name,
        "mode": "gate" if gate_id is not None else "all",
        "pinned": pinned,
        "cameras": cameras,
        "detail": (
            f"This PC processes {gate_name or f'gate {gate_id}'} entry and exit only."
            if gate_id is not None
            else "This PC processes every connected gate (heavy). Pick a lane for development."
        ),
    }
