"""Per-path MediaMTX telemetry read from the local Control API.

The Site Service never infers MediaMTX health from a Python ``_process``
variable owned by another process. It asks the localhost Control API for path
readiness, readers, byte counters, track codecs and per-session RTP counters,
then folds those into SmartPark camera/role health for Hardware Lab.

Everything here is best-effort and bounded: short timeouts, one cached snapshot
shared by all callers, no logging of healthy frames.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from app.services import mediamtx

CACHE_SECONDS = 2.0
TIMEOUT_SECONDS = 1.0
PAGE_SIZE = 500

# Codecs a mainstream browser can render through MediaMTX WebRTC. H.265 support
# varies by browser/platform and is reported as "varies", never silently
# transcoded. Everything else is incompatible and must be surfaced.
_WEBRTC_OK = {"H264", "AV1", "VP8", "VP9"}
_WEBRTC_VARIES = {"H265"}
_VIDEO_HINTS = ("H264", "H265", "AV1", "VP8", "VP9", "MPEG-4 VIDEO", "M-JPEG", "MJPEG", "MPEG-1/2 VIDEO")

_snapshot: dict[str, Any] = {"ok": False, "fetched_at": 0.0, "paths": {}, "error": ""}
_ready_time: dict[str, str] = {}
_reconnects: dict[str, int] = {}


def _get_json(path: str) -> Any | None:
    req = urllib.request.Request(f"{mediamtx.CONTROL_API}{path}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            if not (200 <= int(resp.status) < 300):
                return None
            return json.loads(resp.read().decode("utf-8") or "null")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError):
        return None


def _items(path: str) -> list[dict[str, Any]] | None:
    body = _get_json(f"{path}?itemsPerPage={PAGE_SIZE}&page=0")
    if body is None:
        return None
    if isinstance(body, dict):
        items = body.get("items")
        return [dict(i) for i in items] if isinstance(items, list) else []
    if isinstance(body, list):
        return [dict(i) for i in body if isinstance(i, dict)]
    return []


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _video_codec(tracks: list[Any]) -> str:
    for track in tracks or []:
        name = str(track or "").upper()
        if any(hint in name for hint in _VIDEO_HINTS):
            return name.replace(" ", "-")
    return ""


def webrtc_compatibility(codec: str) -> dict[str, Any]:
    key = str(codec or "").upper().replace("-", "").replace(" ", "")
    if not key:
        return {"compatible": None, "reason": "codec unknown until the path is ready"}
    if key in _WEBRTC_OK:
        return {"compatible": True, "reason": ""}
    if key in _WEBRTC_VARIES:
        return {
            "compatible": None,
            "reason": "H.265 browser WebRTC support varies; use H.264 substream for operator live view",
        }
    return {
        "compatible": False,
        "reason": f"{codec} cannot be played by browser WebRTC; select an H.264 stream. No transcoding is applied.",
    }


def _note_reconnect(name: str, ready: bool, ready_time: str) -> int:
    previous = _ready_time.get(name)
    if ready and ready_time:
        if previous is not None and previous != ready_time:
            _reconnects[name] = _reconnects.get(name, 0) + 1
        _ready_time[name] = ready_time
    return _reconnects.get(name, 0)


def _fold_sessions(paths: dict[str, dict[str, Any]], sessions: list[dict[str, Any]] | None, kind: str) -> None:
    for sess in sessions or []:
        name = str(sess.get("path") or "")
        row = paths.get(name)
        if row is None:
            continue
        state = str(sess.get("state") or "").lower()
        bucket = "publish" if state == "publish" else "read"
        rtp = row["rtp"]
        rtp["packets_received"] += _int(sess.get("rtpPacketsReceived"))
        rtp["packets_sent"] += _int(sess.get("rtpPacketsSent"))
        rtp["packets_lost"] += _int(sess.get("rtpPacketsLost"))
        rtp["packets_in_error"] += _int(sess.get("rtpPacketsInError"))
        rtp["jitter_max"] = max(rtp["jitter_max"], _float(sess.get("rtpPacketsJitter")))
        row["sessions"][kind][bucket] += 1
        if kind == "webrtc" and bucket == "read":
            row["webrtc_readers"] += 1
        if kind == "rtsp" and bucket == "read":
            row["rtsp_readers"] += 1


def refresh(force: bool = False) -> dict[str, Any]:
    """Return the cached Control API snapshot, refreshing at most every CACHE_SECONDS."""
    global _snapshot
    now = time.monotonic()
    if not force and now - float(_snapshot.get("fetched_at") or 0.0) < CACHE_SECONDS:
        return _snapshot

    items = _items("/v3/paths/list")
    if items is None:
        _snapshot = {"ok": False, "fetched_at": now, "paths": {}, "error": "MediaMTX control API unreachable"}
        return _snapshot

    paths: dict[str, dict[str, Any]] = {}
    for item in items:
        name = str(item.get("name") or "")
        if not name:
            continue
        tracks = list(item.get("tracks") or [])
        codec = _video_codec(tracks)
        ready = bool(item.get("ready"))
        ready_time = str(item.get("readyTime") or "")
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        readers = item.get("readers") if isinstance(item.get("readers"), list) else []
        paths[name] = {
            "name": name,
            "ready": ready,
            "ready_time": ready_time,
            "source_type": str((source or {}).get("type") or ""),
            "connected": ready and bool((source or {}).get("type")),
            "readers": len(readers),
            "reader_types": sorted({str(r.get("type") or "") for r in readers if isinstance(r, dict)}),
            "rtsp_readers": 0,
            "webrtc_readers": 0,
            "bytes_received": _int(item.get("bytesReceived")),
            "bytes_sent": _int(item.get("bytesSent")),
            "tracks": [str(t) for t in tracks],
            "codec": codec,
            "webrtc": webrtc_compatibility(codec),
            "reconnects": _note_reconnect(name, ready, ready_time),
            "rtp": {
                "packets_received": 0,
                "packets_sent": 0,
                "packets_lost": 0,
                "packets_in_error": 0,
                "jitter_max": 0.0,
            },
            "sessions": {
                "rtsp": {"read": 0, "publish": 0},
                "webrtc": {"read": 0, "publish": 0},
            },
        }

    _fold_sessions(paths, _items("/v3/rtspsessions/list"), "rtsp")
    _fold_sessions(paths, _items("/v3/webrtcsessions/list"), "webrtc")

    _snapshot = {"ok": True, "fetched_at": now, "paths": paths, "error": ""}
    return _snapshot


def path_telemetry(name: str) -> dict[str, Any] | None:
    return dict(refresh().get("paths", {}).get(name) or {}) or None


def summary() -> dict[str, Any]:
    snap = refresh()
    paths = snap.get("paths", {})
    return {
        "ok": bool(snap.get("ok")),
        "error": snap.get("error", ""),
        "paths_total": len(paths),
        "paths_ready": sum(1 for p in paths.values() if p.get("ready")),
        "readers": sum(int(p.get("readers") or 0) for p in paths.values()),
        "rtp_packets_lost": sum(int(p["rtp"]["packets_lost"]) for p in paths.values()),
        "reconnects": sum(int(p.get("reconnects") or 0) for p in paths.values()),
        "age_seconds": round(time.monotonic() - float(snap.get("fetched_at") or 0.0), 1),
    }


def camera_telemetry(camera_id: int) -> dict[str, Any]:
    """Fold path telemetry into per-role rows for one camera."""
    snap = refresh()
    paths = snap.get("paths", {})
    roles: dict[str, Any] = {}
    for item in mediamtx.path_plan(camera_id):
        row = paths.get(item["name"])
        for role in item["roles"]:
            roles[role] = {
                "mediamtx_path": item["name"],
                "shared_upstream": len(item["roles"]) > 1,
                "on_demand": bool(item["on_demand"]),
                "registered": row is not None,
                **({k: v for k, v in row.items() if k != "name"} if row else {"ready": False, "connected": False}),
            }
    live = roles.get(mediamtx.ROLE_LIVE) or {}
    if not snap.get("ok"):
        state = "OFFLINE"
    elif live.get("ready"):
        state = "LIVE" if not int((live.get("rtp") or {}).get("packets_lost") or 0) else "DEGRADED"
    else:
        state = "OFFLINE" if live.get("registered") else "UNREGISTERED"
    return {
        "camera_id": int(camera_id),
        "control_api_ok": bool(snap.get("ok")),
        "state": state,
        "codec": live.get("codec") or "",
        "webrtc": live.get("webrtc") or webrtc_compatibility(""),
        "roles": roles,
    }


def reset() -> None:
    """Test hook: forget cached snapshot and reconnect counters."""
    global _snapshot
    _snapshot = {"ok": False, "fetched_at": 0.0, "paths": {}, "error": ""}
    _ready_time.clear()
    _reconnects.clear()
