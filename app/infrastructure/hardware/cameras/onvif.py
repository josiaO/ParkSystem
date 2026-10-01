"""ONVIF placeholder. Registered so new vendors can plug in later.

Must never become the default adapter and must never report SDK_CONNECTED.
"""

from __future__ import annotations

from typing import Any

from app.domain.cameras import CameraLike


class ONVIFCameraAdapter:
    id = "onvif"

    async def capabilities(self, device: CameraLike) -> dict[str, Any]:
        return {
            "adapter_id": self.id,
            "sdk_login": False,
            "native_plates": False,
            "onvif": True,
            "onvif_login": False,
            "media_capabilities": ["ONVIF", "RTSP"],
            "note": "ONVIF discovers stream URIs. It is not the site camera login path — keep adapter_id=hvx for QY cameras.",
        }

    async def connect(self, device: CameraLike) -> dict[str, Any]:
        return {
            "connected": False,
            "adapter_id": self.id,
            "error": "ONVIF is not the site camera path. Keep adapter_id=hvx.",
        }

    async def health(self, device: CameraLike) -> dict[str, Any]:
        profile = dict(getattr(device, "onvif_profile", None) or {})
        caps = dict(profile.get("capabilities") or {})
        if not profile:
            return {"ok": False, "adapter_id": self.id, "message": "ONVIF not discovered yet; run ONVIF discovery"}
        return {
            "ok": bool(profile.get("media_url")),
            "adapter_id": self.id,
            "media_version": profile.get("media_version") or 0,
            "profile_m": bool(caps.get("profile_m")),
            "plate_metadata": bool(caps.get("plate_metadata")),
            "events_enabled": bool(profile.get("events_enabled")),
            "message": "ONVIF discovered" if profile.get("media_url") else "ONVIF media service missing",
        }

    async def snapshot(self, device: CameraLike) -> bytes:
        """Evidence still from the Media2/Media1 GetSnapshotUri result, never a guessed URL."""
        profile = dict(getattr(device, "onvif_profile", None) or {})
        uri = str(profile.get("snapshot_uri") or "")
        if not uri:
            return b""
        from app.services.onvif_runtime import fetch_snapshot
        try:
            return await fetch_snapshot(uri, getattr(device, "username", "") or "", getattr(device, "password_secret", "") or "")
        except Exception:
            return b""

    async def live_sources(self, device: CameraLike) -> list[dict[str, Any]]:
        from app.services.onvif_discover import discover_onvif_streams
        try:
            found = await discover_onvif_streams(device.ip_address, device.username, device.password_secret)
        except Exception:
            found = {"profiles": []}
        rows = []
        for profile in found.get("profiles") or []:
            uri = profile.get("uri") or ""
            if uri:
                rows.append({"kind": "onvif", "url": uri, "adapter_id": self.id, **{k: v for k, v in profile.items() if k != "uri"}})
        return rows
