@app.get("/hardware/decode")
async def hardware_decode(_: User = Depends(require("hardware.view"))):
    from app.services.hw_decode import detect_decode_path
    return await detect_decode_path()


async def _sdk_probe_status(c: Camera) -> dict:
    if c.sdk_handle is None:
        return {"handle": None, "status": c.status, "jpeg": False, "note": "SDK Connect first. RTSP is not required."}
    try:
        jpeg = await HVXHostClient().capture_jpeg(int(c.sdk_handle), trigger=True)
    except Exception as exc:
        return {"handle": c.sdk_handle, "status": c.status, "jpeg": False, "error": str(exc)}
    return {
        "handle": c.sdk_handle,
        "status": c.status,
        "jpeg": bool(jpeg),
        "jpeg_bytes": len(jpeg or b""),
        "note": "CONN_STATE_UNKNOW after Net_ConnCameraEx rc=0 is normal on this site.",
    }


# Registered by ``app.api.recognition``; kept here as a compatibility handler
# until the implementation is extracted from this legacy entry point.
def get_alpr_status(_: User = Depends(require("hardware.view"))):
    body = alpr_status()
    body["engines"] = list_engines()
    return body


def camera_recognition_commissioning(
    camera_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require("hardware.view")),
):
    """Side-effect-free recognition/media diagnostics for one camera."""
    from app.services.recognition_commissioning import commissioning_snapshot

    camera = _camera_for_node(db, camera_id, action="recognition-commissioning")
    return commissioning_snapshot(db, camera)


async def camera_recognition_commissioning_read(
    camera_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require("hardware.view")),
):
    """Run one software plate read without creating sessions or controlling gates."""
    from app.services.recognition_commissioning import diagnostic_read

    camera = _camera_for_node(db, camera_id, action="recognition-commissioning-read")
    result = await asyncio.to_thread(diagnostic_read, db, camera)
    write_audit(
        db, user, "camera.recognition_diagnostic", "camera", str(camera.id),
        f"source={result.get('evidence_source')} plate={(result.get('best') or {}).get('plate') if isinstance(result.get('best'), dict) else ''}",
    )
    return result


def get_plate_engine(_: User = Depends(require("cameras.view"))):
    engine = active_engine()
    described = engine.describe()
    described["engines"] = list_engines()
    described["training"] = training_status(engine_id=engine.id)
    described["platform"] = {
        "desktop": "PySide6",
        "windows": True,
        "linux": True,
    }
    return described


def post_plate_correction(
    payload: PlateEngineCorrection,
    _: User = Depends(require("cameras.connect")),
):
    engine = active_engine()
    row = record_correction(
        image_ref=payload.image_ref,
        predicted=payload.predicted,
        corrected=payload.corrected,
        engine_id=engine.id,
        country=payload.country,
    )
    return {"ok": True, "correction": row, "training": training_status(engine_id=engine.id)}


def ai_health(db: Session = Depends(get_db), _: User = Depends(require("hardware.view"))):
    """Optional cloud AI reviewer: disabled by default, never a gate authority."""
    from app.services import ai_review
    return ai_review.health(db)


def ai_recent_reviews(_: User = Depends(require("cameras.view"))):
    from app.services import ai_review
    return {"items": ai_review.recent(), "stats": ai_review.stats()}


async def ai_review_capture(capture_id: int, db: Session = Depends(get_db), user: User = Depends(require("cameras.connect"))):
    """Operator-requested second opinion on a stored capture. Stores the verdict; never edits the plate."""
    from app.services import ai_review
    if not ai_review.enabled(db):
        raise HTTPException(409, "AI review is disabled (SMARTPARK_AI_ENABLED=false)")
    try:
        review = await ai_review.review_capture(db, capture_id)
    except LookupError:
        raise HTTPException(404, "Capture not found")
    write_audit(db, user, "ai.review", "capture", str(capture_id), f"AI verdict {review.verdict}")
    return {"ok": review.verdict != "unavailable", "review": review.as_dict()}


async def ai_incident_summary(payload: AIIncidentSummaryRequest, db: Session = Depends(get_db), _: User = Depends(require("cameras.view"))):
    from app.services import ai_review
    body = await ai_review.summarize_incident(
        db, capture_ids=payload.capture_ids, plate=payload.plate, limit=payload.limit, question=payload.question or "",
    )
    if not body.get("ok") and body.get("reason") == "ai_disabled":
        raise HTTPException(409, "AI review is disabled (SMARTPARK_AI_ENABLED=false)")
    return body


def post_model_pack(
    payload: ModelPackRequest,
    _: User = Depends(require("settings.manage")),
):
    directory = payload.directory.strip()
    if not directory:
        raise HTTPException(400, "directory is required")
    engine = active_engine()
    try:
        applied = apply_model_pack(directory, engine_id=engine.id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return applied


def fuse_plates(payload: FusionRequest, _: User = Depends(require("cameras.connect"))):
    return resolve_readings(
        native_plate=payload.native_plate,
        native_confidence=payload.native_confidence,
        local_plate=payload.local_plate,
        local_confidence=payload.local_confidence,
        operator_plate=payload.operator_plate,
        mode=payload.mode,
    ).as_dict()


async def alpr_recognize_upload(
    file: UploadFile = File(...),
    _: User = Depends(require("cameras.connect")),
):
    jpeg = await _read_upload_limited(file)
    if not jpeg:
        raise HTTPException(400, "Empty image")
    result = await _manual_alpr_read(jpeg, camera_label=file.filename or "upload")
    return result


async def camera_alpr(camera_id: int, db: Session = Depends(get_db), user: User = Depends(require("cameras.connect"))):
    c = _camera_for_node(db, camera_id, action="manual-alpr")
    if await _worker_owns_continuous_reads(c.id):
        # The worker already has the bounded MediaMTX decoder and owns the
        # model session for this camera.  Starting a second detector here is a
        # common cause of stream skips and missed vehicles on Windows.
        raise HTTPException(409, "Continuous recognition owns this camera; use the latest worker result")
    grabbed = await live_snapshot(c)
    if not grabbed.get("ok"):
        write_audit(db, user, "camera.alpr", "camera", str(c.id), grabbed.get("error") or "no frame")
        raise HTTPException(409, grabbed.get("error") or "Could not grab a live frame")
    remember_frame(c.id, grabbed["jpeg"], url=grabbed.get("url") or "", url_redacted=grabbed.get("url_redacted") or "")
    persist_video(db, c, grabbed.get("url"))
    result = await _manual_alpr_read(
        grabbed["jpeg"], camera_label=f"cam-{c.id}-{c.ip_address}",
    )
    native = await _native_capture_for_camera(c)
    local = local_from_fastalpr(result)
    fused = resolve_readings(
        native_plate=native.get("plate") or "",
        native_confidence=float(native.get("confidence") or 0),
        local_plate=local.get("plate") or "",
        local_confidence=float(local.get("confidence") or 0),
        mode=fusion_mode(c),
    )
    result["camera_id"] = c.id
    result["frame"] = {k: v for k, v in grabbed.items() if k not in {"jpeg", "url"}}
    result["native"] = native
    result["local"] = local
    result["fusion"] = fused.as_dict()
    remember_alpr(c.id, result)
    if fused.resolved_plate:
        capture = _capture_from_readings(
            native, local, fused, image_id=int(time.time() * 1000) % 2_000_000_000,
        )
        last = await _persist_capture_event(db, c, capture, grabbed["jpeg"], _crop_from_alpr(result))
        result["last_car"] = last
        result["capture"] = last
    write_audit(db, user, "camera.alpr", "camera", str(c.id), fused.resolved_plate or result.get("detail") or "FastALPR")
    return result
