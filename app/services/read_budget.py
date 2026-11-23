"""At most two plate reads per car.

A camera does not send one picture per car. It fires on its own triggers
(snap types 1 and 2), the loop, and Zirp's video gate, and every one of those
used to start a full OCR read. One car could be read three or four times in a
few seconds, and each read was a fresh chance to get it wrong: a correct
T776DYB followed by T776DVB from the next picture of the same car.

The rule now is the one an attendant would use:

* read the car once;
* if that read is confident (at least ``read_budget_confident``, a valid plate
  for the site), stop: the car is read;
* if it is unread or unsure, read it **once more**, and keep the better of the
  two (``visit_reads`` already keeps the best read for the visit);
* after two reads, stop.

"The car" is the stream of triggers on one camera until the lane has been
quiet for ``read_budget_quiet_seconds`` (the car left), or at most
``read_budget_max_seconds``. Triggers on a settled car extend the quiet
window, because the car is still there. A loop rising edge, or the camera
reporting a clearly different plate, starts a new car at once so the next car
in a queue is never skipped.

Pictures that contain no plate at all do not use up the two reads: they can't
produce a misread and skipping them could miss the car.

Operator reads (``force``) are never limited. The state lives in the shared
cache, so the Site Service and the Recognition Worker count the same car.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass

from app.services.shared_cache import cache

MAX_READS = 2
SKIPPED = "skipped"


@dataclass
class CarReads:
    started: float = 0.0
    last_seen: float = 0.0
    reads: int = 0
    settled: bool = False
    reason: str = ""
    plate: str = ""
    confidence: float = 0.0
    skipped: int = 0


def _settings():
    from app.config import settings

    return settings


def enabled() -> bool:
    return bool(getattr(_settings(), "read_budget_enabled", True))


def _confident_at() -> float:
    return float(getattr(_settings(), "read_budget_confident", 0.90) or 0.90)


def _quiet() -> float:
    return max(0.5, float(getattr(_settings(), "read_budget_quiet_seconds", 4.0) or 4.0))


def _max_age() -> float:
    return max(_quiet(), float(getattr(_settings(), "read_budget_max_seconds", 20.0) or 20.0))


def _key(camera_id: int) -> str:
    return f"reads:camera:{int(camera_id)}"


def _expired(state: CarReads, now: float) -> bool:
    return (now - state.last_seen) > _quiet() or (now - state.started) > _max_age()


def _load(camera_id: int, now: float) -> CarReads | None:
    raw = cache.get_json(_key(camera_id))
    if not isinstance(raw, dict):
        return None
    try:
        state = CarReads(**{k: raw[k] for k in CarReads.__dataclass_fields__ if k in raw})
    except TypeError:
        return None
    return None if _expired(state, now) else state


def _save(camera_id: int, state: CarReads) -> None:
    cache.set_json(_key(camera_id), asdict(state), ttl=_max_age() + 5.0)


def current(camera_id: int, *, now: float | None = None) -> CarReads | None:
    return _load(camera_id, time.time() if now is None else now)


def _plates_differ(a: str, b: str) -> bool:
    """True when two reads can't be the same plate misread (more than 2 edits)."""
    a, b = (a or "").upper(), (b or "").upper()
    if not a or not b:
        return False
    if abs(len(a) - len(b)) > 2:
        return True
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        row = [i]
        for j, cb in enumerate(b, 1):
            row.append(min(previous[j] + 1, row[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = row
    return previous[-1] > 2


def allow(camera_id: int, *, hint_plate: str = "", now: float | None = None) -> bool:
    """May an automatic read run for the car at this camera now?

    ``hint_plate`` is plate text the camera itself attached to the trigger,
    if any. A clearly different plate means a different car.
    """
    if not enabled():
        return True
    now = time.time() if now is None else float(now)
    with cache.lock(_key(camera_id)):
        state = _load(camera_id, now)
        if state is None or not state.settled:
            return True
        if hint_plate and state.plate and _plates_differ(hint_plate, state.plate):
            cache.delete(_key(camera_id))
            return True
        state.last_seen = now
        state.skipped += 1
        _save(camera_id, state)
        return False


def record(camera_id: int, plate: str, confidence: float, *, valid: bool = True,
           now: float | None = None) -> CarReads:
    """Count one finished automatic read for the car at this camera."""
    now = time.time() if now is None else float(now)
    plate = str(plate or "").strip().upper()
    confidence = float(confidence or 0.0)
    with cache.lock(_key(camera_id)):
        state = _load(camera_id, now)
        if state is not None and state.settled and plate and state.plate and _plates_differ(plate, state.plate):
            state = None                     # a different car slipped in
        if state is None:
            state = CarReads(started=now, last_seen=now)
        state.last_seen = now
        if not plate:
            _save(camera_id, state)          # empty picture: not one of the two
            return state
        state.reads += 1
        if confidence >= state.confidence or not state.plate:
            state.plate, state.confidence = plate, confidence
        if valid and confidence >= _confident_at():
            state.settled, state.reason = True, "confident read"
        elif state.reads >= MAX_READS:
            state.settled, state.reason = True, "second read"
        _save(camera_id, state)
        return state


def settle(camera_id: int, plate: str, confidence: float, *, now: float | None = None) -> None:
    """Mark the car read (e.g. the Recognition Worker published it)."""
    now = time.time() if now is None else float(now)
    with cache.lock(_key(camera_id)):
        state = _load(camera_id, now) or CarReads(started=now)
        state.last_seen = now
        state.reads = max(state.reads, 1)
        state.plate = str(plate or state.plate or "").upper()
        state.confidence = max(state.confidence, float(confidence or 0.0))
        state.settled, state.reason = True, state.reason or "published"
        _save(camera_id, state)


def new_car(camera_id: int) -> None:
    """A loop edge or similar says a new car arrived: start counting again."""
    cache.delete(_key(camera_id))


def skipped_result(state: CarReads | None = None) -> dict:
    """What ``_run_local_alpr`` returns for a read that was not needed."""
    detail = "car already read"
    if state is not None and state.plate:
        detail = f"car already read as {state.plate} ({state.reason or 'settled'})"
    return {"ok": True, "backend": "fastalpr", "plates": [], "best": None,
            "read_budget": SKIPPED, "detail": detail}


def is_skipped(result: dict | None) -> bool:
    return bool(result) and (result or {}).get("read_budget") == SKIPPED
