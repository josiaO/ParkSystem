"""Persist ONVIF discovery results onto a Camera row (capabilities, not guesses)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models import Camera
from app.services.onvif_discover import capability_flags

_MANAGED_FLAGS = {"ONVIF", "ONVIF_MEDIA2", "ONVIF_EVENTS", "ONVIF_PROFILE_M", "ONVIF_PLATE_METADATA"}


def apply_discovery(camera: Camera, onvif: dict[str, Any]) -> dict[str, Any]:
    """Store what the device advertised. Preserves the operator's events toggle."""
    if not onvif or not onvif.get("onvif"):
        return dict(camera.onvif_profile or {})
    previous = dict(camera.onvif_profile or {})
    caps = dict(onvif.get("capabilities") or {})
    profile = {
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "media_version": onvif.get("media_version") or 0,
        "device_url": onvif.get("device_url") or "",
        "media_url": onvif.get("media_url") or "",
        "media2_url": onvif.get("media2_url") or "",
        "events_url": onvif.get("events_url") or "",
        "analytics_url": onvif.get("analytics_url") or "",
        "snapshot_uri": onvif.get("snapshot_uri") or "",
        "snapshot_uri_redacted": onvif.get("snapshot_uri_redacted") or "",
        "capabilities": caps,
        "profile_tokens": [p.get("token") for p in (onvif.get("profiles") or []) if p.get("token")],
        # Default: consume plate metadata when the device advertises it. The
        # operator can switch it off; a device that stops advertising loses it.
        "events_enabled": bool(caps.get("plate_metadata")) and previous.get("events_enabled", True),
    }
    camera.onvif_profile = profile
    flags = [f for f in (camera.media_capabilities or []) if f not in _MANAGED_FLAGS]
    flags.extend(capability_flags(caps))
    camera.media_capabilities = flags
    return profile


def set_events_enabled(camera: Camera, enabled: bool) -> dict[str, Any]:
    profile = dict(camera.onvif_profile or {})
    caps = dict(profile.get("capabilities") or {})
    if enabled and not (profile.get("events_url") and caps.get("plate_metadata")):
        raise ValueError("Camera does not advertise ONVIF licence-plate events; run ONVIF discovery first.")
    profile["events_enabled"] = bool(enabled)
    camera.onvif_profile = profile
    return profile
