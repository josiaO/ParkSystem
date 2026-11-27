"""Run the plate detector only when the picture changes.

Zirp's trigger ran the plate detector on every camera's live picture four
times a second, empty lane or not. One detection costs about 80-90 ms of CPU
on a 704 x 576 frame, so four cameras kept more than a whole core busy
watching still tarmac (measured on one site: the Site Service averaged 1.7
cores, about 1.4 of them on idle lanes).

Before each detection a tiny grey thumbnail of the frame (about 1 ms: the
JPEG is decoded at 1/8 scale, then smoothed) is compared with the previous
one, inside the part of the picture where a car must appear: the camera's
calibration zone, extended towards where cars come from. Traffic on the road
behind, people on the pavement and moving trees are outside it (on one site
they made 50-80% of whole-picture samples look like motion). The detector
runs when:

* the watched area moved since the previous sample (a car, the barrier);
* a plate was seen in the last few seconds (a car standing in the lane is
  still watched every sample, so the gate can fire and notice it leave);
* or a few seconds passed since the last detection (a slow, creeping car or a
  change the thumbnail missed is still caught).

Switched under Settings -> Recognition ("Look for plates only when the picture
moves"); on by default.
"""

from __future__ import annotations

import io
import threading
import time
from dataclasses import dataclass

THUMB_SIZE = (64, 48)
PIXEL_CHANGE = 24            # grey levels (0-255) for a thumbnail pixel to count as changed
MOTION_FRACTION = 0.01       # share of the watched area; a car entering it changes far more
APPROACH_MARGIN = 0.30       # watch this much of the picture beyond the zone, where cars come from
SIDE_MARGIN = 0.08           # and this much around the other sides
PLATE_HOLD_SECONDS = 3.0     # keep detecting this long after the last plate
IDLE_CHECK_SECONDS = 2.0     # detect at least this often even when nothing moves


@dataclass
class _State:
    thumb: object = None
    last_detect: float = float("-inf")       # never
    last_plate: float = float("-inf")        # never
    skipped: int = 0
    detected: int = 0


_lock = threading.Lock()
_states: dict[int, _State] = {}


def enabled() -> bool:
    from app.services import runtime_settings

    value = runtime_settings.get("motion_gate")
    return True if value is None else bool(value)


def thumbnail(jpeg: bytes):
    """Smoothed grey 64 x 48 thumbnail as int16, or None if the JPEG can't be read."""
    try:
        import numpy as np
        from PIL import Image, ImageFilter

        with Image.open(io.BytesIO(jpeg)) as image:
            image.draft("L", (max(1, image.width // 8), max(1, image.height // 8)))
            grey = image.convert("L").resize(THUMB_SIZE).filter(ImageFilter.BoxBlur(1))
            return np.asarray(grey, dtype=np.int16)
    except Exception:
        return None


def watch_region(config: dict | None) -> tuple[float, float, float, float] | None:
    """Where a car must appear: the calibration zone, extended towards where cars come from.

    ``None`` (uncalibrated, or no zone) watches the whole picture.
    """
    config = config or {}
    zone = config.get("zone") or []
    if not config.get("enabled") or len(zone) < 3:
        return None
    try:
        xs = [float(p[0]) for p in zone]
        ys = [float(p[1]) for p in zone]
    except (TypeError, ValueError, IndexError):
        return None
    side = ((config.get("trigger_line") or {}).get("side") or "below")
    top_margin = APPROACH_MARGIN if side == "below" else SIDE_MARGIN       # cars come from the top
    bottom_margin = APPROACH_MARGIN if side == "above" else SIDE_MARGIN
    return (max(0.0, min(xs) - SIDE_MARGIN), max(0.0, min(ys) - top_margin),
            min(1.0, max(xs) + SIDE_MARGIN), min(1.0, max(ys) + bottom_margin))


def moved(previous, current, region: tuple[float, float, float, float] | None = None) -> bool:
    if previous is None or current is None or getattr(previous, "shape", None) != getattr(current, "shape", None):
        return True
    import numpy as np

    if region is not None:
        h, w = current.shape[:2]
        x1, y1 = int(region[0] * w), int(region[1] * h)
        x2, y2 = max(x1 + 1, int(round(region[2] * w))), max(y1 + 1, int(round(region[3] * h)))
        previous, current = previous[y1:y2, x1:x2], current[y1:y2, x1:x2]
    changed = np.abs(current - previous) > PIXEL_CHANGE
    return float(changed.mean()) >= MOTION_FRACTION


def should_detect(camera_id: int, jpeg: bytes, *, now: float | None = None,
                  region: tuple[float, float, float, float] | None = None) -> bool:
    """True when this frame should go to the plate detector.

    ``region`` (fractions of the picture, from ``watch_region``) limits the
    motion check to where a car must appear; ``None`` watches everything.
    """
    if not enabled():
        return True
    now = time.monotonic() if now is None else float(now)
    current = thumbnail(jpeg)
    with _lock:
        state = _states.setdefault(int(camera_id), _State())
        previous, state.thumb = state.thumb, current
        run = (
            current is None
            or moved(previous, current, region)
            or now - state.last_plate <= PLATE_HOLD_SECONDS
            or now - state.last_detect >= IDLE_CHECK_SECONDS
        )
        if run:
            state.last_detect = now
            state.detected += 1
        else:
            state.skipped += 1
        return run


def note_result(camera_id: int, *, plate_seen: bool, now: float | None = None) -> None:
    """Tell the gate whether the detector found a plate on this frame."""
    if not plate_seen:
        return
    now = time.monotonic() if now is None else float(now)
    with _lock:
        _states.setdefault(int(camera_id), _State()).last_plate = now


def stats() -> dict[str, dict[str, int]]:
    with _lock:
        return {str(cam): {"detected": s.detected, "skipped": s.skipped} for cam, s in sorted(_states.items())}


def reset() -> None:
    with _lock:
        _states.clear()
