"""Media subsystem contract. Parking and FastALPR must not own RTSP/decode."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


STREAM_STATES = (
    "DISCONNECTED",
    "CONNECTING",
    "STREAMING",
    "DEGRADED",
    "RECONNECTING",
)

STREAM_ROLES = ("MAIN", "SUB", "LIVE", "DETECT", "EVIDENCE")

FFMPEG_PROFILES = (
    "COMPATIBLE",
    "LOW_LATENCY_LAN",
    "LOSSY_NETWORK",
    "VENDOR_SPECIAL",
)

RTSP_TRANSPORTS = ("AUTO", "TCP", "UDP")


@runtime_checkable
class MediaGateway(Protocol):
    async def register_stream(self, camera_id: int, source: dict[str, Any]) -> dict[str, Any]: ...

    async def unregister_stream(self, camera_id: int) -> None: ...

    async def health(self, camera_id: int) -> dict[str, Any]: ...

    async def get_live_endpoint(self, camera_id: int) -> dict[str, Any]: ...

    async def get_detect_endpoint(self, camera_id: int) -> dict[str, Any]: ...

    async def snapshot(self, camera_id: int) -> bytes: ...

    async def register_source(self, camera_id: int, source_config: dict[str, Any]) -> dict[str, Any]: ...

    async def unregister_source(self, camera_id: int) -> None: ...

    async def get_snapshot(self, camera_id: int) -> bytes: ...

    async def metrics(self, camera_id: int) -> dict[str, Any]: ...
