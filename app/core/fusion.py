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
    "min_auto_accept": 0.75,
    "strict_single_local": 0.92,
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
    native_plate: str = ""
    local_plate: str = ""
    native_confidence: float = 0.0
    local_confidence: float = 0.0
    disagreed: bool = False

    def as_dict(self) -> dict:
        return {
            "resolved_plate": self.resolved_plate,
            "resolved_confidence": self.resolved_confidence,
            "method": self.method,
            "reason": self.reason,
            "needs_review": self.needs_review,
            "native_plate": self.native_plate,
            "local_plate": self.local_plate,
            "native_confidence": self.native_confidence,
            "local_confidence": self.local_confidence,
            "disagreed": self.disagreed,
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
    local_consensus: bool = False,
) -> FusionDecision:
    cfg = {**DEFAULT_FUSION, **(settings or {})}
    native = normalize_plate(native_plate)
    local = normalize_plate(local_plate)
    operator = normalize_plate(operator_plate)
    n_conf, l_conf = float(native_confidence or 0), float(local_confidence or 0)
    min_auto = float(cfg.get("min_auto_accept") or 0.75)
    strict_local = float(cfg.get("strict_single_local") or 0.92)

    def _finish(
        plate: str,
        conf: float,
        method: str,
        reason: str,
        *,
        needs_review: bool = False,
    ) -> FusionDecision:
        disagreed = bool(native and local and native != local)
        review = bool(needs_review)
        if plate and conf < min_auto:
            review = True
            if "low confidence" not in reason:
                reason = f"{reason}; low confidence {conf:.2f} held"
        if method in {"LOCAL_ONLY", "LOCAL_SELECTED"} and not native and conf < strict_local and not local_consensus:
            review = True
            if "single-frame" not in reason:
                reason = f"{reason}; single-frame local below {strict_local:.2f}"
        if not plate:
            review = True
        return FusionDecision(
            plate,
            conf,
            method,
            reason,
            needs_review=review,
            native_plate=native,
            local_plate=local,
            native_confidence=n_conf,
            local_confidence=l_conf,
            disagreed=disagreed,
        )

    chosen_mode = (mode or "HYBRID").upper()
    if operator:
        conf = max(n_conf, l_conf, 1.0)
        return _finish(operator, conf, "OPERATOR_CORRECTED", "operator correction")

    if chosen_mode in NATIVE_MODES:
        if native:
            method = "NATIVE_ONLY" if not local else "NATIVE_SELECTED"
            return _finish(native, n_conf, method, "native recognition mode")
        if local:
            return _finish(local, l_conf, "LOCAL_ONLY", "native mode fallback to local", needs_review=True)
        return _finish("", 0.0, "NATIVE_ONLY", "no plate", needs_review=True)
    if chosen_mode in LOCAL_MODES:
        if local:
            method = "LOCAL_ONLY" if not native else "LOCAL_SELECTED"
            return _finish(local, l_conf, method, "local FastALPR recognition mode")
        if native:
            return _finish(native, n_conf, "NATIVE_ONLY", "local mode fallback to native", needs_review=True)
        return _finish("", 0.0, "LOCAL_ONLY", "no plate", needs_review=True)

    if native and not local:
        return _finish(native, n_conf, "NATIVE_ONLY", "native only")
    if local and not native:
        return _finish(local, l_conf, "LOCAL_ONLY", "local FastALPR only")
    if not native and not local:
        return _finish("", 0.0, "NATIVE_ONLY", "no plate", needs_review=True)

    if native == local:
        conf = max(n_conf, l_conf)
        return _finish(native, conf, "AGREED", "native and local agree")

    local_min = float(cfg.get("hybrid_local_min") or 0.85)
    native_min = float(cfg.get("hybrid_native_min") or 0.80)
    margin = float(cfg.get("hybrid_local_margin") or 0.15)
    review_min = float(cfg.get("hybrid_review_min") or 0.90)
    similar = plate_similarity(native, local) >= float(cfg.get("fusion_similarity") or 0.7)

    if n_conf >= review_min and l_conf >= review_min:
        plate, conf = (native, n_conf) if n_conf >= l_conf else (local, l_conf)
        return _finish(
            plate,
            conf,
            "REVIEW_REQUIRED",
            f"both engines high-confidence disagree ({native} {n_conf:.2f} vs {local} {l_conf:.2f})",
            needs_review=True,
        )

    if l_conf >= local_min and (l_conf - n_conf) >= margin:
        return _finish(
            local,
            l_conf,
            "LOCAL_SELECTED",
            f"local confidence {l_conf:.2f} over native {n_conf:.2f}",
            needs_review=not similar,
        )
    if n_conf >= native_min and n_conf >= l_conf:
        return _finish(
            native,
            n_conf,
            "NATIVE_SELECTED",
            f"native confidence {n_conf:.2f} over local {l_conf:.2f}",
            needs_review=not similar,
        )
    if l_conf >= n_conf:
        return _finish(local, l_conf, "LOCAL_SELECTED", "higher local confidence", needs_review=True)
    return _finish(native, n_conf, "NATIVE_SELECTED", "higher native confidence", needs_review=True)
