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
            "onvif": False,
            "note": "ONVIF is not implemented. Site cameras stay on HVX.",
        }

    async def connect(self, device: CameraLike) -> dict[str, Any]:
        return {
            "connected": False,
            "adapter_id": self.id,
            "error": "ONVIF is not the site camera path. Keep adapter_id=hvx.",
        }

    async def health(self, device: CameraLike) -> dict[str, Any]:
        return {"ok": False, "adapter_id": self.id, "message": "ONVIF adapter is a stub"}

    async def snapshot(self, device: CameraLike) -> bytes:
        return b""

    async def live_sources(self, device: CameraLike) -> list[dict[str, Any]]:
        return []
