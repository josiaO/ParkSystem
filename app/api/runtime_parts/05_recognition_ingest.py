def _publish_live_still(camera_id: int, kind: str, jpeg: bytes) -> str:
    """One JPEG per camera so the live pane can show the camera crop without a new file per frame."""
    if jpeg[:2] != b"\xff\xd8":
        return ""
    relative = f"{kind}/live-{int(camera_id)}.jpg"
    path = settings.media_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    import hashlib
    import os
    import tempfile
    digest = hashlib.blake2s(jpeg, digest_size=8).hexdigest()
    if _live_still_digests.get(relative) == digest and path.is_file():
        log.debug("live evidence write skipped duplicate camera_id=%s kind=%s", camera_id, kind)
        return f"/media/{relative}?v={digest}"
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as tmp:
        tmp.write(jpeg)
        temporary = tmp.name
    try:
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    _live_still_digests[relative] = digest
    return f"/media/{relative}?v={digest}"


def _show_camera_read(
    camera_id: int,
    *,
    plate: str,
    confidence: float,
    jpeg: bytes,
    crop: bytes,
    overlay: dict | None,
    detect_roi: str | None = None,
    detect_zoom: float | None = None,
) -> None:
    """Put the camera's plate, crop, and box on the live lane immediately.

    FastALPR may still refine the plate. The operator should see the same
        crop the camera callback paints on the picture as soon as it arrives.
    """
    if not plate and not overlay:
        return
    if overlay:
        remember_plate_box(camera_id, overlay)
    from app.services.captures import _crop_from_bbox, detection_zone_jpeg

    # Keep the immediate live evidence consistent with persisted captures.
    # The raw callback frame is still used for processing, but the operator
    # sees the configured arrival zone and a crop made from its plate box.
    snapshot = detection_zone_jpeg(
        jpeg, detect_roi=detect_roi, detect_zoom=detect_zoom,
    ) or jpeg
    zone_crop = _crop_from_bbox(jpeg, overlay) if overlay else b""
    crop = zone_crop or crop
    snapshot_url = _publish_live_still(camera_id, "snapshots", snapshot)
    crop_url = _publish_live_still(camera_id, "crops", crop)
    if not plate and not snapshot_url and not crop_url:
        return
    remember_last_car(camera_id, {
        "plate": plate,
        "confidence": confidence,
        "snapshot_url": snapshot_url or None,
        "crop_url": crop_url or None,
        "bbox": overlay,
        "source": "camera",
    })


def _note_event_result(camera_id: int, capture: dict, jpeg: bytes, result: dict | None, used_native: bool) -> None:
    """One outcome per camera event (see app/services/event_outcomes.py)."""
    from app.services import event_outcomes

    outcome = "native" if used_native else event_outcomes.classify(result)
    plate = str(((result or {}).get("best") or {}).get("plate") or "")
    event_outcomes.note(
        camera_id, outcome, visit_id=str((capture or {}).get("visit_id") or ""), jpeg=jpeg,
        detail=plate or str((result or {}).get("detail") or (result or {}).get("error") or ""),
    )


async def _native_fallback_if_unread(
    db: Session,
    camera: Camera,
    capture: dict,
    jpeg: bytes,
    crop: bytes,
    native: dict,
    result: dict | None,
) -> bool:
    """Keep the camera's own plate when software verification produced nothing.

    In NATIVE_WITH_LOCAL_VERIFY the software read is a second opinion. When
    it times out, errors, or never runs, discarding the native read lost the
    car. Persist the native capture instead; the normal plate policy,
    duplicate suppression and parking controller still apply.
    """
    from app.core.plate import is_empty_scene_ocr
    from app.services.ocr_policy import NATIVE_WITH_LOCAL_VERIFY, camera_recognition_mode

    if not _local_read_failed(result):
        return False
    if camera_recognition_mode(camera) != NATIVE_WITH_LOCAL_VERIFY:
        return False
    plate = str(native.get("plate") or "")
    if not plate or is_empty_scene_ocr(plate, confidence=float(native.get("confidence") or 0)):
        return False
    log.warning(
        "software verification unavailable; using native plate camera_id=%s plate=%s reason=%s",
        camera.id, plate, (result or {}).get("error") or (result or {}).get("persist_skipped") or "not run",
    )
    await _persist_capture_event(db, camera, {**capture, "source": "native-fallback"}, jpeg, crop)
    return True


async def _process_native_capture(
    camera_id: int,
    capture: dict,
    jpeg: bytes,
    crop: bytes,
    native: dict,
    *,
    presence: bool,
    image_id: int,
) -> None:
    """Finish one native event without holding up callback ingestion.

    The SDK callback queue is the capture boundary.  Database writes and local
    ALPR are deliberately performed in a fresh session/task so a slow OCR call
    cannot stop the next callback from being drained.
    """
    try:
        with short_session() as db:
            row = db.get(Camera, camera_id)
            if row is None:
                return
            from app.services.ocr_policy import NATIVE_ONLY, camera_recognition_mode
            from app.recognition_worker import worker_owns_software_reads
            from app.services import hybrid_fusion
            from app.core.plate import is_empty_scene_ocr

            native_plate = str(native.get("plate") or "")
            real_native = bool(native_plate) and not is_empty_scene_ocr(
                native_plate, confidence=float(native.get("confidence") or 0),
            )
            if presence and real_native and hybrid_fusion.routes_camera(row, db):
                release_connection(db)
                await hybrid_fusion.offer_native(db, row, native, jpeg=jpeg, crop=crop, capture=capture)
                return

            if presence and camera_recognition_mode(row) == NATIVE_ONLY:
                await _persist_capture_event(db, row, capture, jpeg, crop)
            # Software and hybrid modes must reach their FastALPR/fusion
            # decision before native text can create a session or open a gate.
            if presence and not worker_owns_software_reads(camera_id) and should_run_local(
                native_plate=str(native.get("plate") or ""),
                native_confidence=float(native.get("confidence") or 0),
                presence=True,
                native_plates=adapter_has_native_plates(row),
                camera=row,
            ):
                frame = jpeg if jpeg[:2] == b"\xff\xd8" else crop
                result = await _run_event_alpr(
                    db, row, frame, native=native, image_id=image_id, plate_crop=crop,
                )
                used_native = await _native_fallback_if_unread(db, row, capture, jpeg, crop, native, result)
                _note_event_result(camera_id, capture, jpeg, result, used_native)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        from app.services.health import note_worker_failure
        note_worker_failure("camera-capture-processing", str(exc))


def _native_event_age_ms(capture: dict) -> float | None:
    """Age of a host plate callback: perf clock if stamped, else wall clock."""
    from app.core.latency_trace import age_ms_from_perf

    age = age_ms_from_perf(capture.get("captured_perf_ns"))
    if age is not None:
        return age
    try:
        captured = float(capture.get("captured_at_epoch") or 0)
    except (TypeError, ValueError):
        return None
    return round((time.time() - captured) * 1000.0, 2) if captured > 0 else None


def _seed_native_timeline(camera_id: int, capture: dict, visit_id: str, age_ms: float | None) -> None:
    """Start the visit timeline at the camera callback so decisions can report its age."""
    from app.services.lane_timing import mark

    timeline = {"visit_id": visit_id, "camera_id": camera_id,
                "capture_token": str(capture.get("capture_token") or "") or None}
    if age_ms is not None:
        mark("native_event_captured", timeline, at=time.monotonic() - age_ms / 1000.0)
    mark("native_event_ingested", timeline)
    capture["timeline"] = timeline


async def _drain_camera_events(
    camera_id: int,
    handle: int,
    *,
    defer_local_alpr: bool = False,
) -> int:
    hvx = HVXHostClient()
    try:
        events = await hvx.drain_events(handle)
    except Exception:
        events = None
    if events is None:
        # Do not replay last_capture. The host keeps the previous callback in
        # state() after the car has left; re-ingesting it looks hardcoded.
        return 0
    processed = len(events)
    from app.core import latency_trace
    for capture in events:
        image_id = int(capture.get("image_id") or 0)
        plate = str(capture.get("plate") or "")
        drained_age_ms = _native_event_age_ms(capture)
        from app.services.dedup import native_callbacks
        if native_callbacks.seen(
            camera_id=camera_id,
            plate=plate,
            image_id=image_id,
            fingerprint=str(capture.get("capture_token") or ""),
        ):
            # A second callback can carry the box the first one missed. Remember
            # it for the live view, but do not open another session.
            from app.core.plate import is_camera_no_plate
            if is_camera_no_plate(plate):
                continue
            late = native_from_sdk_capture(capture)
            late_box = choose_overlay_box(late)
            if late_box:
                remember_plate_box(camera_id, late_box)
            continue
        try:
            media_key = {"image_id": image_id}
            if capture.get("capture_token"):
                media_key = {"capture_token": capture["capture_token"]}
            media_started = time.perf_counter()
            jpeg, crop = await asyncio.gather(
                hvx.event_jpeg(handle, **media_key), hvx.event_crop(handle, **media_key),
            )
            media_ms = round((time.perf_counter() - media_started) * 1000.0, 2)
        except Exception:
            jpeg, crop = b"", b""
            media_ms = None
        # Do not inject event stills into live preview — that freezes the UI on the car snap.
        # Live frames come only from the media gateway producer (Net_GetJpgBuffer / RTSP / HTTP).
        from app.core.plate import is_camera_no_plate, is_empty_scene_ocr
        from app.services.captures import camera_crop_usable
        raw_plate = str(capture.get("plate") or "")
        if is_camera_no_plate(raw_plate):
            capture = {**capture, "plate": "", "score": 0}
        native = native_from_sdk_capture(capture)
        if is_camera_no_plate(raw_plate):
            # 无车牌 is the camera saying it did not read a plate. That includes
            # an empty lane. It is not evidence that a car is there.
            native = {**native, "plate": "", "plate_raw": "", "bbox": None, "confidence": 0.0, "have_vehicle": False}
            crop = b""
        elif not camera_crop_usable(crop, jpeg, raw_plate):
            crop = b""
        native_plate = str(native.get("plate") or "")
        real_native = bool(native_plate) and not is_empty_scene_ocr(
            native_plate, confidence=float(native.get("confidence") or 0),
        )
        if not real_native and not choose_overlay_box(native):
            from app.services.alpr import locate_plate_boxes
            from app.services.inference_thread import run_inference
            boxes, located = await run_inference(locate_plate_boxes, jpeg)
            found = boxes if located.get("available") else []
            if not found:
                from app.services import event_outcomes

                event_outcomes.note(
                    camera_id, "no_plate_box" if located.get("available") else "not_run",
                    jpeg=jpeg, detail=str(located.get("detail") or located.get("reason") or ""),
                )
                continue
            box = found[0]
            # The event read below would run the detector on this same still
            # again (~70-120 ms on CPU); hand it these full-frame (1x) boxes.
            from app.services.camera_framing import gate_for
            gate_for(int(camera_id)).prepared = (hash(jpeg), found, 1.0)
            native = {
                **native,
                "bbox": box,
                "have_vehicle": True,
                "image_width": int(box.get("image_width") or 0),
                "image_height": int(box.get("image_height") or 0),
            }
            from app.services.captures import _crop_from_bbox
            # Full-size snapshot decode/crop/encode: keep it off the event loop.
            crop = await asyncio.to_thread(_crop_from_bbox, jpeg, box) or b""
        plate_overlay = choose_overlay_box(native)
        if plate_overlay:
            remember_plate_box(camera_id, plate_overlay)
        # Prefer a fresh crop from the full panorama whenever the native
        # usLpBox is available. The SDK vehicle-picture buffer is frequently a
        # lower-resolution/blurrier image, especially under headlight glare;
        # using it first was the main source of unreadable persisted crops.
        if plate_overlay and jpeg[:2] == b"\xff\xd8":
            fitted = await asyncio.to_thread(
                fit_plate_box, plate_overlay, jpeg,
                src_w=int(native.get("image_width") or 0),
                src_h=int(native.get("image_height") or 0),
            )
            if fitted:
                from app.services.captures import _crop_from_bbox
                recrop = await asyncio.to_thread(_crop_from_bbox, jpeg, fitted)
                if recrop[:2] == b"\xff\xd8":
                    crop = recrop
        # A camera plate rectangle is a vehicle even when the plate text is empty.
        # Empty-scene OCR (ZC…) is not.
        presence = bool(native.get("have_vehicle") or real_native or plate_overlay)
        from app.services.recognition_runtime import runtime
        lane = runtime.lane(camera_id)
        lane.note_native_event()
        if presence:
            capture_token = str(capture.get("capture_token") or "")
            capture_key = capture_token
            if image_id:
                capture_key = f"{capture_token}:image:{image_id}" if capture_token else f"image:{image_id}"
            lane.note_native_capture(
                capture_key,
                plate=native_plate if real_native else "",
                repeat_window_seconds=float(
                    getattr(settings, "native_repeat_window_seconds", 8.0) or 8.0
                ),
            )
            coil_watch.observe(camera_id, True, source="image-callback")
            lane.visit.observe(presence=True, plate=native_plate if real_native else "", native_event=True)
            capture["visit_id"] = lane.visit.visit_id
            if not capture.get("timeline"):
                _seed_native_timeline(camera_id, capture, lane.visit.visit_id, _native_event_age_ms(capture))
        ingest_age_ms = _native_event_age_ms(capture)
        latency_trace.emit(
            "recognition.native_event", camera=camera_id, handle=handle,
            capture_token=str(capture.get("capture_token") or "") or None, image_id=image_id,
            plate=native_plate or None, presence=presence, visit_id=capture.get("visit_id"),
            age_at_drain_ms=drained_age_ms, age_after_media_ms=ingest_age_ms, media_ms=media_ms,
            batch=processed,
            stale=bool(ingest_age_ms is not None and ingest_age_ms > latency_trace.event_age_limit_ms()),
        )
        with short_session() as db:
            row = db.get(Camera, camera_id)
            if row is None:
                return processed
            from app.services.ocr_policy import LOCAL_ONLY, camera_recognition_mode
            local_only = camera_recognition_mode(row) == LOCAL_ONLY
            from app.services.camera_framing import framing_from_profiles
            framing = framing_from_profiles(getattr(row, "stream_profiles", None))
            _show_camera_read(
                camera_id,
                plate=native_plate if real_native and not local_only else "",
                confidence=float(native.get("confidence") or 0) if not local_only else 0,
                jpeg=jpeg,
                crop=crop,
                overlay={**plate_overlay, "label": ""} if local_only and plate_overlay else plate_overlay,
                detect_roi=framing["detect_roi"],
                detect_zoom=framing["detect_zoom"],
            )
            from app.services import hybrid_fusion
            if presence and real_native and hybrid_fusion.routes_camera(row, db):
                # HYBRID with a live Recognition Worker: the native reading is one
                # candidate; the worker's FastALPR reading arrives via the outbox.
                # The coordinator persists exactly one fused capture per vehicle.
                if defer_local_alpr:
                    task = asyncio.create_task(
                        _process_native_capture(
                            camera_id, dict(capture), jpeg, crop, dict(native),
                            presence=presence, image_id=image_id,
                        ),
                        name=f"camera-capture-{camera_id}-{image_id}",
                    )
                    task.add_done_callback(_consume_background_task)
                else:
                    release_connection(db)
                    await hybrid_fusion.offer_native(db, row, native, jpeg=jpeg, crop=crop, capture=capture)
                continue
            if defer_local_alpr:
                task = asyncio.create_task(
                    _process_native_capture(
                        camera_id, dict(capture), jpeg, crop, dict(native),
                        presence=presence, image_id=image_id,
                    ),
                    name=f"camera-capture-{camera_id}-{image_id}",
                )
                task.add_done_callback(_consume_background_task)
            else:
                from app.services.ocr_policy import NATIVE_ONLY, camera_recognition_mode
                if presence and camera_recognition_mode(row) == NATIVE_ONLY:
                    await _persist_capture_event(db, row, capture, jpeg, crop)
                # Software and hybrid modes must reach their FastALPR/fusion
                # decision before native text can create a session or open a gate.
                from app.recognition_worker import worker_owns_software_reads
                if presence and not worker_owns_software_reads(camera_id) and should_run_local(
                    native_plate=str(native.get("plate") or ""),
                    native_confidence=float(native.get("confidence") or 0),
                    presence=True,
                    native_plates=adapter_has_native_plates(row),
                    camera=row,
                ):
                    # The camera callback is the capture trigger. FastALPR reads the
                    # JPEG even when the camera sent no plate text.
                    frame = jpeg if jpeg[:2] == b"\xff\xd8" else crop
                    result = await _run_event_alpr(
                        db, row, frame, native=native, image_id=image_id, plate_crop=crop,
                    )
                    used_native = await _native_fallback_if_unread(db, row, capture, jpeg, crop, native, result)
                    _note_event_result(camera_id, capture, jpeg, result, used_native)
    return processed


async def _poll_coil_and_read(camera_id: int, handle: int, *, background: bool = False) -> None:
    """Read camera GPIO IN (ground loop) and trigger a plate read on a rising edge."""
    hvx = HVXHostClient()
    active = int(getattr(settings, "coil_active_value", 1) or 1)
    rising = False
    last_edge = None
    from app.services.manual_open import boom_indexes_cached

    boom_indexes = boom_indexes_cached(camera_id)
    pins = await hvx.scan_gpio(handle, sorted(set(_coil_indexes(camera_id)) | boom_indexes))
    learned = coil_watch.learned_index(camera_id)
    if boom_indexes:
        # A wired "boom up" input is not a vehicle loop: watch it for openings
        # Zirp did not command, and never let the loop learner pick it.
        for state in pins:
            if state.get("ok") and int(state.get("index") or 0) in boom_indexes:
                await _observe_boom_input(camera_id, int(state.get("value") or 0))
    for state in pins:
        if not state.get("ok"):
            continue
        index = int(state.get("index") or 0)
        if index in boom_indexes:
            continue
        if learned is not None and index != learned:
            continue
        occupied = int(state.get("value") or 0) == active
        edge = coil_watch.observe(
            camera_id, occupied, source="gpio", index=index, value=int(state.get("value") or 0),
        )
        last_edge = edge
        if edge.rising:
            rising = True
            break
    await hvx.drain_reports(handle)
    if last_edge is not None:
        from app.services.health import note_camera
        note_camera(
            camera_id,
            coil_occupied=last_edge.occupied,
            coil_source=last_edge.source,
            coil_index=last_edge.index,
        )
        if last_edge.falling:
            await _complete_passage_from_sensor(camera_id)
    if not rising:
        return
    if background:
        task = asyncio.create_task(
            _read_presence_now(camera_id, handle, background=True),
            name=f"camera-snapshot-{camera_id}",
        )
        task.add_done_callback(_consume_background_task)
    else:
        await _read_presence_now(camera_id, handle, background=False)


async def _observe_boom_input(camera_id: int, value: int) -> None:
    """Record an UNCOMMANDED manual open when the boom rises without a Zirp command."""
    from app.services.manual_open import observe_boom_input

    try:
        with short_session() as db:
            camera = db.get(Camera, int(camera_id))
            if camera is not None:
                observe_boom_input(db, camera, value)
    except Exception as exc:
        log.warning("boom input check failed camera=%s: %s", camera_id, redact_text(repr(exc)))


async def _complete_passage_from_sensor(camera_id: int) -> None:
    """Complete an authorized lane only after its vehicle leaves the loop."""
    from app.application.entry_lane import policy_from_parking_settings
    from app.application.exit_lane import ExitLaneController
    from app.domain.parking_engine import GATE_OPEN_REQUESTED, EXIT_GATE_OPEN_REQUESTED
    from app.services.parking_sessions import mark_vehicle_passed
    from app.services.simulation import parking_settings

    with short_session() as db:
        camera = db.get(Camera, int(camera_id))
        if camera is None:
            return
        policy = policy_from_parking_settings(parking_settings(db))
        if (camera.lane_direction or "ENTRY").upper() == "EXIT":
            rows = list(db.scalars(select(ParkingSession).where(
                ParkingSession.exit_camera_id == camera.id,
                ParkingSession.lifecycle == EXIT_GATE_OPEN_REQUESTED,
            ).order_by(ParkingSession.id.desc()).limit(4)).all())
            controller = ExitLaneController()
            for row in rows:
                await controller.vehicle_passed(db, row, policy=policy)
        else:
            rows = list(db.scalars(select(ParkingSession).where(
                ParkingSession.camera_id == camera.id,
                ParkingSession.lifecycle == GATE_OPEN_REQUESTED,
            ).order_by(ParkingSession.id.desc()).limit(4)).all())
            for row in rows:
                mark_vehicle_passed(db, row, policy=policy, side="ENTRY")
            db.commit()


_widest_frames: dict[int, bytes] = {}
_departed_frames: dict[int, bytes] = {}


async def _video_arrival_ready(camera, jpeg: bytes) -> bool:
    """True when this video frame should be cropped and read.

    Moving frames stay on the detector. A still plate in the zone is read
    once. HVX snaps and coil triggers do not use this gate; they already
    mean the car has arrived.
    """
    from app.services.inference_thread import run_inference
    from app.services.alpr import locate_plate_boxes
    from app.services.camera_framing import best_arrival_box, framing_from_profiles, gate_for
    from app.services.recognition_runtime import runtime

    if not _detect_due(int(camera.id)):
        return False
    _mark_detect(int(camera.id))
    framing = framing_from_profiles(getattr(camera, "stream_profiles", None))
    boxes, located = await run_inference(
        locate_plate_boxes,
        jpeg,
        detect_roi=framing["detect_roi"] or None,
        detect_zoom=framing["detect_zoom"],
    )
    gate = gate_for(int(camera.id))
    from app.services.camera_framing import effective_capture_plate_width

    # Per-camera capture distance set in the zone editor (plate width).
    gate.min_plate_width_px = effective_capture_plate_width(framing)
    if not located.get("available"):
        runtime.lane(int(camera.id)).last_error = str(located.get("detail") or located.get("reason") or "Plate detector unavailable")
        return False
    runtime.lane(int(camera.id)).last_error = ""
    # A lane camera never sees a plate wider than ~20% of its frame. Boxes
    # far wider are scene patterns (a bollard row read as "11111"/"HH111" on
    # SERVER01): they fired the trigger with no car and, being permanent,
    # kept the gate busy so real cars on that camera never fired.
    max_fraction = float(getattr(settings, "virtual_loop_max_plate_fraction", 0.40) or 0.40)
    frame_width = float(located.get("image_width") or 0)
    if frame_width > 0:
        boxes = [b for b in boxes if (float(b.get("x2", 0)) - float(b.get("x1", 0))) <= max_fraction * frame_width]
    gate.prepared = (hash(jpeg), boxes, float(framing["detect_zoom"] or 1.0))
    arrival_box = best_arrival_box(boxes, detect_roi=framing["detect_roi"])
    previous_best = gate.best_width
    phase = gate.observe(arrival_box, time.monotonic())
    from app.services import zirp_trigger

    zirp_trigger.observe(int(camera.id), arrival_box, phase, frame_width=int(located.get("image_width") or 0))
    if arrival_box is not None and gate.best_width > previous_best:
        _widest_frames[int(camera.id)] = jpeg           # the sharpest view of this car so far
    if phase == "departed":
        # The car left without reaching the capture distance: one read of the
        # widest frame it showed, so a car is never lost for being far.
        _departed_frames[int(camera.id)] = _widest_frames.pop(int(camera.id), b"")
    elif phase == "absent":
        _widest_frames.pop(int(camera.id), None)
    lane = runtime.lane(int(camera.id))
    if phase == "ready":
        return True
    if phase == "new_vehicle":
        # A following car can replace a published one before an empty detector
        # frame arrives. Reset the visit boundary immediately.
        lane.visit.reset(time.monotonic())
        lane.visit.observe(presence=True)
    if phase == "absent":
        remember_plate_box(int(camera.id), None)
        lane.visit.observe(presence=False, plate="")
        if lane.visit.state == "IDLE":
            gate.reset()
    else:
        lane.visit.observe(presence=True, plate="")
    return False


async def _read_departed_vehicle(db, camera, jpeg: bytes, native: dict) -> None:
    """Read the widest live frame of a car that never reached the capture distance."""
    from app.services import zirp_trigger

    alpr = await _run_local_alpr(db, camera, jpeg, native=native, presence=True, force=False)
    zirp_trigger.ready(int(camera.id), alpr, departed=True)


def _note_arrival_result(camera_id: int, alpr: dict | None) -> bool:
    from app.services.camera_framing import gate_for

    if alpr is None:
        gate_for(int(camera_id)).rearm()
        return False
    best = (alpr or {}).get("best") or {}
    plate = str(best.get("plate_normalized") or best.get("plate") or "")
    kept = bool(plate) and not alpr.get("persist_skipped")
    gate_for(int(camera_id)).note_ocr(published=kept)
    return kept


def _current_recognition_jpeg(camera_id: int) -> bytes:
    from app.services.media_gateway import gateway

    now = time.monotonic()
    maximum_age = float(settings.stale_stream_seconds)
    # Recognition is admitted only from DETECT. LIVE and the preview cache
    # belong to display/evidence consumers; falling back to either lets an
    # open display pane accidentally become an ALPR input path.
    sample = gateway.peek_detect(camera_id)
    if sample is not None and 0 <= now - sample.received_at <= maximum_age:
        return sample.jpeg
    return b""


async def _maybe_watch_local_alpr(camera_id: int, handle: int) -> None:
    """FastALPR samples the latest detect JPEG from the shared camera mailbox.

    Camera = picture source. FastALPR = plate engine (InALPR/OutALPR). Latest-frame
    mailbox bounds OCR. Do not poll HVX live_jpeg here — that stacked SDK grabs
    with inference on the four-camera site.
    """
    from app.recognition_worker import worker_owns_software_reads
    if worker_owns_software_reads(camera_id):
        from app.services.mediamtx_detect import stop_detect_consumer
        stop_detect_consumer(camera_id)
        return
    with short_session() as db:
        camera = db.get(Camera, camera_id)
        if camera is None or not software_ocr_enabled(camera):
            return
    from app.services.media_gateway import gateway
    jpeg = _current_recognition_jpeg(camera_id)
    if jpeg[:2] != b"\xff\xd8":
        from app.infrastructure.media.registry import mediamtx_detect_active
        with short_session() as db:
            camera = db.get(Camera, camera_id)
            if camera is None or not software_ocr_enabled(camera):
                return
            spec = _live_spec(camera, need_detect=True)
            if mediamtx_detect_active(camera_id):
                from app.services.mediamtx_detect import ensure_detect_consumer
                ensure_detect_consumer(spec)
            else:
                acquire_detect(spec)
        return
    fp = hash(jpeg)
    watching = viewers_for(camera_id) > 0
    if fp and _alpr_fp.get(camera_id) == fp:
        if not watching:
            _mark_local_alpr(camera_id)
        gateway.note_ai_sample(camera_id, dropped=True)
        return
    with short_session() as db:
        camera = db.get(Camera, camera_id)
        if camera is None or not software_ocr_enabled(camera):
            return
        from app.services.ocr_policy import LOCAL_ONLY, camera_recognition_mode
        release_connection(db)
        native = {} if camera_recognition_mode(camera) == LOCAL_ONLY else await _native_capture_for_camera(camera)
        from app.services.recognition_runtime import runtime
        # HVX last_capture plate text is not presence. Coil/visit/generic IP are.
        presence = bool(
            coil_watch.occupied(camera_id)
            or runtime.lane(camera_id).visit.vehicle_present
            or (software_ocr_enabled(camera) and not adapter_has_native_plates(camera))
        )
        if not await _video_arrival_ready(camera, jpeg):
            gateway.note_ai_sample(camera_id, dropped=True)
            departed = _departed_frames.pop(int(camera_id), b"")
            if departed[:2] == b"\xff\xd8":
                await _read_departed_vehicle(db, camera, departed, native)
            return
        if str(getattr(settings, "capture_trigger", "zirp")) in {"zirp", "both"} and handle is not None:
            # Zirp's own trigger: command the camera's full-resolution
            # snapshot now (the image a loop-triggered camera would send) and
            # read it through the normal event path, falling back to this
            # live frame if no snapshot arrives.
            from app.services import zirp_trigger

            zirp_trigger.fired(camera_id, mode="snapshot")
            task = asyncio.create_task(
                _read_presence_now(camera_id, int(handle), background=True),
                name=f"zirp-trigger-{camera_id}",
            )
            task.add_done_callback(_consume_background_task)
            return
        # The zone already saw a still plate. Read that crop even if the coil
        # has not pulsed; a moving frame never reaches this call.
        alpr = await _run_local_alpr(db, camera, jpeg, native=native, presence=True)
        from app.services import zirp_trigger
        from app.services.camera_framing import best_arrival_box, gate_for

        prepared = gate_for(int(camera_id)).prepared
        arrival = best_arrival_box(prepared[1]) if prepared else None
        zirp_trigger.ready(camera_id, alpr, width=zirp_trigger.box_width(arrival),
                           frame_width=int((arrival or {}).get("image_width") or 0))
        if _note_arrival_result(camera.id, alpr):
            _alpr_fp[camera_id] = fp


async def _local_watch_once(camera_id: int, handle: int) -> None:
    try:
        await _maybe_watch_local_alpr(camera_id, handle)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        from app.services.health import note_worker_failure
        note_worker_failure("camera-software-recognition", str(exc))
