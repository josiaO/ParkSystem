from __future__ import annotations

def latest_for_camera(db: Session, camera_id: int) -> VehicleCapture | None:
    return db.scalar(
        select(VehicleCapture)
        .where(VehicleCapture.camera_id == camera_id)
        .order_by(VehicleCapture.id.desc())
    )

def latest_for_cameras(db: Session, camera_ids: list[int] | set[int]) -> dict[int, VehicleCapture]:
    """Fetch the latest capture for many cameras in one bounded query."""
    ids = sorted({int(value) for value in camera_ids if value is not None})
    if not ids:
        return {}
    latest_ids = (
        select(func.max(VehicleCapture.id).label("id"))
        .where(VehicleCapture.camera_id.in_(ids))
        .group_by(VehicleCapture.camera_id)
        .subquery()
    )
    rows = db.scalars(
        select(VehicleCapture).where(VehicleCapture.id.in_(select(latest_ids.c.id)))
    ).all()
    return {int(row.camera_id): row for row in rows if row.camera_id is not None}

def captures_for_sessions(db: Session, rows: list[object]) -> dict[int, VehicleCapture]:
    """Resolve session display stills with bounded queries instead of one per row."""
    from app.models import ParkingSession

    sessions = [row for row in rows if isinstance(row, ParkingSession)]
    if not sessions:
        return {}
    plates = {normalize_plate(row.plate) for row in sessions if normalize_plate(row.plate)}
    camera_ids = {int(row.camera_id) for row in sessions if row.camera_id is not None}
    by_plate: dict[str, VehicleCapture] = {}
    by_camera = latest_for_cameras(db, camera_ids)
    if plates:
        latest_ids = (
            select(func.max(VehicleCapture.id).label("id"))
            .where(VehicleCapture.plate.in_(plates))
            .group_by(VehicleCapture.plate)
            .subquery()
        )
        by_plate = {
            normalize_plate(row.plate): row
            for row in db.scalars(
                select(VehicleCapture).where(VehicleCapture.id.in_(select(latest_ids.c.id)))
            ).all()
            if row.plate
        }
    return {
        int(row.id): by_plate.get(normalize_plate(row.plate)) or (
            by_camera.get(int(row.camera_id)) if row.camera_id is not None else None
        )
        for row in sessions
        if row.id is not None
    }

def list_captures(db: Session, *, gate_id: int | None = None, limit: int = 20) -> list[VehicleCapture]:
    stmt = select(VehicleCapture).order_by(VehicleCapture.id.desc()).limit(max(1, min(int(limit), 100)))
    if gate_id is not None:
        stmt = stmt.where(VehicleCapture.gate_id == gate_id)
    return list(db.scalars(stmt).all())

def _dedupe_detection_rows(rows: list[VehicleCapture], *, limit: int) -> list[VehicleCapture]:
    """Collapse repeated reads for the operator history without deleting evidence.

    Native cameras can report the same vehicle several times while it is over
    the trigger line.  Those rows remain in ``vehicle_captures`` for audit and
    troubleshooting; this is only the compact read model used by Detections.
    A different visit id is retained once it is outside the short repeat-read
    window, so a later visit by the same plate is not hidden.
    """
    selected: list[VehicleCapture] = []
    latest_by_key: dict[tuple[int | None, str, str], tuple[object | None, str]] = {}
    for row in rows:
        plate = normalize_plate(row.plate or row.plate_raw or "")
        if not plate:
            selected.append(row)
            if len(selected) >= limit:
                break
            continue
        key = (row.camera_id, str(row.lane_direction or "").upper(), plate)
        created = as_utc(row.created_at)
        visit_id = str(row.visit_id or "")
        previous = latest_by_key.get(key)
        repeated = False
        if previous is not None:
            previous_created, previous_visit = previous
            same_visit = bool(visit_id and previous_visit and visit_id == previous_visit)
            within_window = bool(
                created is not None and previous_created is not None
                and abs((previous_created - created).total_seconds()) <= DETECTION_DISPLAY_DEDUPE_SECONDS
            )
            repeated = same_visit or within_window
        if repeated:
            continue
        latest_by_key[key] = (created, visit_id)
        selected.append(row)
        if len(selected) >= limit:
            break
    return selected

def list_recent_detections(db: Session, *, gate_id: int | None = None, limit: int = 20) -> list[VehicleCapture]:
    """Return a compact detection history while retaining raw capture rows."""
    safe_limit = max(1, min(int(limit), 100))
    # Read enough raw rows to fill the requested compact page when a camera is
    # reporting repeated frames. The hard cap keeps this endpoint bounded.
    raw_limit = min(500, max(safe_limit, safe_limit * 6))
    stmt = select(VehicleCapture).order_by(VehicleCapture.id.desc()).limit(raw_limit)
    if gate_id is not None:
        stmt = stmt.where(VehicleCapture.gate_id == gate_id)
    rows = list(db.scalars(stmt).all())
    return _dedupe_detection_rows(rows, limit=safe_limit)

def apply_operator_plate_correction(row: VehicleCapture, plate: str) -> VehicleCapture:
    """Set the operator plate without erasing the original OCR string."""
    chosen = normalize_plate(plate)
    if not chosen:
        raise ValueError("Corrected plate is empty")
    original = row.plate_raw or row.plate
    if not row.plate_raw:
        row.plate_raw = original
    box = dict(row.bbox or {})
    box["operator_plate"] = chosen
    box["ocr_plate"] = original
    box["needs_review"] = False
    box["pending_confirmation"] = False
    box["fusion"] = {
        **(box.get("fusion") or {}),
        "method": "OPERATOR_CORRECTED",
        "resolved_plate": chosen,
        "needs_review": False,
    }
    row.bbox = box
    row.plate = chosen
    return row
