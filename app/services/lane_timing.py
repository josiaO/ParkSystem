"""Monotonic per-visit timeline carried through the local process boundary."""

from __future__ import annotations

import json
import logging
import time
import threading
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps

_current: ContextVar[dict | None] = ContextVar("lane_timeline", default=None)
_durations: dict[int, dict[str, deque]] = {}
_lock = threading.Lock()


def mark(stage: str, timeline: dict | None = None, *, at: float | None = None, **fields) -> dict:
    timeline = timeline if timeline is not None else _current.get()
    if timeline is None:
        return {}
    stamp = time.monotonic() if at is None else at
    origin = timeline.setdefault("origin_monotonic", stamp)
    timeline.setdefault("origin_stage", stage)
    first = stage not in timeline.setdefault("stages_ms", {})
    timeline.setdefault("stages_ms", {})[stage] = round((stamp - origin) * 1000, 1)
    timeline.update(fields)
    if first and timeline["origin_stage"] == "vehicle_seen" and stage in {"capture_saved", "parking_controller_entered", "session_created", "receipt_requested", "receipt_printed", "gate_requested"}:
        with _lock:
            series = _durations.setdefault(int(timeline.get("camera_id") or 0), {}).setdefault(stage, deque(maxlen=200))
            series.append(timeline["stages_ms"][stage])
    logging.getLogger("smartpark.lane_timeline").info("%s", json.dumps(timeline, default=str))
    return timeline


def timeline_metrics(camera_id: int) -> dict:
    from app.services.recognition_runtime import _percentile

    with _lock:
        return {stage: {"count": len(samples), "p50": _percentile(list(samples), 50),
                        "p95": _percentile(list(samples), 95), "max": max(samples)}
                for stage, samples in _durations.get(int(camera_id), {}).items() if samples}


@contextmanager
def visit_timing(timeline: dict):
    token = _current.set(timeline)
    try:
        yield timeline
    finally:
        _current.reset(token)


def observe_duration(stats: dict, stage: str, milliseconds: float) -> None:
    from app.services.recognition_runtime import _percentile

    samples = stats.setdefault("latency_samples", {}).setdefault(stage, [])
    samples.append(round(float(milliseconds), 1))
    del samples[:-200]
    stats.setdefault("latency_ms", {})[stage] = {
        "count": len(samples), "p50": _percentile(samples, 50),
        "p95": _percentile(samples, 95), "max": max(samples),
    }


def timed_capture(handler):
    @wraps(handler)
    async def wrapped(*args, **kwargs):
        capture = kwargs["capture"]
        timeline = dict((capture.bbox or {}).get("timeline") or {})
        timeline["stages_ms"] = dict(timeline.get("stages_ms") or {})
        timeline.update(visit_id=capture.visit_id, camera_id=capture.camera_id, direction=capture.lane_direction)
        with visit_timing(timeline):
            mark("capture_saved")
            mark("parking_controller_entered")
            result = await handler(*args, **kwargs)
            mark("parking_controller_returned", session_id=(result.get("session") or {}).get("id"))
            capture.bbox = {**(capture.bbox or {}), "timeline": timeline}
            args[0].commit()
            return result
    return wrapped
