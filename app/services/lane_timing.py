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
    _trace_mark(stage, timeline, stamp)
    return timeline


# Stages at which the visit is decided or the barrier is asked to open. The
# age of the newest frame/event the timeline carries is recorded there.
DECISION_STAGES = {"parking_controller_entered", "gate_requested"}
# Timeline stages that stamp the capture time of what recognition used:
# a worker frame (FFmpeg decode of the DETECT path) or a native camera event.
SOURCE_STAGES = {"frame_decoded": "frame", "native_event_captured": "native_event"}


def decision_source_age(timeline: dict, now: float | None = None) -> dict:
    """Age (ms) of the newest frame or native event behind this timeline.

    Uses the timeline's ``time.monotonic`` origin; worker, site service and
    host run on one PC, where that clock is shared.
    """
    origin = timeline.get("origin_monotonic")
    stages = timeline.get("stages_ms") or {}
    now = time.monotonic() if now is None else now
    best = None
    for stage, kind in SOURCE_STAGES.items():
        if stage in stages and origin is not None:
            captured = float(origin) + float(stages[stage]) / 1000.0
            if best is None or captured > best[1]:
                best = (kind, captured)
    if best is None:
        return {"source": None, "age_ms": None, "stale": None}
    from app.core.latency_trace import event_age_limit_ms, frame_age_limit_ms

    kind, captured = best
    age_ms = round((now - captured) * 1000.0, 1)
    limit = frame_age_limit_ms() if kind == "frame" else event_age_limit_ms()
    return {"source": kind, "age_ms": age_ms, "limit_ms": limit, "stale": age_ms > limit}


def _trace_mark(stage: str, timeline: dict, stamp: float) -> None:
    try:
        from app.core import latency_trace

        tracer = latency_trace.get_tracer()
        if not tracer.enabled:
            return
        common = {
            "visit_id": timeline.get("visit_id"),
            "camera": timeline.get("camera_id"),
            "direction": timeline.get("direction"),
            "command_uuid": timeline.get("command_uuid"),
            "frame_seq": timeline.get("frame_seq"),
            "generation": timeline.get("generation"),
            "capture_token": timeline.get("capture_token"),
        }
        tracer.emit(f"lane.{stage}", since_origin_ms=(timeline.get("stages_ms") or {}).get(stage),
                    origin_stage=timeline.get("origin_stage"), **common)
        if stage in DECISION_STAGES:
            source = decision_source_age(timeline, now=stamp)
            tracer.emit("decision.source_age", at_stage=stage, **source, **common)
    except Exception:
        logging.getLogger("smartpark.lane_timeline").debug("latency trace failed", exc_info=True)


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
