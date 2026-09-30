"""Plate correction policies. Neutral is the default; country rules are opt-in."""

from __future__ import annotations

from typing import Any, Iterable

from app.core.plate import (
    _AE_RE,
    _KE_RE,
    _ZA_RE,
    _force_tz_positions,
    confusion_variants,
    normalize_plate,
    plate_shape_score,
)


class NeutralPlatePolicy:
    """Country-neutral normalisation and registered-plate lookalike matching.

    Does not force a leading T, digit/letter positions, or East African shapes.
    """

    id = "NONE"

    def correct(self, raw: str | None, *, known_plates: Iterable[str] | None = None) -> dict[str, Any]:
        normalised = normalize_plate(raw)
        known = {normalize_plate(p) for p in (known_plates or []) if normalize_plate(p)}
        if normalised in known:
            return {"plate": normalised, "corrected": False, "reason": "exact-known", "policy": self.id}
        for plate in confusion_variants(normalised):
            if plate in known:
                return {
                    "plate": plate,
                    "corrected": plate != normalised,
                    "reason": "known-confusion",
                    "policy": self.id,
                }
        return {"plate": normalised, "corrected": False, "reason": "unchanged", "policy": self.id}


class _PatternPlatePolicy(NeutralPlatePolicy):
    """Prefer a confusion variant that matches this country's plate pattern."""

    pattern = None

    def correct(self, raw: str | None, *, known_plates: Iterable[str] | None = None) -> dict[str, Any]:
        base = NeutralPlatePolicy.correct(self, raw, known_plates=known_plates)
        if base.get("reason") in {"exact-known", "known-confusion"}:
            return base
        normalised = normalize_plate(raw)
        if self.pattern is not None and self.pattern.match(normalised):
            return {"plate": normalised, "corrected": False, "reason": "unchanged", "policy": self.id}
        for plate in confusion_variants(normalised):
            if self.pattern is not None and self.pattern.match(plate):
                return {
                    "plate": plate,
                    "corrected": plate != normalised,
                    "reason": "pattern",
                    "policy": self.id,
                }
        return {"plate": normalised, "corrected": False, "reason": "unchanged", "policy": self.id}


class TanzaniaPlatePolicy(NeutralPlatePolicy):
    """Tanzanian private plates: T + 3 digits + letters, including T285DQP."""

    id = "TZ"

    def correct(self, raw: str | None, *, known_plates: Iterable[str] | None = None) -> dict[str, Any]:
        base = NeutralPlatePolicy.correct(self, raw, known_plates=known_plates)
        if base.get("reason") in {"exact-known", "known-confusion"}:
            return base
        normalised = normalize_plate(raw)
        variants = confusion_variants(normalised)
        best = normalised
        best_score = plate_shape_score(normalised)
        for plate in variants:
            score = plate_shape_score(plate)
            if score > best_score:
                best, best_score = plate, score
        forced = _force_tz_positions(normalised)
        if plate_shape_score(forced) > best_score:
            best = forced
        return {
            "plate": best,
            "corrected": best != normalised,
            "reason": "tz-shape" if best != normalised else "unchanged",
            "policy": self.id,
        }


class KenyaPlatePolicy(_PatternPlatePolicy):
    id = "KE"
    pattern = _KE_RE


class SouthAfricaPlatePolicy(_PatternPlatePolicy):
    id = "ZA"
    pattern = _ZA_RE


class UAEPlatePolicy(_PatternPlatePolicy):
    id = "AE"
    pattern = _AE_RE


_POLICIES = {
    "NONE": NeutralPlatePolicy,
    "TZ": TanzaniaPlatePolicy,
    "KE": KenyaPlatePolicy,
    "ZA": SouthAfricaPlatePolicy,
    "AE": UAEPlatePolicy,
}


def plate_policy_for(validation: str | None = None):
    key = str(validation or "NONE").strip().upper()
    if key in {"", "NONE", "CUSTOM"}:
        key = "NONE"
    return _POLICIES.get(key, NeutralPlatePolicy)()
