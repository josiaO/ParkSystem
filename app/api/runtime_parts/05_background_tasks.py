def _schedule_local_watch(camera_id: int, handle: int) -> None:
    """Keep software sampling independent from the native capture poller."""
    existing = _local_watch_tasks.get(int(camera_id))
    if existing is not None and not existing.done():
        return
    task = asyncio.create_task(
        _local_watch_once(camera_id, handle),
        name=f"camera-software-watch-{camera_id}",
    )
    _local_watch_tasks[int(camera_id)] = task

    def _finished(done: asyncio.Task) -> None:
        if _local_watch_tasks.get(int(camera_id)) is done:
            _local_watch_tasks.pop(int(camera_id), None)
        _consume_background_task(done)

    task.add_done_callback(_finished)


async def _outbox_loop():
    from app.services.queues import parking_outbox
    from app.services.health import note_worker_failure

    last_token = None
    pending_known = False
    while True:
        sleep_for = float(settings.parking_event_poll_seconds)
        try:
            box = parking_outbox()
            change_token = getattr(box, "change_token", None)
            token = change_token() if callable(change_token) else None
            # An empty durable queue does not need a SQLite SELECT on every
            # tick. File metadata detects cross-process enqueue activity; the
            # database is opened only after the outbox changes or work is
            # already known to be pending.
            if not pending_known and token is not None and token == last_token:
                await asyncio.sleep(sleep_for)
                continue
            last_token = token
            items = box.pending(limit=20)
            for item in items:
                payload = item.get("payload") or {}
                from app.services.events import recognition_from_outbox
                recognized = recognition_from_outbox(item)
                if recognized is None and item.get("kind") != "plate-event":
                    box.ack(item["id"])
                    continue
                # Durable idempotency: a crash after business processing but before
                # ACK redelivers the row; the processed mark (same SQLite file,
                # committed with the ACK) and the capture event_id (main DB) both
                # stop it from creating a second capture/session.
                event_key = str((recognized or {}).get("event_id") or payload.get("event_id") or "") or None
                if event_key and box.was_processed(event_key):
                    box.ack(item["id"])
                    continue
                try:
                    with short_session() as db:
                        if recognized is not None:
                            from app.services.modules import is_enabled
                            if not is_enabled("recognition.alpr", db):
                                sleep_for = max(1.0, sleep_for * 10)
                                continue
                            camera = db.get(Camera, int(recognized.get("camera_id") or 0)) if recognized.get("camera_id") else None
                            if camera is None or not camera.enabled:
                                box.ack(item["id"], processed_key=event_key)
                                continue
                            if event_key and db.scalar(select(VehicleCapture.id).where(VehicleCapture.event_id == event_key)) is not None:
                                box.ack(item["id"], processed_key=event_key)
                                continue
                            jpeg = b""
                            crop = b""
                            reference = str(recognized.get("image_ref") or "")
                            if reference.startswith("/media/"):
                                pieces = reference.removeprefix("/media/").split("/")
                                if len(pieces) == 2:
                                    evidence = media_path(*pieces)
                                    if evidence is not None:
                                        jpeg = evidence.read_bytes()
                            crop_ref = str(recognized.get("plate_crop_ref") or "")
                            if crop_ref.startswith("/media/"):
                                pieces = crop_ref.removeprefix("/media/").split("/")
                                if len(pieces) == 2:
                                    evidence = media_path(*pieces)
                                    if evidence is not None:
                                        crop = evidence.read_bytes()
                            from app.services import hybrid_fusion
                            if hybrid_fusion.routes_camera(camera, db):
                                release_connection(db)
                                await hybrid_fusion.offer_local(db, camera, recognized, jpeg=jpeg, crop=crop)
                                box.ack(item["id"], processed_key=event_key)
                                continue
                            if adapter_has_native_plates(camera):
                                from app.services.ocr_policy import LOCAL_ONLY, camera_recognition_mode
                                if camera_recognition_mode(camera) != LOCAL_ONLY:
                                    # Native camera not fused by the worker path: the
                                    # in-process native/fusion loop stays authoritative.
                                    box.ack(item["id"], processed_key=event_key)
                                    continue
                            capture = {**recognized, "plate_raw": recognized.get("raw_plate"),
                                       "score": recognized.get("confidence") or recognized.get("recognition_confidence") or 0}
                            await _persist_capture_event(db, camera, capture, jpeg, crop)
                            box.ack(item["id"], processed_key=event_key)
                            continue
                        gate = db.get(Gate, int(payload.get("gate_id") or 0)) if payload.get("gate_id") else None
                        from app.services.modules import is_enabled
                        if not is_enabled("parking.sessions", db):
                            # Keep pending business work for an explicit profile
                            # re-enable rather than processing it while disabled.
                            sleep_for = max(1.0, sleep_for * 10)
                            continue
                        camera = db.get(Camera, int(payload.get("camera_id") or 0)) if payload.get("camera_id") else None
                        if gate is None and camera is None and not payload.get("plate"):
                            box.ack(item["id"])
                            continue
                        side = str(payload.get("side") or "ENTRY").upper()
                        capture_id = int(payload.get("capture_id") or 0)
                        if camera is not None and capture_id:
                            capture_row = db.get(VehicleCapture, capture_id)
                            if capture_row is None or capture_row.camera_id != camera.id:
                                box.ack(item["id"])
                                continue
                            if side == "ENTRY":
                                from app.application.live_parking import handle_live_entry
                                await handle_live_entry(
                                    db, camera=camera, capture=capture_row, gate=gate, source="outbox",
                                )
                            else:
                                from app.application.live_parking import handle_live_exit
                                await handle_live_exit(
                                    db, camera=camera, capture=capture_row, gate=gate, source="outbox",
                                )
                        else:
                            box.ack(item["id"])
                            continue
                    box.ack(item["id"], processed_key=event_key)
                except Exception as exc:
                    box.note_failure()
                    note_worker_failure("outbox", str(exc))
                    break
            pending_known = bool(items)
            last_token = box.change_token()
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(sleep_for)


async def _fusion_flush_loop():
    """Decide hybrid candidates whose counterpart never arrived (bounded wait)."""
    from app.services import hybrid_fusion
    from app.services.health import note_worker_failure

    while True:
        try:
            await hybrid_fusion.flush(short_session)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            note_worker_failure("hybrid-fusion", str(exc))
        await asyncio.sleep(0.5)


async def _onvif_capture(camera_id: int, capture: dict, jpeg: bytes) -> None:
    """Profile M plate metadata enters the same path as an HVX native read."""
    from app.services.dedup import camera_events
    from app.services import hybrid_fusion

    plate = str(capture.get("plate") or "")
    image_id = int(capture.get("image_id") or 0)
    if camera_events.seen(camera_id=camera_id, plate=plate, image_id=image_id):
        return
    native = native_from_sdk_capture(capture)
    if not native.get("plate"):
        return
    coil_watch.observe(camera_id, True, source="onvif-metadata")
    with short_session() as db:
        row = db.get(Camera, camera_id)
        if row is None or not row.enabled:
            return
        if hybrid_fusion.routes_camera(row, db):
            release_connection(db)
            await hybrid_fusion.offer_native(db, row, native, jpeg=jpeg, crop=b"", capture=capture)
            return
        await _persist_capture_event(db, row, capture, jpeg, b"")


async def _onvif_events_loop():
    """Keep one Profile M poller per ONVIF camera that advertises plate events."""
    from app.services import onvif_runtime
    from app.services.health import note_worker_failure

    while True:
        try:
            await onvif_runtime.reconcile(short_session)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            note_worker_failure("onvif-events", str(exc))
        await asyncio.sleep(5.0)


async def _payments_reconcile_loop():
    """Settle PENDING external intents whose webhook never arrived.

    Runs only while payments.core is enabled and an external provider is the
    active mobile provider; an LPR-only site never touches provider code.
    """
    from app.services import mobile_payments
    from app.services.health import note_worker_failure
    from app.services.modules import is_enabled

    from app.services.node_scope import is_processing_node
    if settings.node_role == "CLIENT" or is_processing_node():
        return

    while True:
        delay = max(5.0, float(settings.payments_reconcile_seconds or 60.0))
        try:
            with short_session() as db:
                enabled = is_enabled("payments.core", db)
            if enabled and mobile_payments.active_mobile_provider_id() in mobile_payments.external_provider_ids():
                await mobile_payments.reconcile_pending(SessionLocal)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            note_worker_failure("payments-reconcile", str(exc))
        await asyncio.sleep(delay)


_hvx_restore_attempts: dict[int, float] = {}


async def _restore_hvx_sessions(info: dict) -> None:
    if not info.get("available") or not isinstance(info.get("connections"), list):
        return
    connected = {int(row["handle"]): str(row.get("ip") or "") for row in info["connections"]}
    from app.services.node_scope import camera_active_on_this_installation, camera_in_recognition_scope
    with short_session() as db:
        # sdk_handle is stored with the shared camera record, so it can also
        # describe a session owned by a different lane PC.  Never restore
        # those rows on this host; otherwise a restart on lane 2 can log into
        # lane 1 cameras merely because the shared DB contains their handle.
        cameras = [
            camera for camera in db.scalars(
                select(Camera).where(Camera.enabled == True, Camera.sdk_handle.is_not(None))
            ).all()
            if (
                camera_in_recognition_scope(camera, db=db)
                if getattr(settings, "recognition_gate_id", None)
                else camera_active_on_this_installation(camera, db=db)
            )
        ]
    for camera in cameras:
        if connected.get(int(camera.sdk_handle)) == camera.ip_address:
            _hvx_restore_attempts.pop(camera.id, None)
            continue
        now = time.monotonic()
        if now - _hvx_restore_attempts.get(camera.id, float("-inf")) < 30.0:
            continue
        _hvx_restore_attempts[camera.id] = now
        log.info("Restoring SDK session: camera=%s address=%s previous_handle=%s", camera.id, camera.ip_address, camera.sdk_handle)
        with short_session() as db:
            current = db.get(Camera, camera.id)
            if current is not None and current.enabled and current.sdk_handle is not None:
                release_connection(db)
                await apply_sdk_connect(current, db, None, raise_on_host_error=False)


async def _disconnect_out_of_scope_hvx_sessions(info: dict) -> None:
    """Release local SDK handles that no longer belong to this node's gate.

    Camera rows and SDK handles are shared in the multi-PC database, but the
    HVX host is local to this process. Disconnect only handles reported by this
    host and never rewrite the shared ``sdk_handle`` column, which may belong
    to the other lane PC.
    """
    connections = info.get("connections") if isinstance(info, dict) else None
    if not isinstance(connections, list):
        return
    from app.services.node_scope import camera_active_on_this_installation
    ips = {str(row.get("ip") or "") for row in connections if row.get("ip")}
    if not ips:
        return
    with short_session() as db:
        cameras = {
            str(camera.ip_address): camera
            for camera in db.scalars(select(Camera).where(Camera.enabled == True)).all()
            if str(camera.ip_address or "") in ips
        }
        stale_handles = [
            int(row["handle"])
            for row in connections
            if row.get("handle") is not None
            and str(row.get("ip") or "") in cameras
            and not camera_active_on_this_installation(cameras[str(row.get("ip") or "")], db=db)
        ]
    if not stale_handles:
        return
    hvx = HVXHostClient()
    for handle in stale_handles:
        try:
            await hvx.disconnect(handle, force=True)
            log.info("Released out-of-scope SDK session: handle=%s", handle)
        except Exception as exc:
            log.warning("Could not release out-of-scope SDK session handle=%s: %s", handle, exc)


async def _hvx_watch_loop():
    from app.services.circuit import breaker
    from app.services.runtime import mark_hardware

    hvx_breaker = breaker("hvx-host")
    while True:
        try:
            info = await asyncio.wait_for(HVXHostClient().info(), timeout=1.0)
            ok = bool(info.get("available"))
            if ok:
                hvx_breaker.success()
            else:
                hvx_breaker.failure()
            mark_hardware(ok)
            if ok:
                await _disconnect_out_of_scope_hvx_sessions(info)
                await _restore_hvx_sessions(info)
        except asyncio.CancelledError:
            raise
        except Exception:
            hvx_breaker.failure()
            mark_hardware(False)
        await asyncio.sleep(5.0)


async def _maybe_local_ipcam_alpr(camera_id: int) -> None:
    """Periodic FastALPR for cameras that have no onboard plate engine."""
    # QY/native cameras are serviced by the SDK callback lane.  Keep this
    # guard here as well as in the scheduler so an endpoint, stale task, or
    # future caller cannot start a second generic recognition path.
    with short_session() as db:
        camera = db.get(Camera, camera_id)
        if camera is None or adapter_requires_native_stream(camera.adapter_id):
            return
    from app.recognition_worker import worker_owns_software_reads
    if worker_owns_software_reads(camera_id):
        from app.services.mediamtx_detect import stop_detect_consumer
        stop_detect_consumer(camera_id)
        return
    from app.services.media_gateway import gateway
    # If the optional sidecar became ready after a direct fallback was started,
    # switch the legacy Site Service reader before consuming its old mailbox.
    from app.infrastructure.media.registry import mediamtx_detect_active
    if mediamtx_detect_active(camera_id):
        with short_session() as db:
            camera = db.get(Camera, camera_id)
            if camera is None or not software_ocr_enabled(camera):
                return
            gateway.release_detect(camera_id)
            from app.services.mediamtx_detect import ensure_detect_consumer
            ensure_detect_consumer(_live_spec(camera, need_detect=True))
    jpeg = _current_recognition_jpeg(camera_id)
    if jpeg[:2] != b"\xff\xd8":
        from app.infrastructure.media.registry import mediamtx_detect_active
        if mediamtx_detect_active(camera_id):
            from app.services.mediamtx_detect import ensure_detect_consumer
            with short_session() as db:
                camera = db.get(Camera, camera_id)
                if camera is None or not software_ocr_enabled(camera):
                    return
                ensure_detect_consumer(_live_spec(camera, need_detect=True))
            return
        with short_session() as db:
            camera = db.get(Camera, camera_id)
            if camera is None or not software_ocr_enabled(camera):
                return
            acquire_detect(_live_spec(camera, need_detect=True))
        return
    with short_session() as db:
        camera = db.get(Camera, camera_id)
        if camera is None or not software_ocr_enabled(camera):
            return
        fp = hash(jpeg)
        if fp and _alpr_fp.get(camera_id) == fp:
            gateway.note_ai_sample(camera_id, dropped=True)
            return
        release_connection(db)
        if not await _video_arrival_ready(camera, jpeg):
            gateway.note_ai_sample(camera_id, dropped=True)
            return
        alpr = await _run_local_alpr(db, camera, jpeg, presence=True, force=False)
        if _note_arrival_result(camera.id, alpr):
            _alpr_fp[camera_id] = fp


async def _camera_event_loop():
    """Pull QY plate callbacks and FastALPR frames so cars are not missed while the UI is idle."""
    from app.services.circuit import breaker
    from app.services.health import note_camera, note_worker_failure
    from app.config import settings as cfg

    poll = float(getattr(cfg, "camera_event_poll_seconds", 0.25) or 0.25)
    config_refresh = max(2.0, poll * 8.0)
    idle_config_refresh = max(10.0, config_refresh * 5.0)
    last_config_refresh = 0.0
    config_loaded = False
    rows: list[Camera] = []
    active: list[Camera] = []
    hvx_specs: list[tuple[int, int]] = []
    ipcam_ids: list[int] = []
    inactive_ids: set[int] = set()
    while True:
        try:
            now = time.monotonic()
            refresh = not config_loaded or (now - last_config_refresh) >= config_refresh
            clear_inactive_ids: set[int] = set()
            if refresh:
                with short_session() as db:
                    from app.services.modules import is_enabled
                    from app.services.node_scope import camera_active_on_this_installation
                    rows = list(db.scalars(select(Camera).where(Camera.enabled == True)).all()) if is_enabled("recognition.alpr", db) else []
                    active = [c for c in rows if camera_active_on_this_installation(c, db=db)]
                    active_ids = {int(c.id) for c in active}
                    new_inactive = {int(c.id) for c in rows if int(c.id) not in active_ids}
                    clear_inactive_ids = new_inactive - inactive_ids
                    inactive_ids = new_inactive
                    hvx_specs = [
                        (int(c.id), int(c.sdk_handle))
                        for c in active
                        if c.sdk_handle is not None
                    ]
                    ipcam_ids = [
                        int(c.id) for c in active
                        if c.sdk_handle is None
                        and not adapter_requires_native_stream(c.adapter_id)
                        and c.status in {
                            CameraStatus.VIDEO_CONNECTED.value, CameraStatus.SDK_CONNECTED.value,
                        }
                    ]
                last_config_refresh = now
                config_loaded = True
            async def service_hvx(camera_id: int, handle: int) -> None:
                started_one = time.perf_counter()
                camera_breaker = breaker(f"hvx-camera-{camera_id}")
                # Software video recognition must survive an SDK/GPIO outage,
                # but it must never occupy the native capture poller.
                _schedule_local_watch(camera_id, handle)
                if not camera_breaker.allow():
                    note_camera(camera_id, sdk_callback="circuit-open")
                    return
                try:
                    # Drain callback metadata first, then process OCR/persistence
                    # in detached tasks. A slow FastALPR call cannot starve the
                    # next camera callback or GPIO edge.
                    await _drain_camera_events(camera_id, handle, defer_local_alpr=True)
                    await _poll_coil_and_read(camera_id, handle, background=True)
                    camera_breaker.success()
                    note_camera(camera_id, sdk_callback="ok", last_event_at=time.time())
                except Exception as exc:
                    camera_breaker.failure()
                    note_worker_failure("camera-events", str(exc))
                    note_camera(camera_id, sdk_callback="error")
                finally:
                    note_camera(camera_id, event_latency_ms=int((time.perf_counter() - started_one) * 1000))

            async def service_ipcam(camera_id: int) -> None:
                started_one = time.perf_counter()
                try:
                    await _maybe_local_ipcam_alpr(camera_id)
                    note_camera(camera_id, sdk_callback="local-alpr", last_event_at=time.time())
                except Exception as exc:
                    note_worker_failure("camera-events", str(exc))
                    note_camera(camera_id, sdk_callback="error")
                finally:
                    note_camera(camera_id, event_latency_ms=int((time.perf_counter() - started_one) * 1000))

            async def clear_inactive_camera(camera_id: int) -> None:
                remember_last_car(camera_id, None)
                remember_plate_box(camera_id, None)
                from app.services.recognition_runtime import runtime
                lane = runtime.lane(camera_id)
                lane.clear_current_plate()
                lane.visit.reset()
                # Scope changes must release local consumers immediately. The
                # shared database can contain this camera because another lane
                # PC owns it, so do not leave this process's decoder running
                # merely because the row is still enabled globally.
                from app.services.mediamtx_detect import stop_detect_consumer
                from app.services.mediamtx_live import stop_live_consumer
                from app.services.media_gateway import gateway
                live_task = stop_live_consumer(camera_id)
                stop_detect_consumer(camera_id)
                gateway.stop_producer(camera_id, force=True)
                if live_task is not None:
                    await asyncio.gather(live_task, return_exceptions=True)

            # Cameras are independent failure domains. Draining them serially
            # meant one slow OCR/HTTP call could delay every other gate by
            # several seconds and leave cars undetected. Service lanes
            # concurrently; the ALPR inference limit separately caps CPU work.
            jobs: list[asyncio.Task] = []
            jobs.extend(
                asyncio.create_task(service_hvx(camera_id, handle), name=f"hvx-event-{camera_id}")
                for camera_id, handle in hvx_specs
            )
            jobs.extend(
                asyncio.create_task(clear_inactive_camera(camera_id), name=f"camera-idle-{camera_id}")
                for camera_id in clear_inactive_ids
            )
            jobs.extend(
                asyncio.create_task(service_ipcam(camera_id), name=f"ipcam-event-{camera_id}")
                for camera_id in ipcam_ids
            )
            if jobs:
                await asyncio.gather(*jobs, return_exceptions=True)
            from app.services.recognition_runtime import IDLE, runtime
            runtime.watchdog_once()
            absence = float(getattr(cfg, "live_plate_fresh_seconds", 4.0) or 4.0)
            for camera_id, _handle in hvx_specs:
                if coil_watch.occupied(camera_id):
                    continue
                lane = runtime.lane(camera_id)
                lane.visit.observe(presence=False, absence_seconds=absence)
                if lane.visit.state == IDLE:
                    remember_last_car(camera_id, None)
                    remember_plate_box(camera_id, None)
                    lane.clear_current_plate()
                    remember_alpr(camera_id, {})
            for camera_id in ipcam_ids:
                lane = runtime.lane(camera_id)
                if lane.inflight:
                    continue
                if not lane.visit.vehicle_present and lane.visit.state == IDLE:
                    continue
                if not coil_watch.occupied(camera_id):
                    lane.visit.observe(presence=False, absence_seconds=absence)
                if lane.visit.state == IDLE:
                    remember_last_car(camera_id, None)
                    remember_plate_box(camera_id, None)
                    lane.clear_current_plate()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            note_worker_failure("camera-events", str(exc))
            await asyncio.sleep(1.0)
            continue
        await asyncio.sleep(poll if (hvx_specs or ipcam_ids) else idle_config_refresh)


async def _ingest_camera_event(db: Session, camera: Camera) -> dict | None:
    if camera.sdk_handle is not None:
        await _drain_camera_events(int(camera.id), int(camera.sdk_handle))
    latest = latest_for_camera(db, camera.id)
    return capture_dict(latest) if latest else None
