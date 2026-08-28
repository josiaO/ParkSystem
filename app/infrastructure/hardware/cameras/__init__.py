"""Camera adapters. Default is HVX wrapping the working 32-bit host."""

from __future__ import annotations

from app.domain.cameras import CameraAdapter, CameraLike
from app.domain.devices import DEFAULT_CAMERA_ADAPTER
from app.infrastructure.hardware.cameras.hvx import HVXCameraAdapter
from app.infrastructure.hardware.cameras.onvif import ONVIFCameraAdapter
from app.infrastructure.hardware.cameras.rtsp import RTSPCameraAdapter
from app.infrastructure.hardware.cameras.simulated import SimulatedCameraAdapter

ADAPTERS: dict[str, CameraAdapter] = {
    "hvx": HVXCameraAdapter(),
    "rtsp": RTSPCameraAdapter(),
    "onvif": ONVIFCameraAdapter(),
    "simulated": SimulatedCameraAdapter(),
}


def camera_adapter_for(device: CameraLike | None = None, adapter_id: str | None = None) -> CameraAdapter:
    key = (adapter_id or getattr(device, "adapter_id", None) or DEFAULT_CAMERA_ADAPTER).strip().lower()
    return ADAPTERS.get(key) or ADAPTERS[DEFAULT_CAMERA_ADAPTER]


async def camera_live_sources(device: CameraLike) -> list[dict]:
    adapter = camera_adapter_for(device)
    fn = getattr(adapter, "live_sources", None)
    if callable(fn):
        return await fn(device)
    return [{"kind": "sdk", "adapter_id": adapter.id}]
