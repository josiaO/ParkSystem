"""Camera adapter contract. HVX is the production adapter; others are extras."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


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
