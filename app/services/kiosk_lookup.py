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
from app.services.public_pay import session_by_public_token
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
    plate = normalize_plate(row.plate)
    matched = None
    if plate:
        matched = db.scalar(
            select(VehicleCapture)
            .where(VehicleCapture.plate == plate)
            .order_by(VehicleCapture.id.desc())
        )
    camera_latest = None
    if row.camera_id:
        camera_latest = db.scalar(
            select(VehicleCapture)
            .where(VehicleCapture.camera_id == row.camera_id)
            .order_by(VehicleCapture.id.desc())
        )
    if matched is not None:
        return matched, True
    if camera_latest is not None:
        same = bool(plate and normalize_plate(camera_latest.plate) == plate)
        return camera_latest, same
    return None, False


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
        row = session_by_public_token(db, token)
        if row is not None:
            return row
    ref = normalize_human_reference(raw)
    if ref:
        row = db.scalar(
            select(ParkingSession).where(ParkingSession.human_reference == ref).order_by(ParkingSession.id.desc())
        )
        if row is not None:
            return row
    plate = normalize_plate(raw)
    if not plate:
        return None
    open_row = db.scalar(
        select(ParkingSession)
        .where(ParkingSession.plate == plate, ParkingSession.status.in_(tuple(OPEN_STATUSES)))
        .order_by(ParkingSession.id.desc())
    )
    if open_row is not None:
        return open_row
    return db.scalar(
        select(ParkingSession).where(ParkingSession.plate == plate).order_by(ParkingSession.id.desc())
    )
