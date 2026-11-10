def _plate_payload(camera: Camera, native: dict, alpr: dict | None, db: Session | None = None) -> dict:
    from app.services.flags import native_alpr_enabled
    from app.services.ocr_policy import LOCAL_ONLY, camera_recognition_mode
    from app.services.recognition_runtime import IDLE, runtime
    from app.infrastructure.media.registry import live_provider_label
    from app.services.preview import viewer_live_provider
    state = get_state(camera.id)
    if alpr is state.alpr:
        alpr = fresh_alpr(camera.id)
    if camera_recognition_mode(camera) == LOCAL_ONLY:
        native = {}
    elif not native_alpr_enabled():
        native = {**(native or {}), "plate": "", "confidence": 0.0}
    local = local_from_fastalpr(alpr)
    fused = resolve_readings(
        native_plate=native.get("plate") or "",
        native_confidence=float(native.get("confidence") or 0),
        local_plate=local.get("plate") or "",
        local_confidence=float(local.get("confidence") or 0),
        mode=fusion_mode(camera),
    )
    fresh_overlay = choose_overlay_box(native, None)
    if fresh_overlay:
        remember_plate_box(camera.id, fresh_overlay)
    live = state
    lane = runtime.lane(camera.id)
    rec = lane.snapshot()
    # Keep evidence during an active visit. Cached display data cannot
    # establish occupancy: only current recognition, coil or native evidence can.
    last = fresh_last_car(camera.id)
    held_box = held_plate_box(camera.id)
    occupied = bool(
        rec.get("vehicle_present")
        or coil_watch.occupied(camera.id)
        or (native or {}).get("have_vehicle")
        or fresh_overlay
    )
    overlay = live_plate_overlay(
        native, local, held_box, occupied=occupied,
    )
    if not occupied:
        last = None
        remember_last_car(camera.id, None)
        remember_plate_box(camera.id, None)
    current_plate = str((last or {}).get("plate") or rec.get("last_plate") or "")
    fused_dict = fused.as_dict()
    if not occupied:
        current_plate = ""
        fused_dict["resolved_plate"] = ""
    else:
        current_plate = current_plate or str(fused_dict.get("resolved_plate") or "")
    viewer = viewer_live_provider(camera.id)
    current_video = live_is_current(camera.id)
    live_endpoint = {
        "provider": live.source or "",
        "transport": "MJPEG" if current_video else "",
        "state": "LIVE" if current_video else "OFFLINE",
        "viewer_transport": viewer,
    }
    return {
        "camera": camera_dict(camera),
        "native": native if occupied else {**(native or {}), "plate": "", "confidence": 0.0},
        "local": local if occupied else {},
        "fusion": fused_dict,
        "alpr": alpr if occupied else None,
        "resolved_plate": current_plate,
        "current_plate": current_plate or None,
        "overlay": overlay,
        "plate_crop_url": (
            (last or {}).get("crop_url")
            or ((alpr or {}).get("best") or {}).get("crop_url")
        ) if occupied else None,
        "last_car": last,
        "clear_last_car": not occupied,
        "vehicle_present": occupied,
        "recognition_state": rec.get("recognition_state") or IDLE,
        "visit_id": rec.get("visit_id") or "",
        "live": current_video,
        "error": None if current_video else "Waiting for fresh live video. Recognition evidence is shown separately.",
        "live_source": live.source,
        "live_fps": live.fps,
        "url_redacted": live.url_redacted,
        "live_frame_age_ms": (time.monotonic() - live.captured_at) * 1000 if live.captured_at else None,
        "live_provider": live_provider_label({**live_endpoint, "viewer_transport": viewer}) if viewer else live_provider_label(live_endpoint),
        "media": _camera_media_brief(camera.id),
        "recognition": rec,
    }


_local_alpr_at: dict[int, float] = {}
_alpr_fp: dict[int, int] = {}
_detect_at: dict[int, float] = {}


def _coil_indexes(camera_id: int | None = None) -> list[int]:
    learned = coil_watch.learned_index(camera_id) if camera_id is not None else None
    if learned is not None:
        return [learned]
    raw = str(getattr(settings, "coil_poll_indexes", "1,2,3,4,5,6,7") or "1,2,3,4,5,6,7")
    indexes: list[int] = []
    barrier = int(getattr(settings, "gpio_index", 0) or 0)
    for part in raw.split(","):
        part = part.strip()
        if not part.isdigit():
            continue
        value = int(part)
        if value == barrier:
            continue
        if value not in indexes:
            indexes.append(value)
    default = int(getattr(settings, "coil_gpio_index", 1) or 1)
    if default != barrier and default not in indexes:
        indexes.insert(0, default)
    return indexes or [1]


def _local_alpr_due(camera_id: int) -> bool:
    wait = float(getattr(settings, "local_alpr_cooldown_seconds", 2.0) or 2.0)
    return time.monotonic() - _local_alpr_at.get(camera_id, 0.0) >= wait


def _mark_local_alpr(camera_id: int) -> None:
    _local_alpr_at[camera_id] = time.monotonic()


def _detect_due(camera_id: int) -> bool:
    """Detector cadence while a live picture is open. OCR stays on the still crop."""
    return time.monotonic() - _detect_at.get(int(camera_id), 0.0) >= 0.5


def _mark_detect(camera_id: int) -> None:
    _detect_at[int(camera_id)] = time.monotonic()


def _local_alpr_ready(camera_id: int) -> bool:
    """True when this camera may start OCR. Does not consume the cooldown."""
    return _local_alpr_due(camera_id)


def _crop_from_alpr(alpr: dict | None, jpeg: bytes = b"") -> bytes:
    best = (alpr or {}).get("best") or {}
    rel = best.get("plate_crop_path")
    if not rel:
        from app.services.captures import _crop_from_bbox
        return _crop_from_bbox(jpeg, best.get("bbox")) if jpeg else b""
    path = settings.media_dir / rel.replace("\\", "/")
    try:
        data = path.read_bytes()
    except Exception:
        return b""
    return data if data[:2] == b"\xff\xd8" else b""


def _capture_from_readings(native: dict, local: dict, fused, *, image_id: int = 0, pending: bool = False) -> dict:
    from app.services.camera_lpr import capture_from_readings

    return capture_from_readings(native, local, fused, image_id=image_id, pending=pending)


async def _run_local_alpr(
    db: Session,
    camera: Camera,
    jpeg: bytes,
    *,
    native: dict | None = None,
    presence: bool = True,
    image_id: int = 0,
    force: bool = False,
    plate_crop: bytes = b"",
) -> dict | None:
    jpeg = jpeg or b""
    if jpeg[:2] != b"\xff\xd8":
        return None
    pending = _local_alpr_pending.get(int(camera.id))
    if pending is not None and not pending.done():
        return {"ok": False, "backend": "fastalpr", "error": "busy", "detail": "recognition already running"}
    if pending is not None and pending.done():
        _local_alpr_pending.pop(int(camera.id), None)
    native = native or {}
    from app.services.ocr_policy import LOCAL_ONLY, camera_recognition_mode
    if camera_recognition_mode(camera) == LOCAL_ONLY:
        native = {}
        plate_crop = b""
    from app.services.node_scope import camera_active_on_this_installation
    if not force and not camera_active_on_this_installation(camera, db=db):
        return None
    if not should_run_local(
        native_plate=str(native.get("plate") or ""),
        native_confidence=float(native.get("confidence") or 0),
        explicit=force,
        presence=presence,
        native_plates=adapter_has_native_plates(camera),
        camera=camera,
    ):
        return None
    from app.services.recognition_runtime import runtime
    runtime.offer_frame(int(camera.id), jpeg, source="site-alpr")
    if not force and not _local_alpr_ready(camera.id):
        return None
    from app.domain.recognition_engine import policy_from_settings
    stale_frame_ms = policy_from_settings().stale_frame_ms
    ticket = runtime.begin_if_idle(int(camera.id), stale_frame_ms=stale_frame_ms)
    if ticket is None:
        return None
    _mark_local_alpr(camera.id)
    # OCR is native/CPU work and may take several seconds. Do not keep the
    # caller's PostgreSQL connection checked out while the inference task runs.
    release_connection(db)
    jpeg = ticket.jpeg or jpeg
    abandon = asyncio.Event()
    work = asyncio.create_task(_run_local_alpr_locked(
        db, camera, jpeg, native=native, presence=presence, image_id=image_id,
        force=force, plate_crop=plate_crop, ticket=ticket, abandon=abandon,
    ))
    _local_alpr_pending[int(camera.id)] = work
    try:
        alpr = await asyncio.wait_for(
            asyncio.shield(work),
            timeout=float(getattr(settings, "alpr_timeout_seconds", 15.0) or 15.0),
        )
        return alpr
    except asyncio.CancelledError:
        if not work.done():
            await work
        runtime.finish(ticket, plate="")
        raise
    except asyncio.TimeoutError:
        # The native thread continues in the background, but this camera is
        # explicitly marked busy until that task drains. No duplicate ONNX
        # call or stale result is admitted for the same lane.
        abandon.set()
        work.add_done_callback(_consume_background_task)
        runtime.recover(int(camera.id))
        runtime.lane(int(camera.id)).last_error = "FastALPR crop recognition timed out."
        from app.services.health import note_worker_failure
        note_worker_failure("alpr", f"camera {camera.id} recognition timed out")
        return {"ok": False, "backend": "fastalpr", "plates": [], "detail": "recognition timeout", "error": "timeout"}
    except Exception as exc:
        runtime.finish(ticket, plate="")
        runtime.lane(int(camera.id)).last_error = redact_text(str(exc))
        from app.services.health import note_worker_failure
        note_worker_failure("alpr", str(exc))
        return {"ok": False, "backend": "fastalpr", "plates": [], "detail": str(exc), "error": str(exc)}
    finally:
        if work.done() and _local_alpr_pending.get(int(camera.id)) is work:
            _local_alpr_pending.pop(int(camera.id), None)


def _alpr_busy() -> bool:
    from app.services.recognition_runtime import runtime
    snap = runtime.scheduler.snapshot()
    return int(snap.get("inflight") or 0) >= int(snap.get("max_concurrency") or getattr(settings, "recognition_max_concurrency", 4) or 4)


def _alpr_enter() -> None:
    _alpr_inflight["n"] = int(_alpr_inflight["n"]) + 1


def _alpr_leave() -> None:
    _alpr_inflight["n"] = max(0, int(_alpr_inflight["n"]) - 1)


_alpr_inflight = {"n": 0}


async def _run_local_alpr_locked(
    db: Session,
    camera: Camera,
    jpeg: bytes,
    *,
    native: dict | None = None,
    presence: bool = True,
    image_id: int = 0,
    force: bool = False,
    plate_crop: bytes = b"",
    ticket=None,
    abandon: asyncio.Event | None = None,
) -> dict | None:
    from app.services.inference_thread import run_inference
    native = native or {}
    from app.services.media_gateway import gateway
    from app.services.queues import AI_FRAMES
    from app.services.recognition_runtime import runtime
    from app.domain.recognition_engine import policy_from_settings
    stale_frame_ms = policy_from_settings().stale_frame_ms
    sample = gateway.peek_detect(camera.id)
    if sample:
        AI_FRAMES.put((camera.id, sample.seq))
    started = time.perf_counter()
    from app.services.alpr import recognize_arrival_bytes, recognize_plate_crop_bytes
    from app.services.camera_framing import framing_from_profiles, native_plate_region_to_roi
    framing = framing_from_profiles(getattr(camera, "stream_profiles", None))
    # ParkWatch/OcxConfig's polygon is the camera-side zone.  Use it only when
    # the operator has not explicitly saved an application ROI; this keeps the
    # native camera configuration useful without silently overriding settings.
    native_roi = native_plate_region_to_roi(
        native.get("plate_region"),
        image_width=int(native.get("image_width") or 0),
        image_height=int(native.get("image_height") or 0),
    )
    effective_roi = framing["detect_roi"] or native_roi or None
    from app.services.camera_framing import gate_for
    prepared = gate_for(int(camera.id)).prepared
    boxes = prepared[1] if prepared and prepared[0] == hash(jpeg) else None
    native_box = None
    if isinstance(native.get("bbox"), dict):
        native_box = fit_plate_box(
            {**native["bbox"], "image_width": native.get("image_width") or 0, "image_height": native.get("image_height") or 0},
            jpeg,
            src_w=int(native.get("image_width") or 0),
            src_h=int(native.get("image_height") or 0),
        )
    # A native usLpBox is a useful fallback, but it is not trusted as the
    # primary FastALPR crop.  The panorama detector runs inside this one
    # recognition call and only uses the native box if it finds no current box.
    if boxes:
        alpr = await run_inference(
            recognize_arrival_bytes, jpeg,
            camera_label=f"cam-{camera.id}-{camera.ip_address}",
            detect_roi=effective_roi,
            detect_zoom=framing["detect_zoom"],
            detected_boxes=boxes,
            fallback_box=native_box,
        )
    else:
        alpr = await run_inference(
            recognize_arrival_bytes, jpeg,
            camera_label=f"cam-{camera.id}-{camera.ip_address}",
            detect_roi=effective_roi,
            detect_zoom=framing["detect_zoom"],
            fallback_box=native_box,
        )
    if not (alpr or {}).get("best") and plate_crop[:2] == b"\xff\xd8":
        # The SDK vehicle-picture buffer is a last-resort source only when the
        # full panorama detector is unavailable; never prefer it over the
        # current full panorama.
        crop_result = await run_inference(
            recognize_plate_crop_bytes,
            plate_crop,
            camera_label=f"cam-{camera.id}-{camera.ip_address}-native-crop",
        )
        if crop_result.get("best") or not (alpr or {}).get("ok", True):
            alpr = crop_result
    if not alpr:
        alpr = {"ok": True, "backend": "fastalpr", "plates": [], "best": None,
                "detail": "no plate box in the current panorama"}
    # A timed-out API request may outlive its dependency-scoped SQLAlchemy
    # session while this native call drains. Do not touch the closed session,
    # persist a late result, or update lane state from an abandoned task.
    if abandon is not None and abandon.is_set():
        return {"ok": False, "backend": "fastalpr", "error": "timeout", "detail": "recognition timeout"}
    gateway.note_ai_sample(camera.id, infer_ms=(time.perf_counter() - started) * 1000, dropped=False)
    if alpr.get("ok") is False:
        runtime.lane(int(camera.id)).last_error = redact_text(str(alpr.get("detail") or "FastALPR crop recognition failed"))
    local = local_from_fastalpr(alpr)
    plate = str(local.get("plate") or "")
    accepted = True
    if ticket is not None:
        accepted = runtime.finish(ticket, plate=plate, stale_frame_ms=stale_frame_ms)
        if not accepted:
            runtime.lane(int(camera.id)).last_error = "Recognition result expired; retrying a fresh frame."
            return {**(alpr or {}), "persist_skipped": "stale recognition result"}
    if plate:
        runtime.lane(int(camera.id)).visit.observe(presence=True, plate=plate, native_event=bool(native.get("plate")))
    else:
        runtime.lane(int(camera.id)).visit.observe(presence=bool(presence), plate="")
    rec = runtime.lane(int(camera.id)).snapshot()
    if rec.get("vehicle_present") and plate:
        remember_alpr(camera.id, alpr)
    elif not rec.get("vehicle_present"):
        remember_alpr(camera.id, {})
    fused = resolve_readings(
        native_plate=native.get("plate") or "",
        native_confidence=float(native.get("confidence") or 0),
        local_plate=local.get("plate") or "",
        local_confidence=float(local.get("confidence") or 0),
        mode=fusion_mode(camera),
        local_consensus=False,
    )
    if not fused.resolved_plate:
        return alpr
    # Unique image id so FastALPR hits create a VehicleCapture only when the frame looks like a car/plate.
    if not image_id:
        image_id = int(time.time() * 1000) % 2_000_000_000
    capture = _capture_from_readings(native, local, fused, image_id=image_id)
    capture["visit_id"] = rec.get("visit_id") or ""
    from app.services.presence import coil_watch
    allowed, reason = should_persist_vehicle_capture(
        capture, coil_occupied=coil_watch.occupied(camera.id),
        plate_policy=site_policy(db).get("plate_validation", "NONE"),
    )
    if not allowed:
        alpr = dict(alpr or {})
        alpr["persist_skipped"] = reason
        return alpr
    await _persist_capture_event(db, camera, capture, jpeg, _crop_from_alpr(alpr, jpeg))
    return alpr
