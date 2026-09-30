"""Parking-facing recognition: one vehicle -> one normalized event.

Wraps the working ConsensusTrack + FusionCoordinator. Does not import printers,
vendor SDKs, HTTP routes, or operator clients. Native ALPR and FastALPR enter as
provider reads and leave as
NormalizedRecognitionEvent. Parking consumes only that event.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.core.consensus import ConsensusTrack
from app.core.fusion import DEFAULT_FUSION
from app.core.hybrid import SOURCE_LOCAL, SOURCE_NATIVE, Candidate, FusionCoordinator, FusionOutcome
from app.core.plate import apply_site_plate
from app.domain.recognition import (
    CONF_HIGH,
    CONF_LOW,
    CONF_MEDIUM,
    NormalizedRecognitionEvent,
)

NATIVE_ONLY = "NATIVE_ONLY"
FASTALPR_ONLY = "FASTALPR_ONLY"
HYBRID = "HYBRID"
PROVIDER_NATIVE = "HVX_NATIVE"
PROVIDER_FASTALPR = "FASTALPR"


def canonical_mode(value: str | None) -> str:
    chosen = str(value or FASTALPR_ONLY).upper()
    if chosen in {"FASTALPR_ONLY", "LOCAL_ONLY", "FASTALPR", "LOCAL"}:
        return FASTALPR_ONLY
    if chosen in {NATIVE_ONLY, "NATIVE"}:
        return NATIVE_ONLY
    if chosen in {HYBRID, "NATIVE_WITH_LOCAL_VERIFY"}:
        return HYBRID
    return FASTALPR_ONLY


def canonical_provider(value: str | None) -> str:
    chosen = str(value or PROVIDER_FASTALPR).upper()
    if chosen in {PROVIDER_NATIVE, "NATIVE", NATIVE_ONLY, "QY", "HVX"}:
        return PROVIDER_NATIVE
    return PROVIDER_FASTALPR


@dataclass
class RecognitionPolicy:
    """Operational recognition policy. Window/thresholds are configuration."""

    mode: str = FASTALPR_ONLY
    high_min: float = 0.92
    medium_min: float = 0.75
    consensus_window_seconds: float = 2.0
    hold_seconds: float = 20.0
    min_reads: int = 2
    min_agreeing: int = 2
    min_share: float = 0.6
    similarity: float = 0.7
    stale_frame_ms: float = 1000.0
    require_presence_when_available: bool = True
    plate_normalization: str = "ALNUM_UPPER"
    plate_validation: str = "NONE"
    bbox_iou_min: float = 0.15
    pair_window_seconds: float = 3.0
    wait_seconds: float = 1.5
    fusion_hold_seconds: float = 20.0

    def __post_init__(self) -> None:
        self.mode = canonical_mode(self.mode)


def classify_confidence(confidence: float, policy: RecognitionPolicy) -> str:
    score = float(confidence or 0)
    if score >= float(policy.high_min):
        return CONF_HIGH
    if score >= float(policy.medium_min):
        return CONF_MEDIUM
    return CONF_LOW


def policy_from_settings() -> RecognitionPolicy:
    from app.config import settings

    return RecognitionPolicy(
        mode=str(getattr(settings, "alpr_mode", FASTALPR_ONLY) or FASTALPR_ONLY),
        high_min=float(getattr(settings, "recognition_high_confidence", 0.92) or 0.92),
        medium_min=float(getattr(settings, "recognition_medium_confidence", 0.75) or 0.75),
        consensus_window_seconds=float(
            getattr(settings, "recognition_consensus_window_seconds", 2.0) or 2.0
        ),
        plate_normalization=str(getattr(settings, "plate_normalization", "ALNUM_UPPER") or "ALNUM_UPPER"),
        plate_validation=str(getattr(settings, "plate_validation", "NONE") or "NONE"),
    )


def _box_xyxy(box: dict[str, Any] | None) -> tuple[float, float, float, float] | None:
    if not isinstance(box, dict):
        return None
    if all(key in box for key in ("x1", "y1", "x2", "y2")):
        return float(box["x1"]), float(box["y1"]), float(box["x2"]), float(box["y2"])
    if all(key in box for key in ("x", "y", "w", "h")):
        x, y, width, height = float(box["x"]), float(box["y"]), float(box["w"]), float(box["h"])
        return x, y, x + width, y + height
    return None


def boxes_overlap(left: dict | None, right: dict | None, *, min_iou: float = 0.15) -> bool:
    """Unknown boxes do not split a visit. Low IoU means a different vehicle."""
    a, b = _box_xyxy(left), _box_xyxy(right)
    if a is None or b is None:
        return True
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(0.0, min(ay2, by2) - max(ay1, by1))
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    if union <= 0:
        return True
    return (inter / union) >= float(min_iou or 0)


def _new_track(policy: RecognitionPolicy) -> ConsensusTrack:
    return ConsensusTrack(
        window_seconds=float(policy.consensus_window_seconds),
        hold_seconds=float(policy.hold_seconds),
        min_reads=int(policy.min_reads),
        min_agreeing=int(policy.min_agreeing),
        min_share=float(policy.min_share),
        similarity=float(policy.similarity),
    )


class LaneRecognitionEngine:
    """Per-lane temporal consensus + optional native/FastALPR fusion."""

    def __init__(
        self,
        camera_id: int,
        *,
        site_id: int | None = None,
        lane_id: int | None = None,
        policy: RecognitionPolicy | None = None,
        presence_capable: bool = False,
    ) -> None:
        self.camera_id = int(camera_id)
        self.site_id = site_id
        self.lane_id = lane_id
        self.policy = policy or RecognitionPolicy()
        self.presence_capable = bool(presence_capable)
        self.presence_occupied = False
        self.stale_dropped = 0
        self.background_ignored = 0
        self._tracks = {PROVIDER_NATIVE: _new_track(self.policy), PROVIDER_FASTALPR: _new_track(self.policy)}
        self._fusion = FusionCoordinator(
            pair_window_seconds=self.policy.pair_window_seconds,
            wait_seconds=self.policy.wait_seconds,
            hold_seconds=self.policy.fusion_hold_seconds,
            settings=dict(DEFAULT_FUSION),
        )
        self._last_bbox: dict[str, Any] | None = None
        self._evidence: dict[str, dict[str, Any]] = {}

    def set_presence(self, occupied: bool) -> None:
        self.presence_occupied = bool(occupied)

    def _provider_allowed(self, provider: str) -> bool:
        mode = self.policy.mode
        if mode == NATIVE_ONLY:
            return provider == PROVIDER_NATIVE
        if mode == FASTALPR_ONLY:
            return provider == PROVIDER_FASTALPR
        return True

    def observe(
        self,
        *,
        plate_raw: str,
        confidence: float,
        now: float,
        provider: str = PROVIDER_FASTALPR,
        bbox: dict[str, Any] | None = None,
        frame_age_ms: float = 0.0,
        image_ref: str | None = None,
        plate_crop_ref: str | None = None,
        counterpart_available: bool | None = None,
        vehicle_detected: bool = True,
    ) -> list[NormalizedRecognitionEvent]:
        """Ingest one OCR frame. Empty list unless a parking-worthy event is ready."""
        if float(frame_age_ms or 0) > float(self.policy.stale_frame_ms):
            self.stale_dropped += 1
            return []
        if self.presence_capable and self.policy.require_presence_when_available and not self.presence_occupied:
            self.background_ignored += 1
            return []
        provider = canonical_provider(provider)
        if not self._provider_allowed(provider):
            return []
        applied = apply_site_plate(
            plate_raw,
            normalization=self.policy.plate_normalization,
            validation=self.policy.plate_validation,
        )
        plate = str(applied.get("normalized_plate") or "")
        if not plate or not vehicle_detected:
            return []
        if bbox and self._last_bbox and not boxes_overlap(bbox, self._last_bbox, min_iou=self.policy.bbox_iou_min):
            self._tracks[provider]._new_visit(now)
        if bbox:
            self._last_bbox = bbox
        self._evidence[provider] = {
            "plate_raw": str(applied.get("raw_plate") or plate_raw or plate),
            "bbox": bbox,
            "image_ref": image_ref,
            "plate_crop_ref": plate_crop_ref,
        }
        decision = self._tracks[provider].observe(plate, now, confidence=float(confidence or 0))
        if not decision.publish:
            return []
        if classify_confidence(decision.confidence, self.policy) == CONF_LOW:
            return []
        if self.policy.mode != HYBRID:
            return [self._event_from_track(provider, decision)]
        source = SOURCE_NATIVE if provider == PROVIDER_NATIVE else SOURCE_LOCAL
        waiting = True if counterpart_available is None else bool(counterpart_available)
        candidate = Candidate(
            source,
            decision.plate,
            decision.confidence,
            now,
            payload={
                "plate_raw": self._evidence[provider]["plate_raw"],
                "bbox": bbox,
                "image_ref": image_ref,
                "plate_crop_ref": plate_crop_ref,
                "consensus": decision.as_dict(),
            },
            consensus=True,
        )
        outcomes = self._fusion.offer(
            self.camera_id, candidate, now=now, counterpart_available=waiting,
        )
        return [event for event in (self._event_from_outcome(item) for item in outcomes) if event is not None]

    def flush(self, now: float) -> list[NormalizedRecognitionEvent]:
        return [event for event in (self._event_from_outcome(item) for item in self._fusion.flush(now)) if event is not None]

    def _event_from_track(self, provider: str, decision) -> NormalizedRecognitionEvent:
        evidence = self._evidence.get(provider) or {}
        klass = classify_confidence(decision.confidence, self.policy)
        return NormalizedRecognitionEvent(
            event_id=uuid4().hex,
            site_id=self.site_id,
            camera_id=self.camera_id,
            lane_id=self.lane_id,
            occurred_at=datetime.now(timezone.utc).isoformat(),
            provider=provider,
            plate_raw=str(evidence.get("plate_raw") or decision.plate),
            plate_normalized=decision.plate,
            confidence=float(decision.confidence),
            bbox=evidence.get("bbox"),
            vehicle_detected=True,
            image_ref=evidence.get("image_ref"),
            plate_crop_ref=evidence.get("plate_crop_ref"),
            confidence_class=klass,
            needs_review=False,
            accepted=klass != CONF_LOW,
            mode=self.policy.mode,
            presence=self.presence_occupied if self.presence_capable else None,
            consensus=decision.as_dict(),
        )

    def _event_from_outcome(self, outcome: FusionOutcome) -> NormalizedRecognitionEvent | None:
        if outcome.suppressed:
            return None
        decision = outcome.decision
        plate = str(decision.resolved_plate or "")
        if not plate:
            return None
        klass = classify_confidence(decision.resolved_confidence, self.policy)
        needs_review = bool(decision.needs_review or klass == CONF_LOW)
        winner = PROVIDER_NATIVE if decision.method.startswith("NATIVE") else PROVIDER_FASTALPR
        if decision.method in {"AGREED", "REVIEW_REQUIRED"}:
            winner = PROVIDER_NATIVE if (outcome.native and outcome.native.plate == plate) else PROVIDER_FASTALPR
        evidence = self._evidence.get(winner) or {}
        if outcome.native and winner == PROVIDER_NATIVE:
            evidence = {**evidence, **(outcome.native.payload or {})}
        if outcome.local and winner == PROVIDER_FASTALPR:
            evidence = {**evidence, **(outcome.local.payload or {})}
        return NormalizedRecognitionEvent(
            event_id=uuid4().hex,
            site_id=self.site_id,
            camera_id=self.camera_id,
            lane_id=self.lane_id,
            occurred_at=datetime.now(timezone.utc).isoformat(),
            provider=winner if not outcome.paired else "HYBRID",
            plate_raw=str(evidence.get("plate_raw") or plate),
            plate_normalized=plate,
            confidence=float(decision.resolved_confidence),
            bbox=evidence.get("bbox") if isinstance(evidence.get("bbox"), dict) else None,
            vehicle_detected=True,
            image_ref=evidence.get("image_ref"),
            plate_crop_ref=evidence.get("plate_crop_ref"),
            confidence_class=klass,
            needs_review=needs_review,
            accepted=bool(plate) and not needs_review,
            mode=HYBRID,
            presence=self.presence_occupied if self.presence_capable else None,
            consensus=evidence.get("consensus") if isinstance(evidence.get("consensus"), dict) else None,
            fusion=outcome.as_dict(),
        )
