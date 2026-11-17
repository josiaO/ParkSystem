"""Plate correction policies. Neutral is the default; country rules are opt-in."""

from __future__ import annotations

import re
from typing import Any, Iterable

from app.core.plate import (
    _AE_RE,
    _KE_RE,
    _ZA_RE,
    confusion_variants,
    normalize_plate,
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


_TZ_STANDARD_7 = re.compile(r"^T\d{3}[A-Z]{3}$")
# Characters the OCR confuses between digit and letter slots.
# J -> 3 and G -> 6 were confirmed on SITE-PC01 (TJ22BCR was T322BCR,
# TJ71COM and TG21EMM were read correctly on other passes).
_TZ_TO_DIGIT = {"O": "0", "D": "0", "Q": "0", "I": "1", "L": "1", "Z": "2", "J": "3", "S": "5", "G": "6", "B": "8"}
_TZ_TO_LETTER = {"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B"}
# A leading T read as one of these (night glare, worn paint).
_TZ_T_LOOKALIKES = {"1", "7", "I"}
# Formats that are not T + 3 digits + 3 letters and must never be rewritten.
TZ_SPECIAL_PREFIXES = ("STK", "STL", "STM", "STN", "STJ", "SU", "SM", "DFPA", "DFP", "CD", "TCDF", "JWTZ", "PT", "MC")
TZ_MAX_CORRECTIONS = 2
# Registrations are issued in alphabetical series (T123 ABC ... T123 EXX in
# 2026; F and G are just starting). On SITE-PC01, A-G was the first letter of
# 99.6% of 9,800 standard reads. A correction must land in an issued series
# (H is headroom); a read already in the standard shape is never changed.
TZ_SERIES_LETTERS = frozenset("ABCDEFGH")


def correct_tz_standard_plate(plate: str) -> tuple[str, list[str]]:
    """Fit a 7-character read to T + 3 digits + 3 letters (T123ABC).

    Fixed-slot OCR puts each character in a known position, so a letter in
    a digit slot (S -> 5) or a digit in a letter slot (8 -> B) is a misread,
    and a leading 1/7/I is a T. Accepted only when the result is exactly the
    standard shape with at most two characters changed; special prefixes,
    other lengths and anything else stay as read.
    """
    if len(plate) != 7 or plate.startswith(TZ_SPECIAL_PREFIXES) or _TZ_STANDARD_7.match(plate):
        return plate, []
    head = "T" if plate[0] in _TZ_T_LOOKALIKES else plate[0]
    digits = "".join(_TZ_TO_DIGIT.get(ch, ch) for ch in plate[1:4])
    letters = "".join(_TZ_TO_LETTER.get(ch, ch) for ch in plate[4:7])
    candidate = head + digits + letters
    changes = [f"{i}:{a}->{b}" for i, (a, b) in enumerate(zip(plate, candidate)) if a != b]
    if (
        not _TZ_STANDARD_7.match(candidate)
        or len(changes) > TZ_MAX_CORRECTIONS
        or candidate[4] not in TZ_SERIES_LETTERS
    ):
        return plate, []
    return candidate, changes


class TanzaniaPlatePolicy(NeutralPlatePolicy):
    """Tanzanian standard plates: T + 3 digits + 3 letters (T385DQP).

    Measured on SITE-PC01 (24 h, 366 non-standard reads): the previous
    shape-score search also rewrote government and special plates
    (SM15711 -> SM154II, STN5611 -> STN57II, DFA6205 -> DFA79OS) and longer
    reads (T8790DKV -> T879ODKV). Only the strict positional rule remains.
    """

    id = "TZ"

    def correct(self, raw: str | None, *, known_plates: Iterable[str] | None = None) -> dict[str, Any]:
        base = NeutralPlatePolicy.correct(self, raw, known_plates=known_plates)
        if base.get("reason") in {"exact-known", "known-confusion"}:
            return base
        normalised = normalize_plate(raw)
        fixed, changes = correct_tz_standard_plate(normalised)
        return {
            "plate": fixed,
            "corrected": fixed != normalised,
            "reason": "tz-slots " + ",".join(changes) if changes else "unchanged",
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
