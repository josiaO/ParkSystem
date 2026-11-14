"""Process-safe native + FastALPR fusion for one physical vehicle event.

Native ALPR candidates arrive in the Site Service from the HVX host callback.
FastALPR candidates arrive from the separate Recognition Worker through the
durable outbox. This coordinator pairs the two by camera and time, applies
``resolve_readings`` in HYBRID mode, and guarantees that one physical arrival
produces at most one accepted plate decision:

- strong agreement is accepted as soon as both candidates are present
- when the counterpart provider is unavailable the single provider decides
  immediately; otherwise the first candidate waits ``wait_seconds`` for it
- disagreements are held for operator review by ``resolve_readings``
- a decision for the same or a near-identical plate on the same camera within
  ``hold_seconds`` is suppressed as a duplicate

No I/O happens here; the service layer persists the outcome.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from app.core.fusion import FusionDecision, resolve_readings
from app.core.plate import normalize_plate, plate_similarity

SOURCE_NATIVE = "NATIVE"
SOURCE_LOCAL = "FASTALPR"


@dataclass
class Candidate:
    source: str
    plate: str
    confidence: float
    at: float
    payload: dict[str, Any] = field(default_factory=dict)
    consensus: bool = False

    def __post_init__(self) -> None:
        self.source = SOURCE_NATIVE if str(self.source).upper() == SOURCE_NATIVE else SOURCE_LOCAL
        self.plate = normalize_plate(self.plate)
        self.confidence = max(0.0, min(1.0, float(self.confidence or 0.0)))


@dataclass
class FusionOutcome:
    camera_id: int
    decision: FusionDecision
    native: Candidate | None
    local: Candidate | None
    paired: bool
    suppressed: bool = False
    suppressed_reason: str = ""
    decided_at: float = 0.0

    @property
    def plate(self) -> str:
        return self.decision.resolved_plate

    def as_dict(self) -> dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "paired": self.paired,
            "suppressed": self.suppressed,
            "suppressed_reason": self.suppressed_reason,
            "native": {"plate": self.native.plate, "confidence": self.native.confidence} if self.native else None,
            "local": {"plate": self.local.plate, "confidence": self.local.confidence} if self.local else None,
            **self.decision.as_dict(),
        }


@dataclass
class _Lane:
    # Providers are asynchronous and may report the next vehicle before the
    # other provider has finished the previous one. A single slot per provider
    # silently overwrote that earlier vehicle. Keep a small bounded queue and
    # pair by plate first, then by arrival time.
    native: deque[Candidate] = field(default_factory=deque)
    local: deque[Candidate] = field(default_factory=deque)
    decided: list[tuple[str, float]] = field(default_factory=list)


@dataclass
class FusionCoordinator:
    pair_window_seconds: float = 3.0
    wait_seconds: float = 1.5
    hold_seconds: float = 20.0
    duplicate_similarity: float = 0.85
    max_pending_candidates: int = 8
    settings: dict[str, Any] = field(default_factory=dict)
    _lanes: dict[int, _Lane] = field(default_factory=dict)

    def _lane(self, camera_id: int) -> _Lane:
        return self._lanes.setdefault(int(camera_id), _Lane())

    def pending(self, camera_id: int) -> dict[str, Candidate | None]:
        lane = self._lane(camera_id)
        return {
            SOURCE_NATIVE: lane.native[0] if lane.native else None,
            SOURCE_LOCAL: lane.local[0] if lane.local else None,
        }

    def _duplicate_of(self, lane: _Lane, plate: str, now: float) -> str:
        lane.decided = [(p, at) for p, at in lane.decided if now - at < self.hold_seconds]
        for previous, _at in lane.decided:
            if previous == plate or plate_similarity(previous, plate) >= self.duplicate_similarity:
                return previous
        return ""

    def _decide(self, camera_id: int, lane: _Lane, native: Candidate | None,
                local: Candidate | None, now: float) -> FusionOutcome:
        decision = resolve_readings(
            native_plate=native.plate if native else "",
            native_confidence=native.confidence if native else 0.0,
            local_plate=local.plate if local else "",
            local_confidence=local.confidence if local else 0.0,
            mode="HYBRID",
            settings=self.settings,
            local_consensus=bool(local and local.consensus),
        )
        outcome = FusionOutcome(
            camera_id=int(camera_id),
            decision=decision,
            native=native,
            local=local,
            paired=bool(native and local),
            decided_at=now,
        )
        plate = decision.resolved_plate
        if plate:
            previous = self._duplicate_of(lane, plate, now)
            if previous:
                outcome.suppressed = True
                outcome.suppressed_reason = f"duplicate of {previous} within {self.hold_seconds:.0f}s"
            elif not decision.needs_review:
                # Only accepted decisions own the duplicate window. A held plate
                # can still be accepted later once the operator or consensus agrees.
                lane.decided.append((plate, now))
        return outcome

    def _decide_single(self, camera_id: int, lane: _Lane, candidate: Candidate,
                       now: float) -> FusionOutcome:
        if candidate.source == SOURCE_NATIVE:
            return self._decide(camera_id, lane, candidate, None, now)
        return self._decide(camera_id, lane, None, candidate, now)

    @staticmethod
    def _plate_match(left: Candidate, right: Candidate) -> bool:
        return bool(left.plate and right.plate and (
            left.plate == right.plate
            or plate_similarity(left.plate, right.plate) >= 0.85
        ))

    def _match_index(self, incoming: Candidate, queue: deque[Candidate]) -> int | None:
        if not queue:
            return None
        # If the two processes carry a shared visit/capture identity, use it as
        # the strongest pairing signal. Otherwise an agreeing plate is safer
        # than nearest-time pairing when two vehicles are close together.
        incoming_visit = str(incoming.payload.get("visit_id") or "")
        if incoming_visit:
            for index, candidate in enumerate(queue):
                if incoming_visit == str(candidate.payload.get("visit_id") or ""):
                    return index
        for index, candidate in enumerate(queue):
            if self._plate_match(incoming, candidate):
                return index
        candidates = [
            (index, abs(float(candidate.at) - float(incoming.at)))
            for index, candidate in enumerate(queue)
            if abs(float(candidate.at) - float(incoming.at)) <= self.pair_window_seconds
        ]
        return min(candidates, key=lambda item: item[1])[0] if candidates else None

    def _pop_index(self, queue: deque[Candidate], index: int) -> Candidate:
        queue.rotate(-index)
        candidate = queue.popleft()
        queue.rotate(index)
        return candidate

    def _match_ready(self, camera_id: int, lane: _Lane, now: float) -> list[FusionOutcome]:
        outcomes: list[FusionOutcome] = []
        # Process the oldest candidate first so a busy lane cannot let a newer
        # car repeatedly jump ahead of a waiting one.
        while lane.native and lane.local:
            native = lane.native[0]
            index = self._match_index(native, lane.local)
            if index is None:
                local = lane.local[0]
                index = self._match_index(local, lane.native)
                if index is None:
                    break
                local = lane.local.popleft()
                native = self._pop_index(lane.native, index)
            else:
                native = lane.native.popleft()
                local = self._pop_index(lane.local, index)
            outcomes.append(self._decide(camera_id, lane, native, local, now))
        return outcomes

    def _expire(self, camera_id: int, lane: _Lane, now: float) -> list[FusionOutcome]:
        outcomes: list[FusionOutcome] = []
        for queue in (lane.native, lane.local):
            while queue and (now - float(queue[0].at)) >= self.wait_seconds:
                # A candidate older than the pairing wait has earned a
                # standalone decision. It is removed, so later cars cannot be
                # paired with a stale result.
                candidate = queue.popleft()
                outcomes.append(self._decide_single(camera_id, lane, candidate, now))
        return outcomes

    def offer(
        self,
        camera_id: int,
        candidate: Candidate,
        *,
        now: float,
        counterpart_available: bool = True,
    ) -> list[FusionOutcome]:
        """Register a candidate. Returns zero, one or two ready decisions."""
        lane = self._lane(camera_id)
        queue = lane.native if candidate.source == SOURCE_NATIVE else lane.local
        queue.append(candidate)
        outcomes = self._match_ready(camera_id, lane, now)
        if not counterpart_available:
            # The provider is known to be unavailable; do not hold every
            # candidate until the periodic flush loop.
            while queue:
                outcomes.append(self._decide_single(camera_id, lane, queue.popleft(), now))
        else:
            # Keep bounded memory and bounded decision latency even if a
            # provider floods callbacks while the other process is down.
            limit = max(1, int(self.max_pending_candidates or 1))
            while len(queue) > limit:
                outcomes.append(self._decide_single(camera_id, lane, queue.popleft(), now))
            outcomes.extend(self._expire(camera_id, lane, now))
        return outcomes

    def flush(self, now: float) -> list[FusionOutcome]:
        """Decide candidates whose counterpart did not arrive within wait_seconds."""
        outcomes: list[FusionOutcome] = []
        for camera_id, lane in list(self._lanes.items()):
            outcomes.extend(self._match_ready(camera_id, lane, now))
            outcomes.extend(self._expire(camera_id, lane, now))
        return outcomes

    def reset(self, camera_id: int | None = None) -> None:
        if camera_id is None:
            self._lanes.clear()
        else:
            self._lanes.pop(int(camera_id), None)
