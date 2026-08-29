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


def camera_type_for(adapter_id: str, *, native_plates: bool = False) -> str:
    key = (adapter_id or "hvx").strip().lower()
    if key == "hvx" or native_plates:
        return "VENDOR_SDK_CAMERA"
    if key == "onvif":
        return "GENERIC_ONVIF"
    if key == "simulated":
        return "GENERIC_RTSP"
    return "GENERIC_RTSP"
