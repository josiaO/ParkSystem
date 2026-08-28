"""Fuse native camera ALPR and local FastALPR into one plate reading.

Extracted from the earlier FastAPI build. The parking engine must never see two
detections for the same physical arrival; this helper is the resolution step.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.plate import normalize_plate, plate_similarity

DEFAULT_FUSION = {
    "fusion_similarity": 0.7,
    "hybrid_local_min": 0.85,
    "hybrid_native_min": 0.80,
    "hybrid_local_margin": 0.15,
    "hybrid_review_min": 0.90,
}

NATIVE_MODES = {"NATIVE", "NATIVE_ONLY"}
LOCAL_MODES = {"LOCAL", "LOCAL_ONLY", "FASTALPR"}


@dataclass
class FusionDecision:
    resolved_plate: str
    resolved_confidence: float
    method: str
    reason: str
    needs_review: bool = False

    def as_dict(self) -> dict:
        return {
            "resolved_plate": self.resolved_plate,
            "resolved_confidence": self.resolved_confidence,
            "method": self.method,
            "reason": self.reason,
            "needs_review": self.needs_review,
        }


def resolve_readings(
    *,
    native_plate: str = "",
    native_confidence: float = 0.0,
    local_plate: str = "",
    local_confidence: float = 0.0,
    settings: dict | None = None,
    operator_plate: str = "",
    mode: str = "",
) -> FusionDecision:
    cfg = {**DEFAULT_FUSION, **(settings or {})}
    native = normalize_plate(native_plate)
    local = normalize_plate(local_plate)
    operator = normalize_plate(operator_plate)
    chosen_mode = (mode or "HYBRID").upper()
    if operator:
        conf = max(float(native_confidence or 0), float(local_confidence or 0), 1.0)
        return FusionDecision(operator, conf, "OPERATOR_CORRECTED", "operator correction")

    if chosen_mode in NATIVE_MODES:
        if native:
            method = "NATIVE_ONLY" if not local else "NATIVE_SELECTED"
            return FusionDecision(native, float(native_confidence or 0), method, "native recognition mode")
        if local:
            return FusionDecision(local, float(local_confidence or 0), "LOCAL_ONLY", "native mode fallback to local", needs_review=True)
        return FusionDecision("", 0.0, "NATIVE_ONLY", "no plate", needs_review=True)
    if chosen_mode in LOCAL_MODES:
        if local:
            method = "LOCAL_ONLY" if not native else "LOCAL_SELECTED"
            return FusionDecision(local, float(local_confidence or 0), method, "local FastALPR recognition mode")
        if native:
            return FusionDecision(native, float(native_confidence or 0), "NATIVE_ONLY", "local mode fallback to native", needs_review=True)
        return FusionDecision("", 0.0, "LOCAL_ONLY", "no plate", needs_review=True)

    if native and not local:
        return FusionDecision(native, float(native_confidence or 0), "NATIVE_ONLY", "native only")
    if local and not native:
        return FusionDecision(local, float(local_confidence or 0), "LOCAL_ONLY", "local FastALPR only")
    if not native and not local:
        return FusionDecision("", 0.0, "NATIVE_ONLY", "no plate", needs_review=True)

    if native == local:
        conf = max(float(native_confidence or 0), float(local_confidence or 0))
        return FusionDecision(native, conf, "AGREED", "native and local agree")

    n_conf, l_conf = float(native_confidence or 0), float(local_confidence or 0)
    local_min = float(cfg.get("hybrid_local_min") or 0.85)
    native_min = float(cfg.get("hybrid_native_min") or 0.80)
    margin = float(cfg.get("hybrid_local_margin") or 0.15)
    review_min = float(cfg.get("hybrid_review_min") or 0.90)
    similar = plate_similarity(native, local) >= float(cfg.get("fusion_similarity") or 0.7)

    if n_conf >= review_min and l_conf >= review_min:
        plate, conf = (native, n_conf) if n_conf >= l_conf else (local, l_conf)
        return FusionDecision(
            plate,
            conf,
            "REVIEW_REQUIRED",
            f"both engines high-confidence disagree ({native} {n_conf:.2f} vs {local} {l_conf:.2f})",
            needs_review=True,
        )

    if l_conf >= local_min and (l_conf - n_conf) >= margin:
        return FusionDecision(
            local,
            l_conf,
            "LOCAL_SELECTED",
            f"local confidence {l_conf:.2f} over native {n_conf:.2f}",
            needs_review=not similar,
        )
    if n_conf >= native_min and n_conf >= l_conf:
        return FusionDecision(
            native,
            n_conf,
            "NATIVE_SELECTED",
            f"native confidence {n_conf:.2f} over local {l_conf:.2f}",
            needs_review=not similar,
        )
    if l_conf >= n_conf:
        return FusionDecision(local, l_conf, "LOCAL_SELECTED", "higher local confidence", needs_review=True)
    return FusionDecision(native, n_conf, "NATIVE_SELECTED", "higher native confidence", needs_review=True)
