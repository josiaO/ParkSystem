"""Resolve camera upstream RTSP URIs and register them with the MediaMTX sidecar."""

from __future__ import annotations

from typing import Any

from app.services.rtsp_probe import vendor_candidates
from app.services.stream_roles import ROLE_DETECT, ROLE_LIVE, ROLE_SUB, uri_for_role


def _pick_hvx_sub(candidates: list[str]) -> str:
    for url in candidates:
        if "av0_1" in url:
            return url
    if len(candidates) > 1:
        return candidates[1]
    return candidates[0] if candidates else ""


def _pick_hvx_main(candidates: list[str]) -> str:
    for url in candidates:
        if "av0_0" in url:
            return url
    return candidates[0] if candidates else ""


def upstream_uris(
    *,
    ip: str,
    username: str,
    password: str,
    rtsp_url: str = "",
    stream_profiles: dict | None = None,
) -> tuple[str, str]:
    """Return (live_upstream, detect_upstream) RTSP URIs for MediaMTX path registration."""
    profiles = stream_profiles or {}
    explicit = str(rtsp_url or "").strip()
    if explicit.startswith("rtsp://"):
        live = uri_for_role(profiles, ROLE_LIVE, explicit) or explicit
        detect = uri_for_role(profiles, ROLE_DETECT, live) or live
        return live, detect

    candidates = vendor_candidates(ip, username, password, explicit)
    sub = _pick_hvx_sub(candidates)
    main = _pick_hvx_main(candidates)
    live = uri_for_role(profiles, ROLE_LIVE, sub or main)
    detect = uri_for_role(profiles, ROLE_DETECT, sub or live)
    return live or sub or main, detect or sub or main


def source_config_for_camera(camera) -> dict[str, Any]:
    live_uri, detect_uri = upstream_uris(
        ip=camera.ip_address,
        username=camera.username,
        password=camera.password_secret,
        rtsp_url=getattr(camera, "rtsp_url", None) or "",
        stream_profiles=dict(getattr(camera, "stream_profiles", None) or {}),
    )
    return {
        "uri": live_uri,
        "detect_uri": detect_uri,
        "ip": camera.ip_address,
        "rtsp_url": live_uri,
    }


def sync_camera(camera, *, db=None) -> dict[str, Any]:
    from app.infrastructure.media.registry import register_camera_source

    cfg = source_config_for_camera(camera)
    if not str(cfg.get("uri") or "").startswith("rtsp://"):
        return {"registered": False, "reason": "no RTSP upstream URI resolved"}
    return register_camera_source(int(camera.id), cfg, db=db)
