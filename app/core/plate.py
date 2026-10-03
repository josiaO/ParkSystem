"""Country-neutral plate normalisation and optional site validation."""

from __future__ import annotations

import re
from typing import Any, Iterable

_ALNUM_RE = re.compile(r"[^A-Z0-9]+")
_TZ_RE = re.compile(r"^T[A-Z0-9]{5,8}$")
_TZ_STANDARD_RE = re.compile(r"^T\d{3}[A-Z]{2,4}$")
_KE_RE = re.compile(r"^K[A-Z]{2}\d{3}[A-Z]$")
_ZA_RE = re.compile(r"^[A-Z]{2,3}\d{2,3}[A-Z]{2}$")
_AE_RE = re.compile(r"^[A-Z]?\d{1,6}$")
_DENYLIST = frozenset({
    "STATION", "POLICE", "TAXI", "STOP", "ENTRY", "EXIT", "OPEN", "CLOSE",
    "DANGER", "PARKING", "WELCOME", "THANKYOU", "THANK", "PLEASE", "SLOW",
    "SPEED", "CAMERA", "SMARTPARK", "DAHUA", "HIKVISION",
    "NOPLATE", "NOPLAT", "NOPLATEY",
})
# FastALPR's global OCR and Chinese-configured QY cameras invent these on
# empty lanes (bollards, barrier arms, glare). Not a country denylist.
_EMPTY_SCENE_PREFIXES = ("ZC", "ZH", "ZJ", "ZL")
_EMPTY_SCENE_EXACT = frozenset({"ZC", "ZH", "ZJ", "ZL", "NOPLATE", "NOPLAT", "NOPLATEY"})
# OCR pairs seen on Tanzanian plates (digit/letter lookalikes).
_CONFUSION_PAIRS = (("O", "0"), ("I", "1"), ("B", "8"), ("S", "5"))


def normalize_plate(value: str | None, policy: str = "ALNUM_UPPER") -> str:
    if not value:
        return ""
    chosen = (policy or "ALNUM_UPPER").upper()
    if chosen == "AS_READ":
        return str(value).strip()
    if chosen == "UPPER_STRIP":
        return str(value).upper().replace(" ", "").replace("-", "").strip()
    return _ALNUM_RE.sub("", str(value).upper())


def plate_similarity(left: str | None, right: str | None) -> float:
    """1.0 is identical after normalisation; used to fuse native vs local reads."""
    a, b = normalize_plate(left), normalize_plate(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    n, m = len(a), len(b)
    prev = list(range(m + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            ins, delete, sub = curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb)
            curr.append(min(ins, delete, sub))
        prev = curr
    dist = prev[-1]
    return 1.0 - (dist / max(n, m))


def validate_plate(value: str | None, policy: str = "NONE") -> dict[str, Any]:
    """Optional format check. NONE accepts any non-empty normalised plate."""
    chosen = (policy or "NONE").upper()
    normalised = normalize_plate(value)
    if not normalised:
        return {"ok": False, "policy": chosen, "result": "EMPTY", "normalized": ""}
    if chosen in {"", "NONE"}:
        return {"ok": True, "policy": "NONE", "result": "ACCEPTED", "normalized": normalised}
    patterns = {"TZ": _TZ_RE, "KE": _KE_RE, "ZA": _ZA_RE, "AE": _AE_RE}
    regex = patterns.get(chosen)
    if regex is None:
        return {"ok": True, "policy": chosen, "result": "UNVALIDATED", "normalized": normalised}
    ok = bool(regex.match(normalised))
    return {
        "ok": ok,
        "policy": chosen,
        "result": "VALID" if ok else "INVALID",
        "normalized": normalised,
    }


def _letter_digit_mix(plate: str) -> bool:
    letters = sum(ch.isalpha() for ch in plate)
    digits = sum(ch.isdigit() for ch in plate)
    return letters >= 1 and digits >= 2 and 5 <= len(plate) <= 10


def plate_shape_score(plate: str) -> int:
    """Higher is a more typical East-African private plate."""
    if _TZ_STANDARD_RE.match(plate):
        return 3
    if _TZ_RE.match(plate) or _KE_RE.match(plate) or _ZA_RE.match(plate):
        return 2
    if _letter_digit_mix(plate):
        return 1
    return 0


def confusion_variants(plate: str, *, max_subs: int = 2) -> list[str]:
    """Generate OCR lookalike spellings (0/O, 1/I, 8/B, 5/S) without exploding."""
    seed = normalize_plate(plate)
    if not seed:
        return []
    found = {seed}
    layer = {seed}
    for _ in range(max(1, int(max_subs or 1))):
        nxt: set[str] = set()
        for text in layer:
            for i, ch in enumerate(text):
                for a, b in _CONFUSION_PAIRS:
                    swap = b if ch == a else a if ch == b else None
                    if swap:
                        nxt.add(text[:i] + swap + text[i + 1 :])
        found.update(nxt)
        layer = nxt
        if len(found) > 64:
            break
    return list(found)


def correct_ocr_confusions(
    raw: str | None,
    *,
    known_plates: Iterable[str] | None = None,
    policy: str = "NONE",
) -> dict[str, Any]:
    """Correct OCR lookalikes using the site plate policy. Default is neutral."""
    from app.core.plate_policy import plate_policy_for

    return plate_policy_for(policy).correct(raw, known_plates=known_plates)


def _force_tz_positions(plate: str) -> str:
    """Tanzanian private plates are typically T + 3 digits + 3 letters (T285DQP)."""
    if not plate.startswith("T") or len(plate) < 6:
        return plate
    body = list(plate[1:])
    digit_map = {"O": "0", "I": "1", "B": "8", "S": "5"}
    letter_map = {"0": "O", "1": "I", "8": "B", "5": "S"}
    for i, ch in enumerate(body):
        if i < 3:
            body[i] = digit_map.get(ch, ch)
        else:
            body[i] = letter_map.get(ch, ch)
    return "T" + "".join(body)


def is_empty_scene_ocr(value: str | None, *, confidence: float = 0.0) -> bool:
    """True when OCR looks like an empty-lane hallucination, not a vehicle plate.

    ParkWatch OcxConfig filters 无车牌 (no vehicle). FastALPR's CCT-global model
    and a QY camera left on 全国 Chinese plate types commonly emit ``ZC…`` on
    bollards and empty asphalt. A real registration that happens to start with
    those letters still passes when it matches a known plate shape or is a
    high-confidence mixed alphanumeric read.
    """
    plate = normalize_plate(value)
    if not plate:
        return False
    if plate in _EMPTY_SCENE_EXACT:
        return True
    if any(plate.startswith(prefix) for prefix in _EMPTY_SCENE_PREFIXES):
        # A real ZA-style plate can start with ZC (e.g. ZC12GP). FastALPR
        # empty-lane reads never match a country shape.
        if _TZ_STANDARD_RE.match(plate) or _KE_RE.match(plate) or _ZA_RE.match(plate):
            return False
        return True
    return False


def assess_plate(value: str | None, policy: str = "NONE", *, confidence: float = 0.0) -> dict[str, Any]:
    """Flag garbage OCR as unlikely without changing the site validation default (NONE)."""
    chosen = (policy or "NONE").upper()
    normalised = normalize_plate(value)
    checked = validate_plate(normalised, chosen)
    likely = True
    flag = "LIKELY"
    if not normalised:
        likely, flag = False, "EMPTY"
    elif normalised in _DENYLIST:
        likely, flag = False, "DENYLIST"
    elif is_empty_scene_ocr(normalised, confidence=confidence):
        likely, flag = False, "EMPTY_SCENE_OCR"
    elif chosen not in {"", "NONE", "CUSTOM"} and not checked["ok"]:
        likely, flag = False, "UNLIKELY_PATTERN"
    elif chosen in {"", "NONE", "CUSTOM"} and not 5 <= len(normalised) <= 12:
        likely, flag = False, "UNLIKELY_LENGTH"
    return {
        **checked,
        "likely": likely,
        "likelihood": flag,
        "hold_for_operator": not likely,
    }


def apply_site_plate(
    raw: str | None,
    *,
    normalization: str = "ALNUM_UPPER",
    validation: str = "NONE",
    confidence: float = 0.0,
) -> dict[str, Any]:
    normalised = normalize_plate(raw, normalization)
    corrected = correct_ocr_confusions(normalised, policy=validation)
    chosen = corrected.get("plate") or normalised
    checked = assess_plate(chosen, validation, confidence=confidence)
    return {
        "raw_plate": str(raw or "").strip(),
        "normalized_plate": chosen,
        "ocr_corrected": bool(corrected.get("corrected")),
        "ocr_correction_reason": corrected.get("reason") or "",
        "validation_result": checked.get("result") or "NONE",
        "validation_ok": bool(checked.get("ok")),
        "likely": bool(checked.get("likely")),
        "likelihood": checked.get("likelihood") or "LIKELY",
        "hold_for_operator": bool(checked.get("hold_for_operator")),
        "normalization_policy": normalization,
        "validation_policy": validation,
    }
