def persist_video(db: Session, camera: Camera, url: str | None = None) -> None:
    changed = False
    if url and str(url).startswith("rtsp://") and camera.rtsp_url != url:
        camera.rtsp_url = url
        changed = True
    if camera.status in {
        CameraStatus.UNKNOWN.value, CameraStatus.DISCOVERED.value,
        CameraStatus.SDK_CONNECTED.value,
    }:
        camera.status = CameraStatus.VIDEO_CONNECTED.value
        changed = True
    if changed:
        camera.last_seen_at = datetime.now(timezone.utc)
        camera.last_error = ""
        db.commit()


async def _native_capture_for_camera(camera: Camera) -> dict:
    """Return only a *fresh* native capture callback plate.

    The vendor host keeps its last callback for diagnostics. That cached value
    must never become a permanent plate in the operator UI or be fused into a
    later vehicle. New host versions stamp callbacks with captured_at_epoch.
    """
    if camera.sdk_handle is None:
        return native_from_sdk_capture(None)
    try:
        state = await HVXHostClient().state(int(camera.sdk_handle))
    except Exception:
        return native_from_sdk_capture(None)
    capture = state.get("last_capture") if isinstance(state, dict) else None
    if not isinstance(capture, dict):
        return native_from_sdk_capture(None)
    try:
        captured_at = float(capture.get("captured_at_epoch") or 0)
    except (TypeError, ValueError):
        captured_at = 0.0
    # Hosts upgraded from older builds have no timestamp. Treat their state()
    # value as diagnostic-only; live event ingestion still comes from drain_events().
    if captured_at <= 0 or (time.time() - captured_at) > float(settings.live_plate_fresh_seconds):
        return native_from_sdk_capture(None)
    return native_from_sdk_capture(capture)


async def _worker_owns_continuous_reads(camera_id: int) -> bool:
    """Read worker ownership without blocking the Site Service event loop."""
    from app.recognition_worker import worker_owns_software_reads

    try:
        return bool(await asyncio.to_thread(worker_owns_software_reads, int(camera_id)))
    except Exception:
        # A missing/stale worker heartbeat must not make the camera API fail.
        # The caller can use the bounded local fallback in that case.
        return False


async def _manual_alpr_read(jpeg: bytes, *, camera_label: str) -> dict:
    """Run one operator-requested read without blocking the async API loop.

    The continuous recognition worker is checked by the callers first.  This
    path is only a fallback for commissioning/native-only cameras, and is
    deliberately single-flight because ONNX CPU inference is not free on the
    Windows edge machine.
    """
    global _manual_alpr_pending
    if _manual_alpr_lock.locked() or (_manual_alpr_pending is not None and not _manual_alpr_pending.done()):
        raise HTTPException(409, "Recognition is already running; wait for the current result")
    async with _manual_alpr_lock:
        from app.services.inference_thread import run_inference
        work = asyncio.create_task(run_inference(recognize_frame, jpeg, camera_label=camera_label))
        _manual_alpr_pending = work
        try:
            return await asyncio.wait_for(
                asyncio.shield(work),
                timeout=float(getattr(settings, "alpr_timeout_seconds", 15.0) or 15.0),
            )
        except asyncio.TimeoutError as exc:
            work.add_done_callback(_consume_background_task)
            raise HTTPException(504, "Recognition timed out; the live stream was not restarted") from exc
        finally:
            if work.done():
                _manual_alpr_pending = None


async def _discover_cameras(db: Session, *, scan_lan: bool = False) -> dict:
    defaults = site_camera_defaults()
    existing = {c.ip_address: camera_dict(c) for c in db.scalars(select(Camera)).all()}
    ips = list(existing)
    if settings.deployment_profile == "DEVELOPMENT":
        ips.extend(row["ip_address"] for row in KNOWN_SITE_CAMERAS if row["ip_address"] not in ips)
    hvx = {"ok": False, "ips": [], "error": None, "note": "32-bit HVX host not queried yet"}
    try:
        hvx = await HVXHostClient().discover(wait_seconds=2.0)
        for ip in hvx.get("ips") or []:
            if ip and ip not in ips:
                ips.append(ip)
    except HVXHostUnavailable as exc:
        hvx = {
            "ok": False,
            "ips": [],
            "error": str(exc),
            "note": "Start tools\\hvx_sdk_host\\run_hvx_host.bat on 32-bit Python. TCP probe still runs.",
        }
    lan_ips: list[str] = []
    generic: list[dict] = []
    if scan_lan:
        devices = await scan_lan_devices()
        for device in devices:
            ip = device["ip"]
            if device.get("kind") == "hvx":
                if ip not in ips:
                    ips.append(ip)
                lan_ips.append(ip)
            else:
                generic.append(device)
    probed = await probe_ips(ips, defaults["sdk_port"])
    hvx_set = set(hvx.get("ips") or [])
    generic_by_ip = {row["ip"]: row for row in generic}
    cameras = []
    for ip in ips:
        sdk_open = bool(probed.get(ip))
        extra = generic_by_ip.pop(ip, None)
        if not sdk_open and ip not in hvx_set and extra is not None:
            cameras.append(generic_discovery_row(extra, existing.get(ip)))
            continue
        cameras.append(discovery_row(
            ip,
            tcp_open=sdk_open,
            hvx_found=ip in hvx_set,
            existing=existing.get(ip),
        ))
    for extra in generic_by_ip.values():
        cameras.append(generic_discovery_row(extra, existing.get(extra["ip"])))
    return {
        "sdk_port": defaults["sdk_port"],
        "username": defaults["username"],
        "scan_lan": scan_lan,
        "hvx": hvx,
        "lan_ips": lan_ips,
        "cameras": cameras,
        "note": (
            "TCP open or vendor FindDeviceIp is not SDK_CONNECTED. Use Connect / Connect all. "
            "Dahua/Hikvision/web cameras need only username and password; they stream video and FastALPR reads plates."
        ),
    }


def _ensure_known_gates(db: Session, lanes: tuple[dict, ...]) -> dict[str, Gate]:
    by_name: dict[str, Gate] = {}
    for spec in lanes:
        gate = db.scalar(select(Gate).where(Gate.name == spec["name"]))
        if gate is None:
            gate = Gate(name=spec["name"], mode=GateMode.COMMISSIONING.value)
            db.add(gate)
            db.flush()
        by_name[spec["name"]] = gate
    return by_name


def _import_site_layout(db: Session, user: User) -> tuple[list[Camera], list[dict], list[Gate]]:
    lanes = seed_site_lanes()
    gates = _ensure_known_gates(db, lanes)
    specs = []
    for row in flatten_site_cameras(lanes):
        spec = dict(row)
        gate = gates.get(row["gate_name"])
        if gate is not None:
            spec["gate_id"] = gate.id
            spec["gate_name"] = gate.name
        specs.append(spec)
    created, skipped = _import_camera_specs(db, user, specs, preserve_existing=True)
    names = [spec["name"] for spec in lanes]
    gates_list = list(db.scalars(select(Gate).where(Gate.name.in_(names)).order_by(Gate.id)).all())
    return created, skipped, gates_list


def _import_camera_specs(db: Session, user: User, specs: list[dict], *, preserve_existing: bool = False) -> tuple[list[Camera], list[dict]]:
    node_gate_ids = _processing_node_gate_ids(db)
    existing_ips = {c.ip_address: c for c in db.scalars(select(Camera)).all()}
    existing_names = {c.name for c in existing_ips.values()}
    created: list[Camera] = []
    skipped: list[dict] = []
    defaults = site_camera_defaults()
    for spec in specs:
        if node_gate_ids:
            requested_gate = spec.get("gate_id")
            if requested_gate not in (None, "", 0, "0") and int(requested_gate) not in node_gate_ids:
                raise HTTPException(403, "This camera belongs to another gate. Use the Site Server to assign it.")
            spec = dict(spec)
            if requested_gate in (None, "", 0, "0"):
                if len(node_gate_ids) != 1:
                    raise HTTPException(409, "Select an assigned gate when importing cameras on a multi-gate node.")
                requested_gate = next(iter(node_gate_ids))
            spec["gate_id"] = int(requested_gate)
        ip = spec["ip_address"]
        if ip in existing_ips:
            camera = existing_ips[ip]
            if node_gate_ids and int(camera.gate_id or 0) not in node_gate_ids:
                skipped.append({"ip_address": ip, "reason": "camera belongs to another gate", "camera_id": camera.id, "updated": False})
                continue
            if preserve_existing or settings.deployment_profile != "DEVELOPMENT":
                skipped.append({"ip_address": ip, "reason": "already added", "camera_id": camera.id, "updated": False})
                continue
            if spec.get("gate_id") is not None:
                camera.gate_id = spec["gate_id"]
            if spec.get("controller_ip") is not None:
                camera.controller_ip = spec.get("controller_ip") or ""
            if spec.get("display_ip") is not None:
                camera.display_ip = spec.get("display_ip") or ""
            if spec.get("lane_direction"):
                camera.lane_direction = spec["lane_direction"]
            new_name = spec.get("name")
            if new_name and new_name != camera.name and new_name not in existing_names:
                existing_names.discard(camera.name)
                camera.name = new_name
                existing_names.add(new_name)
            skipped.append({"ip_address": ip, "reason": "already added", "camera_id": camera.id, "updated": True})
            continue
        name = spec.get("name") or f"Camera {ip}"
        if name in existing_names:
            name = f"{name} ({ip})"
        camera = Camera(
            name=name,
            ip_address=ip,
            sdk_port=int(spec.get("sdk_port") or defaults["sdk_port"]),
            username=spec.get("username") or defaults["username"],
            password_secret=spec.get("password") or defaults["password"],
            lane_direction=spec.get("lane_direction") or "ENTRY",
            controller_ip=spec.get("controller_ip") or "",
            display_ip=spec.get("display_ip") or "",
            gate_id=spec.get("gate_id"),
            adapter_id=(spec.get("adapter_id") or "hvx").strip().lower() or "hvx",
            rtsp_url=spec.get("rtsp_url") or "",
            status=CameraStatus.DISCOVERED.value,
        )
        db.add(camera)
        db.flush()
        existing_ips[ip] = camera
        existing_names.add(camera.name)
        created.append(camera)
        write_audit(db, user, "camera.create", "camera", str(camera.id), f"Imported {camera.name} {camera.ip_address}")
    db.commit()
    for camera in created:
        db.refresh(camera)
    return created, skipped


def _connect_audit(result: dict) -> dict:
    return {k: v for k, v in result.items() if k not in {"password", "jpeg"}}


def _commit_camera(db: Session, camera: Camera) -> None:
    """Commit camera row changes; recover from stale/rolled-back sessions."""
    from sqlalchemy.exc import PendingRollbackError, InvalidRequestError
    from sqlalchemy.orm.attributes import flag_modified
    from sqlalchemy.orm.exc import StaleDataError

    for json_field in ("stream_profiles", "media_capabilities"):
        if json_field in camera.__dict__:
            try:
                flag_modified(camera, json_field)
            except Exception:
                pass
    try:
        db.commit()
        return
    except (StaleDataError, PendingRollbackError, InvalidRequestError):
        try:
            db.rollback()
        except Exception:
            pass
    camera_id = getattr(camera, "id", None)
    if camera_id is None:
        raise RuntimeError("Camera row is missing an id after rollback")
    fresh = db.get(Camera, camera_id)
    if fresh is None:
        raise RuntimeError(f"Camera {camera_id} was deleted during connect")
    for field in (
        "status", "sdk_handle", "last_error", "last_seen_at", "rtsp_url",
        "adapter_id", "stream_profiles", "media_capabilities",
    ):
        if field in camera.__dict__:
            setattr(fresh, field, getattr(camera, field))
            if field in {"stream_profiles", "media_capabilities"}:
                flag_modified(fresh, field)
    db.commit()
    for field in (
        "status", "sdk_handle", "last_error", "last_seen_at", "rtsp_url",
        "adapter_id", "stream_profiles", "media_capabilities",
    ):
        setattr(camera, field, getattr(fresh, field))


async def apply_camera_connect(camera: Camera, db: Session, user: User, *, raise_on_host_error: bool = True) -> dict:
    # A lane assignment is an ownership boundary, not only a recognition
    # filter.  Connect-all already filters its query, but this helper is also
    # used by the per-camera endpoint and onboarding flow; keep those paths
    # from opening an SDK/RTSP session for another node's gate.
    from app.services.node_scope import camera_active_on_this_installation, describe_recognition_scope
    if not camera_active_on_this_installation(camera, db=db):
        scope = describe_recognition_scope(db)
        return {
            **camera_dict(camera),
            "sdk_result": {
                "connected": False,
                "skipped": True,
                "reason": "Camera belongs to another recognition owner",
                "scope": scope.get("detail") or "Camera is outside this node's assigned gate",
            },
        }
    # QY/HVX rows, including the persisted ``hvx`` alias, have a single
    # physical-stream owner: the vendor SDK host.  A web port on the same
    # device is not permission to silently mutate the row to RTSP.
    native_stream = adapter_requires_native_stream(camera.adapter_id)
    adapter = camera_adapter_for(camera)
    caps = await adapter.capabilities(camera)
    if not caps.get("sdk_login"):
        return await apply_video_connect(camera, db, user, raise_on_host_error=raise_on_host_error)
    port = int(camera.sdk_port or settings.default_hvx_sdk_port)
    if await tcp_open(camera.ip_address, port, timeout=settings.camera_tcp_probe_seconds):
        return await apply_sdk_connect(camera, db, user, raise_on_host_error=raise_on_host_error)
    web = False
    for web_port in (80, 8000, 8080, 554):
        if await tcp_open(camera.ip_address, web_port, timeout=0.4):
            web = True
            break
    if web and not native_stream:
        previous = camera.adapter_id
        camera.adapter_id = "rtsp"
        _commit_camera(db, camera)
        video = await apply_video_connect(camera, db, user, raise_on_host_error=False)
        if video.get("status") == CameraStatus.VIDEO_CONNECTED.value:
            return video
        camera.adapter_id = previous
        _commit_camera(db, camera)
    return await apply_sdk_connect(camera, db, user, raise_on_host_error=raise_on_host_error)


async def apply_video_connect(camera: Camera, db: Session, user: User, *, raise_on_host_error: bool = True) -> dict:
    adapter = camera_adapter_for(camera)
    try:
        result = await adapter.connect(camera)
        jpeg = result.get("jpeg") or b""
        if result.get("connected"):
            # A generic RTSP adapter may only have registered a source
            # configuration here.  Until the shared media owner admits a
            # fresh frame, do not present configuration as operational health.
            camera.status = (
                CameraStatus.VIDEO_CONNECTED.value
                if jpeg[:2] == b"\xff\xd8" or not result.get("configured_only")
                else CameraStatus.DEGRADED.value
            )
            camera.sdk_handle = None
            camera.last_seen_at = datetime.now(timezone.utc)
            camera.last_error = ""
            url = str(result.get("url") or "")
            if url.startswith("rtsp://"):
                camera.rtsp_url = url
            from app.services.stream_roles import default_capabilities, recommend_roles
            camera.media_capabilities = default_capabilities(rtsp=True)
            if url:
                camera.stream_profiles = recommend_roles([{
                    "uri": url,
                    "protocol": str(result.get("source") or "rtsp"),
                    "codec": str(result.get("codec") or ""),
                }])
            if jpeg[:2] == b"\xff\xd8":
                remember_frame(
                    camera.id, jpeg,
                    url=url,
                    url_redacted=str(result.get("url_redacted") or ""),
                    source=str(result.get("source") or "rtsp"),
                )
            # Register the physical source before acquiring a detector. The
            # previous order could leave a direct FFmpeg pump alive beside the
            # same camera's MediaMTX path after the sidecar became ready.
            media_registered = False
            try:
                from app.services.mediamtx_sources import sync_camera
                media_registered = bool(sync_camera(camera, db=db).get("registered"))
            except Exception:
                media_registered = False
        else:
            camera.status = CameraStatus.OFFLINE.value
            camera.sdk_handle = None
            camera.last_error = result.get("error") or f"{adapter.id} did not return a live JPEG"
        _commit_camera(db, camera)
        if result.get("connected"):
            from app.infrastructure.media.registry import mediamtx_detect_active
            spec = _live_spec(camera, need_detect=True)
            if media_registered and mediamtx_detect_active(camera.id, db):
                from app.services.mediamtx_detect import ensure_detect_consumer
                ensure_detect_consumer(spec)
            else:
                # MediaMTX is optional; keep the bounded direct fallback only
                # when its registered detect path is not currently usable.
                acquire_detect(spec)
        write_audit(db, user, "camera.video_connect", "camera", str(camera.id), str(_connect_audit(result)))
        return {**camera_dict(camera), "sdk_result": _connect_audit(result)}
    except HTTPException:
        raise
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        try:
            fresh = db.get(Camera, camera.id) if getattr(camera, "id", None) else None
            target = fresh or camera
            target.status = CameraStatus.OFFLINE.value
            target.sdk_handle = None
            target.last_error = str(exc)
            _commit_camera(db, target)
            if fresh is not None:
                camera.status = target.status
                camera.sdk_handle = target.sdk_handle
                camera.last_error = target.last_error
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
        if raise_on_host_error:
            raise HTTPException(502, f"IP camera connection failed: {exc}")
        return {**camera_dict(camera), "sdk_result": {"connected": False, "error": str(exc)}}


async def apply_sdk_connect(camera: Camera, db: Session, user: User, *, raise_on_host_error: bool = True) -> dict:
    adapter = camera_adapter_for(camera)
    caps = await adapter.capabilities(camera)
    if not caps.get("sdk_login"):
        raise HTTPException(
            400,
            f"SDK connect is HVX-only. Camera adapter {adapter.id} cannot replace the working NetSDK login.",
        )
    port = int(camera.sdk_port or settings.default_hvx_sdk_port)
    reachable = await tcp_open(camera.ip_address, port, timeout=settings.camera_tcp_probe_seconds)
    if not reachable:
        camera.status = CameraStatus.SDK_FAILED.value
        camera.last_error = (
            f"No TCP on {camera.ip_address}:{port} — skipped SDK login so other cameras can still connect."
        )
        _commit_camera(db, camera)
        write_audit(db, user, "camera.sdk_connect", "camera", str(camera.id), camera.last_error)
        return {
            **camera_dict(camera),
            "sdk_result": {"connected": False, "skipped": True, "error": camera.last_error},
        }
    camera.status = CameraStatus.SDK_CONNECTING.value
    camera.last_error = ""
    _commit_camera(db, camera)
    try:
        result = await adapter.connect(camera)
        if result.get("connected"):
            camera.status = CameraStatus.SDK_CONNECTED.value
            camera.sdk_handle = result.get("handle")
            camera.last_seen_at = datetime.now(timezone.utc)
            camera.last_error = ""
            from app.services.stream_roles import default_capabilities, hvx_profiles
            camera.stream_profiles = hvx_profiles(camera.sdk_handle)
            camera.media_capabilities = default_capabilities(native_alpr=True, sdk=True)
            _commit_camera(db, camera)
            try:
                from app.services.mediamtx_sources import sync_camera
                sync_camera(camera, db=db)
            except Exception:
                pass
        else:
            camera.status = CameraStatus.SDK_FAILED.value
            name = result.get("connect_rc_name") or result.get("connect_rc")
            camera.last_error = result.get("error") or f"SDK return code: {name}"
        _commit_camera(db, camera)
        write_audit(
            db, user, "camera.sdk_connect", "camera", str(camera.id),
            str(_connect_audit(result)),
        )
        return {**camera_dict(camera), "sdk_result": result}
    except HTTPException:
        raise
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        try:
            fresh = db.get(Camera, camera.id) if getattr(camera, "id", None) else None
            target = fresh or camera
            target.status = CameraStatus.SDK_FAILED.value
            target.last_error = str(exc)
            _commit_camera(db, target)
            if fresh is not None:
                camera.status = target.status
                camera.last_error = target.last_error
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
        if raise_on_host_error:
            raise HTTPException(502, f"HVX SDK connection failed: {exc}")
        return {**camera_dict(camera), "sdk_result": {"connected": False, "error": str(exc)}}
