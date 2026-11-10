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
                await _run_local_alpr(
                    db, row, frame, native=native, presence=True,
                    image_id=image_id, force=False, plate_crop=crop,
                )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        from app.services.health import note_worker_failure
        note_worker_failure("camera-capture-processing", str(exc))


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
    for capture in events:
        image_id = int(capture.get("image_id") or 0)
        plate = str(capture.get("plate") or "")
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
            jpeg, crop = await asyncio.gather(
                hvx.event_jpeg(handle, **media_key), hvx.event_crop(handle, **media_key),
            )
        except Exception:
            jpeg, crop = b"", b""
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
                continue
            box = found[0]
            native = {
                **native,
                "bbox": box,
                "have_vehicle": True,
                "image_width": int(box.get("image_width") or 0),
                "image_height": int(box.get("image_height") or 0),
            }
            from app.services.captures import _crop_from_bbox
            crop = _crop_from_bbox(jpeg, box) or b""
        plate_overlay = choose_overlay_box(native)
        if plate_overlay:
            remember_plate_box(camera_id, plate_overlay)
        # Prefer a fresh crop from the full panorama whenever the native
        # usLpBox is available. The SDK vehicle-picture buffer is frequently a
        # lower-resolution/blurrier image, especially under headlight glare;
        # using it first was the main source of unreadable persisted crops.
        if plate_overlay and jpeg[:2] == b"\xff\xd8":
            fitted = fit_plate_box(
                plate_overlay, jpeg,
                src_w=int(native.get("image_width") or 0),
                src_h=int(native.get("image_height") or 0),
            )
            if fitted:
                from app.services.captures import _crop_from_bbox
                recrop = _crop_from_bbox(jpeg, fitted)
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
                    await _run_local_alpr(
                        db, row, frame, native=native, presence=True,
                        image_id=image_id, force=False, plate_crop=crop,
                    )
    return processed


async def _poll_coil_and_read(camera_id: int, handle: int, *, background: bool = False) -> None:
    """Read camera GPIO IN (ground loop) and trigger a plate read on a rising edge."""
    hvx = HVXHostClient()
    active = int(getattr(settings, "coil_active_value", 1) or 1)
    rising = False
    last_edge = None
    pins = await hvx.scan_gpio(handle, _coil_indexes(camera_id))
    learned = coil_watch.learned_index(camera_id)
    for state in pins:
        if not state.get("ok"):
            continue
        index = int(state.get("index") or 0)
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
    if not located.get("available"):
        runtime.lane(int(camera.id)).last_error = str(located.get("detail") or located.get("reason") or "Plate detector unavailable")
        return False
    runtime.lane(int(camera.id)).last_error = ""
    gate.prepared = (hash(jpeg), boxes)
    phase = gate.observe(best_arrival_box(boxes, detect_roi=framing["detect_roi"]), time.monotonic())
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
            return
        # The zone already saw a still plate. Read that crop even if the coil
        # has not pulsed; a moving frame never reaches this call.
        alpr = await _run_local_alpr(db, camera, jpeg, native=native, presence=True)
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
