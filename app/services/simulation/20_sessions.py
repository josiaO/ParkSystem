from __future__ import annotations

def session_dict(row: ParkingSession, capture=None, *, lookup_capture: bool = True) -> dict:
    from sqlalchemy.orm import object_session
    db = object_session(row)
    policy = site_policy(db) if db is not None else None
    token = row.public_token or ""
    body = {
        "id": row.id,
        "plate": row.plate,
        "gate_id": row.gate_id,
        "camera_id": row.camera_id,
        "visit_id": getattr(row, "visit_id", "") or "",
        "lane_direction": row.lane_direction,
        "car_type": row.car_type,
        "status": row.status,
        "receipt_status": row.receipt_status or "",
        "simulated": bool(row.simulated),
        "parker_kind": getattr(row, "parker_kind", None) or "CASUAL",
        "access_plan_id": getattr(row, "access_plan_id", None),
        "vehicle_id": getattr(row, "vehicle_id", None),
        "public_token": token,
        "receipt_url": f"/p/{token}" if token else None,
        "qr_url": f"/p/{token}/qr.png" if token else None,
        "qr_payload": session_qr_payload(token),
        "entry_time": as_site_local(row.entry_time, policy).isoformat() if row.entry_time else None,
        "exit_time": as_site_local(row.exit_time, policy).isoformat() if row.exit_time else None,
        "currency": row.currency,
        "amount_due": float(row.amount_due or 0),
        "amount_paid": float(row.amount_paid or 0),
        "breakdown": row.breakdown or [],
        "snapshot_url": None,
        "crop_url": None,
        "plate_confidence": None,
    }
    try:
        from sqlalchemy.orm import object_session
        from app.services.captures import capture_dict, find_capture_for_session
        db = object_session(row)
        if db is not None:
            cap = capture
            if cap is None and lookup_capture:
                cap = find_capture_for_session(
                    db,
                    plate=row.plate,
                    camera_id=row.camera_id,
                    event_id=getattr(row, "entry_event_id", "") or "",
                    visit_id=getattr(row, "visit_id", "") or "",
                    image_ref=getattr(row, "entry_image_ref", "") or "",
                )
            # Very old sessions created before event/visit/image identity was
            # persisted can still be shown in the operator UI. Keep their
            # photo only when the latest same-camera capture is temporally
            # adjacent to entry and the plate differs by at most one OCR
            # character. This fallback is intentionally not used by the
            # public payment projection.
            if cap is None and lookup_capture and db is not None and row.camera_id:
                from app.services.captures import latest_for_camera

                candidate = latest_for_camera(db, int(row.camera_id))
                entry_at = as_utc(row.entry_time or row.created_at)
                capture_at = as_utc(candidate.created_at) if candidate is not None else None
                if (
                    candidate is not None
                    and candidate.snapshot_path
                    and entry_at is not None
                    and capture_at is not None
                    and abs((capture_at - entry_at).total_seconds()) <= 5.0
                    and plate_similarity(row.plate, candidate.plate) >= 0.85
                ):
                    cap = candidate
            if cap:
                info = capture_dict(cap)
                body["snapshot_url"] = info.get("snapshot_url")
                body["crop_url"] = info.get("crop_url")
                body["plate_confidence"] = info.get("confidence")
    except Exception:
        pass
    return body

def _side_camera(gate: Gate, side: str) -> Camera | None:
    want = (side or "ENTRY").upper()
    for camera in gate.cameras or []:
        if (camera.lane_direction or "").upper() == want:
            return camera
    return None

def _active_for_plate(db: Session, plate: str) -> ParkingSession | None:
    plate = normalize_plate(plate)
    if not plate:
        return None
    return db.scalar(
        select(ParkingSession)
        .where(ParkingSession.plate == plate, ParkingSession.status.in_(tuple(OPEN_STATUSES)))
        .order_by(ParkingSession.id.desc())
    )

def receipt_text(row: ParkingSession, cfg: dict) -> str:
    from sqlalchemy.orm import object_session
    db = object_session(row)
    local_when = as_site_local(row.entry_time or utcnow(), site_policy(db) if db is not None else None)
    when = local_when.strftime("%Y-%m-%d %H:%M:%S %Z")
    policy = resolve_receipt_policy(cfg)
    wait = "Gate opens only after this receipt is taken.\n" if policy_requires_taken(policy) else "Keep this receipt for payment.\n"
    return (
        f"{app_settings.site_name} receipt\n"
        f"Plate: {row.plate}\n"
        f"Lane: {row.lane_direction}\n"
        f"Entry: {when}\n"
        f"Ref: {row.public_token}\n"
        f"Kind: {getattr(row, 'parker_kind', None) or 'CASUAL'}\n"
        f"{wait}"
    )
