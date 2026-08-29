"""Discover MAIN/SUB URIs: ONVIF first, then vendor adapter, then manual RTSP."""

from __future__ import annotations

from typing import Any

from app.services.onvif_discover import discover_onvif_streams
from app.services.rtsp_probe import probe, vendor_candidates
from app.services.stream_roles import classify_stream, recommend_roles


async def discover_camera_streams(
    ip: str,
    username: str,
    password: str,
    explicit: str = "",
    *,
    timeout: float = 3.0,
) -> dict[str, Any]:
    onvif = await discover_onvif_streams(ip, username, password, timeout=timeout)
    discovered: list[dict[str, Any]] = list(onvif.get("profiles") or [])
    source = "onvif" if discovered else ""
    if not discovered and explicit:
        result = await probe(explicit)
        row = {
            "uri": explicit,
            "uri_redacted": result.url_redacted,
            "protocol": "rtsp",
            "codec": result.codec,
            "width": result.width,
            "height": result.height,
            "fps": result.fps,
            "ok": result.ok,
            "error": result.error,
        }
        row["role"] = classify_stream(row)
        discovered.append(row)
        source = "manual"
    if not discovered:
        source = "vendor"
        for index, url in enumerate(vendor_candidates(ip, username, password, explicit)[:6]):
            result = await probe(url)
            if not result.ok:
                continue
            row = {
                "uri": url,
                "uri_redacted": result.url_redacted,
                "protocol": "rtsp",
                "codec": result.codec,
                "width": result.width,
                "height": result.height,
                "fps": result.fps,
            }
            row["role"] = classify_stream(row)
            discovered.append(row)
            if index >= 1 and len(discovered) >= 2:
                break
    profiles = recommend_roles(discovered)
    return {
        "ok": bool(discovered),
        "source": source or "none",
        "onvif": onvif,
        "discovered": discovered,
        "stream_profiles": profiles,
        "error": "" if discovered else (onvif.get("error") or "No stream profiles found"),
    }
