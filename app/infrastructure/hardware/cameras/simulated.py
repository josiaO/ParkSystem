"""Simulated camera for tests. Never selected for site cameras by default."""

from __future__ import annotations

from typing import Any

from app.domain.cameras import CameraLike


class SimulatedCameraAdapter:
    id = "simulated"

    async def capabilities(self, device: CameraLike) -> dict[str, Any]:
        return {"adapter_id": self.id, "sdk_login": False, "simulated": True}

    async def connect(self, device: CameraLike) -> dict[str, Any]:
        return {"connected": True, "adapter_id": self.id, "handle": None, "simulated": True}

    async def health(self, device: CameraLike) -> dict[str, Any]:
        return {"ok": True, "adapter_id": self.id, "simulated": True}

    async def snapshot(self, device: CameraLike) -> bytes:
        return b""

    async def live_sources(self, device: CameraLike) -> list[dict[str, Any]]:
        return [{"kind": "simulated", "adapter_id": self.id}]
