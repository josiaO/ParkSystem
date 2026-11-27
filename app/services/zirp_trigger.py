"""Zirp's own vehicle trigger: shadow records for proving independence.

On SITE-PC01 97.5% of captures started from camera snapshots commanded by
the legacy ParkWatch system (the ground loops are wired to its I/O
boards). Zirp must find cars on its own. Its trigger is the live-video
arrival gate (a plate box that settles at the configured capture width).
These records let that trigger be measured car-by-car against the
ParkWatch-triggered reads before Zirp relies on it:

    zirp.seen     a plate box appeared (start of an episode), with its width
    zirp.ready    the gate fired; with the live-frame read (plate, confidence)
    zirp.gone     the episode ended; widest plate seen and whether it fired

Nothing here commands a camera. ``fired``/``claim`` also match each
snapshot Zirp commands to its request and learn the camera's snapshot delay.
"""

from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_episodes: dict[int, dict] = {}


def _emit(stage: str, **fields) -> None:
    try:
        from app.core import latency_trace

        latency_trace.emit(stage, **fields)
    except Exception:
        pass


def box_width(box: dict | None) -> int:
    if not isinstance(box, dict):
        return 0
    try:
        return int(box["x2"]) - int(box["x1"])
    except (KeyError, TypeError, ValueError):
        return 0


def observe(camera_id: int, box: dict | None, phase: str, *, frame_width: int = 0) -> None:
    """Called for every detector sample of the arrival gate."""
    width = box_width(box)
    now = time.time()
    with _lock:
        episode = _episodes.get(int(camera_id))
        if width and episode is None:
            episode = _episodes[int(camera_id)] = {"since": now, "max_width": width, "fired": False,
                                                    "frame_width": int(frame_width or 0)}
            _emit("zirp.seen", camera=int(camera_id), width=width, frame_width=int(frame_width or 0))
        elif episode is not None and width:
            episode["max_width"] = max(episode["max_width"], width)
        if phase == "ready" and episode is not None:
            episode["fired"] = True
        if phase in {"absent", "departed"} and episode is not None:
            _episodes.pop(int(camera_id), None)
            _emit("zirp.gone", camera=int(camera_id), max_width=episode["max_width"], fired=episode["fired"],
                  seconds=round(now - episode["since"], 1), frame_width=episode["frame_width"])


# -- Zirp's own snapshot requests --------------------------------------------
#
# The camera takes the snapshot some time after Zirp asks for it (0.32-0.75 s,
# median 0.57 s on one site). The capture gate fires that much early, so the
# picture is taken when the plate is inside the calibration. Each snapshot
# that comes back is matched to its request, which measures the delay for
# that camera and tells the event path to fall back to the last in-zone live
# frame when the snapshot missed the plate.

DEFAULT_DELAY_SECONDS = 0.55
MIN_DELAY_SECONDS = 0.1
MAX_DELAY_SECONDS = 1.5
MATCH_WINDOW_SECONDS = 2.0
_SMOOTHING = 0.3
_pending: dict[int, int] = {}            # camera -> perf_counter_ns when Zirp asked
_delay: dict[int, float] = {}            # camera -> learned snapshot delay (s)


def lead_seconds(camera_id: int) -> float:
    """How long after asking this camera takes its snapshot."""
    with _lock:
        return float(_delay.get(int(camera_id), DEFAULT_DELAY_SECONDS))


def fired(camera_id: int, *, mode: str, predicted: bool = False) -> None:
    """The virtual loop fired and Zirp commanded the camera (mode=snapshot)."""
    if mode == "snapshot":
        with _lock:
            _pending[int(camera_id)] = time.perf_counter_ns()
    _emit("zirp.fired", camera=int(camera_id), mode=mode, predicted=bool(predicted) or None,
          lead_ms=round(lead_seconds(camera_id) * 1000) if mode == "snapshot" else None)


def claim(camera_id: int, captured_perf_ns) -> bool:
    """True when this camera picture is the snapshot Zirp asked for.

    The first picture from that camera inside the match window is taken as
    the answer; its delay updates the camera's learned delay.
    """
    try:
        captured = int(captured_perf_ns or 0)
    except (TypeError, ValueError):
        captured = 0
    with _lock:
        asked = _pending.get(int(camera_id))
        if not asked:
            return False
        if not captured:
            _pending.pop(int(camera_id), None)
            return True
        delay = (captured - asked) / 1e9
        if delay < 0 or delay > MATCH_WINDOW_SECONDS:
            if delay > MATCH_WINDOW_SECONDS:
                _pending.pop(int(camera_id), None)
            return False
        _pending.pop(int(camera_id), None)
        if MIN_DELAY_SECONDS <= delay <= MAX_DELAY_SECONDS:
            old = _delay.get(int(camera_id), DEFAULT_DELAY_SECONDS)
            _delay[int(camera_id)] = round(old + _SMOOTHING * (delay - old), 3)
    _emit("zirp.snapshot", camera=int(camera_id), delay_ms=round(delay * 1000, 1))
    return True


def expire(camera_id: int) -> bool:
    """No snapshot arrived: forget the request. True if one was pending."""
    with _lock:
        return _pending.pop(int(camera_id), None) is not None


def reset() -> None:
    with _lock:
        _pending.clear()
        _delay.clear()


def ready(camera_id: int, alpr: dict | None, *, width: int = 0, frame_width: int = 0, departed: bool = False) -> None:
    """The gate fired (or a far car left) and a live frame was read."""
    best = (alpr or {}).get("best") or {}
    _emit("zirp.departed_read" if departed else "zirp.ready", camera=int(camera_id), plate=str(best.get("plate") or "") or None,
          confidence=round(float(best.get("confidence") or 0), 3) or None, width=int(width or 0),
          frame_width=int(frame_width or 0), skipped=(alpr or {}).get("persist_skipped") or None)
