"""MAIN / SUB / LIVE / DETECT / EVIDENCE roles. One camera, several stream jobs."""

from __future__ import annotations

from typing import Any

from app.domain.media import STREAM_ROLES
from app.services.rtsp_probe import redact_url

ROLE_LIVE = "LIVE"
ROLE_DETECT = "DETECT"
ROLE_MAIN = "MAIN"
ROLE_SUB = "SUB"
ROLE_EVIDENCE = "EVIDENCE"

CAPABILITY_FLAGS = (
    "ONVIF",
    "RTSP",
    "RTSPS",
    "HTTP_MJPEG",
    "SNAPSHOT",
    "H264",
    "H265",
    "MAIN_STREAM",
    "SUB_STREAM",
    "THIRD_STREAM",
    "NATIVE_ALPR",
    "ANALYTICS_METADATA",
    "HARDWARE_EVENTS",
)


def empty_profiles() -> dict[str, dict[str, Any]]:
    return {role: {} for role in STREAM_ROLES}


def _pixels(row: dict[str, Any]) -> int:
    return int(row.get("width") or 0) * int(row.get("height") or 0)


def _fps_value(row: dict[str, Any]) -> float:
    raw = row.get("fps")
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw or "")
    if "/" in text:
        num, den = text.split("/", 1)
        try:
            return float(num) / max(float(den), 1.0)
        except ValueError:
            return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def classify_stream(row: dict[str, Any]) -> str:
    """Recommend a role from resolution. Admin may override."""
    width = int(row.get("width") or 0)
    height = int(row.get("height") or 0)
    pixels = width * height
    if pixels >= 1920 * 1080 or width >= 1920:
        return ROLE_MAIN
    if pixels >= 1280 * 720 or width >= 1280:
        return ROLE_SUB
    if pixels > 0:
        return ROLE_SUB
    return ROLE_MAIN


def recommend_roles(discovered: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    ranked = sorted(
        [dict(row) for row in discovered if row],
        key=lambda row: (_pixels(row), _fps_value(row)),
        reverse=True,
    )
    profiles = empty_profiles()
    if not ranked:
        return profiles
    main = ranked[0]
    sub = ranked[1] if len(ranked) > 1 else ranked[0]
    profiles[ROLE_MAIN] = {**main, "role": ROLE_MAIN}
    profiles[ROLE_SUB] = {**sub, "role": ROLE_SUB}
    profiles[ROLE_EVIDENCE] = {"source": ROLE_MAIN, "role": ROLE_EVIDENCE}
    profiles[ROLE_LIVE] = {"source": ROLE_SUB, "role": ROLE_LIVE}
    profiles[ROLE_DETECT] = {"source": ROLE_SUB, "role": ROLE_DETECT, "ai_fps": 5}
    return profiles


def hvx_profiles(handle: int | None = None) -> dict[str, dict[str, Any]]:
    uri = f"sdk://handle/{int(handle)}" if handle is not None else "sdk://live"
    sdk = {
        "protocol": "sdk",
        "uri": uri,
        "codec": "jpeg",
        "transport": "host",
        "note": "Net_StartVideo + Net_GetJpgBuffer on the HVX host. Not RTSP.",
    }
    return {
        ROLE_MAIN: {**sdk, "role": ROLE_MAIN, "stream_index": 0},
        ROLE_SUB: {**sdk, "role": ROLE_SUB, "stream_index": 1},
        ROLE_LIVE: {"source": ROLE_SUB, "role": ROLE_LIVE},
        ROLE_DETECT: {"source": ROLE_SUB, "role": ROLE_DETECT, "ai_fps": 5},
        ROLE_EVIDENCE: {"source": ROLE_MAIN, "role": ROLE_EVIDENCE},
    }


def uri_for_role(profiles: dict[str, Any] | None, role: str, fallback: str = "") -> str:
    rows = profiles or {}
    wanted = str(role or ROLE_LIVE).upper()
    seen: set[str] = set()
    while wanted and wanted not in seen:
        seen.add(wanted)
        row = rows.get(wanted) or {}
        uri = str(row.get("uri") or row.get("url") or "")
        if uri:
            return uri
        wanted = str(row.get("source") or "")
    return fallback


def resolve_role_row(profiles: dict[str, Any] | None, role: str) -> dict[str, Any]:
    rows = profiles or {}
    wanted = str(role or ROLE_LIVE).upper()
    seen: set[str] = set()
    current: dict[str, Any] = {}
    while wanted and wanted not in seen:
        seen.add(wanted)
        current = dict(rows.get(wanted) or {})
        if current.get("uri") or current.get("url"):
            return {**current, "role": wanted}
        wanted = str(current.get("source") or "")
    return current


def profile_warnings(
    profiles: dict[str, Any] | None,
    *,
    upstream_consumers: int = 1,
    decoder_overloaded: bool = False,
    smart_codec: bool = False,
) -> list[str]:
    rows = profiles or {}
    warnings: list[str] = []
    main = rows.get(ROLE_MAIN) or {}
    sub = rows.get(ROLE_SUB) or {}
    live = resolve_role_row(rows, ROLE_LIVE)
    detect = resolve_role_row(rows, ROLE_DETECT)
    if smart_codec or "264+" in str(main.get("codec") or "").lower() or "265+" in str(main.get("codec") or "").lower():
        warnings.append("Smart codec enabled")
    gop = int(main.get("gop") or live.get("gop") or 0)
    fps = _fps_value(main) or _fps_value(live)
    if gop and fps and gop > max(fps * 2, 30):
        warnings.append("GOP unusually long")
    if not (sub.get("uri") or sub.get("url")) and (main.get("uri") or main.get("url")):
        if str(live.get("uri") or "") == str(main.get("uri") or "") or live.get("source") == ROLE_MAIN:
            warnings.append("No substream")
            warnings.append("Main stream used for all roles")
    if upstream_consumers > 1:
        warnings.append("Multiple upstream consumers")
    if decoder_overloaded:
        warnings.append("Decoder overloaded")
    detect_src = str((rows.get(ROLE_DETECT) or {}).get("source") or ROLE_SUB)
    if detect_src == ROLE_MAIN and (sub.get("uri") or sub.get("url")):
        warnings.append("DETECT is using MAIN while a substream exists")
    return warnings


def public_profiles(profiles: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for role, row in (profiles or {}).items():
        item = dict(row or {})
        uri = str(item.get("uri") or item.get("url") or "")
        if uri:
            item["uri_redacted"] = redact_url(uri)
            item.pop("uri", None)
            item.pop("url", None)
        out[str(role).upper()] = item
    return out


def merge_profiles(existing: dict[str, Any] | None, incoming: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(existing or {})
    for role, row in (incoming or {}).items():
        key = str(role).upper()
        if key not in STREAM_ROLES:
            continue
        current = dict(merged.get(key) or {})
        current.update({k: v for k, v in dict(row or {}).items() if v not in (None, "")})
        merged[key] = current
    return merged


def default_capabilities(*, native_alpr: bool = False, sdk: bool = False, rtsp: bool = False) -> list[str]:
    flags: list[str] = []
    if sdk:
        flags.extend(["HARDWARE_EVENTS", "SNAPSHOT"])
    if native_alpr:
        flags.append("NATIVE_ALPR")
    if rtsp:
        flags.extend(["RTSP", "SNAPSHOT", "MAIN_STREAM", "SUB_STREAM"])
    return flags
