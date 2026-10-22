"""The media surface the rest of SmartPark is allowed to call.

FFmpeg, the HVX host, and MediaMTX stay behind this object. Parking, receipts,
payments, and gate decisions are not part of it.
"""

from __future__ import annotations

from typing import Any

from app.services.latest_frame import FrameSample
from app.services.media_gateway import CameraLiveSpec, LocalMediaGateway, gateway


class MediaService:
    """One acquisition engine. Live, detect, and evidence are consumers of it."""

    def __init__(self, engine: LocalMediaGateway | None = None) -> None:
        self.engine = engine if engine is not None else gateway

    def register_camera(self, camera_id: int, source: dict[str, Any] | CameraLiveSpec) -> None:
        spec = source if isinstance(source, CameraLiveSpec) else _spec_from_mapping(camera_id, source)
        self.engine.ensure_producer(spec)

    def start(self, camera_id: int, source: dict[str, Any] | CameraLiveSpec | None = None) -> None:
        if source is None:
            row = self.engine.session(int(camera_id))
            if row is None:
                return
            source = row.spec
        self.register_camera(int(camera_id), source)

    def stop(self, camera_id: int) -> None:
        self.engine.stop_producer(int(camera_id), force=True)

    def stop_all(self) -> None:
        self.engine.stop_all()

    def latest_live_frame(self, camera_id: int) -> FrameSample | None:
        return self.engine.peek_live(int(camera_id))

    def latest_detect_frame(self, camera_id: int) -> FrameSample | None:
        sample = self.engine.peek_detect(int(camera_id))
        if sample is not None:
            return sample
        return self.engine.peek_live(int(camera_id))

    def evidence_frame(self, camera_id: int) -> FrameSample | None:
        """Newest retained frame. Does not open a second camera connection."""
        return self.latest_live_frame(int(camera_id))

    def health(self, camera_id: int) -> dict[str, Any]:
        return self.engine.health_sync(int(camera_id))

    def sessions(self) -> list[dict[str, Any]]:
        return self.engine.live_metrics()

    async def live_endpoint(self, camera_id: int, db=None) -> dict[str, Any]:
        from app.infrastructure.media.registry import get_live_endpoint

        return await get_live_endpoint(int(camera_id), db)


def _spec_from_mapping(camera_id: int, source: dict[str, Any]) -> CameraLiveSpec:
    from app.services.ffmpeg_profiles import DEFAULT_PROFILE
    from app.services.stream_roles import ROLE_LIVE

    return CameraLiveSpec(
        id=int(camera_id),
        ip=str(source.get("ip") or source.get("ip_address") or ""),
        username=str(source.get("username") or ""),
        password=str(source.get("password") or ""),
        rtsp_url=str(source.get("rtsp_url") or source.get("uri") or ""),
        sdk_handle=source.get("sdk_handle"),
        ffmpeg_profile=str(source.get("ffmpeg_profile") or DEFAULT_PROFILE),
        transport=str(source.get("transport") or source.get("rtsp_transport") or "TCP"),
        need_detect=bool(source.get("need_detect", True)),
        live_role=str(source.get("live_role") or ROLE_LIVE),
        stream_profiles=dict(source.get("stream_profiles") or {}),
    )


media = MediaService()
