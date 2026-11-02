"""Database-backed developer playground controls.

The controls are deliberately fail-closed for physical actions.  They are
stored in ``site_settings`` so a restart does not silently re-enable a gate
or a printer while a developer is testing a lane.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import SiteSetting


DEFAULT_DEVELOPER_SETTINGS: dict[str, Any] = {
    "developer_mode": False,
    "logging_enabled": False,
    "printing_enabled": True,
    "gate_opening_enabled": True,
    "automatic_gate_opening_enabled": True,
    "recognition_enabled": True,
    "capture_enabled": True,
    "camera_connections_enabled": True,
    "destructive_tools_enabled": False,
}

_BOOL_KEYS = set(DEFAULT_DEVELOPER_SETTINGS)


def developer_settings(db: Session | None = None) -> dict[str, Any]:
    current = dict(DEFAULT_DEVELOPER_SETTINGS)
    if db is None:
        return current
    row = db.get(SiteSetting, "developer")
    if row and isinstance(row.value, dict):
        for key in _BOOL_KEYS:
            if key in row.value:
                current[key] = bool(row.value[key])
    return current


def save_developer_settings(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    current = developer_settings(db)
    for key in _BOOL_KEYS:
        if key in payload and payload[key] is not None:
            current[key] = bool(payload[key])
    row = db.get(SiteSetting, "developer")
    if row is None:
        db.add(SiteSetting(key="developer", value=current))
    else:
        row.value = current
    db.commit()
    return developer_settings(db)


def _enabled(db: Session | None, key: str) -> bool:
    cfg = developer_settings(db)
    # The individual switches are intentionally inert until the playground is
    # explicitly enabled.  This keeps a stale database row from changing a
    # production lane after an upgrade.
    return bool(cfg.get(key, True)) if bool(cfg.get("developer_mode")) else True


def gate_opening_enabled(db: Session | None) -> bool:
    return _enabled(db, "gate_opening_enabled")


def automatic_gate_opening_enabled(db: Session | None) -> bool:
    return _enabled(db, "automatic_gate_opening_enabled")


def printing_enabled(db: Session | None) -> bool:
    return _enabled(db, "printing_enabled")


def recognition_enabled(db: Session | None) -> bool:
    return _enabled(db, "recognition_enabled")


def capture_enabled(db: Session | None) -> bool:
    return _enabled(db, "capture_enabled")


def camera_connections_enabled(db: Session | None) -> bool:
    return _enabled(db, "camera_connections_enabled")


def destructive_tools_enabled(db: Session | None) -> bool:
    cfg = developer_settings(db)
    return bool(cfg.get("developer_mode")) and bool(cfg.get("destructive_tools_enabled"))
