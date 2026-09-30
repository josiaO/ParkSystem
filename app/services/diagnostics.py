"""Redacted diagnostics bundle for support tickets.

Everything in here passes through ``redaction.redact_obj`` before it leaves the
process. Camera rows are summarised (no password column, no credential URIs);
settings are listed by name with a configured/not-configured flag only.
"""

from __future__ import annotations

from datetime import datetime, timezone
import platform
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Camera, Gate
from app.services.redaction import redact_obj

_SECRET_SETTINGS = (
    "flutterwave_secret_key", "flutterwave_secret_hash", "clickpesa_client_id", "clickpesa_api_key",
    "clickpesa_checksum_key", "mobile_money_webhook_secret", "gemini_api_key", "bootstrap_password",
    "default_camera_password",
)


def _camera_row(cam: Camera) -> dict:
    from app.services.stream_roles import public_profiles

    return {
        "id": cam.id,
        "site_id": getattr(cam, "site_id", None),
        "name": cam.name,
        "ip_address": cam.ip_address,
        "adapter_id": cam.adapter_id,
        "connection_mode": cam.connection_mode,
        "status": cam.status,
        "enabled": cam.enabled,
        "recognition_mode": cam.recognition_mode,
        "username": cam.username,
        "credentials_ref": getattr(cam, "credentials_ref", "") or "",
        "password_configured": cam.has_password(),
        "rtsp_url": cam.rtsp_url,  # redact_obj masks user:pass@
        "stream_profiles": public_profiles(cam.stream_profiles or {}),
        "onvif": {k: v for k, v in (cam.onvif_profile or {}).items() if k in ("media_version", "capabilities", "capability_flags", "events_enabled")},
        "last_error": cam.last_error,
        "last_seen_at": cam.last_seen_at.isoformat() if cam.last_seen_at else None,
    }


def bundle(db: Session) -> dict:
    from app.services.health import details
    from app.infrastructure.secrets import describe as secrets_describe
    from app.migrations.runner import status as schema_status
    from app.db import engine, is_sqlite

    cameras = db.scalars(select(Camera).order_by(Camera.id)).all()
    gates = db.scalars(select(Gate).order_by(Gate.id)).all()
    body = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "app": {"name": settings.app_name, "version": settings.app_version},
        "runtime": {"python": sys.version.split()[0], "platform": platform.platform(), "sqlite": is_sqlite()},
        "schema": schema_status(engine),
        "secret_store": secrets_describe(),
        "settings_configured": {name: bool(getattr(settings, name, "")) for name in _SECRET_SETTINGS},
        "cameras": [_camera_row(c) for c in cameras],
        "gates": [
            {"id": g.id, "site_id": g.site_id, "name": g.name, "mode": g.mode, "enabled": g.enabled,
             "physical_control_verified": g.physical_control_verified}
            for g in gates
        ],
        "health": details(),
    }
    return redact_obj(body)
