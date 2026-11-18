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

Nothing here commands a camera.
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


def fired(camera_id: int, *, mode: str) -> None:
    """The virtual loop fired and Zirp commanded the camera (mode=snapshot)."""
    _emit("zirp.fired", camera=int(camera_id), mode=mode)


def ready(camera_id: int, alpr: dict | None, *, width: int = 0, frame_width: int = 0, departed: bool = False) -> None:
    """The gate fired (or a far car left) and a live frame was read."""
    best = (alpr or {}).get("best") or {}
    _emit("zirp.departed_read" if departed else "zirp.ready", camera=int(camera_id), plate=str(best.get("plate") or "") or None,
          confidence=round(float(best.get("confidence") or 0), 3) or None, width=int(width or 0),
          frame_width=int(frame_width or 0), skipped=(alpr or {}).get("persist_skipped") or None)
