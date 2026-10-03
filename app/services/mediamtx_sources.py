"""Resolve camera upstream RTSP URIs and register them with the MediaMTX sidecar."""

from __future__ import annotations

from typing import Any

from app.services.rtsp_probe import vendor_candidates
from app.services.stream_roles import ROLE_DETECT, ROLE_EVIDENCE, ROLE_LIVE, ROLE_SUB, uri_for_role


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
    live, detect, _evidence = upstream_role_uris(
        ip=ip, username=username, password=password, rtsp_url=rtsp_url, stream_profiles=stream_profiles
    )
    return live, detect


def upstream_role_uris(
    *,
    ip: str,
    username: str,
    password: str,
    rtsp_url: str = "",
    stream_profiles: dict | None = None,
) -> tuple[str, str, str]:
    """Return (live, detect, evidence) upstream RTSP URIs.

    Roles resolving to the same URI are deduplicated later by
    ``mediamtx.path_plan`` so the camera is pulled once per distinct stream.
    Evidence is empty when no distinct MAIN stream is known; the caller then
    reuses the live path for evidence snapshots.
    """
    profiles = stream_profiles or {}
    explicit = str(rtsp_url or "").strip()
    if explicit.startswith("rtsp://"):
        live = uri_for_role(profiles, ROLE_LIVE, explicit) or explicit
        detect = uri_for_role(profiles, ROLE_DETECT, live) or live
        evidence = uri_for_role(profiles, ROLE_EVIDENCE, "")
        return live, detect, evidence

    candidates = vendor_candidates(ip, username, password, explicit)
    sub = _pick_hvx_sub(candidates)
    main = _pick_hvx_main(candidates)
    live = uri_for_role(profiles, ROLE_LIVE, sub or main)
    detect = uri_for_role(profiles, ROLE_DETECT, sub or live)
    evidence = uri_for_role(profiles, ROLE_EVIDENCE, main if main and main != (live or sub) else "")
    return live or sub or main, detect or sub or main, evidence


def source_config_for_camera(camera) -> dict[str, Any]:
    profiles = dict(getattr(camera, "stream_profiles", None) or {})
    protocol = str(
        (profiles.get(ROLE_SUB) or profiles.get(ROLE_LIVE) or profiles.get("MAIN") or {}).get("protocol") or ""
    )
    if protocol == "sdk" or getattr(camera, "sdk_handle", None) is not None:
        # OcxConfig/NetSDK already owns the live stream. Do not invent an RTSP
        # client — QY cameras have few stream slots and a second pull stacks.
        return {
            "uri": "",
            "detect_uri": "",
            "evidence_uri": "",
            "ip": camera.ip_address,
            "rtsp_url": "",
            "transport": "TCP",
        }
    live_uri, detect_uri, evidence_uri = upstream_role_uris(
        ip=camera.ip_address,
        username=camera.username,
        password=camera.password_secret,
        rtsp_url=getattr(camera, "rtsp_url", None) or "",
        stream_profiles=profiles,
    )
    return {
        "uri": live_uri,
        "detect_uri": detect_uri,
        "evidence_uri": evidence_uri,
        "ip": camera.ip_address,
        "rtsp_url": live_uri,
        "transport": str(getattr(camera, "rtsp_transport", None) or "TCP").upper(),
    }


def sync_camera(camera, *, db=None) -> dict[str, Any]:
    from app.infrastructure.media.registry import register_camera_source, unregister_camera_source

    cfg = source_config_for_camera(camera)
    if not str(cfg.get("uri") or "").startswith("rtsp://"):
        # HVX/QY live video is Net_StartVideo + GetJpgBuffer (OcxConfig PlaySdk).
        # A leftover MediaMTX RTSP pull is a second camera client and is how one
        # lane stays live while the next stacks or drops.
        try:
            unregister_camera_source(int(camera.id))
        except Exception:
            pass
        return {"registered": False, "reason": "HVX uses SDK JPEG, not MediaMTX RTSP"}
    return register_camera_source(int(camera.id), cfg, db=db)
