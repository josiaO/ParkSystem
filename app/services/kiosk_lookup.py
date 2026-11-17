"""Find a parking session from a receipt QR, a pasted link, or a plate.

The photo is shown beside the fee so a wrong plate read can still be checked
against the car that actually entered.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.plate import normalize_plate
from app.domain.receipt_engine import extract_session_token, normalize_human_reference
from app.models import ParkingSession, VehicleCapture
from app.services.simulation import OPEN_STATUSES


def extract_receipt_token(raw: str) -> str:
    """Pull the public receipt token out of a scanner string.

    Scanners often type the full URL printed in the QR, not only the code.
    Accepts `/s/{token}` (canonical) and `/p/{token}` (existing public page).
    """
    return extract_session_token(raw)


def format_stay(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, _secs = divmod(rem, 60)
    if hours and minutes:
        return f"{hours} h {minutes} min"
    if hours:
        return f"{hours} h"
    if minutes:
        return f"{minutes} min"
    return "under 1 min"


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def stay_for(row: ParkingSession, *, now: datetime | None = None) -> dict:
    start = _aware(row.entry_time)
    finish = _aware(row.exit_time) or _aware(now) or datetime.now(timezone.utc)
    if start is None:
        return {"duration_seconds": 0, "duration_label": "—", "still_inside": row.status not in ("CLOSED", "PAID")}
    seconds = max(0, int((finish - start).total_seconds()))
    inside = row.status not in ("CLOSED",) or row.exit_time is None
    if row.status == "CLOSED" and row.exit_time is not None:
        inside = False
    return {
        "duration_seconds": seconds,
        "duration_label": format_stay(seconds),
        "still_inside": bool(inside and row.status not in ("CLOSED",)),
    }


def _capture_for_session(db: Session, row: ParkingSession) -> tuple[VehicleCapture | None, bool]:
    """Return the best photo and whether its plate matches the session plate."""
    from app.services.captures import find_capture_for_session

    plate = normalize_plate(row.plate)
    capture = find_capture_for_session(
        db,
        plate=plate,
        camera_id=row.camera_id,
        event_id=getattr(row, "entry_event_id", "") or "",
        visit_id=getattr(row, "visit_id", "") or "",
        image_ref=getattr(row, "entry_image_ref", "") or "",
    )
    matches = bool(capture and plate and normalize_plate(capture.plate) == plate)
    return capture, matches


def capture_for_session(db: Session, row: ParkingSession) -> VehicleCapture | None:
    """Return only evidence identified by this session's event/visit identity."""
    capture, _ = _capture_for_session(db, row)
    return capture


def image_fields(db: Session, row: ParkingSession) -> dict:
    capture, matches = _capture_for_session(db, row)
    token = row.public_token or ""
    snapshot_url = f"/p/{token}/snapshot.jpg" if token and capture and capture.snapshot_path else None
    crop_url = f"/p/{token}/crop.jpg" if token and capture and capture.crop_path else None
    read_plate = capture.plate if capture else ""
    note = "Compare the photo with the plate. If the read is wrong, correct it before taking payment."
    if capture is None:
        note = "No entry photo is stored for this visit yet. Use the plate and the time inside."
    elif not matches:
        note = f"The camera read {read_plate or 'no plate'}, which does not match this ticket. Use the photo."
    return {
        "snapshot_url": snapshot_url,
        "crop_url": crop_url,
        "image_plate": read_plate or "",
        "image_matches_plate": bool(matches) if capture else None,
        "image_note": note,
    }


def find_session(db: Session, query: str) -> ParkingSession | None:
    raw = (query or "").strip()
    if not raw:
        return None
    token = extract_receipt_token(raw)
    if token:
        from app.services.public_pay import session_by_public_token

        row = session_by_public_token(db, token)
        if row is not None:
            return row
    ref = normalize_human_reference(raw)
    if ref:
        row = db.scalar(
            select(ParkingSession).where(ParkingSession.human_reference == ref).order_by(ParkingSession.id.desc()).limit(1)
        )
        if row is not None:
            return row
    plate = normalize_plate(raw)
    if not plate:
        return None
    open_row = db.scalar(
        select(ParkingSession)
        .where(ParkingSession.plate == plate, ParkingSession.status.in_(tuple(OPEN_STATUSES)))
        .order_by(ParkingSession.id.desc()).limit(1)
    )
    if open_row is not None:
        return open_row
    return db.scalar(
        select(ParkingSession).where(ParkingSession.plate == plate).order_by(ParkingSession.id.desc()).limit(1)
    )


NEAR_MATCH_MIN_SIMILARITY = 0.8  # about one character off for a 5-9 character plate


def near_matches(
    db: Session,
    plate: str,
    *,
    site_id: int | None = None,
    limit: int = 3,
    min_similarity: float = NEAR_MATCH_MIN_SIMILARITY,
) -> list[dict]:
    """Open visits whose plate is close to *plate* (OCR confusions such as 8/B, 0/O).

    For an operator "did you mean" prompt only. A fuzzy match must never open a
    barrier by itself.
    """
    from app.core.plate import plate_similarity

    wanted = normalize_plate(plate)
    if not wanted:
        return []
    query = select(ParkingSession).where(ParkingSession.status.in_(tuple(OPEN_STATUSES)))
    if site_id is not None:
        query = query.where(ParkingSession.site_id == int(site_id))
    scored = []
    for row in db.scalars(query).all():
        candidate = normalize_plate(row.plate)
        if not candidate or candidate == wanted:
            continue
        score = plate_similarity(wanted, candidate)
        if score >= min_similarity:
            scored.append((score, row))
    scored.sort(key=lambda item: (-item[0], -(item[1].id or 0)))
    return [
        {
            "session_id": row.id,
            "plate": row.plate,
            "similarity": round(score, 2),
            "token": row.public_token or "",
            "entry_time": row.entry_time.isoformat() if row.entry_time else None,
            "status": row.status,
        }
        for score, row in scored[: max(1, int(limit))]
    ]
