from __future__ import annotations

import re

_PLATE_RE = re.compile(r"[^A-Z0-9]+")


def normalize_plate(value: str | None) -> str:
    if not value:
        return ""
    return _PLATE_RE.sub("", value.upper())


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
