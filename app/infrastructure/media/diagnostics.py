"""Turn media-health samples into a PASS / DEGRADED / FAIL report.

This module does not open cameras, create parking sessions, or print secrets.
"""

from __future__ import annotations

from typing import Any

from app.services.rtsp_probe import redact_url

PASS = "PASS"
DEGRADED = "DEGRADED"
FAIL = "FAIL"

LIVE_AGE_WARN_MS = 500.0
LIVE_AGE_FAIL_MS = 2500.0
INTERVAL_FAIL_MS = 2000.0
QUEUE_MAX = 1
CHILD_PID_MAX = 3
FROZEN_FAIL_RATIO = 0.5
FROZEN_WARN_RATIO = 0.1


def scrub(value: Any) -> Any:
    """Remove credentials before a report is printed or stored."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(word in lowered for word in ("password", "secret", "token", "authorization")):
                continue
            if lowered in {"url", "uri", "rtsp"} and isinstance(item, str):
                out[key] = redact_url(item)
            else:
                out[key] = scrub(item)
        return out
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, str) and "://" in value:
        return redact_url(value)
    return value


def summarize_samples(samples: list[dict[str, Any]], *, name: str = "", adapter: str = "") -> dict[str, Any]:
    if not samples:
        return {
            "camera_id": None,
            "name": name,
            "adapter": adapter,
            "samples": 0,
            "frames_changed": 0,
            "frames_received": 0,
            "duplicate_frames": 0,
            "frames_dropped": 0,
            "max_live_frame_age_ms": None,
            "max_queue_depth": 0,
            "max_detect_queue_depth": 0,
            "max_child_pids": 0,
            "reconnects": 0,
            "decoder_restarts": 0,
            "frozen_samples": 0,
            "connection_state": "DISCONNECTED",
        }
    first, last = samples[0], samples[-1]

    def delta(key: str) -> int:
        return int(last.get(key) or 0) - int(first.get(key) or 0)

    ages = [float(row["live_frame_age_ms"]) for row in samples if row.get("live_frame_age_ms") is not None]
    detect_ages = [float(row["detect_frame_age_ms"]) for row in samples if row.get("detect_frame_age_ms") is not None]
    queues = [int(row.get("queue_depth") or 0) for row in samples]
    detect_queues = [int(row.get("detect_queue_depth") or 0) for row in samples]
    children = [len(row.get("child_pids") or []) for row in samples]
    frozen_samples = sum(1 for row in samples if row.get("frozen"))
    return {
        "camera_id": last.get("camera_id"),
        "name": name or last.get("name") or "",
        "adapter": adapter or _adapter(last),
        "source": last.get("source") or "",
        "measurement": last.get("measurement") or "frames",
        "bytes_received": max(0, delta("bytes_received")),
        "live_role": "LIVE",
        "detect_role": "DETECT",
        "connection_state": last.get("connection_state") or "DISCONNECTED",
        "source_fps": last.get("source_fps") or 0,
        "live_fps": last.get("live_fps") or last.get("fps") or 0,
        "frames_received": max(0, delta("frames_received")),
        "frames_changed": max(0, delta("frames_changed")),
        "duplicate_frames": max(0, delta("duplicate_frames")),
        "frames_dropped": max(0, delta("frames_dropped_live")),
        "live_frame_age_ms": last.get("live_frame_age_ms"),
        "detect_frame_age_ms": last.get("detect_frame_age_ms") if last.get("detect_frame_age_ms") is not None else last.get("ai_frame_age_ms"),
        "max_live_frame_age_ms": max(ages) if ages else None,
        "max_detect_frame_age_ms": max(detect_ages) if detect_ages else None,
        "frame_interval_avg_ms": last.get("frame_interval_avg_ms"),
        "frame_interval_p50_ms": last.get("frame_interval_p50_ms"),
        "frame_interval_p95_ms": last.get("frame_interval_p95_ms"),
        "frame_interval_max_ms": last.get("frame_interval_max_ms"),
        "reconnects": max(0, delta("reconnects")),
        "decoder_restarts": max(0, delta("decoder_restarts")),
        "ffmpeg_pid": last.get("ffmpeg_pid"),
        "child_pids": list(last.get("child_pids") or []),
        "max_queue_depth": max(queues) if queues else 0,
        "max_detect_queue_depth": max(detect_queues) if detect_queues else 0,
        "max_child_pids": max(children) if children else 0,
        "frozen_samples": frozen_samples,
        "samples": len(samples),
        "codec": last.get("codec") or "",
        "width": last.get("width") or 0,
        "height": last.get("height") or 0,
        "gop": last.get("gop") or 0,
        "bitrate_bps": last.get("bitrate_bps") or 0,
        "transport": last.get("transport") or "",
        "url_redacted": last.get("url_redacted") or "",
        "last_error": last.get("last_error") or "",
        "warnings": list(last.get("warnings") or []),
    }


def verdict_for(summary: dict[str, Any], *, duration_s: float) -> tuple[str, list[str]]:
    reasons: list[str] = []
    fails: list[str] = []
    warns: list[str] = []
    samples = int(summary.get("samples") or 0)
    if samples <= 0:
        return FAIL, ["no media samples were collected"]
    if summary.get("measurement") == "transport":
        if summary.get("connection_state") != "STREAMING" or int(summary.get("bytes_received") or 0) <= 0:
            return FAIL, ["MediaMTX did not receive increasing stream bytes on a ready path"]
        return DEGRADED, ["MediaMTX stream bytes are advancing; decoded FPS, picture freshness and display latency require a player check"]
    changed = int(summary.get("frames_changed") or 0)
    if duration_s >= 5 and changed <= 0:
        fails.append("no fresh frames during the run")
    queue = int(summary.get("max_queue_depth") or 0)
    detect_queue = int(summary.get("max_detect_queue_depth") or 0)
    if queue > QUEUE_MAX or detect_queue > QUEUE_MAX:
        fails.append(f"frame buffer grew above {QUEUE_MAX} (live {queue}, detect {detect_queue})")
    if int(summary.get("max_child_pids") or 0) > CHILD_PID_MAX:
        fails.append("decoder process count grew past the per-camera cap")
    age = summary.get("max_live_frame_age_ms")
    if age is not None and float(age) > LIVE_AGE_FAIL_MS:
        fails.append(f"live frame age reached {float(age):.0f} ms")
    elif age is not None and float(age) > LIVE_AGE_WARN_MS:
        warns.append(f"live frame age peaked at {float(age):.0f} ms (target < {LIVE_AGE_WARN_MS:.0f} ms)")
    interval = summary.get("frame_interval_p95_ms")
    if interval is not None and float(interval) > INTERVAL_FAIL_MS:
        fails.append(f"p95 frame interval {float(interval):.0f} ms")
    elif interval is not None and float(interval) > LIVE_AGE_WARN_MS:
        warns.append(f"p95 frame interval {float(interval):.0f} ms")
    frozen = int(summary.get("frozen_samples") or 0)
    ratio = frozen / samples if samples else 0.0
    if ratio > FROZEN_FAIL_RATIO:
        fails.append(f"repeated the same frame on {frozen}/{samples} samples")
    elif ratio > FROZEN_WARN_RATIO:
        warns.append(f"repeated the same frame on {frozen}/{samples} samples")
    restarts = int(summary.get("reconnects") or 0)
    if restarts > 5:
        warns.append(f"{restarts} reconnects during the run")
    if changed > 0 and str(summary.get("connection_state") or "") not in {"STREAMING", "DEGRADED"}:
        warns.append(f"ended in {summary.get('connection_state')}")
    if fails:
        reasons.extend(fails)
        reasons.extend(warns)
        return FAIL, reasons
    if warns:
        return DEGRADED, warns
    return PASS, ["fresh frames stayed within the live-age target and buffers stayed at 1"]


def overall(rows: list[tuple[str, list[str]]]) -> str:
    states = [state for state, _reasons in rows]
    if not states or FAIL in states:
        return FAIL
    if DEGRADED in states:
        return DEGRADED
    return PASS


def _adapter(row: dict[str, Any]) -> str:
    source = str(row.get("source") or "").lower()
    if source == "sdk" or row.get("sdk"):
        return "hvx-sdk"
    if source == "mediamtx":
        return "mediamtx"
    if source == "rtsp":
        return "rtsp"
    if source == "http":
        return "http-snapshot"
    return source or "unknown"
