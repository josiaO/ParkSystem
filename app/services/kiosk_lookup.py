"""Find a parking session from a receipt QR, a pasted link, or a plate.

The photo is shown beside the fee so a wrong plate read can still be checked
against the car that actually entered.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import unquote, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.plate import normalize_plate
from app.models import ParkingSession, VehicleCapture
from app.services.public_pay import session_by_public_token
from app.services.simulation import OPEN_STATUSES


def extract_receipt_token(raw: str) -> str:
    """Pull the public receipt token out of a scanner string.

    Scanners often type the full URL printed in the QR, not only the code.
    """
    text = (raw or "").strip().strip('"').strip("'")
    if not text:
        return ""
    candidate = text
    if "://" in text or text.startswith("/"):
        parsed = urlparse(text if "://" in text else f"http://local{text}")
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        if "p" in parts:
            idx = parts.index("p")
            if idx + 1 < len(parts):
                token = parts[idx + 1]
                if token.lower() not in {"qr.png", "status", "pay", "kiosk-pay", "snapshot.jpg", "crop.jpg"}:
                    return token
        query = parsed.query or ""
        for bit in query.split("&"):
            if bit.startswith("token="):
                return unquote(bit.split("=", 1)[1])
        return ""
    if "token=" in candidate:
        tail = candidate.split("token=", 1)[1]
        return unquote(tail.split("&", 1)[0].strip())
    return candidate.split()[0]


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
