"""RTSP helper adapter. Extra path for ffprobe — never replaces HVX SDK login."""

from __future__ import annotations

from typing import Any

from app.domain.cameras import CameraLike
from app.services.rtsp_probe import probe, vendor_candidates


class RTSPCameraAdapter:
    id = "rtsp"

    async def capabilities(self, device: CameraLike) -> dict[str, Any]:
        return {
            "adapter_id": self.id,
            "sdk_login": False,
            "native_plates": False,
            "rtsp_probe": True,
            "note": "RTSP is optional media proof. Live ANPR stays on the HVX SDK host.",
        }

    async def connect(self, device: CameraLike) -> dict[str, Any]:
        return {
            "connected": False,
            "adapter_id": self.id,
            "error": "RTSP adapter cannot replace HVX SDK login. Use Probe RTSP; keep adapter_id=hvx.",
        }

    async def health(self, device: CameraLike) -> dict[str, Any]:
        url = (device.rtsp_url or "").strip()
        if not url:
            return {"ok": False, "adapter_id": self.id, "message": "no RTSP URL stored"}
        result = await probe(url)
        return {"ok": result.ok, "adapter_id": self.id, **result.__dict__}

    async def snapshot(self, device: CameraLike) -> bytes:
        return b""

    async def live_sources(self, device: CameraLike) -> list[dict[str, Any]]:
        urls = vendor_candidates(device.ip_address, device.username, device.password_secret, device.rtsp_url)
        return [{"kind": "rtsp", "url": url, "adapter_id": self.id} for url in urls]

    async def probe_candidates(self, device: CameraLike) -> list[dict[str, Any]]:
        rows = []
        for url in vendor_candidates(device.ip_address, device.username, device.password_secret, device.rtsp_url):
            result = await probe(url)
            rows.append(result.__dict__)
            if result.ok:
                break
        return rows
