"""Camera adapter contract. HVX is the production adapter; others are extras."""

from __future__ import annotations

from dataclasses import dataclass
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

# Adapter identity is deliberately separate from recognition identity.  All
# QY/HVX rows, including the persisted legacy ``hvx`` alias, have one physical
# owner: the native OcxConfig/NetSDK host.  A missing SDK handle means the
# camera is disconnected, not that another component may open RTSP beside it.
SDK_CAMERA_ADAPTER_IDS = frozenset({"qy", "hvx", "native"})
NATIVE_STREAM_ADAPTER_IDS = frozenset({"qy", "hvx", "native"})
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


@dataclass(frozen=True)
class CameraStreamStatus:
    """Normalized stream contract shared by native and generic cameras."""

    camera_id: int
    state: str
    latest_frame: dict[str, Any] | None
    frame_timestamp: float | None
    frame_age_seconds: float | None
    generation: int
    fps: float
    reconnect_count: int
    startup_duration_ms: float | None
    time_since_reconnect_seconds: float | None
    last_successful_frame_at: float | None
    decoder_health: dict[str, Any]
    last_error: str
    healthy: bool
    source: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "state": self.state,
            "latest_frame": dict(self.latest_frame) if self.latest_frame else None,
            "frame_timestamp": self.frame_timestamp,
            "frame_age_seconds": self.frame_age_seconds,
            "generation": self.generation,
            "fps": self.fps,
            "reconnect_count": self.reconnect_count,
            "startup_duration_ms": self.startup_duration_ms,
            "time_since_reconnect_seconds": self.time_since_reconnect_seconds,
            "last_successful_frame_at": self.last_successful_frame_at,
            "decoder_health": dict(self.decoder_health),
            "last_error": self.last_error,
            "healthy": self.healthy,
            "source": self.source,
        }


def camera_type_for(adapter_id: str, *, native_plates: bool = False) -> str:
    key = (adapter_id or "hvx").strip().lower()
    if key in SDK_CAMERA_ADAPTER_IDS or native_plates:
        return "VENDOR_SDK_CAMERA"
    if key == "onvif":
        return "GENERIC_ONVIF"
    if key == "simulated":
        return "GENERIC_RTSP"
    return "GENERIC_RTSP"
