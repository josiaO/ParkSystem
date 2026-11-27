@app.get("/lanes")
def list_lanes(db: Session = Depends(get_db), _: User = Depends(require("cameras.view"))):
    gates = db.scalars(
        select(Gate).options(selectinload(Gate.cameras)).order_by(Gate.id)
    ).all()
    node_gate_id = _processing_node_gate_id(db, required=False)
    from app.services.node_scope import is_processing_node
    if is_processing_node():
        gates = [g for g in gates if node_gate_id is not None and int(g.id) == int(node_gate_id)]
    return [gate_dict(g) for g in gates]


@app.get("/lanes/overview")
def lanes_overview(db: Session = Depends(get_db), _: User = Depends(require("cameras.view"))):
    gates = db.scalars(
        select(Gate).options(selectinload(Gate.cameras)).order_by(Gate.id)
    ).all()
    node_gate_id = _processing_node_gate_id(db, required=False)
    from app.services.node_scope import is_processing_node
    if is_processing_node():
        gates = [g for g in gates if node_gate_id is not None and int(g.id) == int(node_gate_id)]
    camera_ids = [camera.id for gate in gates for camera in (gate.cameras or [])]
    latest_by_camera = latest_for_cameras(db, camera_ids)
    lanes = [_lane_view_dict(db, gate, latest_by_camera) for gate in gates]
    return {"lanes": lanes}


@app.get("/lanes/{gate_id}/view")
def lane_view(gate_id: int, db: Session = Depends(get_db), _: User = Depends(require("cameras.view"))):
    gate = _gate_for_node(db, gate_id, action="lane-view")
    latest_by_camera = latest_for_cameras(db, [camera.id for camera in (gate.cameras or [])])
    return _lane_view_dict(db, gate, latest_by_camera)


@app.get("/captures")
def get_captures(
    gate_id: int | None = None,
    limit: int = 20,
    db: Session = Depends(get_db),
    _: User = Depends(require("cameras.view")),
):
    node_gate_id = _processing_node_gate_id(db, required=False)
    from app.services.node_scope import is_processing_node
    if is_processing_node():
        if node_gate_id is None:
            return []
        if gate_id is not None and int(gate_id) != int(node_gate_id):
            raise HTTPException(403, "A Processing Node can read captures only for its assigned gate.")
        gate_id = node_gate_id
    return [capture_dict(row) for row in list_recent_detections(db, gate_id=gate_id, limit=limit)]


@app.get("/gates/{gate_id}")
def get_gate(gate_id: int, db: Session = Depends(get_db), _: User = Depends(require("gates.view"))):
    return gate_dict(_gate_for_node(db, gate_id, action="gate-view"))


@app.post("/gates")
def create_gate(payload: GateCreate, db: Session = Depends(get_db), user: User = Depends(require("gates.manage"))):
    g = Gate(name=payload.name, mode=validate_gate_mode(payload.mode), enabled=payload.enabled)
    db.add(g)
    commit_or_conflict(db, "A gate with that name already exists")
    db.refresh(g)
    write_audit(db, user, "gate.create", "gate", str(g.id), g.name)
    return gate_dict(g)


@app.patch("/gates/{gate_id}")
def update_gate(gate_id: int, payload: GateUpdate, db: Session = Depends(get_db), user: User = Depends(require("gates.manage"))):
    g = get_gate_or_404(db, gate_id)
    data = payload.model_dump(exclude_unset=True)
    if "mode" in data and data["mode"] is not None:
        data["mode"] = validate_gate_mode(data["mode"])
    for k, v in data.items():
        setattr(g, k, v)
    commit_or_conflict(db, "A gate with that name already exists")
    db.refresh(g)
    write_audit(db, user, "gate.update", "gate", str(g.id), "Gate settings updated")
    return gate_dict(g)


@app.delete("/gates/{gate_id}")
def delete_gate(gate_id: int, db: Session = Depends(get_db), user: User = Depends(require("gates.manage"))):
    g = get_gate_or_404(db, gate_id)
    name = g.name
    for camera in db.scalars(select(Camera).where(Camera.gate_id == gate_id)).all():
        camera.gate_id = None
    db.delete(g)
    db.commit()
    write_audit(db, user, "gate.delete", "gate", str(gate_id), f"Deleted {name}")
    return {"ok": True}


@app.post("/gates/{gate_id}/open")
async def gate_open(gate_id: int, payload: ManualGateCommand, db: Session = Depends(get_db), user: User = Depends(require("gates.open"))):
    def _prepare():
        g = _gate_for_node(db, gate_id, action="gate-open")
        _require_manual_reason(payload)
        from app.services.developer import gate_opening_enabled
        if not gate_opening_enabled(db):
            raise HTTPException(409, "Developer mode has gate opening disabled. No actuator was called.")
        cameras = list(g.cameras or [])
        release_connection(db)
        return g, cameras

    g, cameras = await run_db(_prepare)
    result = await controller().open(
        g, cameras, payload.reason,
        side=payload.side, dry_run=payload.dry_run, led_text=payload.led_text, action=payload.action or "open",
    )

    def _finish():
        if result.ok and not result.simulated and not payload.dry_run:
            g.physical_control_verified = True
        write_audit(db, user, "gate.open", "gate", str(g.id), result.message)
        db.commit()
        _record_manual_open_from_command(db, payload, result, user=user, gate=g, side=payload.side or "")

    await run_db(_finish)
    if not result.ok:
        raise HTTPException(409, result.message)
    return result.__dict__


def _require_manual_reason(payload: ManualGateCommand) -> None:
    """Every manual open must say why; the reason goes into the alert."""
    if (payload.action or "open") == "open" and not payload.dry_run and len((payload.reason or "").strip()) < 3:
        raise HTTPException(400, "A reason (at least 3 characters) is required to open a barrier manually.")


def _record_manual_open_from_command(db: Session, payload: ManualGateCommand, result, *, user: User,
                                     gate: Gate | None = None, camera: Camera | None = None, side: str = "") -> None:
    """Record a manual OPEN (never a close or dry run) with its car, visit and money."""
    if (payload.action or "open") != "open" or payload.dry_run:
        return
    from app.models import MANUAL_SOURCE_CAMERA, MANUAL_SOURCE_GATE
    from app.services.manual_open import safe_record_manual_open

    safe_record_manual_open(
        db,
        source=MANUAL_SOURCE_CAMERA if camera is not None else MANUAL_SOURCE_GATE,
        gate=gate if (gate is not None and gate.id) else None,
        camera=camera,
        side=side,
        user=user,
        reason=payload.reason,
        command_ok=bool(result.ok),
        command_message=result.message or "",
        extra={"simulated": bool(result.simulated)},
    )


@app.post("/cameras/{camera_id}/led")
async def camera_led(camera_id: int, payload: LedWrite, db: Session = Depends(get_db), user: User = Depends(require("gates.open"))):
    def _prepare():
        camera = _camera_for_node(db, camera_id, action="led-write")
        release_connection(db)
        return camera

    camera = await run_db(_prepare)
    result = await send_led_text(camera.display_ip or "", payload.text, dry_run=payload.dry_run)

    def _finish():
        write_audit(db, user, "led.write", "camera", str(camera.id), result.message)
        db.commit()

    await run_db(_finish)
    if not result.ok:
        raise HTTPException(409, result.message)
    return result.__dict__


@app.post("/cameras/{camera_id}/barrier/open")
async def camera_barrier_open(camera_id: int, payload: ManualGateCommand, db: Session = Depends(get_db), user: User = Depends(require("gates.open"))):
    def _prepare():
        camera = _camera_for_node(db, camera_id, action="barrier-open")
        _require_manual_reason(payload)
        from app.services.developer import gate_opening_enabled
        if not gate_opening_enabled(db):
            raise HTTPException(409, "Developer mode has gate opening disabled. No actuator was called.")
        gate = camera.gate or Gate(id=0, name=camera.name)
        release_connection(db)
        return camera, gate

    camera, gate = await run_db(_prepare)
    result = await controller().open(
        gate, [camera], payload.reason,
        dry_run=payload.dry_run, led_text=payload.led_text, action=payload.action or "open",
    )

    def _finish():
        write_audit(db, user, "barrier.open", "camera", str(camera.id), result.message)
        db.commit()
        _record_manual_open_from_command(db, payload, result, user=user, camera=camera, side=camera.lane_direction or "")

    await run_db(_finish)
    if not result.ok:
        raise HTTPException(409, result.message)
    return result.__dict__


def tariff_dict(row: Tariff) -> dict:
    from app.services.fee_engine import tariff_editor
    return {
        "id": row.id, "name": row.name, "car_type": row.car_type, "currency": row.currency,
        "source": row.source, "rules": row.rules, "active": row.active,
        "editor": tariff_editor(row),
    }


def session_dict(row: ParkingSession) -> dict:
    return sim_session_dict(row)


@app.get("/fees/tariff")
def get_fee_tariff(db: Session = Depends(get_db), _: User = Depends(require("fees.view"))):
    row = ensure_car1_tariff(db)
    return tariff_dict(row)


@app.patch("/fees/tariff")
def patch_fee_tariff(
    payload: TariffEditorUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_any("fees.manage", "settings.manage")),
):
    from app.services.fee_engine import apply_tariff_editor
    try:
        row = apply_tariff_editor(db, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    write_audit(db, user, "tariff.update", "tariff", str(row.id), row.name)
    db.commit()
    return tariff_dict(row)


@app.post("/fees/quote")
def fee_quote(payload: FeeQuoteRequest, db: Session = Depends(get_db), _: User = Depends(require("fees.view"))):
    rules = load_active_rules(db, payload.car_type or "Car1")
    # datetime-local controls intentionally omit an offset. Interpret those
    # values in the configured site timezone instead of silently treating
    # them as UTC.
    from app.services.site_policy import as_site_utc, site_policy
    policy = site_policy(db)
    entry_at = as_site_utc(payload.entry_time, policy)
    exit_at = as_site_utc(payload.exit_time, policy) if payload.exit_time else datetime.now(timezone.utc)
    result = calculate_car1_fee(entry_at, exit_at, rules)
    return result.__dict__


@app.post("/sessions")
def open_session(payload: SessionCreate, db: Session = Depends(get_db), user: User = Depends(require("sessions.create"))):
    """Manual entry for a car the cameras missed: same engine as a camera entry."""
    from app.domain.parking_engine import InvalidTransition
    from app.domain.vehicle_groups import GroupOccupied, VisitorPassExhausted
    from app.services.parking_sessions import manual_entry

    camera = db.get(Camera, payload.camera_id) if payload.camera_id else None
    site_id = int((camera.site_id if camera is not None else 0) or DEFAULT_SITE_ID)
    try:
        row = manual_entry(
            db, plate=payload.plate, site_id=site_id,
            gate_id=payload.gate_id or (camera.gate_id if camera else None),
            camera_id=payload.camera_id, lane_id=camera.lane_id if camera else None,
        )
    except GroupOccupied as exc:
        raise HTTPException(409, f"Not allowed: {exc}. Confirm that vehicle's exit first.") from exc
    except VisitorPassExhausted as exc:
        raise HTTPException(409, "The visitor pass for this plate is already used") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except InvalidTransition as exc:
        raise HTTPException(409, str(exc)) from exc
    write_audit(db, user, "session.manual_entry", "parking_session", str(row.id), row.plate)
    db.commit()
    return session_dict(row)


@app.post("/lanes/{camera_id}/entry-fallback")
async def entry_fallback(
    camera_id: int,
    payload: dict = Body(default_factory=dict),
    db: Session = Depends(get_db),
    user: User = Depends(require_any("sessions.create", "gates.open")),
):
    """Operator fallback at an entry when the camera did not capture the car.

    Takes a picture from the entry camera now and forces a plate read on it.
    The plate is, in order: what the operator typed, what the read found, or a
    placeholder (``UNREAD…``) when neither exists, in which case the printed
    ticket's QR is the car's identity at the exit. The visit then goes through
    the normal entry path: session, ticket printing and barrier policy are the
    same as for a camera read. Every use is audited with the picture.
    """
    import secrets as _secrets
    from uuid import uuid4

    from app.application.live_parking import UNREAD_PLATE_PREFIX, handle_operator_entry
    from app.core.plate import apply_site_plate, normalize_plate
    from app.services.captures import _write_jpeg
    from app.services.site_policy import site_policy

    def _prepare():
        c = _camera_for_node(db, camera_id, action="entry-fallback")
        if str(c.lane_direction or "ENTRY").upper() == "EXIT":
            raise HTTPException(409, "This is an exit camera. Use the receipt scanner at the exit.")
        spec = _live_spec(c)
        validation = site_policy(db).get("plate_validation", "NONE")
        release_connection(db)
        return c, spec, validation

    camera, spec, validation = await run_db(_prepare)
    touch_live(spec)
    jpeg = b""
    try:
        grabbed = await snapshot_for_camera(
            spec.id, spec.ip, spec.username, spec.password, spec.rtsp_url,
            sdk_handle=spec.sdk_handle, adapter_id=spec.adapter_id,
        )
        jpeg = (grabbed.get("jpeg") or b"") if grabbed.get("ok") else b""
    except Exception as exc:
        log.warning("entry fallback camera=%s: no picture: %s", camera_id, exc)
    read_plate, read_confidence = "", 0.0
    if jpeg[:2] == b"\xff\xd8":
        try:
            alpr = await _manual_alpr_read(jpeg, camera_label=f"entry-fallback-{camera_id}")
        except HTTPException:
            alpr = {}
        best = (alpr or {}).get("best") or {}
        raw = normalize_plate(best.get("plate_normalized") or best.get("plate") or "")
        if raw:
            read_plate = str(apply_site_plate(raw, validation=validation).get("normalized_plate") or raw)
            read_confidence = float(best.get("confidence") or 0.0)
    typed = normalize_plate(str((payload or {}).get("plate") or ""))
    plate = typed or read_plate or f"{UNREAD_PLATE_PREFIX}{_secrets.token_hex(2).upper()}"
    image_ref = _write_jpeg("snapshots", f"cam{camera_id}-fallback-{uuid4().hex[:12]}.jpg", jpeg) if jpeg[:2] == b"\xff\xd8" else ""

    def _gate():
        return db.get(Gate, camera.gate_id) if camera.gate_id else None

    gate = await run_db(_gate)
    result = await handle_operator_entry(
        db, camera=camera, gate=gate, plate=plate,
        confidence=1.0 if typed else max(read_confidence, 0.5),
        image_ref=image_ref, source="operator-fallback",
    )
    write_audit(db, user, "entry.fallback", "camera", str(camera_id),
                f"plate={plate} typed={typed or '-'} read={read_plate or '-'} ({read_confidence:.2f}) photo={image_ref or '-'}")
    db.commit()
    log.warning("ENTRY FALLBACK camera=%s plate=%s typed=%s read=%s operator=%s",
                camera_id, plate, typed or "-", read_plate or "-", user.username)
    return {
        **(result if isinstance(result, dict) else {}),
        "plate": plate,
        "typed_plate": typed,
        "read_plate": read_plate,
        "read_confidence": read_confidence,
        "placeholder": plate.startswith(UNREAD_PLATE_PREFIX) and not typed and not read_plate,
        "snapshot": image_ref,
    }


@app.post("/sessions/{session_id}/exit")
def close_session(
    session_id: int,
    payload: dict = Body(default_factory=dict),
    db: Session = Depends(get_db),
    user: User = Depends(require("sessions.close")),
):
    """Supervised close of a visit the lane never closed; owed amount is recorded as written off."""
    from app.domain.parking_engine import InvalidTransition
    from app.services.parking_sessions import supervised_close

    row = db.get(ParkingSession, session_id)
    if not row:
        raise HTTPException(404, "Session not found")
    try:
        result = supervised_close(db, row, reason=str((payload or {}).get("reason") or ""), user_id=user.id,
                                  vehicle_left=bool((payload or {}).get("vehicle_left")))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except InvalidTransition as exc:
        raise HTTPException(409, str(exc)) from exc
    write_audit(db, user, "session.supervised_close", "parking_session", str(row.id),
                f"{row.plate} written_off={result['written_off']} {result['currency']}: {(payload or {}).get('reason')}"[:240])
    db.commit()
    return {**session_dict(db.get(ParkingSession, session_id)), **result}


@app.get("/sessions")
def list_sessions(
    limit: int = 100,
    before_id: int | None = None,
    q: str = "",
    status: str = "",
    open_only: bool = False,
    db: Session = Depends(get_db),
    # Not kiosk.use: a kiosk looks up one visit (/sessions/lookup), it does
    # not browse other drivers' visits.
    _: User = Depends(require_any("sessions.view", "fees.view")),
):
    """Newest sessions first, filtered and paged on the server.

    Filtering used to happen in the browser over the newest 100 rows only, so
    on a busy lane older visits (and everything still owing money) fell off the
    list within an hour. ``before_id`` pages further back.
    """
    query = select(ParkingSession)
    needle = "".join(ch for ch in (q or "").upper() if ch.isalnum())
    if needle:
        query = query.where(ParkingSession.plate.contains(needle))
    if status:
        query = query.where(ParkingSession.status == status)
    if open_only:
        query = query.where(ParkingSession.exit_time.is_(None), ParkingSession.status.not_in(("PAID", "CLOSED", "REVOKED")))
    if before_id:
        query = query.where(ParkingSession.id < int(before_id))
    rows = db.scalars(query.order_by(ParkingSession.id.desc()).limit(max(1, min(int(limit or 100), 1000)))).all()
    captures = captures_for_sessions(db, rows)
    out = [sim_session_dict(row, captures.get(int(row.id)), lookup_capture=False) for row in rows]
    _add_live_due(db, rows, out)
    return out


def _add_live_due(db: Session, rows, out: list[dict]) -> None:
    """Amount owed right now for visits still inside (read-only: nothing is saved).

    The stored ``amount_due`` is only written when a fee is quoted (exit, pay
    page), so an open visit otherwise shows TZS 0 however long it has stayed.
    """
    from app.services.fee_engine import calculate_car1_fee, load_active_rules, normalize_tariff_rules

    now = datetime.now(timezone.utc)
    rules_cache: dict = {}
    for row, body in zip(rows, out):
        body["due_now"] = None
        if row.exit_time is not None or (row.status or "").upper() in {"PAID", "CLOSED", "REVOKED"}:
            continue
        if (getattr(row, "parker_kind", "") or "CASUAL").upper() != "CASUAL" or not row.entry_time:
            continue
        try:
            if row.tariff_rules:
                rules = normalize_tariff_rules(row.tariff_rules, car_type=row.car_type or "Car1")
            else:
                key = (row.car_type or "Car1", int(row.site_id or DEFAULT_SITE_ID))
                if key not in rules_cache:
                    rules_cache[key] = load_active_rules(db, key[0], site_id=key[1])
                rules = rules_cache[key]
            fee = calculate_car1_fee(row.entry_time, now, rules)
        except Exception:
            continue
        paid = float(row.amount_paid or 0)
        body["due_now"] = max(0.0, float(fee.due) - paid)
        body["amount_due"] = max(float(body.get("amount_due") or 0), float(fee.due))


@app.get("/sessions/{session_id}/receipt")
def get_session_receipt(session_id: int, db: Session = Depends(get_db), _: User = Depends(require_any("sessions.view", "fees.view", "kiosk.use"))):
    row = db.get(ParkingSession, session_id)
    if not row:
        raise HTTPException(404, "Session not found")
    slip = db.scalar(select(Receipt).where(Receipt.session_id == session_id).order_by(Receipt.id.desc()).limit(1))
    if slip is None:
        raise HTTPException(404, "No receipt for this session")
    return receipt_dict(slip)


@app.get("/sessions/{session_id}/receipt.txt")
def get_session_receipt_text(session_id: int, db: Session = Depends(get_db), _: User = Depends(require_any("sessions.view", "fees.view", "kiosk.use"))):
    row = db.get(ParkingSession, session_id)
    if not row:
        raise HTTPException(404, "Session not found")
    slip = db.scalar(select(Receipt).where(Receipt.session_id == session_id).order_by(Receipt.id.desc()).limit(1))
    if slip is None:
        raise HTTPException(404, "No receipt for this session")
    filename = f"parking-{''.join(ch for ch in (row.plate or str(session_id)) if ch.isalnum()) or session_id}.txt"
    return Response(
        content=slip.body_text or "",
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/sessions/{session_id}/receipt")
async def reprint_session_receipt(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_any("sessions.view", "payments.create", "kiosk.use", "simulation.run")),
):
    def _prepare():
        row = db.get(ParkingSession, session_id)
        if not row:
            raise HTTPException(404, "Session not found")
        gate = db.get(Gate, row.gate_id) if row.gate_id else None
        return row, gate, parking_settings(db)

    row, gate, cfg = await run_db(_prepare)
    issued = await issue_receipt(
        db, row, gate=gate,
        adapter_id=cfg.get("printer_adapter"),
        printer_name=cfg.get("printer_name") or "",
    )

    def _finish():
        write_audit(db, user, "receipt.print", "parking_session", str(row.id), row.plate)
        db.commit()

    await run_db(_finish)
    return issued


@app.get("/settings/parking")
def get_parking_settings(db: Session = Depends(get_db), _: User = Depends(require("simulation.run"))):
    return parking_settings(db)


@app.patch("/settings/parking")
def patch_parking_settings(payload: ParkingSettingsUpdate, db: Session = Depends(get_db), user: User = Depends(require("simulation.run"))):
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    saved = save_parking_settings(db, data)
    write_audit(db, user, "settings.parking", "site", "parking", str(saved))
    db.commit()
    return saved


@app.get("/settings/site")
def get_site_policy(db: Session = Depends(get_db), _: User = Depends(require_any("dashboard.view", "fees.view", "simulation.run"))):
    from app.services.site_policy import site_policy
    return site_policy(db)


@app.get("/settings/clock")
def get_site_clock(db: Session = Depends(get_db), _: User = Depends(require_any("settings.view", "dashboard.view"))):
    from app.services.site_policy import site_clock
    return site_clock(db)


@app.patch("/settings/site")
def patch_site_policy(payload: SitePolicyUpdate, db: Session = Depends(get_db), user: User = Depends(require_any("settings.view", "settings.manage", "simulation.run"))):
    from app.services.site_policy import save_site_policy
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    permissions = user_permissions(user)
    if "*" not in permissions and "settings.manage" not in permissions and "simulation.run" not in permissions:
        allowed = {"timezone", "locale", "language", "date_format", "time_format"}
        forbidden = sorted(set(data) - allowed)
        if forbidden:
            raise HTTPException(403, "Only timezone and display locale can be changed with settings.view")
    try:
        saved = save_site_policy(db, data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    write_audit(db, user, "settings.site", "site", "site", str(saved.get("timezone")))
    return saved


@app.get("/settings/migration")
def get_migration_flags(db: Session = Depends(get_db), _: User = Depends(require("hardware.view"))):
    from app.services.flags import flags as migration_flags
    return migration_flags(db)


@app.patch("/settings/migration")
def patch_migration_flags(payload: MigrationFlagsUpdate, db: Session = Depends(get_db), user: User = Depends(require("hardware.view"))):
    from app.services.flags import save_flags
    saved = save_flags(db, payload.model_dump(exclude_unset=True))
    write_audit(db, user, "settings.migration", "site", "migration", saved.get("live_view_provider") or "")
    return saved


@app.get("/settings/recognition")
def get_recognition_settings(_: User = Depends(require_any("settings.manage", "cameras.manage"))):
    """Settings -> Recognition: camera trigger, two-read limit, receipt photo, camera-area search."""
    from app.services import runtime_settings
    return runtime_settings.all_values()


@app.patch("/settings/recognition")
def patch_recognition_settings(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(require("settings.manage")),
):
    from app.services import runtime_settings
    try:
        changed = runtime_settings.save(db, payload or {})
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    write_audit(db, user, "settings.recognition", "site", "recognition",
                ", ".join(f"{k}={v}" for k, v in sorted(changed.items())))
    db.commit()
    runtime_settings.invalidate()
    return runtime_settings.all_values()


@app.get("/developer/settings")
def get_developer_settings(db: Session = Depends(get_db), _: User = Depends(require("settings.manage"))):
    from app.services.developer import developer_settings
    return developer_settings(db)


@app.patch("/developer/settings")
def patch_developer_settings(
    payload: DeveloperSettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require("settings.manage")),
):
    from app.services.developer import save_developer_settings
    saved = save_developer_settings(db, payload.model_dump(exclude_unset=True))
    # Apply the diagnostic verbosity immediately for the running Site Service;
    # the persisted setting is also visible to worker processes on restart.
    base_level = getattr(logging, str(getattr(settings, "log_level", "INFO") or "INFO").upper(), logging.INFO)
    log.setLevel(logging.DEBUG if saved.get("developer_mode") and saved.get("logging_enabled") else base_level)
    write_audit(db, user, "settings.developer", "site", "developer", str(saved))
    return saved


def _developer_destructive_guard(db: Session) -> None:
    from app.services.developer import destructive_tools_enabled
    if not destructive_tools_enabled(db):
        raise HTTPException(
            409,
            "Enable Developer mode and destructive tools in Developer Playground before deleting test data.",
        )


@app.get("/developer/summary")
def get_developer_summary(db: Session = Depends(get_db), _: User = Depends(require("settings.manage"))):
    from app.services.developer import developer_settings
    tables = {
        "cameras": Camera,
        "gates": Gate,
        "captures": VehicleCapture,
        "sessions": ParkingSession,
        "vehicles": RegisteredVehicle,
        "receipts": Receipt,
        "payments": PaymentTransaction,
        "audit_logs": AuditLog,
    }
    counts = {name: int(db.scalar(select(func.count()).select_from(model)) or 0) for name, model in tables.items()}
    return {"settings": developer_settings(db), "counts": counts}


def _capture_media_path(raw: str):
    """Return a capture media path only for the app's two-component paths."""
    value = str(raw or "").replace("\\", "/").lstrip("/")
    parts = Path(value).parts
    if len(parts) != 2 or parts[0] not in {"snapshots", "crops", "annotated", "alpr", "recognition"}:
        return None
    candidate = settings.media_dir / parts[0] / parts[1]
    try:
        candidate.resolve().relative_to(settings.media_dir.resolve())
    except ValueError:
        return None
    return candidate


def _delete_capture_rows(db: Session, rows: list[VehicleCapture]) -> int:
    removed = 0
    for row in rows:
        for raw in (row.snapshot_path, row.crop_path):
            path = _capture_media_path(raw)
            if path is not None:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
        db.delete(row)
        removed += 1
    return removed


@app.post("/developer/captures/bulk-delete")
def developer_delete_captures(
    payload: DeveloperDeleteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require("settings.manage")),
):
    _developer_destructive_guard(db)
    if not payload.confirm:
        raise HTTPException(400, "Set confirm=true to delete capture evidence.")
    rows = db.scalars(select(VehicleCapture).where(VehicleCapture.id.in_(payload.ids))).all()
    removed = _delete_capture_rows(db, rows)
    write_audit(db, user, "developer.delete", "vehicle_capture", "bulk", f"Deleted {removed} capture(s)")
    db.commit()
    return {"ok": True, "removed": removed}


@app.delete("/developer/captures/{capture_id}")
def developer_delete_capture(
    capture_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require("settings.manage")),
):
    _developer_destructive_guard(db)
    row = db.get(VehicleCapture, capture_id)
    if row is None:
        raise HTTPException(404, "Capture not found")
    _delete_capture_rows(db, [row])
    write_audit(db, user, "developer.delete", "vehicle_capture", str(capture_id), "Deleted capture")
    db.commit()
    return {"ok": True, "removed": 1}


@app.post("/developer/sessions/bulk-delete")
def developer_delete_sessions(
    payload: DeveloperDeleteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require("settings.manage")),
):
    _developer_destructive_guard(db)
    if not payload.confirm:
        raise HTTPException(400, "Set confirm=true to delete sessions and their test ledger rows.")
    rows = db.scalars(select(ParkingSession).where(ParkingSession.id.in_(payload.ids))).all()
    ids = [int(row.id) for row in rows]
    if ids:
        for model in (Receipt, AccessDecision, GateCommandRecord, PaymentTransaction, PaymentIntent, ParkingEntryClaim):
            column = getattr(model, "session_id", None)
            if column is not None:
                for child in db.scalars(select(model).where(column.in_(ids))).all():
                    db.delete(child)
    removed = len(rows)
    for row in rows:
        db.delete(row)
    write_audit(db, user, "developer.delete", "parking_session", "bulk", f"Deleted {removed} session(s)")
    db.commit()
    return {"ok": True, "removed": removed}


@app.delete("/developer/sessions/{session_id}")
def developer_delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require("settings.manage")),
):
    _developer_destructive_guard(db)
    row = db.get(ParkingSession, session_id)
    if row is None:
        raise HTTPException(404, "Session not found")
    for model in (Receipt, AccessDecision, GateCommandRecord, PaymentTransaction, PaymentIntent, ParkingEntryClaim):
        column = getattr(model, "session_id", None)
        if column is not None:
            for child in db.scalars(select(model).where(column == session_id)).all():
                db.delete(child)
    db.delete(row)
    write_audit(db, user, "developer.delete", "parking_session", str(session_id), "Deleted session and test ledger rows")
    db.commit()
    return {"ok": True, "removed": 1}


@app.get("/lanes/status")
def lanes_status(db: Session = Depends(get_db), _: User = Depends(require_any("dashboard.view", "cameras.view", "gates.view"))):
    from app.services.lane_status import lane_operator_status
    return lane_operator_status(db)


@app.post("/cameras/onboard/probe")
async def cameras_onboard_probe(payload: CameraOnboardProbe, _: User = Depends(require("cameras.view"))):
    from app.services.camera_onboard import probe_connection
    return await probe_connection(
        ip=payload.ip_address,
        username=payload.username,
        password=payload.password,
        port=payload.sdk_port,
        rtsp_url=payload.rtsp_url,
    )


@app.post("/cameras/onboard/test")
async def cameras_onboard_test(payload: CameraOnboardTest, _: User = Depends(require("cameras.connect"))):
    from app.services.camera_onboard import test_path
    return await test_path(
        ip=payload.ip_address,
        username=payload.username,
        password=payload.password,
        adapter_id=payload.adapter_id,
        rtsp_url=payload.rtsp_url,
        port=payload.sdk_port,
        duration_seconds=payload.duration_seconds,
    )


@app.post("/sim/entry")
async def sim_entry(payload: SimEntryRequest, db: Session = Depends(get_db), user: User = Depends(require("simulation.run"))):
    _require_development_simulation()
    gate = await run_db(get_gate_or_404, db, payload.gate_id)
    try:
        result = await handle_plate_event(
            db, plate=payload.plate, gate=gate, side=payload.side, simulated=True, source="simulation",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    def _finish():
        write_audit(db, user, "sim.entry", "parking_session", str((result.get("session") or {}).get("id") or ""), payload.plate)
        db.commit()

    await run_db(_finish)
    return result


@app.post("/sim/capture")
async def sim_capture(
    gate_id: int = Form(...),
    side: str = Form("ENTRY"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require("simulation.run")),
):
    _require_development_simulation()
    jpeg = await _read_upload_limited(file)
    if jpeg[:2] != b"\xff\xd8":
        try:
            from io import BytesIO
            from PIL import Image, ImageOps
            image = ImageOps.exif_transpose(Image.open(BytesIO(jpeg))).convert("RGB")
            converted = BytesIO()
            image.save(converted, format="JPEG", quality=92)
            jpeg = converted.getvalue()
        except Exception:
            jpeg = b""
    if jpeg[:2] != b"\xff\xd8":
        raise HTTPException(400, "Upload a JPEG or PNG photo of the car")
    alpr = recognize_frame(jpeg, camera_label=file.filename or "sim-upload")
    best = (alpr or {}).get("best") or {}
    plate = str(best.get("plate") or "").strip()
    if not plate:
        reason = alpr.get("detail") or "FastALPR did not read a number plate in that photo"
        raise HTTPException(
            409,
            f"{reason}. Simulation does not use the cameras — FastALPR reads the plate from the uploaded photo on this PC.",
        )
    def _store():
        gate = get_gate_or_404(db, gate_id)
        camera = None
        want = (side or "ENTRY").upper()
        for row in gate.cameras or []:
            if (row.lane_direction or "").upper() == want:
                camera = row
                break
        stored = None
        if camera is not None:
            box = best.get("bbox") if isinstance(best.get("bbox"), dict) else None
            stored = persist_event(
                db, camera, jpeg=jpeg, crop=_crop_from_alpr(alpr),
                capture={
                    "plate": plate,
                    "plate_raw": str(best.get("plate_raw") or plate),
                    "score": float(best.get("confidence") or 0),
                    "bbox": box,
                    "source": "fastalpr",
                    "plate_crop_path": best.get("plate_crop_path"),
                    "image_id": int(time.time() * 1000) % 2_000_000_000,
                },
            )
            if stored is not None:
                remember_last_car(camera.id, capture_dict(stored))
        return gate, camera, stored

    gate, camera, stored = await run_db(_store)
    try:
        result = await handle_plate_event(
            db, plate=plate, gate=gate, side=side, simulated=True, alpr=alpr,
            source="fastalpr-upload", camera=camera,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    def _finish():
        write_audit(db, user, "sim.capture", "parking_session", str((result.get("session") or {}).get("id") or ""), f"{plate} {side}")
        db.commit()
        return capture_dict(stored) if stored is not None else None

    info = await run_db(_finish)
    if stored is not None:
        session = dict(result.get("session") or {})
        session["snapshot_url"] = session.get("snapshot_url") or info.get("snapshot_url")
        session["crop_url"] = session.get("crop_url") or info.get("crop_url")
        session["plate_confidence"] = session.get("plate_confidence") or info.get("confidence")
        result["session"] = session
        result["capture"] = info
        result["last_car"] = info
    if not result.get("ok") and not result.get("pay_required"):
        raise HTTPException(409, result.get("message") or "Capture failed")
    return result


@app.post("/sim/sessions/{session_id}/receipt-taken")
async def sim_receipt_taken(session_id: int, db: Session = Depends(get_db), user: User = Depends(require_any("simulation.run", "gates.open"))):
    _require_development_simulation()
    row = await run_db(db.get, ParkingSession, session_id)
    if not row:
        raise HTTPException(404, "Session not found")
    taken = await take_receipt(db, row, reason=f"receipt taken {row.plate}")

    def _finish():
        write_audit(db, user, "sim.receipt_taken", "parking_session", str(row.id), row.plate)
        db.commit()

    await run_db(_finish)
    return taken


@app.post("/sessions/{session_id}/receipt-taken")
async def session_receipt_taken(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require("gates.open")),
):
    """Confirm a real entry ticket removal through the authoritative controller.

    Generic printers without a taken sensor fail closed. The simulation endpoint
    remains separate and is never used as production receipt authority.
    """
    from app.application.entry_lane import EntryLaneController, policy_from_parking_settings
    from app.domain.receipt_engine import InvalidPrintJob
    from app.infrastructure.hardware.receipt_printers import receipt_printer_for

    def _prepare():
        row = db.get(ParkingSession, session_id)
        if row is None:
            raise HTTPException(404, "Session not found")
        cfg = parking_settings(db)
        gate = db.get(Gate, row.gate_id) if row.gate_id else None
        camera = db.get(Camera, row.camera_id) if row.camera_id else None
        return row, cfg, gate, camera

    row, cfg, gate, camera = await run_db(_prepare)
    controller = EntryLaneController(
        printer=receipt_printer_for(
            str(cfg.get("printer_adapter") or settings.printer_adapter or "simulated"),
            str(cfg.get("printer_name") or settings.printer_name or ""),
        )
    )
    try:
        result = await controller.confirm_receipt_taken(
            db,
            row,
            policy=policy_from_parking_settings(cfg),
            gate=gate,
            camera=camera,
            sensor_confirmed=False,
        )
    except InvalidPrintJob as exc:
        raise HTTPException(409, str(exc)) from exc
    await run_db(write_audit, db, user, "receipt.taken", "parking_session", str(row.id), "sensor-confirmed path")
    return result


@app.post("/sessions/{session_id}/admit-without-receipt")
async def session_admit_without_receipt(
    session_id: int,
    payload: dict = Body(default_factory=dict),
    db: Session = Depends(get_db),
    user: User = Depends(require("gates.open")),
):
    """Audited operator override for a casual entry waiting on a receipt.

    There is no physical receipt-taken confirmation (no printer, a failed
    printer, or no taken sensor). The operator states a reason; the entry then
    follows the normal authorization and gate path.
    """
    from app.application.entry_lane import EntryLaneController, policy_from_parking_settings
    from app.infrastructure.hardware.receipt_printers import receipt_printer_for

    reason = str((payload or {}).get("reason") or "").strip()
    if len(reason) < 3:
        raise HTTPException(400, "A reason is required to admit a vehicle without a receipt.")
    def _prepare():
        row = db.get(ParkingSession, session_id)
        if row is None:
            raise HTTPException(404, "Session not found")
        gate = db.get(Gate, row.gate_id) if row.gate_id else None
        if gate is not None:
            _gate_for_node(db, gate.id, action="admit-without-receipt")
        cfg = parking_settings(db)
        camera = db.get(Camera, row.camera_id) if row.camera_id else None
        return row, gate, cfg, camera

    row, gate, cfg, camera = await run_db(_prepare)
    controller = EntryLaneController(
        printer=receipt_printer_for(
            str(cfg.get("printer_adapter") or settings.printer_adapter or "simulated"),
            str(cfg.get("printer_name") or settings.printer_name or ""),
        )
    )
    result = await controller.operator_admit_without_receipt(
        db, row, reason=reason, user_id=user.id,
        policy=policy_from_parking_settings(cfg), gate=gate, camera=camera,
    )

    def _finish():
        write_audit(db, user, "receipt.override", "parking_session", str(row.id), f"{row.plate}: {reason}"[:240])
        db.commit()
        # Only when a barrier command was actually issued (accepted or failed);
        # "already open", "in progress" and developer holds open nothing.
        if isinstance(result, dict) and result.get("reason") in {"active", "gate_unavailable"} and gate is not None:
            from app.models import MANUAL_SOURCE_ADMIT
            from app.services.manual_open import safe_record_manual_open

            barrier = result.get("barrier") if isinstance(result.get("barrier"), dict) else {}
            safe_record_manual_open(
                db,
                source=MANUAL_SOURCE_ADMIT,
                gate=gate,
                camera=camera,
                side="ENTRY",
                user=user,
                reason=reason,
                session=db.get(ParkingSession, row.id),
                command_ok=bool(result.get("barrier_command_accepted") or result.get("barrier_opened")),
                command_message=str(barrier.get("message") or result.get("message") or ""),
            )

    await run_db(_finish)
    return result


@app.post("/sessions/{session_id}/correct-plate")
def correct_session_plate(
    session_id: int,
    payload: PlateCorrection,
    db: Session = Depends(get_db),
    user: User = Depends(require_any("gates.open", "sessions.view", "kiosk.use", "simulation.run")),
):
    from app.core.plate import normalize_plate
    from app.services.captures import apply_operator_plate_correction

    row = db.get(ParkingSession, session_id)
    if row is None:
        raise HTTPException(404, "Session not found")
    chosen = normalize_plate(payload.plate)
    if not chosen:
        raise HTTPException(400, "Corrected plate is empty")
    original = row.plate
    row.plate = chosen
    capture = None
    if row.camera_id:
        capture = latest_for_camera(db, row.camera_id)
        if capture and (not capture.plate or capture.plate == original):
            apply_operator_plate_correction(capture, chosen)
    write_audit(db, user, "plate.correct", "parking_session", str(row.id), f"ocr={original} corrected={chosen}")
    db.commit()
    return {"ok": True, "session": sim_session_dict(row), "capture": capture_dict(capture) if capture else None}


@app.post("/sim/sessions/{session_id}/pay")
def sim_pay(session_id: int, db: Session = Depends(get_db), user: User = Depends(require("simulation.run"))):
    _require_development_simulation()
    row = db.get(ParkingSession, session_id)
    if not row:
        raise HTTPException(404, "Session not found")
    try:
        row = mark_paid(db, row, operator_id=user.id, method="KIOSK_CASH")
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    write_audit(db, user, "sim.pay", "parking_session", str(row.id), f"{row.plate} {row.amount_paid}")
    db.commit()
    return sim_session_dict(row)


def _is_kiosk_device(user: User) -> bool:
    return str(getattr(user, "username", "") or "").startswith("kiosk-device:")


def _refuse_cash_on_unattended_kiosk(db: Session, user: User) -> None:
    """An unattended kiosk must not record cash: nobody is there to take it."""
    if _is_kiosk_device(user) and not bool(parking_settings(db).get("kiosk_cash_enabled", True)):
        raise HTTPException(403, "This kiosk is unattended: pay with mobile money or at a staffed desk.")


OPERATOR_PAYMENT_METHODS = {"KIOSK_CASH": "KIOSK_CASH", "CASH": "KIOSK_CASH", "KIOSK": "KIOSK_CASH"}


def _operator_payment_method(method: str | None) -> str:
    """An operator can record cash they received; nothing else.

    Mobile money is credited only by the provider-verified intent flow. A
    free-text method let an operator record "MOBILE_MONEY" without any
    provider proof.
    """
    key = str(method or "KIOSK_CASH").strip().upper()
    if key not in OPERATOR_PAYMENT_METHODS:
        raise HTTPException(400, "Operators can record cash only. Mobile money is confirmed by the payment provider.")
    return OPERATOR_PAYMENT_METHODS[key]


@app.post("/sessions/{session_id}/pay")
def confirm_session_payment(
    session_id: int,
    payload: PaymentConfirm = PaymentConfirm(),
    db: Session = Depends(get_db),
    user: User = Depends(require_any("payments.create", "kiosk.use", "simulation.run")),
):
    _refuse_cash_on_unattended_kiosk(db, user)
    row = db.get(ParkingSession, session_id)
    if not row:
        raise HTTPException(404, "Session not found")
    method = _operator_payment_method(payload.method)
    try:
        row = mark_paid(db, row, operator_id=user.id, method=method)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    write_audit(db, user, "payments.create", "parking_session", str(row.id), f"{row.plate} {row.amount_paid} {method}")
    db.commit()
    return sim_session_dict(row)
