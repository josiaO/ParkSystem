"""AI review contract (Codex §9). Cloud AI is an optional second opinion.

It may *support* or *question* a plate read and describe a vehicle; it may
never open a gate, settle a payment, change a tariff, or overwrite a verified
native/FastALPR read on its own. Providers return ``VehicleReview`` without any
invented probability: agreement with the existing candidates is computed here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Protocol

REASON_LOW_CONFIDENCE = "low_confidence"
REASON_DISAGREEMENT = "disagreement"
REASON_MANUAL = "manual"
REASON_VEHICLE_ATTRIBUTES = "vehicle_attributes"
REASONS = (REASON_LOW_CONFIDENCE, REASON_DISAGREEMENT, REASON_MANUAL, REASON_VEHICLE_ATTRIBUTES)

_PLATE_CLEAN = re.compile(r"[^A-Z0-9]")


def normalize_candidate(text: str | None) -> str:
    return _PLATE_CLEAN.sub("", str(text or "").upper())[:16]


@dataclass
class VehicleReviewRequest:
    camera_id: int
    capture_id: int | None
    reason: str
    plate_candidates: list[str]
    crop_jpeg: bytes = b""
    vehicle_jpeg: bytes = b""
    synthetic: bool = False  # simulated/test imagery: allowed on free tier
    want_vehicle_attributes: bool = False

    def candidates(self) -> list[str]:
        seen: list[str] = []
        for c in self.plate_candidates:
            n = normalize_candidate(c)
            if n and n not in seen:
                seen.append(n)
        return seen


@dataclass
class VehicleReview:
    readable: bool
    plate_candidate: str
    vehicle_type: str = ""
    vehicle_color: str = ""
    notes: str = ""
    provider: str = ""
    model: str = ""
    latency_ms: float = 0.0
    agrees_with: str = ""  # which existing candidate the AI read matches, if any
    verdict: str = "unavailable"  # supporting | conflicting | unreadable | unavailable
    reason: str = ""
    error: str = ""
    at: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IncidentSummaryRequest:
    events: list[dict[str, Any]] = field(default_factory=list)
    question: str = ""
    synthetic: bool = False


@dataclass
class IncidentSummary:
    text: str
    provider: str = ""
    model: str = ""
    latency_ms: float = 0.0
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class AIReviewProvider(Protocol):
    provider_id: str

    async def review_vehicle_event(self, request: VehicleReviewRequest) -> VehicleReview: ...

    async def summarize_incident(self, request: IncidentSummaryRequest) -> IncidentSummary: ...

    def health(self) -> dict[str, Any]: ...


def judge(review: VehicleReview, candidates: list[str]) -> VehicleReview:
    """Fusion rule: same read → supporting evidence; different → conflicting (operator/consensus)."""
    if review.error:
        review.verdict = "unavailable"
        return review
    ai = normalize_candidate(review.plate_candidate)
    review.plate_candidate = ai
    if not review.readable or not ai:
        review.verdict = "unreadable"
        review.agrees_with = ""
        return review
    for c in candidates:
        if normalize_candidate(c) == ai:
            review.agrees_with = normalize_candidate(c)
            review.verdict = "supporting"
            return review
    review.agrees_with = ""
    review.verdict = "conflicting"
    return review
