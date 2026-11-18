"""One car waiting at a lane = one stay, however many captures it produces.

Cameras keep capturing a car that waits at the barrier (on SITE-PC01, 69% of
vehicles were captured 2+ times, about 4 s apart, for up to 2.5 minutes).
Each capture used to be judged on its own:

* a first read from far away could be wrong (T940OWQ, T135EOT) and open a
  session; the correct later read (T940DWQ, T135EJT) then opened a second
  session for the same car, and the wrong plate stayed on the first;
* every repeat at the exit raised another "no session" alert.

A stay chains the captures of one lane while the plates look alike and each
arrives within ``STAY_GAP_SECONDS`` of the previous one. The reads vote; the
stay's best plate is the one with the most confidence behind it, preferring
a plate in the issued Tanzanian shape. The entry controller opens at most one
visit per stay and corrects its plate when later reads outvote the first; the
exit controller acts on the stay's best plate and ignores repeats once the
barrier has opened for the stay.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field

STAY_GAP_SECONDS = 45.0        # repeats come ~4 s apart (p90 span 23 s)
STAY_MAX_SECONDS = 600.0       # a stay never outlives 10 minutes
MAX_EDIT_DISTANCE = 2          # T940OWQ / T940DWQ: one slip; allow two
MIN_CONFIDENCE = 0.30          # a read with no confidence still counts a little
VALID_SHAPE_BONUS = 1.5        # T + 3 digits + issued series letter

_TZ_STANDARD = re.compile(r"^T\d{3}[A-H][A-Z]{2}$")


def edit_distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def same_vehicle(a: str, b: str) -> bool:
    """Two reads that can be OCR slips of one plate (same length, <= 2 changes)."""
    if not a or not b:
        return False
    if a == b:
        return True
    return len(a) == len(b) and len(a) >= 5 and edit_distance(a, b) <= MAX_EDIT_DISTANCE


def _shape_weight(plate: str) -> float:
    return VALID_SHAPE_BONUS if _TZ_STANDARD.match(plate) else 1.0


@dataclass
class Stay:
    camera_id: int
    started: float
    last: float
    reads: list[tuple[str, float]] = field(default_factory=list)
    session_id: int | None = None
    barrier_opened: bool = False
    reported_no_session: set[str] = field(default_factory=set)   # exit: alerted once per plate

    @property
    def repeats(self) -> int:
        return max(0, len(self.reads) - 1)

    def scores(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for plate, confidence in self.reads:
            totals[plate] = totals.get(plate, 0.0) + max(MIN_CONFIDENCE, float(confidence or 0.0))
        return {plate: score * _shape_weight(plate) for plate, score in totals.items()}

    def best_plate(self) -> str:
        scores = self.scores()
        # ties go to the most recent read (closer to the camera)
        order = {plate: i for i, (plate, _) in enumerate(self.reads)}
        return max(scores, key=lambda p: (scores[p], order[p])) if scores else ""

    def matches(self, plate: str) -> bool:
        return any(same_vehicle(plate, seen) for seen, _ in self.reads)


_lock = threading.Lock()
_stays: dict[int, Stay] = {}


def observe(camera_id: int, plate: str, confidence: float | None = None, *, now: float | None = None) -> Stay:
    """Add one read; returns its stay (``stay.repeats == 0`` for a new car)."""
    now = time.monotonic() if now is None else now
    camera_id = int(camera_id)
    plate = (plate or "").strip().upper()
    with _lock:
        stay = _stays.get(camera_id)
        fresh = (
            stay is None
            or now - stay.last > STAY_GAP_SECONDS
            or now - stay.started > STAY_MAX_SECONDS
            or not stay.matches(plate)
        )
        if fresh:
            stay = _stays[camera_id] = Stay(camera_id=camera_id, started=now, last=now)
        stay.reads.append((plate, float(confidence or 0.0)))
        stay.last = now
        return stay


def attach_session(camera_id: int, session_id: int | None) -> None:
    with _lock:
        stay = _stays.get(int(camera_id))
        if stay is not None and session_id is not None:
            stay.session_id = int(session_id)


def mark_opened(camera_id: int) -> None:
    with _lock:
        stay = _stays.get(int(camera_id))
        if stay is not None:
            stay.barrier_opened = True


def current(camera_id: int) -> Stay | None:
    with _lock:
        return _stays.get(int(camera_id))


def reset(camera_id: int | None = None) -> None:
    with _lock:
        if camera_id is None:
            _stays.clear()
        else:
            _stays.pop(int(camera_id), None)
