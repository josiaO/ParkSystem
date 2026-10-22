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

LIVE_PROVIDER_WEBRTC = "MEDIAMTX_WEBRTC"
LIVE_PROVIDER_DIRECT_MJPEG = "DIRECT_MJPEG"
LIVE_PROVIDER_SNAPSHOT = "SNAPSHOT"
LIVE_PROVIDER_OFFLINE = "OFFLINE"


def live_provider_label(endpoint: dict[str, Any] | None) -> str:
    """Operator-visible transport. Configuration is not proof of WebRTC."""
    if not isinstance(endpoint, dict):
        return LIVE_PROVIDER_OFFLINE
    transport = str(endpoint.get("transport") or "").upper()
    provider = str(endpoint.get("provider") or "").upper()
    state = str(endpoint.get("state") or "").upper()
    negotiated = str(endpoint.get("viewer_transport") or "").upper()
    if negotiated in {LIVE_PROVIDER_WEBRTC, "WEBRTC"}:
        return LIVE_PROVIDER_WEBRTC
    if negotiated in {LIVE_PROVIDER_DIRECT_MJPEG, "MJPEG"}:
        return LIVE_PROVIDER_DIRECT_MJPEG
    if negotiated in {LIVE_PROVIDER_SNAPSHOT, "SNAPSHOT"}:
        return LIVE_PROVIDER_SNAPSHOT
    if negotiated in {LIVE_PROVIDER_OFFLINE, "OFFLINE"}:
        return LIVE_PROVIDER_OFFLINE
    if state in {"OFFLINE", "DISCONNECTED"} and transport not in {"WEBRTC", "MJPEG"}:
        return LIVE_PROVIDER_OFFLINE
    if provider == LIVE_VIEW_MEDIAMTX and transport == "WEBRTC":
        return LIVE_PROVIDER_WEBRTC
    if transport == "SNAPSHOT" or "snapshot" in str(endpoint.get("path") or "").lower():
        return LIVE_PROVIDER_SNAPSHOT
    if transport == "MJPEG" or provider == LIVE_VIEW_DIRECT_LEGACY:
        return LIVE_PROVIDER_DIRECT_MJPEG
    if not transport and not provider:
        return LIVE_PROVIDER_OFFLINE
    return LIVE_PROVIDER_DIRECT_MJPEG


def _migration_flags(db=None) -> dict[str, Any]:
    return flags(db)


def _camera_enabled(camera_id: int, db=None) -> bool:
    cfg = _migration_flags(db)
    return bool(cfg.get("media_gateway_enabled")) and media_mtx_for_camera(int(camera_id), db)


def _sdk_camera(camera_id: int, db=None) -> bool:
    from app.db import short_session
    from app.models import Camera

    if db is None:
        with short_session() as session:
            return _sdk_camera(camera_id, session)
    camera = db.get(Camera, int(camera_id))
    if camera is None:
        return False
    profiles = camera.stream_profiles or {}
    return camera.sdk_handle is not None or any(
        str(profile.get("protocol") or "").lower() == "sdk"
        for profile in profiles.values() if isinstance(profile, dict)
    )


def mediamtx_live_active(camera_id: int, db=None) -> bool:
    """True only when MediaMTX is selected and has this camera's path."""
    cfg = _migration_flags(db)
    selected = (
        _camera_enabled(camera_id, db)
        and not _sdk_camera(camera_id, db)
        and str(cfg.get("live_view_provider") or "").upper() == LIVE_VIEW_MEDIAMTX
        and mediamtx.running()
    )
    if not selected:
        return False
    telemetry = media_telemetry(camera_id)
    roles = telemetry.get("roles") or {}
    if roles:
        return bool((roles.get(mediamtx.ROLE_LIVE) or {}).get("registered"))
    return str(telemetry.get("state") or "").upper() not in {"", "OFFLINE", "UNREGISTERED"}


def mediamtx_detect_active(camera_id: int, db=None) -> bool:
    """Use MediaMTX as the detect source only while its local control API is alive."""
    return _camera_enabled(camera_id, db) and not _sdk_camera(camera_id, db) and mediamtx.running()


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
    if _sdk_camera(camera_id, db):
        endpoint = await gateway.get_live_endpoint(camera_id)
        return {**endpoint, "provider": LIVE_VIEW_DIRECT_LEGACY, "camera_id": camera_id,
                "transport": "MJPEG", "live_provider": LIVE_PROVIDER_DIRECT_MJPEG,
                "state": "DIRECT", "mediamtx_selected": False, "mediamtx_running": None,
                "reason": "SDK camera uses direct JPEG video"}
    if mediamtx_live_active(camera_id, db):
        if not _migration_flags(db).get("webrtc_live_enabled"):
            endpoint = await gateway.get_live_endpoint(camera_id)
            return {**endpoint, "provider": LIVE_VIEW_MEDIAMTX, "camera_id": camera_id,
                    "transport": "MJPEG", "live_provider": LIVE_PROVIDER_DIRECT_MJPEG, "state": "LIVE"}
        endpoint = mediamtx.live_endpoint(camera_id)
        telemetry = media_telemetry(camera_id)
        compat = dict(telemetry.get("webrtc") or {})
        if compat.get("compatible") is False:
            # Report the codec problem and keep the operator on the established
            # MediaMTX-fed MJPEG cache. Never start a hidden high-CPU transcode.
            fallback = await gateway.get_live_endpoint(camera_id)
            return {
                **fallback,
                "provider": LIVE_VIEW_MEDIAMTX,
                "camera_id": camera_id,
                "transport": "MJPEG",
                "live_provider": LIVE_PROVIDER_DIRECT_MJPEG,
                "state": "DEGRADED",
                "codec": telemetry.get("codec") or "",
                "reason": compat.get("reason") or "codec not supported by browser WebRTC",
                "webrtc_compatible": False,
            }
        return {
            "provider": LIVE_VIEW_MEDIAMTX,
            "camera_id": camera_id,
            **endpoint,
            "transport": "WEBRTC",
            "live_provider": LIVE_PROVIDER_WEBRTC,
            "state": telemetry.get("state") or "LIVE",
            "codec": telemetry.get("codec") or "",
            "webrtc_compatible": compat.get("compatible"),
            "codec_note": compat.get("reason") or "",
        }

    endpoint = await gateway.get_live_endpoint(camera_id)
    cfg = _migration_flags(db)
    sdk_camera = _sdk_camera(camera_id, db) if _camera_enabled(camera_id, db) else False
    return {
        "provider": LIVE_VIEW_DIRECT_LEGACY,
        "camera_id": camera_id,
        **endpoint,
        "transport": "MJPEG",
        "live_provider": LIVE_PROVIDER_DIRECT_MJPEG if endpoint else LIVE_PROVIDER_OFFLINE,
        "mediamtx_selected": (
            str(cfg.get("live_view_provider") or "").upper() == LIVE_VIEW_MEDIAMTX
            and _camera_enabled(camera_id, db)
            and not sdk_camera
        ),
        "mediamtx_running": mediamtx.running(),
        "state": "DIRECT" if sdk_camera else ("DEGRADED" if str(cfg.get("live_view_provider") or "").upper() == LIVE_VIEW_MEDIAMTX else "DIRECT"),
        "reason": "SDK camera uses direct JPEG video" if sdk_camera else ("MEDIA PATH OFFLINE: MediaMTX unavailable; using fallback" if str(cfg.get("live_view_provider") or "").upper() == LIVE_VIEW_MEDIAMTX else ""),
    }


async def get_detect_endpoint(camera_id: int, db=None) -> dict[str, Any]:
    camera_id = int(camera_id)
    if mediamtx_detect_active(camera_id, db):
        endpoint = mediamtx.detect_endpoint(camera_id)
        role = (media_telemetry(camera_id).get("roles") or {}).get(mediamtx.ROLE_DETECT) or {}
        path = role.get("mediamtx_path")
        if path:
            endpoint = {**endpoint, "mediamtx_path": path, "rtsp": f"rtsp://127.0.0.1:8554/{path}"}
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


async def get_evidence_endpoint(camera_id: int, db=None) -> dict[str, Any]:
    """Highest-quality stream for explicit snapshots. Shares the live upstream unless
    a distinct MAIN stream is configured, in which case MediaMTX pulls it on demand."""
    camera_id = int(camera_id)
    if mediamtx_detect_active(camera_id, db):
        endpoint = mediamtx.evidence_endpoint(camera_id)
        return {"provider": LIVE_VIEW_MEDIAMTX, "camera_id": camera_id, **endpoint}
    return {
        "provider": LIVE_VIEW_DIRECT_LEGACY,
        "camera_id": camera_id,
        "kind": "snapshot",
        "role": "EVIDENCE",
        "path": f"/cameras/{camera_id}/snapshot.jpg?role=MAIN",
    }


def media_telemetry(camera_id: int) -> dict[str, Any]:
    """Per-role MediaMTX path telemetry for one camera, or an offline stub.

    Only this seam decides whether MediaMTX telemetry applies to a camera; the
    Control API is the health source, never a process handle in another service.
    """
    camera_id = int(camera_id)
    if _sdk_camera(camera_id):
        return {"camera_id": camera_id, "control_api_ok": None, "state": "DIRECT", "codec": "JPEG",
                "webrtc": {"compatible": False, "reason": "SDK JPEG source, not a MediaMTX path"}, "roles": {}}
    if not mediamtx.running():
        return {"camera_id": camera_id, "control_api_ok": False, "state": "OFFLINE", "codec": "",
                "webrtc": {"compatible": None, "reason": "MediaMTX not running"}, "roles": {}}
    from app.services.mediamtx_telemetry import camera_telemetry

    try:
        return camera_telemetry(camera_id)
    except Exception as exc:  # telemetry must never break live view
        return {"camera_id": camera_id, "control_api_ok": False, "state": "OFFLINE", "codec": "",
                "webrtc": {"compatible": None, "reason": str(exc)[:120]}, "roles": {}}
