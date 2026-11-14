"""Kiosk enrolment on this PC (Phase 2.3).

An administrator creates a kiosk device on the Site Server (Admin → Kiosk
devices) and types the device id and one-time credential into this PC once.
The credential is kept in the platform secret store (DPAPI on Windows, a
0600 file elsewhere); only its reference and the device id are written to
``kiosk_device.json``. The desktop then signs in by itself at start-up and
again whenever the kiosk session expires.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.config import settings


def _path() -> Path:
    return settings.data_dir / "kiosk_device.json"


def enrolled_device_id() -> str:
    try:
        body = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return str(body.get("device_id") or "") if isinstance(body, dict) else ""


def load_device() -> tuple[str, str] | None:
    """Return (device_id, credential) for an enrolled kiosk, else None."""
    from app.infrastructure.secrets import resolve_secret

    try:
        body = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(body, dict):
        return None
    device_id = str(body.get("device_id") or "").strip()
    credential = resolve_secret(str(body.get("credential_ref") or ""), fallback="")
    if not device_id or not credential:
        return None
    return device_id, credential


def enrol(device_id: str, credential: str) -> None:
    from app.infrastructure.secrets import store_secret

    device_id = str(device_id or "").strip()
    if not device_id or not credential:
        raise ValueError("Enter the kiosk device id and credential from Admin → Kiosk devices.")
    ref = store_secret(credential, kind="kiosk")
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"device_id": device_id, "credential_ref": ref}), encoding="utf-8")


def forget() -> None:
    from app.infrastructure.secrets import is_ref, secret_store

    path = _path()
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
        ref = str(body.get("credential_ref") or "") if isinstance(body, dict) else ""
        if is_ref(ref):
            secret_store().delete(ref)
    except (OSError, ValueError):
        pass
    path.unlink(missing_ok=True)
