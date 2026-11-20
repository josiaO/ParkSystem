"""One car, several reads: the best read of a lane visit wins.

A car in front of a lane camera is usually read more than once: Zirp's video
gate reads the live sub-stream (704 px) and the camera's own trigger sends one
or two full-resolution stills. The database keeps exactly one capture per lane
visit, so before this module the *first* read owned the visit and every later
read of the same car got that first row back unchanged.

Measured on SITE-PC01 (20 Nov 2026, 30 h): 79% of sub-stream reads were held
for review (average confidence 0.67), and they usually arrived first. The good
full-resolution read that followed was then dropped:

* at an exit, the car was never handled (the controller only runs for a new
  capture), so it looked like a car without a visit;
* at an entry, 27 sessions were opened from the held row's plate instead of
  the better read.

Rules (``plan_upgrade``). Only a capture that is still **held** (needs review /
pending confirmation) can change. A held capture never opened a session or a
barrier, so changing it cannot contradict a decision already made.

* ``consensus``: a second, independent read of the same visit gives exactly
  the same plate, and the better of the two is at least
  ``CONSENSUS_MIN_CONFIDENCE``. Two frames agreeing is stronger evidence than
  one frame above 0.92, so the hold is released.
* ``better``: the new read is not held and is more confident: it replaces the
  held plate and the hold is released.
* ``better_candidate``: the new read is still held but clearly more confident
  (by ``CANDIDATE_MARGIN``): it replaces the plate the operator will be asked
  to confirm, and stays held.

The site's plate validation still applies afterwards: an upgraded plate that
fails it is held again by the caller.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.plate import normalize_plate

CONSENSUS_MIN_CONFIDENCE = 0.80
CANDIDATE_MARGIN = 0.05

CONSENSUS = "consensus"
BETTER = "better"
BETTER_CANDIDATE = "better_candidate"


def _flag(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def row_is_held(row: Any) -> bool:
    bbox = getattr(row, "bbox", None)
    bbox = bbox if isinstance(bbox, dict) else {}
    return _flag(bbox.get("needs_review")) or _flag(bbox.get("pending_confirmation"))


def capture_is_held(capture: dict | None) -> bool:
    capture = capture or {}
    return _flag(capture.get("needs_review")) or _flag(capture.get("pending_confirmation"))


def capture_confidence(capture: dict | None) -> float:
    capture = capture or {}
    for key in ("score", "confidence"):
        try:
            value = float(capture.get(key) or 0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            return value
    fusion = capture.get("fusion") if isinstance(capture.get("fusion"), dict) else {}
    try:
        return float(fusion.get("resolved_confidence") or 0)
    except (TypeError, ValueError):
        return 0.0


def plan_upgrade(
    *,
    held: bool,
    held_plate: str,
    held_confidence: float,
    incoming_plate: str,
    incoming_confidence: float,
    incoming_held: bool,
) -> str | None:
    """Decide how a new read of a visit changes its existing capture (see module doc)."""
    if not held:
        return None
    old = normalize_plate(held_plate)
    new = normalize_plate(incoming_plate)
    if not new:
        return None
    old_conf = float(held_confidence or 0)
    new_conf = float(incoming_confidence or 0)
    if old and new == old:
        if max(old_conf, new_conf) >= CONSENSUS_MIN_CONFIDENCE:
            return CONSENSUS
        return None
    if not incoming_held and new_conf > old_conf:
        return BETTER
    if incoming_held and new_conf >= old_conf + CANDIDATE_MARGIN:
        return BETTER_CANDIDATE
    return None


def apply_upgrade(row: Any, capture: dict, kind: str, *, crop_ref: str = "", snapshot_ref: str = "") -> None:
    """Change the held capture ``row`` in place (the caller commits)."""
    capture = capture or {}
    incoming_plate = normalize_plate(capture.get("plate"))
    incoming_conf = capture_confidence(capture)
    bbox = dict(row.bbox) if isinstance(row.bbox, dict) else {}
    history = {
        "kind": kind,
        "from_plate": str(row.plate or ""),
        "from_confidence": float(row.confidence or 0),
        "at": datetime.now(timezone.utc).isoformat(),
    }
    if kind in {BETTER, BETTER_CANDIDATE}:
        row.plate = incoming_plate
        row.plate_raw = str(capture.get("plate_raw") or incoming_plate)[:64]
        row.confidence = incoming_conf
        incoming_box = capture.get("bbox") if isinstance(capture.get("bbox"), dict) else {}
        for key in ("x1", "y1", "x2", "y2", "image_width", "image_height", "confidence"):
            if incoming_box.get(key) not in (None, ""):
                bbox[key] = incoming_box[key]
        if isinstance(capture.get("fusion"), dict):
            bbox["fusion"] = capture["fusion"]
        if crop_ref:
            row.crop_path = crop_ref
        if snapshot_ref:
            row.snapshot_path = snapshot_ref
    else:
        row.confidence = max(float(row.confidence or 0), incoming_conf)
    release = kind in {CONSENSUS, BETTER}
    bbox["needs_review"] = not release
    bbox["pending_confirmation"] = not release
    bbox["visit_upgrades"] = [*list(bbox.get("visit_upgrades") or [])[-4:], history]
    row.bbox = bbox
