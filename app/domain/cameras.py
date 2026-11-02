"""Camera adapter contract. HVX is the production adapter; others are extras."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


CAMERA_TYPES = (
    "GENERIC_RTSP",
    "GENERIC_ONVIF",
    "NATIVE_ALPR",
    "USB_CAMERA",
    "HTTP_MJPEG",
    "VENDOR_SDK_CAMERA",
)

CAMERA_CAPABILITIES = (
    "RTSP",
    "RTSPS",
    "ONVIF",
    "HTTP_STREAM",
    "SNAPSHOT",
    "NATIVE_ALPR",
    "NATIVE_VEHICLE_DETECTION",
    "MAIN_STREAM",
    "SUB_STREAM",
    "THIRD_STREAM",
    "IO_OUTPUT",
    "PTZ",
    "AUDIO",
    "H264",
    "H265",
    "JPEG",
)

# Adapter identity is deliberately separate from recognition identity.  A QY
# camera can use FastALPR in Zirp while its video/control plane is owned by the
# native OcxConfig/NetSDK adapter.  ``hvx`` remains a persisted legacy alias
# for installations created before the adapter registry was introduced.
SDK_CAMERA_ADAPTER_IDS = frozenset({"qy", "hvx", "native"})
# ``hvx`` was the historical default for older rows and may describe an
# unclassified camera until it connects. ``qy`` and ``native`` are explicit
# native-stream selections and must never fall back to RTSP.
NATIVE_STREAM_ADAPTER_IDS = frozenset({"qy", "native"})
GENERIC_CAMERA_ADAPTER_IDS = frozenset({"rtsp", "ipcam", "dahua", "hikvision", "onvif"})


@runtime_checkable
class CameraLike(Protocol):
    id: int
    name: str
    ip_address: str
    sdk_port: int
    username: str
    password_secret: str
    rtsp_url: str
    sdk_handle: int | None
    adapter_id: str
    connection_mode: str


@runtime_checkable
class CameraAdapter(Protocol):
    id: str

    async def capabilities(self, device: CameraLike) -> dict[str, Any]: ...

    async def connect(self, device: CameraLike) -> dict[str, Any]: ...

    async def health(self, device: CameraLike) -> dict[str, Any]: ...

    async def snapshot(self, device: CameraLike) -> bytes: ...

    async def live_sources(self, device: CameraLike) -> list[dict[str, Any]]: ...

    async def disconnect(self, device: CameraLike) -> dict[str, Any]: ...

    async def detection_zones(self, device: CameraLike) -> dict[str, Any]: ...

    async def drain_events(self, device: CameraLike) -> list[dict[str, Any]]: ...


def camera_type_for(adapter_id: str, *, native_plates: bool = False) -> str:
    key = (adapter_id or "hvx").strip().lower()
    if key in SDK_CAMERA_ADAPTER_IDS or native_plates:
        return "VENDOR_SDK_CAMERA"
    if key == "onvif":
        return "GENERIC_ONVIF"
    if key == "simulated":
        return "GENERIC_RTSP"
    return "GENERIC_RTSP"
