from __future__ import annotations

def create_entry(
    db: Session,
    *,
    plate: str,
    gate: Gate | None,
    side: str,
    simulated: bool = False,
    entitlement: Entitlement | None = None,
    status: str = "WAITING_RECEIPT",
    receipt_status: str = "PRINTED",
    camera: Camera | None = None,
) -> ParkingSession:
    plate = normalize_plate(plate)
    if not plate:
        raise ValueError("Enter a number plate")
    existing = _active_for_plate(db, plate)
    if existing:
        if camera is not None and not existing.camera_id:
            existing.camera_id = camera.id
            db.commit()
            db.refresh(existing)
        return existing
    if camera is None and gate is not None:
        camera = _side_camera(gate, side)
    token, human = _allocate_identity(db)
    tariff = ensure_car1_tariff(db)
    entitlement = entitlement or Entitlement(plate=plate)
    site_id = getattr(gate, "site_id", None) or DEFAULT_SITE_ID
    row = ParkingSession(
        site_id=site_id,
        plate=plate,
        plate_raw=plate,
        gate_id=gate.id if gate else None,
        camera_id=camera.id if camera else None,
        lane_direction=(side or "ENTRY").upper(),
        status=status,
        receipt_status=receipt_status,
        public_token=token,
        human_reference=human,
        simulated=bool(simulated),
        currency=(tariff.currency if tariff else "TZS"),
        parker_kind=entitlement.kind if entitlement.registered else "CASUAL",
        access_plan_id=entitlement.plan_id,
        vehicle_id=entitlement.vehicle_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

def _attach_latency(result: dict, started: float) -> dict:
    result["latency_ms"] = int((time.perf_counter() - started) * 1000)
    return result

def _finish_entry(
    db: Session,
    result: dict,
    row: ParkingSession,
    gate: Gate | None,
    started: float,
    outcome: str,
) -> dict:
    token = row.public_token or ""
    if token:
        result["public_token"] = result.get("public_token") or token
        result["qr_url"] = result.get("qr_url") or f"/p/{token}/qr.png"
        result["qr_payload"] = result.get("qr_payload") or session_qr_payload(token)
    _attach_latency(result, started)
    record_access_decision(
        db,
        session=row,
        plate=row.plate,
        gate=gate,
        lane_direction=row.lane_direction or "ENTRY",
        outcome=outcome,
        reason=str(result.get("message") or ""),
        parker_kind=getattr(row, "parker_kind", None) or "CASUAL",
        barrier_opened=bool(result.get("barrier_opened")),
        latency_ms=int(result.get("latency_ms") or 0),
    )
    return result
