"""Country-neutral plate normalisation and optional site validation."""

from __future__ import annotations

import re
from typing import Any

_ALNUM_RE = re.compile(r"[^A-Z0-9]+")
_TZ_RE = re.compile(r"^T[A-Z0-9]{5,8}$")
_KE_RE = re.compile(r"^K[A-Z]{2}\d{3}[A-Z]$")
_ZA_RE = re.compile(r"^[A-Z]{2,3}\d{2,3}[A-Z]{2}$")
_AE_RE = re.compile(r"^[A-Z]?\d{1,6}$")


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


def apply_site_plate(raw: str | None, *, normalization: str = "ALNUM_UPPER", validation: str = "NONE") -> dict[str, Any]:
    normalised = normalize_plate(raw, normalization)
    checked = validate_plate(normalised, validation)
    return {
        "raw_plate": str(raw or "").strip(),
        "normalized_plate": normalised,
        "validation_result": checked.get("result") or "NONE",
        "validation_ok": bool(checked.get("ok")),
        "normalization_policy": normalization,
        "validation_policy": validation,
    }
