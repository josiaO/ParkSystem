"""Universal camera onboarding. Tries HVX, then ONVIF, RTSP, HTTP, then manual URI."""

from __future__ import annotations

import time
from typing import Any

from app.infrastructure.hardware.cameras import camera_adapter_for
from app.services.http_snapshot import grab_http_snapshot
from app.services.rtsp_probe import probe, vendor_candidates
from app.services.site_cameras import tcp_open
from app.services.stream_discover import discover_camera_streams
from app.services.stream_roles import recommend_roles


def _cam(ip: str, username: str, password: str, port: int, rtsp_url: str = "", adapter_id: str = "hvx"):
    return type("OnboardCam", (), {
        "id": 0,
        "name": ip,
        "ip_address": ip,
        "sdk_port": port,
        "username": username,
        "password_secret": password,
        "rtsp_url": rtsp_url,
        "sdk_handle": None,
        "adapter_id": adapter_id,
        "connection_mode": "DIRECT",
    })()


async def probe_connection(
    *,
    ip: str,
    username: str = "admin",
    password: str = "admin",
    port: int | None = None,
    rtsp_url: str = "",
) -> dict[str, Any]:
    ip = (ip or "").strip()
    attempts: list[dict[str, Any]] = []
    recommended = "rtsp"
    profiles: dict[str, Any] = {}
    capabilities: list[str] = []
    sdk_port = int(port or 30000)

    hvx_open = await tcp_open(ip, sdk_port, timeout=1.0) if ip else False
    attempts.append({"step": "vendor_adapter", "adapter_id": "hvx", "tcp_open": hvx_open, "port": sdk_port})
    if hvx_open:
        recommended = "hvx"
        capabilities.extend(["NATIVE_ALPR", "SNAPSHOT", "MAIN_STREAM", "SUB_STREAM"])

    onvif = await discover_camera_streams(ip, username, password, rtsp_url)
    attempts.append({
        "step": "onvif",
        "ok": bool(onvif.get("ok")),
        "source": onvif.get("source") or "",
        "count": len(onvif.get("discovered") or []),
        "error": onvif.get("error") or "",
    })
    if onvif.get("stream_profiles") or onvif.get("discovered"):
        profiles = onvif.get("stream_profiles") or {}
        if "ONVIF" not in capabilities and onvif.get("source") == "onvif":
            capabilities.append("ONVIF")
        if recommended != "hvx":
            recommended = "onvif" if onvif.get("source") == "onvif" else recommended

    urls = vendor_candidates(ip, username, password, rtsp_url)
    rtsp_ok = False
    rtsp_detail: dict[str, Any] = {}
    for url in urls[:4]:
        result = await probe(url)
        rtsp_detail = result.__dict__ if hasattr(result, "__dict__") else dict(result or {})
        if rtsp_detail.get("ok"):
            rtsp_ok = True
            if not profiles:
                profiles = recommend_roles([{
                    "uri": url,
                    "codec": rtsp_detail.get("codec") or "",
                    "width": rtsp_detail.get("width") or 0,
                    "height": rtsp_detail.get("height") or 0,
                    "fps": rtsp_detail.get("fps") or 0,
                }])
            break
    attempts.append({"step": "rtsp", "ok": rtsp_ok, "tried": len(urls), **{k: v for k, v in rtsp_detail.items() if k != "url"}})
    if rtsp_ok:
        capabilities.extend([c for c in ("RTSP", "SNAPSHOT") if c not in capabilities])
        if recommended not in {"hvx"}:
            recommended = "rtsp"

    http = await grab_http_snapshot(ip, username, password)
    attempts.append({
        "step": "http_mjpeg",
        "ok": bool(http.get("ok")),
        "url_redacted": http.get("url_redacted") or "",
        "error": http.get("error") or "",
    })
    if http.get("ok"):
        capabilities.extend([c for c in ("HTTP_STREAM", "SNAPSHOT") if c not in capabilities])
        if recommended not in {"hvx", "rtsp"}:
            recommended = "rtsp"

    attempts.append({"step": "manual_stream", "ok": bool((rtsp_url or "").strip()), "provided": bool((rtsp_url or "").strip())})

    camera_type = "VENDOR_SDK_CAMERA" if recommended == "hvx" else (
        "GENERIC_ONVIF" if recommended == "onvif" else "GENERIC_RTSP"
    )
    recognition = "NATIVE_ONLY" if recommended == "hvx" else "FASTALPR_ONLY"
    return {
        "ok": hvx_open or rtsp_ok or bool(http.get("ok")) or bool(onvif.get("ok")),
        "ip": ip,
        "recommended_adapter": recommended,
        "camera_type": camera_type,
        "recognition_mode": recognition,
        "capabilities": sorted(set(capabilities)),
        "profiles": profiles,
        "attempts": attempts,
        "note": (
            "HVX stays the site default when port 30000 is open. "
            "ONVIF/RTSP/HTTP are extras and never replace a working NetSDK login."
        ),
    }


async def test_path(
    *,
    ip: str,
    username: str = "admin",
    password: str = "admin",
    adapter_id: str = "rtsp",
    rtsp_url: str = "",
    port: int = 30000,
    duration_seconds: float = 8.0,
) -> dict[str, Any]:
    """Short stability sample. UI may request 60s; tests use a few seconds."""
    started = time.monotonic()
    device = _cam(ip, username, password, port, rtsp_url, adapter_id)
    adapter = camera_adapter_for(device)
    connect = await adapter.connect(device)
    snapshot = b""
    try:
        snapshot = await adapter.snapshot(device)
    except Exception:
        snapshot = connect.get("jpeg") or b""
    wait = max(0.2, min(float(duration_seconds or 1.0), 60.0))
    await __import__("asyncio").sleep(min(wait, 1.5) if wait > 1.5 else wait)
    health = await adapter.health(device)
    elapsed = round((time.monotonic() - started) * 1000.0, 1)
    return {
        "ok": bool(connect.get("connected") or snapshot[:2] == b"\xff\xd8"),
        "adapter_id": adapter.id,
        "connect": {k: v for k, v in connect.items() if k != "jpeg"},
        "snapshot_bytes": len(snapshot or b""),
        "health": health,
        "duration_ms": elapsed,
        "reconnect": bool(health.get("ok")),
        "recognition": "native" if adapter.id == "hvx" else "fastalpr",
        "note": "Full 60s soak belongs on the parking PC after save. This probe confirms connect + snapshot.",
    }
