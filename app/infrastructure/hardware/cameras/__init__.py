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

# Same live-JPEG + FastALPR path. Unknown ids still fall back to HVX.
GENERIC_IP_ADAPTER_IDS = frozenset({"rtsp", "ipcam", "dahua", "hikvision"})


def resolve_adapter_key(adapter_id: str | None = None) -> str:
    key = (adapter_id or DEFAULT_CAMERA_ADAPTER).strip().lower() or DEFAULT_CAMERA_ADAPTER
    if key in GENERIC_IP_ADAPTER_IDS:
        return "rtsp"
    return key if key in ADAPTERS else DEFAULT_CAMERA_ADAPTER


def camera_adapter_for(device: CameraLike | None = None, adapter_id: str | None = None) -> CameraAdapter:
    key = resolve_adapter_key(adapter_id or getattr(device, "adapter_id", None))
    return ADAPTERS[key]


def adapter_has_native_plates(device: CameraLike | None = None, adapter_id: str | None = None) -> bool:
    return camera_adapter_for(device, adapter_id).id == DEFAULT_CAMERA_ADAPTER


async def camera_live_sources(device: CameraLike) -> list[dict]:
    adapter = camera_adapter_for(device)
    fn = getattr(adapter, "live_sources", None)
    if callable(fn):
        return await fn(device)
    return [{"kind": "sdk", "adapter_id": adapter.id}]
