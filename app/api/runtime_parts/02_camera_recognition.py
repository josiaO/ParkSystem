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
        **_refused_read(camera.id),
    }


REFUSED_SHOWN_SECONDS = 120.0


def _refused_read(camera_id: int) -> dict:
    """The newest read the calibration refused, when no car was stored after it.

    The live view shows its picture marked NOT STORED, so the operator never
    sees an older stored car as if it were the one at the gate.
    """
    from app.services import capture_calibration as calibration

    state = calibration.live_state(camera_id)
    out = {"calibration_warning": state.get("warning") or ""}
    rejected = state.get("last_rejected") or {}
    at = float(rejected.get("at") or 0)
    if (rejected.get("has_image") and at > float(state.get("last_stored_at") or 0)
            and time.time() - at <= REFUSED_SHOWN_SECONDS):
        stamp = int(at * 1000)
        out["refused"] = {
            "plate": rejected.get("plate") or "",
            "reasons": list(rejected.get("reasons") or []),
            "at": at,
            "snapshot_url": f"/cameras/{int(camera_id)}/calibration/rejected.jpg?t={stamp}",
            "crop_url": f"/cameras/{int(camera_id)}/calibration/rejected.jpg?part=crop&t={stamp}",
        }
    return out


_local_alpr_at: dict[int, float] = {}
_alpr_fp: dict[int, int] = {}
_detect_at: dict[int, float] = {}


_coil_full_scan_at: dict[int, float] = {}
COIL_FULL_SCAN_SECONDS = 10.0


def _coil_indexes(camera_id: int | None = None) -> list[int]:
    """GPIO inputs to read this cycle.

    Each input is a separate SDK call (~110 ms on QY cameras). Scanning all
    seven every 0.25 s held the SDK for ~0.8 s per cycle, delayed plate-event
    draining by ~1 s and slowed the boom relay. Until the loop input is
    learned, read only the configured loop pin each cycle and the full
    learning scan every COIL_FULL_SCAN_SECONDS.
    """
    learned = coil_watch.learned_index(camera_id) if camera_id is not None else None
    if learned is not None:
        return [learned]
    if camera_id is not None:
        now = time.monotonic()
        if now - _coil_full_scan_at.get(int(camera_id), float("-inf")) < COIL_FULL_SCAN_SECONDS:
            default = int(getattr(settings, "coil_gpio_index", 1) or 1)
            return [default]
        _coil_full_scan_at[int(camera_id)] = now
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
    # 0.25 s by default (virtual_loop_detect_seconds): at 0.5 s a car rolling
    # past the camera could cross the capture distance between two samples.
    interval = float(getattr(settings, "virtual_loop_detect_seconds", 0.25) or 0.25)
    return time.monotonic() - _detect_at.get(int(camera_id), 0.0) >= max(0.1, interval)


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
    event_still: bool = False,
) -> dict | None:
    """Run FastALPR for one camera.

    ``event_still`` marks a JPEG captured by a native vehicle event. Such a
    still is the evidence of one physical arrival: it is not rate-limited by
    the live-video cooldown and its result is never discarded as a "stale
    frame" merely because OCR took longer than the live-video freshness
    window. Dropping it used to lose the car entirely.
    """
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
    if not force and not event_still and not _local_alpr_ready(camera.id):
        return None
    from app.services import read_budget
    if not force and not read_budget.allow(int(camera.id), hint_plate=_trigger_plate_hint(native)):
        # This car was already read (confidently, or twice). Another picture
        # of it can only add a chance of a misread.
        return read_budget.skipped_result(read_budget.current(int(camera.id)))
    from app.domain.recognition_engine import policy_from_settings
    stale_frame_ms = EVENT_STILL_MAX_AGE_MS if event_still else policy_from_settings().stale_frame_ms
    ticket = runtime.begin_if_idle(int(camera.id), stale_frame_ms=stale_frame_ms)
    if ticket is None:
        return None
    _mark_local_alpr(camera.id)
    # OCR is native/CPU work and may take several seconds. Do not keep the
    # caller's PostgreSQL connection checked out while the inference task runs.
    release_connection(db)
    if not event_still:
        # Live-video reads use the newest mailbox frame. An event read must
        # keep its own still: a newer live frame may no longer show the car.
        jpeg = ticket.jpeg or jpeg
    abandon = asyncio.Event()
    work = asyncio.create_task(_run_local_alpr_locked(
        db, camera, jpeg, native=native, presence=presence, image_id=image_id,
        force=force, plate_crop=plate_crop, ticket=ticket, abandon=abandon,
        stale_frame_ms=stale_frame_ms,
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


EVENT_STILL_MAX_AGE_MS = 120_000.0


def _trigger_plate_hint(native: dict | None) -> str:
    """Plate text the camera sent with its trigger, when it looks like a real read."""
    from app.core.plate import is_empty_scene_ocr, normalize_plate

    native = native or {}
    plate = normalize_plate(native.get("plate") or "")
    confidence = float(native.get("confidence") or 0)
    if not plate or confidence < 0.5 or is_empty_scene_ocr(plate, confidence=confidence):
        return ""
    return plate


def _count_read(db, camera: Camera, local: dict) -> None:
    """Count one automatic read toward this car's two-read limit."""
    from app.core.plate import validate_plate
    from app.services import read_budget

    plate = str((local or {}).get("plate") or "")
    try:
        policy = site_policy(db).get("plate_validation", "NONE")
    except Exception:
        policy = "NONE"
    valid = bool(plate) and validate_plate(plate, policy).get("ok", False)
    try:
        read_budget.record(int(camera.id), plate, float((local or {}).get("confidence") or 0), valid=valid)
    except Exception:
        log.debug("read budget not updated", exc_info=True)


def _correct_site_plate(db, alpr: dict | None) -> dict | None:
    """Apply the site plate policy (e.g. TZ slot rules) to FastALPR's best read.

    The corrected plate is what the capture, session and live label use; the
    OCR text stays in ``plate_raw``. Previously the corrected value was only
    used to decide whether to hold the read, and 7716BAZ was stored as read.
    """
    best = (alpr or {}).get("best")
    if not isinstance(best, dict):
        return alpr
    from app.core.plate import correct_ocr_confusions, normalize_plate

    raw = str(best.get("plate_raw") or best.get("plate") or "")
    read = normalize_plate(best.get("plate_normalized") or best.get("plate") or raw)
    if not read:
        return alpr
    try:
        policy = site_policy(db).get("plate_validation", "NONE")
    except Exception:
        return alpr
    fixed = correct_ocr_confusions(read, policy=policy)
    plate = str(fixed.get("plate") or "")
    if not fixed.get("corrected") or not plate or plate == read:
        return alpr
    corrected = {**best, "plate": plate, "plate_normalized": plate, "plate_raw": raw or read,
                 "ocr_correction": fixed.get("reason") or ""}
    return {**alpr, "best": corrected}


async def _run_event_alpr(
    db: Session,
    camera: Camera,
    jpeg: bytes,
    *,
    native: dict | None = None,
    image_id: int = 0,
    plate_crop: bytes = b"",
    attempts: int = 3,
) -> dict | None:
    """Read one native-event still, waiting for an in-flight read instead of dropping it.

    Two cars can trigger the same camera within one OCR duration. The second
    event used to get ``busy``/``None`` and vanish. Wait (bounded) for the
    previous read to finish, then read this still.
    """
    timeout = float(getattr(settings, "alpr_timeout_seconds", 15.0) or 15.0)
    result: dict | None = None
    for _ in range(max(1, attempts)):
        pending = _local_alpr_pending.get(int(camera.id))
        if pending is not None and not pending.done():
            await asyncio.wait({pending}, timeout=timeout)
        result = await _run_local_alpr(
            db, camera, jpeg, native=native, presence=True,
            image_id=image_id, force=False, plate_crop=plate_crop, event_still=True,
        )
        if result is not None and result.get("error") != "busy":
            return result
        await asyncio.sleep(0.05)
    return result


def _local_read_failed(result: dict | None) -> bool:
    """True when software OCR produced no decision at all for an event."""
    if result is None:
        return True
    if result.get("ok") is False:
        return True
    return bool(result.get("persist_skipped") == "stale recognition result")


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
    stale_frame_ms: float | None = None,
) -> dict | None:
    from app.services.inference_thread import run_inference
    native = native or {}
    from app.services.media_gateway import gateway
    from app.services.queues import AI_FRAMES
    from app.services.recognition_runtime import runtime
    from app.domain.recognition_engine import policy_from_settings
    if stale_frame_ms is None:
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
    from app.services.capture_calibration import gate_for
    prepared = gate_for(int(camera.id)).prepared
    # Boxes already found on this exact still are reused when they were
    # searched at the zoom this read would use (the read re-checks the zone).
    boxes = None
    if prepared and prepared[0] == hash(jpeg):
        searched_zoom = float(prepared[2]) if len(prepared) > 2 else float(framing["detect_zoom"] or 1.0)
        if abs(searched_zoom - float(framing["detect_zoom"] or 1.0)) < 1e-6:
            boxes = prepared[1]
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
    alpr = _correct_site_plate(db, alpr)
    local = local_from_fastalpr(alpr)
    plate = str(local.get("plate") or "")
    accepted = True
    if ticket is not None:
        accepted = runtime.finish(ticket, plate=plate, stale_frame_ms=stale_frame_ms)
        if not accepted:
            runtime.lane(int(camera.id)).last_error = "Recognition result expired; retrying a fresh frame."
            return {**(alpr or {}), "persist_skipped": "stale recognition result"}
    if not force and alpr.get("ok") is not False:
        _count_read(db, camera, local)
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
        # ``force`` is the explicit operator read action. It is the one
        # documented override that may use FastALPR even when the lane's
        # automatic mode is NATIVE_ONLY.
        mode="LOCAL_ONLY" if force else fusion_mode(camera),
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
    from app.services import capture_calibration as calibration
    calibration.note_read(int(camera.id), plate=fused.resolved_plate, confidence=float(local.get("confidence") or native.get("confidence") or 0),
                          source="fastalpr" if local.get("plate") else "camera",
                          test_mode=calibration.in_test_mode(int(camera.id)), accepted=None)
    if local.get("plate") and not native.get("plate") and not force and calibration.for_camera(int(camera.id)).get("enabled") \
            and not calibration.ocr_confidence_ok(int(camera.id), float(local.get("confidence") or 0)):
        # Below this camera's minimum recognition confidence: not this
        # passage's plate. The capture gate tries a later frame instead.
        alpr = dict(alpr or {})
        alpr["persist_skipped"] = "below the camera's minimum recognition confidence"
        return alpr
    # Cropping decodes the full frame: keep it off the event loop.
    plate_crop_jpeg = await asyncio.to_thread(_crop_from_alpr, alpr, jpeg)
    await _persist_capture_event(db, camera, capture, jpeg, plate_crop_jpeg)
    return alpr
