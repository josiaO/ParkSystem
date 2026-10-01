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
    """Return whether the camera can originate plate metadata/events itself.

    HVX/QY is native by adapter. Other vendors may expose native LPR through
    persisted capability flags or ONVIF Profile M plate metadata; do not force
    those cameras through continuous software OCR merely because they are not
    HVX.
    """
    adapter = camera_adapter_for(device, adapter_id)
    if adapter.id == DEFAULT_CAMERA_ADAPTER:
        return True
    if device is None:
        return False
    capabilities = {
        str(item).upper()
        for item in (getattr(device, "media_capabilities", None) or [])
    }
    if {"NATIVE_ALPR", "ONVIF_PLATE_METADATA"} & capabilities:
        return True
    profile = dict(getattr(device, "onvif_profile", None) or {})
    caps = dict(profile.get("capabilities") or {})
    return bool(caps.get("plate_metadata"))


async def camera_live_sources(device: CameraLike) -> list[dict]:
    adapter = camera_adapter_for(device)
    fn = getattr(adapter, "live_sources", None)
    if callable(fn):
        return await fn(device)
    return [{"kind": "sdk", "adapter_id": adapter.id}]
