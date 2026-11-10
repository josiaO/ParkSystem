@app.get("/gates")
def list_gates(db: Session = Depends(get_db), _: User = Depends(require("gates.view"))):
    rows = [gate_dict(g) for g in db.scalars(
        select(Gate).options(selectinload(Gate.cameras)).order_by(Gate.id)
    ).all()]
    from app.services.node_scope import is_processing_node
    node_gate_id = _processing_node_gate_id(db, required=False)
    if is_processing_node():
        # Gate names/IDs are read-only site metadata needed for assignment;
        # foreign camera details are not exposed to a Processing Node.
        for row in rows:
            if node_gate_id is None or int(row.get("id") or 0) != node_gate_id:
                row["cameras"] = []
    return rows


@app.get("/runtime/recognition-scope")
def get_recognition_scope(db: Session = Depends(get_db), _: User = Depends(require("cameras.view"))):
    from app.services.node_scope import describe_recognition_scope
    return describe_recognition_scope(db)


@app.put("/runtime/recognition-owner")
def put_recognition_owner(
    payload: RecognitionScopeUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require("settings.manage", processing_node_allowed=True)),
):
    """Explicit administrator assignment; browsing video never changes ownership."""
    from app.services.node_scope import authoritative_node_gate_ids, env_recognition_gate_id, node_registry_present, set_recognition_gate_id
    pinned = env_recognition_gate_id()
    if pinned is not None and payload.gate_id != pinned:
        raise HTTPException(409, "This computer is pinned by SMARTPARK_RECOGNITION_GATE_ID.")
    if payload.gate_id is None or payload.gate_id <= 0:
        raise HTTPException(422, "Assign this PC to one gate with entry and exit cameras.")
    assigned = authoritative_node_gate_ids(db)
    if node_registry_present(db) and (not assigned or int(payload.gate_id) not in assigned):
        raise HTTPException(409, "This node's gate assignment is controlled centrally by the Site Server.")
    if db.get(Gate, payload.gate_id) is None:
        raise HTTPException(404, "Gate not found")
    body = set_recognition_gate_id(payload.gate_id, db)
    write_audit(db, user, "recognition.owner", "gate", str(payload.gate_id), body.get("detail") or "")
    return body


@app.post("/runtime/recognition-scope")
def post_recognition_scope(
    payload: RecognitionScopeUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_any("cameras.connect", "cameras.manage", "gates.view")),
):
    """This PC processes one gate's entry+exit. Other gates stay idle until chosen."""
    from app.services.node_scope import authoritative_node_gate_ids, env_recognition_gate_id, node_registry_present, set_recognition_gate_id
    if settings.deployment_profile == "PRODUCTION":
        raise HTTPException(409, "Production ownership is configured by SMARTPARK_RECOGNITION_GATE_ID or the persisted node setting, not the browser lane selector.")
    if env_recognition_gate_id() is not None and payload.gate_id not in (None, env_recognition_gate_id()):
        raise HTTPException(409, "This computer is pinned to one gate by SMARTPARK_RECOGNITION_GATE_ID.")
    assigned = authoritative_node_gate_ids(db)
    if node_registry_present(db) and payload.gate_id not in (None, *assigned):
        raise HTTPException(409, "This node's gate assignment is controlled centrally by the Site Server.")
    if payload.gate_id is not None:
        gate = db.get(Gate, int(payload.gate_id))
        if gate is None:
            raise HTTPException(404, "Gate not found")
    body = set_recognition_gate_id(payload.gate_id, db)
    write_audit(db, user, "recognition.scope", "gate", str(payload.gate_id or ""), body.get("detail") or "")
    return body



async def _persist_capture_event(db: Session, camera: Camera, capture: dict | None, jpeg: bytes, crop: bytes) -> dict | None:
    from app.services.node_scope import camera_active_on_this_installation
    if not camera_active_on_this_installation(camera, db=db):
        return None
    from app.services.recognition_runtime import runtime
    lane = runtime.lane(int(camera.id))
    capture = dict(capture or {})
    incoming_visit_id = str(capture.get("visit_id") or "").strip()
    if incoming_visit_id and incoming_visit_id != lane.visit.visit_id:
        # Recognition Worker and Site Service maintain separate in-memory
        # lanes. The worker's visit identity is authoritative at this
        # boundary; otherwise a new car can be rejected because Site Service
        # still marks the previous car as EVENT_PUBLISHED.
        lane.visit.adopt_visit(incoming_visit_id)
    if not capture.get("visit_id"):
        lane.visit.observe(presence=True, native_event=True)
        capture["visit_id"] = lane.visit.visit_id
    previous = latest_for_camera(db, camera.id)
    previous_id = previous.id if previous else None
    previous_plate = str(previous.plate or "") if previous else ""
    row = persist_event(
        db, camera, jpeg=jpeg, crop=crop, capture=capture,
        coil_occupied=coil_watch.occupied(camera.id),
    )
    if row is None:
        return capture_dict(previous) if previous else None
    latest = row or previous
    if row is not None:
        from app.services.recognition_runtime import runtime
        lane = runtime.lane(int(camera.id))
        visit_id = str((capture or {}).get("visit_id") or lane.visit.visit_id or "")
        if visit_id and not getattr(row, "visit_id", ""):
            row.visit_id = visit_id
            db.commit()
        if row.plate:
            lane.visit.observe(presence=True, plate=str(row.plate or ""), native_event=True)
            if not lane.visit.mark_published(str(row.plate or "")):
                lane.note_duplicate()
            else:
                lane.note_published()
            remember_last_car(camera.id, capture_dict(row))
        else:
            remember_last_car(camera.id, None)
    elif latest is None:
        remember_last_car(camera.id, None)
    if row is not None and row.id != previous_id:
        # Optional cloud second opinion: background task, never on the gate path.
        from app.services import ai_review
        ai_review.schedule_capture_review(capture_dict(row), crop=crop, jpeg=jpeg, db=db)
    from app.services.modules import is_enabled
    if not is_enabled("parking.sessions", db):
        return capture_dict(latest) if latest else None
    side = (camera.lane_direction or "ENTRY").upper()
    new_capture = bool(row and (row.id != previous_id or row.plate != previous_plate))
    # Fuzzy OCR correction is for operator assistance only.  Automatic
    # barrier authority requires an exact normalized registered plate.
    entitlement = lookup_entitlement(db, row.plate, site_id=camera.site_id, strict=True) if row and row.plate else None
    registered_auto = bool(
        entitlement and entitlement.registered and entitlement.auto_open
    )
    gate = None
    if camera.gate_id:
        gate = db.get(Gate, camera.gate_id)
    elif row and row.plate:
        # Auto-link only when the site has a single enabled lane (unambiguous).
        gates = list(db.scalars(select(Gate).where(Gate.enabled == True).order_by(Gate.id)).all())
        if len(gates) == 1:
            gate = gates[0]
            if camera.gate_id is None:
                camera.gate_id = gate.id
                db.commit()
    needs_session = False
    if row and row.plate and side == "ENTRY":
        from app.services.parking_sessions import active_for_plate
        needs_session = active_for_plate(db, row.plate, site_id=camera.site_id) is None
    from app.core.plate import apply_site_plate
    hold = bool((capture or {}).get("needs_review") or (capture or {}).get("pending_confirmation"))
    if row and row.plate:
        assessed = apply_site_plate(row.plate, validation=site_policy(db).get("plate_validation", "NONE"))
        if assessed.get("hold_for_operator"):
            hold = True
    if latest and hold:
        payload = capture_dict(latest)
        payload["pending_confirmation"] = True
        payload["needs_review"] = True
        remember_last_car(camera.id, payload)
        if isinstance(row.bbox, dict):
            row.bbox = {**row.bbox, "pending_confirmation": True, "needs_review": True}
            db.commit()
    # Plate-first: create/update parking sessions even when the camera has no Gate.
    # Barrier open still needs a gate; the session (plate + receipt token) does not.
    should_handle = bool(
        row and row.plate and not hold
        # Do not route the same persisted exit visit through the controller on
        # every repeated native callback. A new visit/capture is sufficient to
        # trigger exit handling; repeated reads stay display-only.
        and (new_capture or registered_auto or needs_session)
    )
    if should_handle:
        from app.services.dedup import camera_events
        image_id = int(getattr(row, "image_id", 0) or 0)
        dedupe_id = image_id or int(row.id or 0)
        if camera_events.seen(camera_id=camera.id, plate=row.plate, image_id=dedupe_id):
            return capture_dict(latest) if latest else None
        try:
            source_name = str((capture or {}).get("source") or "camera")
            # Printing/payment/gate control may await hardware or a provider.
            # Commit the capture checkpoint before entering that external path.
            release_connection(db)
            if side == "ENTRY":
                from app.application.live_parking import handle_live_entry
                result = await handle_live_entry(
                    db, camera=camera, capture=row, gate=gate, source=source_name,
                )
                from app.services.recognition_runtime import runtime
                if result.get("created_session"):
                    runtime.lane(int(camera.id)).note_session_created()
            else:
                from app.application.live_parking import handle_live_exit
                result = await handle_live_exit(
                    db, camera=camera, capture=row, gate=gate, source=source_name,
                )
            log.info(
                "plate event decision camera_id=%s side=%s plate=%s capture_id=%s "
                "reason=%s barrier_opened=%s session_id=%s message=%s",
                camera.id,
                side,
                row.plate,
                row.id,
                result.get("reason") if isinstance(result, dict) else "",
                result.get("barrier_opened") if isinstance(result, dict) else False,
                ((result.get("session") or {}).get("id") if isinstance(result, dict) else None),
                result.get("message") if isinstance(result, dict) else "",
            )
            if result.get("session") and latest:
                session_id = (result["session"] or {}).get("id")
                if session_id:
                    session_row = db.get(ParkingSession, session_id)
                    if session_row is not None:
                        if not session_row.camera_id:
                            session_row.camera_id = camera.id
                        if gate is None:
                            camera.last_error = (
                                f"Session saved for {row.plate} (no Gate on camera — "
                                "assign a lane/gate to enable barrier control)."
                            )
                        elif camera.last_error and "no Gate" in (camera.last_error or ""):
                            camera.last_error = ""
                        db.commit()
        except Exception as exc:
            from app.services.health import note_worker_failure
            from app.services.queues import parking_outbox
            note_worker_failure("plate-event", str(exc))
            parking_outbox().enqueue("plate-event", {
                "plate": row.plate,
                "gate_id": gate.id if gate else None,
                "side": side,
                "camera_id": camera.id,
                "capture_id": row.id,
            })
    return capture_dict(latest) if latest else None
