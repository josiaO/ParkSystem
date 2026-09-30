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
    native: Candidate | None = None
    local: Candidate | None = None
    decided: list[tuple[str, float]] = field(default_factory=list)


@dataclass
class FusionCoordinator:
    pair_window_seconds: float = 3.0
    wait_seconds: float = 1.5
    hold_seconds: float = 20.0
    duplicate_similarity: float = 0.85
    settings: dict[str, Any] = field(default_factory=dict)
    _lanes: dict[int, _Lane] = field(default_factory=dict)

    def _lane(self, camera_id: int) -> _Lane:
        return self._lanes.setdefault(int(camera_id), _Lane())

    def pending(self, camera_id: int) -> dict[str, Candidate | None]:
        lane = self._lane(camera_id)
        return {SOURCE_NATIVE: lane.native, SOURCE_LOCAL: lane.local}

    def _duplicate_of(self, lane: _Lane, plate: str, now: float) -> str:
        lane.decided = [(p, at) for p, at in lane.decided if now - at < self.hold_seconds]
        for previous, _at in lane.decided:
            if previous == plate or plate_similarity(previous, plate) >= self.duplicate_similarity:
                return previous
        return ""

    def _decide(self, camera_id: int, lane: _Lane, now: float) -> FusionOutcome:
        native, local = lane.native, lane.local
        lane.native = None
        lane.local = None
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
        slot = "native" if candidate.source == SOURCE_NATIVE else "local"
        other_slot = "local" if slot == "native" else "native"
        outcomes: list[FusionOutcome] = []
        # Stale unpaired candidates belong to an earlier vehicle: decide them alone
        # before the new candidate can be mistaken for their counterpart.
        for stale_slot in (slot, other_slot):
            stale: Candidate | None = getattr(lane, stale_slot)
            if stale is not None and (now - stale.at) > self.pair_window_seconds:
                outcomes.append(self._decide_slot(camera_id, lane, stale_slot, now))
        setattr(lane, slot, candidate)
        counterpart: Candidate | None = getattr(lane, other_slot)
        if counterpart is not None:
            outcomes.append(self._decide(camera_id, lane, now))
        elif not counterpart_available:
            outcomes.append(self._decide(camera_id, lane, now))
        return outcomes

    def _decide_slot(self, camera_id: int, lane: _Lane, slot: str, now: float) -> FusionOutcome:
        other_slot = "local" if slot == "native" else "native"
        keep = getattr(lane, other_slot)
        setattr(lane, other_slot, None)
        try:
            return self._decide(camera_id, lane, now)
        finally:
            setattr(lane, other_slot, keep)

    def flush(self, now: float) -> list[FusionOutcome]:
        """Decide candidates whose counterpart did not arrive within wait_seconds."""
        outcomes: list[FusionOutcome] = []
        for camera_id, lane in list(self._lanes.items()):
            for slot in ("native", "local"):
                waiting: Candidate | None = getattr(lane, slot)
                if waiting is not None and now - waiting.at >= self.wait_seconds:
                    outcomes.append(self._decide_slot(camera_id, lane, slot, now))
        return outcomes

    def reset(self, camera_id: int | None = None) -> None:
        if camera_id is None:
            self._lanes.clear()
        else:
            self._lanes.pop(int(camera_id), None)
