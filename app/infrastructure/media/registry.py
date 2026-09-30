"""Authoritative media-provider selection.

This is the seam between SmartPark's parking/recognition code and the concrete
streaming implementation.  DIRECT_LEGACY remains a safe rollback path while
MediaMTX is rolled out camera-by-camera.
"""

from __future__ import annotations

from typing import Any

from app.domain.flags import LIVE_VIEW_DIRECT_LEGACY, LIVE_VIEW_MEDIAMTX
from app.services import mediamtx
from app.services.flags import flags, media_mtx_for_camera
from app.services.media_gateway import gateway


def _migration_flags(db=None) -> dict[str, Any]:
    return flags(db)


def _camera_enabled(camera_id: int, db=None) -> bool:
    cfg = _migration_flags(db)
    return bool(cfg.get("media_gateway_enabled")) and media_mtx_for_camera(int(camera_id), db)


def mediamtx_live_active(camera_id: int, db=None) -> bool:
    """True only when MediaMTX is the selected and healthy live-view provider."""
    cfg = _migration_flags(db)
    return (
        _camera_enabled(camera_id, db)
        and str(cfg.get("live_view_provider") or "").upper() == LIVE_VIEW_MEDIAMTX
        and bool(cfg.get("webrtc_live_enabled"))
        and mediamtx.running()
    )


def mediamtx_detect_active(camera_id: int, db=None) -> bool:
    """Use MediaMTX as the detect source only while its local control API is alive."""
    return _camera_enabled(camera_id, db) and mediamtx.running()


def register_camera_source(camera_id: int, source_config: dict[str, Any], db=None) -> dict[str, Any]:
    """Persist/reload a MediaMTX source when this camera is in the rollout set.

    Registration is intentionally allowed before MediaMTX is running so the
    generated config is ready when the media service starts.
    """
    camera_id = int(camera_id)
    if not _camera_enabled(camera_id, db):
        return {
            "registered": False,
            "camera_id": camera_id,
            "provider": LIVE_VIEW_DIRECT_LEGACY,
            "reason": "MediaMTX is not enabled for this camera",
        }
    endpoint = mediamtx.register_source(camera_id, dict(source_config or {}))
    return {
        "registered": True,
        "camera_id": camera_id,
        "provider": LIVE_VIEW_MEDIAMTX,
        **endpoint,
    }


def unregister_camera_source(camera_id: int) -> None:
    mediamtx.unregister_source(int(camera_id))


async def get_live_endpoint(camera_id: int, db=None) -> dict[str, Any]:
    """Return one live transport.

    Never ask the UI to run both WebRTC and snapshot polling at the same time.
    If MediaMTX is selected but unhealthy, fall back to the established direct
    MJPEG endpoint so operators still have a picture.
    """
    camera_id = int(camera_id)
    if mediamtx_live_active(camera_id, db):
        endpoint = mediamtx.live_endpoint(camera_id)
        return {
            "provider": LIVE_VIEW_MEDIAMTX,
            "camera_id": camera_id,
            **endpoint,
        }

    endpoint = await gateway.get_live_endpoint(camera_id)
    cfg = _migration_flags(db)
    return {
        "provider": LIVE_VIEW_DIRECT_LEGACY,
        "camera_id": camera_id,
        **endpoint,
        "mediamtx_selected": (
            str(cfg.get("live_view_provider") or "").upper() == LIVE_VIEW_MEDIAMTX
            and _camera_enabled(camera_id, db)
        ),
        "mediamtx_running": mediamtx.running(),
    }


async def get_detect_endpoint(camera_id: int, db=None) -> dict[str, Any]:
    camera_id = int(camera_id)
    if mediamtx_detect_active(camera_id, db):
        endpoint = mediamtx.detect_endpoint(camera_id)
        return {
            "provider": LIVE_VIEW_MEDIAMTX,
            "camera_id": camera_id,
            **endpoint,
        }
    endpoint = await gateway.get_detect_endpoint(camera_id)
    return {
        "provider": LIVE_VIEW_DIRECT_LEGACY,
        "camera_id": camera_id,
        **endpoint,
    }
