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



def _upgrade_visit_capture(db: Session, camera: Camera, capture: dict, jpeg: bytes, crop: bytes) -> str | None:
    """Let a better or agreeing read of the same visit replace its held capture.

    Returns the upgrade kind (``consensus`` / ``better`` / ``better_candidate``)
    or None when the stored capture stays as it is.
    """
    from app.services import visit_reads
    from app.services.captures import _plate_jpeg, _write_jpeg

    visit_id = str(capture.get("visit_id") or "")
    row = db.scalar(select(VehicleCapture).where(
        VehicleCapture.camera_id == camera.id, VehicleCapture.visit_id == visit_id))
    if row is None:
        return None
    incoming_plate = str(capture.get("plate") or "").strip().upper()
    kind = visit_reads.plan_upgrade(
        held=visit_reads.row_is_held(row),
        held_plate=str(row.plate or ""),
        held_confidence=float(row.confidence or 0),
        incoming_plate=incoming_plate,
        incoming_confidence=visit_reads.capture_confidence(capture),
        incoming_held=visit_reads.capture_is_held(capture),
    )
    if kind is None:
        return None
    crop_ref = snapshot_ref = ""
    if kind != visit_reads.CONSENSUS:
        stem = f"cam{camera.id}-visit{visit_id[:12]}-{visit_reads.normalize_plate(incoming_plate) or 'plate'}"
        try:
            box = capture.get("bbox") if isinstance(capture.get("bbox"), dict) else None
            plate_jpeg = _plate_jpeg(jpeg or b"", crop or b"", box, capture)
            if plate_jpeg[:2] == b"\xff\xd8":
                crop_ref = _write_jpeg("crops", f"{stem}.jpg", plate_jpeg)
            if (jpeg or b"")[:2] == b"\xff\xd8":
                snapshot_ref = _write_jpeg("snapshots", f"{stem}-car.jpg", jpeg)
        except Exception:
            log.debug("visit upgrade evidence failed camera=%s", camera.id, exc_info=True)
    previous_plate, previous_conf = str(row.plate or ""), float(row.confidence or 0)
    visit_reads.apply_upgrade(row, capture, kind, crop_ref=crop_ref, snapshot_ref=snapshot_ref)
    db.commit()
    log.info("camera=%s visit %s read %s: %s (%.2f) -> %s (%.2f)%s",
             camera.id, visit_id[:12], kind, previous_plate, previous_conf, row.plate,
             float(row.confidence or 0), "" if kind == visit_reads.BETTER_CANDIDATE else "; released for decision")
    return kind


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
    # One capture per visit is enforced by the database. A visit stays open
    # while the lane looks occupied, so a second car that arrives without an
    # empty-lane gap used to inherit the first car's visit: its read was
    # folded into the first car's capture, and the snapshot/crop (and the
    # session evidence shown at the kiosk) stayed on the first car. A clearly
    # different plate (not an OCR slip of it) is a new car: new visit.
    new_plate = str(capture.get("plate") or native_from_sdk_capture(capture).get("plate") or "").strip().upper()
    if capture.get("visit_id") and new_plate:
        visit_id = str(capture["visit_id"])

        def _visit_plate() -> str:
            row = db.scalar(select(VehicleCapture).where(
                VehicleCapture.camera_id == camera.id, VehicleCapture.visit_id == visit_id))
            return str(row.plate or "") if row is not None else ""

        held_plate = (await asyncio.to_thread(_visit_plate)).strip().upper()
        from app.services.lane_stay import different_vehicle
        if held_plate and different_vehicle(held_plate, new_plate):
            lane.visit.reset(time.monotonic())
            lane.visit.observe(presence=True, plate=new_plate, native_event=True)
            capture["visit_id"] = lane.visit.visit_id
            log.info("camera=%s new car %s while visit %s still held %s: new visit %s",
                     camera.id, new_plate, visit_id[:12], held_plate, capture["visit_id"][:12])
    # Same car read again (same visit): the best read wins. A held first read
    # (usually the 704 px live frame) must not swallow the camera's better
    # full-resolution read of the same car. See app/services/visit_reads.py.
    visit_upgrade = None
    if capture.get("visit_id") and new_plate:
        visit_upgrade = await asyncio.to_thread(_upgrade_visit_capture, db, camera, capture, jpeg, crop)
        if visit_upgrade in {"consensus", "better"}:
            capture["needs_review"] = False
            capture["pending_confirmation"] = False
    started_ns = time.perf_counter_ns()
    previous = latest_for_camera(db, camera.id)
    previous_id = previous.id if previous else None
    previous_plate = str(previous.plate or "") if previous else ""
    # The INSERT runs off the event loop (it also carries live video, gate
    # commands and the other lane). This coroutine owns ``db`` and waits here,
    # so the session is used by one thread at a time; duplicate events are
    # still resolved by the unique capture keys. The photos (zone snapshot,
    # plate crop) are produced after the decision by app.services.evidence.
    persist_started_ns = time.perf_counter_ns()
    row = await asyncio.to_thread(
        persist_event,
        db, camera, jpeg=jpeg, crop=crop, capture=capture,
        coil_occupied=coil_watch.occupied(camera.id),
        defer_evidence=True,
    )
    persisted_ns = time.perf_counter_ns()
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
    new_capture = bool(row and (
        row.id != previous_id or row.plate != previous_plate
        # A held read of this visit was released by a better or agreeing read:
        # this is the first time the car can be decided.
        or visit_upgrade in {"consensus", "better"}
    ))
    # Fuzzy OCR correction is for operator assistance only.  Automatic
    # barrier authority requires an exact normalized registered plate.
    entitlement = lookup_entitlement(db, row.plate, site_id=camera.site_id, strict=True) if row and row.plate else None
    registered_auto = bool(
        entitlement and entitlement.registered and entitlement.auto_open
    )
    gate = None
    if camera.gate_id:
        gate = db.get(Gate, camera.gate_id)
    # A camera without an explicit gate never drives a barrier. Silently
    # binding it to the only gate (the previous behaviour) attached exit or
    # test cameras to the entry barrier as soon as one gate existed.
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
            try:
                # Splits "plate read -> parking controller" into the capture
                # save and the lookups after it (tools/critical_path_report.py).
                from app.core import latency_trace

                now_ns = time.perf_counter_ns()
                latency_trace.emit(
                    "capture.pre_decision", camera=camera.id, visit_id=str(getattr(row, "visit_id", "") or ""),
                    prefetch_ms=round((persist_started_ns - started_ns) / 1e6, 1),
                    persist_ms=round((persisted_ns - persist_started_ns) / 1e6, 1),
                    lookups_ms=round((now_ns - persisted_ns) / 1e6, 1),
                    total_ms=round((now_ns - started_ns) / 1e6, 1),
                    evidence_deferred=str(getattr(row, "evidence_state", "") or "") == "PENDING",
                )
            except Exception:
                pass
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
