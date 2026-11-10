def _resolve_stream_profiles(camera: Camera) -> dict:
    profiles = dict(getattr(camera, "stream_profiles", None) or {})
    if profiles:
        return profiles
    if camera.sdk_handle is not None:
        from app.services.stream_roles import hvx_profiles
        return hvx_profiles(camera.sdk_handle)
    if camera.rtsp_url:
        from app.services.stream_roles import recommend_roles
        return recommend_roles([{"uri": camera.rtsp_url, "width": 1280, "height": 720, "fps": 15}])
    return profiles


def _live_spec(camera: Camera, *, need_detect: bool = False, live_role: str = "LIVE") -> CameraLiveSpec:
    # Software recognition needs frames even on cameras capable of native LPR.
    # WebRTC viewing does not populate the Python recognition buffer.
    detect = need_detect or software_ocr_enabled(camera)
    return CameraLiveSpec(
        id=camera.id,
        ip=camera.ip_address,
        username=camera.username,
        password=camera.password_secret,
        rtsp_url=camera.rtsp_url or "",
        sdk_handle=camera.sdk_handle,
        ffmpeg_profile=getattr(camera, "ffmpeg_profile", None) or settings.ffmpeg_profile,
        transport=getattr(camera, "rtsp_transport", None) or settings.rtsp_transport,
        need_detect=detect,
        live_role=live_role,
        stream_profiles=_resolve_stream_profiles(camera),
        adapter_id=str(getattr(camera, "adapter_id", None) or "hvx").strip().lower() or "hvx",
        recognition_mode=str(getattr(camera, "recognition_mode", None) or ""),
    )


def _camera_live_spec(camera_id: int) -> CameraLiveSpec:
    with short_session() as db:
        c = _camera_for_node(db, camera_id, action="live-spec")
        return _live_spec(c)


@app.get("/cameras/{camera_id}/live/endpoint")
async def camera_live_endpoint(
    camera_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(require("cameras.view")),
):
    _camera_for_node(db, camera_id, action="live-endpoint")
    from app.infrastructure.media import registry as media_registry
    endpoint = await media_registry.get_live_endpoint(camera_id, db)
    from app.services.whep import browser_endpoint
    endpoint = browser_endpoint(endpoint, request)
    from app.services.preview import viewer_live_provider
    negotiated = viewer_live_provider(camera_id)
    if negotiated:
        endpoint = {**endpoint, "viewer_transport": negotiated}
        endpoint["live_provider"] = media_registry.live_provider_label(endpoint)
    else:
        endpoint.setdefault("live_provider", media_registry.live_provider_label(endpoint))
    return endpoint


@app.api_route("/cameras/{camera_id}/live/whep", methods=["OPTIONS", "POST"])
@app.api_route("/cameras/{camera_id}/live/whep/{session_id}", methods=["OPTIONS", "PATCH", "DELETE"])
async def camera_whep_signaling(
    camera_id: int, request: Request, session_id: str = "",
    db: Session = Depends(get_db), _: User = Depends(require("cameras.view")),
):
    _camera_for_node(db, camera_id, action="whep")
    from app.services.mediamtx import live_endpoint
    from app.services.whep import proxy_signaling
    path = live_endpoint(camera_id)["mediamtx_path"]
    return await proxy_signaling(request, camera_id, path, session_id)


_snapshot_status_checked: set[int] = set()


@app.get("/cameras/{camera_id}/snapshot.jpg")
async def camera_snapshot(camera_id: int, db: Session = Depends(get_db), _: User = Depends(require_media("cameras.view"))):
    _camera_for_node(db, camera_id, action="snapshot")
    spec = pumping_spec(camera_id) or _camera_live_spec(camera_id)
    # A snapshot is a temporary live consumer. This guarantees that MediaMTX
    # or the SDK producer is already supplying the shared latest-frame cache;
    # snapshot capture must never open a competing RTSP/FFmpeg reader.
    acquire_live(spec)
    try:
        return await _camera_snapshot_with_live_lease(camera_id, spec)
    finally:
        release_live(camera_id)


async def _camera_snapshot_with_live_lease(camera_id: int, spec: CameraLiveSpec):
    row = get_state(camera_id)

    def _jpeg_response(jpeg: bytes, seq: int | None = None) -> Response:
        headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
        }
        if seq is not None:
            headers["X-Frame-Seq"] = str(seq)
        return Response(content=jpeg, media_type="image/jpeg", headers=headers)

    if live_is_current(camera_id):
        touch_live(spec)
        # Promote DISCOVERED→VIDEO_CONNECTED once; never open SQLite on every 40ms poll.
        if camera_id not in _snapshot_status_checked:
            with short_session() as db:
                camera = db.get(Camera, spec.id)
                if camera is not None:
                    if camera.status in {
                        CameraStatus.UNKNOWN.value, CameraStatus.DISCOVERED.value,
                    }:
                        persist_video(db, camera, row.url or None)
                    _snapshot_status_checked.add(camera_id)
        return _jpeg_response(row.jpeg, row.seq)
    touch_live(spec)
    if pumping_spec(camera_id) is not None:
        for _ in range(24):
            await asyncio.sleep(0.05)
            row = get_state(camera_id)
            if live_is_current(camera_id):
                return Response(
                    content=row.jpeg,
                    media_type="image/jpeg",
                    headers={
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                        "Pragma": "no-cache",
                        "X-Frame-Seq": str(row.seq),
                    },
                )
    grabbed = await snapshot_for_camera(
        spec.id,
        spec.ip,
        spec.username,
        spec.password,
        spec.rtsp_url,
        sdk_handle=spec.sdk_handle,
        adapter_id=spec.adapter_id,
    )
    if not grabbed.get("ok"):
        raise HTTPException(409, grabbed.get("error") or "No live JPEG")
    if not grabbed.get("cached"):
        with short_session() as db:
            camera = db.get(Camera, spec.id)
            if camera is not None and camera.status in {
                CameraStatus.UNKNOWN.value, CameraStatus.DISCOVERED.value,
            }:
                persist_video(db, camera, grabbed.get("url"))
    return Response(
        content=grabbed["jpeg"],
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"},
    )


@app.post("/cameras/{camera_id}/live/watch")
def watch_camera_live(camera_id: int, db: Session = Depends(get_db), _: User = Depends(require_media("cameras.view"))):
    _camera_for_node(db, camera_id, action="live-watch")
    spec = _camera_live_spec(camera_id)
    watch_live(spec)
    return {"ok": True, "camera_id": camera_id, "viewers": viewers_for(camera_id)}


@app.post("/cameras/{camera_id}/live/unwatch")
def unwatch_camera_live(camera_id: int, db: Session = Depends(get_db), _: User = Depends(require_media("cameras.view"))):
    _camera_for_node(db, camera_id, action="live-unwatch")
    release_live(camera_id)
    return {"ok": True, "camera_id": camera_id, "viewers": viewers_for(camera_id)}


@app.post("/cameras/{camera_id}/snapshot/capture")
async def capture_camera_snapshot(camera_id: int, db: Session = Depends(get_db), user: User = Depends(require("cameras.view"))):
    """Grab one live JPEG and save a car snapshot only when a vehicle/plate is present."""
    c = _camera_for_node(db, camera_id, action="snapshot-capture")
    spec = _live_spec(c)
    touch_live(spec)
    grabbed = await snapshot_for_camera(
        spec.id, spec.ip, spec.username, spec.password, spec.rtsp_url, sdk_handle=spec.sdk_handle,
    )
    if not grabbed.get("ok"):
        raise HTTPException(409, grabbed.get("error") or "No live JPEG")
    jpeg = grabbed["jpeg"]
    native = await _native_capture_for_camera(c)
    alpr = fresh_alpr(c.id)
    worker_owned = await _worker_owns_continuous_reads(c.id)
    if worker_owned:
        # Do not launch a competing detector/OCR call from the API process.
        # The worker's event is already the authoritative production read and
        # its evidence is persisted asynchronously through the outbox.
        local = local_from_fastalpr(alpr)
        fused = resolve_readings(
            native_plate=native.get("plate") or "",
            native_confidence=float(native.get("confidence") or 0),
            local_plate=local.get("plate") or "",
            local_confidence=float(local.get("confidence") or 0),
            mode=fusion_mode(c),
        )
        latest = latest_for_camera(db, c.id)
        recent = False
        if latest is not None and latest.created_at is not None:
            created = latest.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            recent = (datetime.now(timezone.utc) - created).total_seconds() <= max(
                4.0, float(getattr(settings, "live_plate_fresh_seconds", 4.0) or 4.0),
            )
        if recent and latest is not None and fused.resolved_plate and latest.plate == fused.resolved_plate:
            write_audit(db, user, "camera.snapshot", "camera", str(c.id), c.name)
            return {
                "ok": True,
                "camera_id": c.id,
                "bytes": len(jpeg),
                "snapshot_url": f"/cameras/{c.id}/snapshot.jpg",
                "capture": capture_dict(latest),
                "plate": latest.plate or fused.resolved_plate or "",
                "recognition": "worker",
            }
        raise HTTPException(
            409,
            "Continuous recognition is processing this camera; snapshot capture did not start a competing model read",
        )
    if alpr is None:
        alpr = await _manual_alpr_read(jpeg, camera_label=f"cam-{c.id}-snap")
    local = local_from_fastalpr(alpr)
    fused = resolve_readings(
        native_plate=native.get("plate") or "",
        native_confidence=float(native.get("confidence") or 0),
        local_plate=local.get("plate") or "",
        local_confidence=float(local.get("confidence") or 0),
        mode=fusion_mode(c),
    )
    image_id = int(time.time() * 1000) % 2_000_000_000
    if fused.resolved_plate or native.get("have_vehicle"):
        capture = _capture_from_readings(native, local, fused, image_id=image_id)
        if native.get("have_vehicle"):
            capture["have_vehicle"] = True
        allowed, reason = should_persist_vehicle_capture(capture, coil_occupied=coil_watch.occupied(c.id), plate_policy=site_policy(db).get("plate_validation", "NONE"))
        if not allowed and native.get("have_vehicle"):
            capture = {
                "plate": "", "image_id": image_id, "have_vehicle": True,
                "score": 0, "source": native.get("source") or "camera",
            }
            allowed, reason = should_persist_vehicle_capture(capture, plate_policy=site_policy(db).get("plate_validation", "NONE"))
        if not allowed:
            raise HTTPException(409, f"No vehicle in frame ({reason}). Snapshot not saved.")
        row = persist_event(db, c, jpeg=jpeg, crop=_crop_from_alpr(alpr), capture=capture)
    else:
        raise HTTPException(409, "No vehicle or plate in frame. Snapshot not saved.")
    write_audit(db, user, "camera.snapshot", "camera", str(c.id), c.name)
    latest = row or latest_for_camera(db, c.id)
    return {
        "ok": True,
        "camera_id": c.id,
        "bytes": len(jpeg),
        "snapshot_url": f"/cameras/{c.id}/snapshot.jpg",
        "capture": capture_dict(latest) if latest else None,
        "plate": (latest.plate if latest else "") or fused.resolved_plate or "",
    }


@app.get("/cameras/{camera_id}/live.mjpeg")
async def camera_live(camera_id: int, role: str = "LIVE", db: Session = Depends(get_db), _: User = Depends(require_media("cameras.view"))):
    _camera_for_node(db, camera_id, action="mjpeg")
    # The MJPEG response can remain open for hours.  Do not keep the request's
    # SQLAlchemy session checked out for the lifetime of that stream: with the
    # old behavior four live panes plus plate polling exhausted PostgreSQL's
    # 5+5 pool and made unrelated recognition queries fail with QueuePool
    # timeouts.  The generator reads only the in-memory frame cache.
    close = getattr(db, "close", None)
    if close is not None:
        close()
    spec = _camera_live_spec(camera_id)
    wanted = (role or "LIVE").upper()
    if wanted in {"MAIN", "EVIDENCE"}:
        from dataclasses import replace
        spec = replace(spec, live_role="MAIN")
    acquire_live(spec)
    try:
        for i in range(80):
            if live_is_current(spec.id):
                break
            if i == 60:
                # Give the MediaMTX path three seconds to negotiate. Production
                # generic cameras fail closed; only native SDK cameras or
                # development/simulation may use the compatibility lane.
                from app.services.media_gateway import gateway
                from app.services.preview import ensure_mjpeg_source, start_idle_watch
                from app.services.flags import direct_generic_media_allowed
                if spec.sdk_handle is None and not direct_generic_media_allowed():
                    raise HTTPException(409, "MediaMTX did not provide a fresh live frame")
                start_idle_watch()
                from app.services.mediamtx_live import stop_live_consumer
                consumer = stop_live_consumer(spec.id)
                if consumer is not None:
                    await asyncio.gather(consumer, return_exceptions=True)
                gateway.ensure_producer(spec)
            await asyncio.sleep(0.05)
        if not live_is_current(spec.id):
            raise HTTPException(409, "No live video yet. Connect the camera, then wait a second.")

        async def parts():
            try:
                async for part in mjpeg_from_cache(spec.id):
                    yield part
            finally:
                release_live(spec.id)

        return StreamingResponse(
            parts(),
            media_type=f"multipart/x-mixed-replace; boundary={MJPEG_BOUNDARY}",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except BaseException:
        release_live(spec.id)
        raise


@app.get("/cameras/{camera_id}/preview")
async def camera_preview(
    camera_id: int,
    run_alpr: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require("cameras.view")),
):
    c = _camera_for_node(db, camera_id, action="preview")
    cached = get_state(c.id)
    live = live_is_current(c.id)
    grabbed = {"ok": live, "jpeg": cached.jpeg, "url_redacted": cached.url_redacted}
    if not live:
        grabbed = await live_snapshot(c)
        live = bool(grabbed.get("ok"))
    alpr = fresh_alpr(c.id)
    native = await _native_capture_for_camera(c)
    if live and grabbed.get("jpeg") and should_run_local(
        native_plate=str(native.get("plate") or ""),
        native_confidence=float(native.get("confidence") or 0),
        explicit=run_alpr,
        native_plates=adapter_has_native_plates(c),
        camera=c,
        presence=True,
    ):
        alpr = await asyncio.to_thread(
            recognize_frame, grabbed["jpeg"], camera_label=f"cam-{c.id}-{c.ip_address}",
        )
        remember_alpr(c.id, alpr)
    plates = _plate_payload(c, native, alpr, db)
    return {
        "camera": camera_dict(c),
        "live": live,
        "error": None if live else (grabbed.get("error") or "No live JPEG"),
        "url_redacted": grabbed.get("url_redacted") or get_state(c.id).url_redacted,
        "snapshot_url": f"/cameras/{c.id}/snapshot.jpg",
        "live_url": f"/cameras/{c.id}/live.mjpeg",
        "live_source": cached.source or grabbed.get("source") or "",
        "live_fps": cached.fps,
        "alpr": alpr,
        "native": plates["native"],
        "local": plates["local"],
        "fusion": plates["fusion"],
        "resolved_plate": plates["resolved_plate"],
        "overlay": plates["overlay"],
        "last_car": plates["last_car"],
    }


@app.get("/cameras/{camera_id}/plates")
async def camera_plates(camera_id: int, db: Session = Depends(get_db), _: User = Depends(require("cameras.view"))):
    c = _camera_for_node(db, camera_id, action="plates")
    from app.services.ocr_policy import LOCAL_ONLY, camera_recognition_mode
    native = {} if camera_recognition_mode(c) == LOCAL_ONLY else await _native_capture_for_camera(c)
    payload = _plate_payload(c, native, fresh_alpr(c.id), db)
    from app.services.node_scope import camera_active_on_this_installation
    if not camera_active_on_this_installation(c, db=db):
        payload["recognition"]["last_error"] = "View only: assign this PC to this camera's gate under Devices to enable recognition."
    latest = latest_for_camera(db, c.id)
    payload["evidence"] = capture_dict(latest) if latest else None
    return payload


@app.post("/cameras/{camera_id}/plate-corrections")
async def correct_camera_plate(
    camera_id: int,
    payload: PlateCorrection,
    db: Session = Depends(get_db),
    user: User = Depends(require_any("gates.open", "sessions.view", "cameras.connect")),
):
    """Operator confirms or corrects a held misread. Raw OCR stays on plate_raw."""
    from app.core.plate import apply_site_plate, normalize_plate
    from app.services.captures import apply_operator_plate_correction

    camera = _camera_for_node(db, camera_id, action="plate-correction")
    row = db.get(VehicleCapture, int(payload.capture_id)) if payload.capture_id else latest_for_camera(db, camera.id)
    if row is None or row.camera_id != camera.id:
        raise HTTPException(404, "No vehicle capture to correct")
    original = row.plate_raw or row.plate
    chosen = normalize_plate(payload.plate) if payload.plate else normalize_plate(row.plate)
    if not chosen:
        raise HTTPException(400, "Corrected plate is empty")
    assessed = apply_site_plate(chosen, validation=str(getattr(settings, "plate_validation", "NONE") or "NONE"))
    apply_operator_plate_correction(row, chosen)
    write_audit(
        db, user, "plate.correct", "vehicle_capture", str(row.id),
        f"ocr={original} corrected={chosen} confirm={bool(payload.confirm)}",
    )
    db.commit()
    db.refresh(row)
    gate = db.get(Gate, camera.gate_id) if camera.gate_id else None
    side = (camera.lane_direction or "ENTRY").upper()
    if side == "ENTRY":
        from app.application.live_parking import handle_live_entry
        result = await handle_live_entry(
            db, camera=camera, capture=row, gate=gate, source="operator-correction",
        )
    else:
        from app.application.live_parking import handle_live_exit
        result = await handle_live_exit(
            db, camera=camera, capture=row, gate=gate, source="operator-correction",
        )
    last = capture_dict(row)
    remember_last_car(camera.id, last)
    return {
        "ok": True,
        "capture": last,
        "session": result.get("session"),
        "barrier_opened": result.get("barrier_opened"),
        "likely": assessed.get("likely"),
        "message": result.get("message") or "Plate confirmed",
    }


@app.get("/cameras/{camera_id}/presence")
async def get_camera_presence(camera_id: int, db: Session = Depends(get_db), _: User = Depends(require("cameras.view"))):
    c = _camera_for_node(db, camera_id, action="presence-read")
    gpio = None
    pins: list[dict] = []
    learned = coil_watch.learned_index(c.id)
    configured_index = getattr(settings, "coil_gpio_index", None)
    gpio_index = learned if learned is not None else configured_index
    if c.sdk_handle is not None:
        pins = await HVXHostClient().scan_gpio(int(c.sdk_handle), _coil_indexes(c.id))
        gpio = next((row for row in pins if row.get("index") == gpio_index), None)
        if gpio is None and gpio_index is not None:
            gpio = await HVXHostClient().read_gpio(int(c.sdk_handle), int(gpio_index))
    return {
        "camera_id": c.id,
        "occupied": coil_watch.occupied(c.id),
        "recent": coil_watch.recently_triggered(c.id),
        "gpio_index": gpio_index,
        "learned_index": learned,
        "scanning": learned is None,
        "active_value": int(settings.coil_active_value),
        "gpio": gpio,
        "pins": pins,
        "last_car": get_state(c.id).last_car or None,
        "note": (
            "You do not need to know the GPIO number. Zirp scans camera GPIO IN pins 1–7 "
            "(not the barrier output on 0) and locks onto the pin that changes when a car hits the loop. "
            "If the camera already snaps on the coil, that image callback is enough even without GPIO. "
            "POST this URL with occupied=true to simulate a car on the loop."
        ),
    }


@app.post("/cameras/{camera_id}/presence")
async def post_camera_presence(
    camera_id: int,
    occupied: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(require("cameras.connect")),
):
    c = _camera_for_node(db, camera_id, action="presence-write")
    edge = coil_watch.observe(c.id, occupied, source="api")
    if edge.falling:
        await _complete_passage_from_sensor(c.id)
    write_audit(db, user, "camera.presence", "camera", str(c.id), f"occupied={occupied}")
    if edge.rising and c.sdk_handle is not None:
        await _read_presence_now(c.id, int(c.sdk_handle))
    elif edge.rising:
        jpeg = get_state(c.id).jpeg
        if jpeg[:2] != b"\xff\xd8":
            grabbed = await live_snapshot(c)
            jpeg = grabbed.get("jpeg") or b""
        await _run_local_alpr(db, c, jpeg, presence=True, force=True)
    return {**edge.as_dict(), "last_car": get_state(c.id).last_car or None}


async def _read_presence_now(camera_id: int, handle: int, *, background: bool = False) -> None:
    coil_watch.mark_triggered(camera_id)
    with short_session() as db:
        previous = latest_for_camera(db, camera_id)
        previous_key = (previous.id, previous.image_id, previous.plate) if previous else None
    hvx = HVXHostClient()
    try:
        await hvx.snapshot_trigger(handle)
    except Exception:
        pass
    # Net_ImageSnap only queues the request; the JPEG arrives asynchronously
    # through the image callback. Poll for a new callback briefly instead of
    # assuming 200 ms is enough and OCR'ing an unrelated live frame.
    wait_until = time.monotonic() + max(
        0.2, float(getattr(settings, "capture_event_wait_seconds", 1.5) or 1.5)
    )
    while True:
        drained = await _drain_camera_events(camera_id, handle, defer_local_alpr=background)
        if isinstance(drained, int) and drained > 0:
            return
        if time.monotonic() >= wait_until:
            break
        await asyncio.sleep(0.05)
    with short_session() as db:
        camera = db.get(Camera, camera_id)
        if camera is None:
            return
        latest = latest_for_camera(db, camera.id)
        if latest and latest.plate and (latest.id, latest.image_id, latest.plate) != previous_key:
            return
        # The live SDK read is external I/O; release the read connection first.
        release_connection(db)
        jpeg = await hvx.live_jpeg(handle)
        if jpeg[:2] != b"\xff\xd8":
            jpeg = get_state(camera_id).jpeg
        if background:
            task = asyncio.create_task(
                _run_presence_alpr_background(camera_id, jpeg),
                name=f"camera-presence-alpr-{camera_id}",
            )
            task.add_done_callback(_consume_background_task)
        else:
            await _run_local_alpr(db, camera, jpeg, presence=True, force=True)


async def _run_presence_alpr_background(camera_id: int, jpeg: bytes) -> None:
    """Run the coil fallback without blocking the SDK callback poller."""
    try:
        with short_session() as db:
            camera = db.get(Camera, camera_id)
            if camera is not None:
                release_connection(db)
                await _run_local_alpr(db, camera, jpeg, presence=True, force=True)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        from app.services.health import note_worker_failure
        note_worker_failure("camera-presence-recognition", str(exc))


@app.get("/media/{kind}/{name}")
def serve_media(kind: str, name: str, _: User = Depends(require("cameras.view")), v: str | None = None):
    path = media_path(kind, name)
    if path is None:
        raise HTTPException(404, "Media not found")
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        raise HTTPException(404, "Media not found")
    if name.startswith("live-") and v:
        import hashlib
        if hashlib.blake2s(content, digest_size=8).hexdigest() != v:
            raise HTTPException(410, "Live evidence was superseded; refresh plate status")
    return Response(content, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
