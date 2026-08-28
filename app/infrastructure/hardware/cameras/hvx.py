"""HVX camera adapter — thin wrap of the working HVXHostClient.

Does not change Net_Init / Net_AddCamera / Net_ConnCameraEx / plate callbacks.
Live view and GPIO stay on the existing host.
"""

from __future__ import annotations

from typing import Any

from app.domain.cameras import CameraLike
from app.domain.devices import ConnectionMode, DEFAULT_CONNECTION_MODE
from app.services.hvx_client import HVXHostClient, HVXHostUnavailable


class HVXCameraAdapter:
    id = "hvx"

    def __init__(self, client: HVXHostClient | None = None):
        self._client = client

    def _host(self) -> HVXHostClient:
        return self._client or HVXHostClient()

    async def capabilities(self, device: CameraLike) -> dict[str, Any]:
        return {
            "adapter_id": self.id,
            "sdk_login": True,
            "native_plates": True,
            "live_jpeg": True,
            "gpio": True,
            "connection_mode": getattr(device, "connection_mode", None) or DEFAULT_CONNECTION_MODE,
        }

    async def live_sources(self, device: CameraLike) -> list[dict[str, Any]]:
        return [{
            "kind": "sdk",
            "adapter_id": self.id,
            "note": "Moving live video is Net_StartVideo + Net_GetJpgBuffer on the HVX host.",
        }]

    async def connect(self, device: CameraLike) -> dict[str, Any]:
        mode = (getattr(device, "connection_mode", None) or DEFAULT_CONNECTION_MODE).upper()
        if mode == ConnectionMode.EDGE_AGENT.value:
            return {
                "connected": False,
                "adapter_id": self.id,
                "error": "EDGE_AGENT is reserved; this camera stays on DIRECT to the working HVX host.",
            }
        return await self._host().connect(
            ip=device.ip_address,
            port=int(device.sdk_port),
            username=device.username,
            password=device.password_secret,
        )

    async def health(self, device: CameraLike) -> dict[str, Any]:
        handle = device.sdk_handle
        if handle is None:
            return {"ok": False, "adapter_id": self.id, "message": "not SDK-connected"}
        try:
            state = await self._host().state(int(handle))
            return {"ok": True, "adapter_id": self.id, "state": state}
        except HVXHostUnavailable as exc:
            return {"ok": False, "adapter_id": self.id, "message": str(exc)}

    async def snapshot(self, device: CameraLike) -> bytes:
        handle = device.sdk_handle
        if handle is None:
            return b""
        return await self._host().live_jpeg(int(handle))
