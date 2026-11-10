@app.get("/cameras")
def list_cameras(db: Session = Depends(get_db), _: User = Depends(require("cameras.view"))):
    rows = _management_camera_rows(db)
    # A central Site Server must be able to configure/assign cameras before it
    # has a gate owner.  This list is still only a management view: all media,
    # connect, snapshot, and recognition endpoints enforce the stricter node
    # ownership boundary immediately before touching a camera.
    return [camera_dict(c, db=db) for c in rows]


@app.get("/cameras/discover")
async def discover_cameras(
    scan_lan: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require("cameras.manage")),
):
    return await _discover_cameras(db, scan_lan=scan_lan)


@app.post("/cameras/seed-site")
def seed_site_cameras(payload: dict | None = Body(default=None), db: Session = Depends(get_db), user: User = Depends(require("cameras.manage"))):
    from app.services.node_scope import is_processing_node
    if is_processing_node():
        raise HTTPException(403, "Processing Nodes cannot seed or replace the central site layout. Add cameras for the assigned gate only.")
    if settings.deployment_profile != "DEVELOPMENT" and (payload or {}).get("confirm_test_data") is not True:
        raise HTTPException(409, "Confirm loading example camera records with confirm_test_data=true, or discover/manually add cameras.")
    created, skipped, gates = _import_site_layout(db, user)
    return {
        "created": [camera_dict(c) for c in created],
        "skipped": skipped,
        "gates": [gate_dict(g) for g in gates],
        "cameras": [camera_dict(c, db=db) for c in _management_camera_rows(db)],
        "note": (
            "Example setup records only. Review and edit addresses, names and gate assignments before use. "
            "Existing cameras are preserved. No cameras are connected and recognition ownership is unchanged."
        ),
    }


@app.post("/cameras/import-discovered")
async def import_discovered_cameras(
    payload: CameraImport | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require("cameras.manage")),
):
    node_gate_ids = _processing_node_gate_ids(db)
    payload = payload or CameraImport()
    username = (payload.username or "admin").strip() or "admin"
    password = payload.password if payload.password is not None else "admin"
    if str(getattr(settings, "deployment_profile", "DEVELOPMENT")).upper() != "DEVELOPMENT" and password.strip().lower() in {"", "admin"}:
        raise HTTPException(422, "Set the real camera password before importing cameras in a non-development deployment.")
    specs = []
    if payload.cameras:
        for item in payload.cameras:
            adapter = (item.adapter_id or "rtsp").strip().lower() or "rtsp"
            spec = camera_spec_for_ip(item.ip_address, adapter_id=adapter)
            spec["adapter_id"] = adapter
            spec["username"] = username
            spec["password"] = password
            spec["lane_direction"] = item.lane_direction or spec.get("lane_direction") or "ENTRY"
            if item.name:
                spec["name"] = item.name
            specs.append(spec)
    elif payload.ips:
        specs = [camera_spec_for_ip(ip) for ip in payload.ips]
    else:
        discovered = await _discover_cameras(db, scan_lan=payload.scan_lan)
        specs = []
        for row in discovered["cameras"]:
            if not row.get("reachable"):
                continue
            spec = camera_spec_for_ip(row["ip_address"], adapter_id=row.get("adapter_id") or "hvx")
            spec["adapter_id"] = row.get("adapter_id") or "hvx"
            spec["username"] = username
            spec["password"] = password
            specs.append(spec)
        if not specs and settings.deployment_profile == "DEVELOPMENT":
            specs = [camera_spec_for_ip(row["ip_address"]) for row in KNOWN_SITE_CAMERAS]
    for spec in specs:
        spec["username"] = spec.get("username") or username
        spec["password"] = spec.get("password") or password
        if node_gate_ids:
            requested_gate = spec.get("gate_id")
            if requested_gate not in (None, "", 0, "0") and int(requested_gate) not in node_gate_ids:
                raise HTTPException(403, "This camera is assigned to another gate. Use the Site Server to reassign it.")
            if requested_gate in (None, "", 0, "0"):
                if len(node_gate_ids) != 1:
                    raise HTTPException(409, "Select an assigned gate when importing cameras on a multi-gate node.")
                requested_gate = next(iter(node_gate_ids))
            spec["gate_id"] = int(requested_gate)
    created, skipped = _import_camera_specs(db, user, specs)
    connected = []
    if payload.connect:
        ids = [c.id for c in created]
        for row in skipped:
            if row.get("camera_id"):
                ids.append(int(row["camera_id"]))
        seen = set()
        for camera_id in ids:
            if camera_id in seen:
                continue
            seen.add(camera_id)
            camera = db.get(Camera, camera_id)
            if camera is None:
                continue
            connected.append(await apply_camera_connect(camera, db, user, raise_on_host_error=False))
    return {
        "created": [camera_dict(c) for c in created],
        "skipped": skipped,
        "connected": connected,
        "cameras": [camera_dict(c, db=db) for c in db.scalars(
            select(Camera).options(joinedload(Camera.gate)).order_by(Camera.id)
        ).all()],
    }


@app.post("/cameras/sdk/connect-all")
async def sdk_connect_all(db: Session = Depends(get_db), user: User = Depends(require("cameras.connect"))):
    from app.services.developer import camera_connections_enabled
    if not camera_connections_enabled(db):
        return {"connected": 0, "attempted": 0, "skipped": 0, "results": [], "note": "Developer mode has camera connections disabled."}
    rows = db.scalars(select(Camera).where(Camera.enabled == True).order_by(Camera.id)).all()
    from app.services.node_scope import camera_active_on_this_installation, camera_in_recognition_scope
    rows = [camera for camera in rows if camera_active_on_this_installation(camera, db=db)]
    results = []
    connected = 0
    skipped = 0
    for camera in rows:
        item = await apply_camera_connect(camera, db, user, raise_on_host_error=False)
        if item.get("status") in {CameraStatus.SDK_CONNECTED.value, CameraStatus.VIDEO_CONNECTED.value}:
            connected += 1
        if (item.get("sdk_result") or {}).get("skipped"):
            skipped += 1
        results.append(item)
    return {
        "connected": connected,
        "attempted": len(results),
        "skipped": skipped,
        "results": results,
        "note": (
            "Connect lane logs in only the cameras assigned to this PC (NetSDK port 30000 for HVX). "
            "Generic IP cameras (rtsp/dahua/hikvision) use HTTP snapshot or RTSP and FastALPR — not SDK_CONNECTED. "
            "Unreachable HVX cameras are skipped after a short TCP probe so one slow camera cannot stall the rest."
        ),
    }


def camera_dict(c: Camera, db: Session | None = None):
    gate = c.gate
    lane_name = None if gate is None else gate.name
    from app.services.stream_roles import public_profiles
    from app.services.camera_framing import framing_from_profiles
    from app.domain.cameras import camera_type_for
    native = adapter_has_native_plates(c)
    from app.services.ocr_policy import LOCAL_ONLY, NATIVE_ONLY, camera_recognition_mode
    from app.services.node_scope import camera_active_on_this_installation
    canonical = camera_recognition_mode(c)
    if canonical == LOCAL_ONLY:
        recog = "FASTALPR_ONLY"
        plate_engine = "fastalpr"
    elif canonical == NATIVE_ONLY:
        recog = "NATIVE_ONLY"
        plate_engine = "native"
    else:
        recog = "HYBRID"
        plate_engine = "fastalpr"
    return {
        "id": c.id, "name": c.name, "ip_address": c.ip_address, "sdk_port": c.sdk_port,
        "site_id": getattr(c, "site_id", None) or DEFAULT_SITE_ID,
        "username": c.username, "gate_id": c.gate_id, "gate_name": lane_name,
        # Secret-store references are internal implementation details. They
        # are not credentials, but returning them teaches a node how the
        # server stores camera secrets and is unnecessary for the UI. The
        # camera password is never returned.
        "password_configured": bool(c.has_password()) if hasattr(c, "has_password") else False,
        "lane_name": lane_name or "",
        "side": side_label(c.lane_direction),
        "lane_direction": c.lane_direction,
        "controller_ip": c.controller_ip or "",
        "display_ip": c.display_ip or "",
        "adapter_id": camera_adapter_id(c),
        "connection_mode": camera_connection_mode(c),
        "native_plates": native,
        "plate_engine": plate_engine,
        "recognition_mode": recog,
        "camera_type": getattr(c, "camera_type", None) or camera_type_for(camera_adapter_id(c), native_plates=native),
        "vendor": getattr(c, "vendor", None) or "",
        "model_name": getattr(c, "model_name", None) or "",
        "serial": getattr(c, "serial", None) or "",
        "timezone": getattr(c, "timezone", None) or "",
        # Embedded RTSP credentials never leave the API; PATCH accepts the masked
        # form back unchanged (see update_camera).
        "rtsp_url": redact_text(c.rtsp_url or ""), "status": c.status, "sdk_handle": c.sdk_handle,
        "ffmpeg_profile": getattr(c, "ffmpeg_profile", None) or settings.ffmpeg_profile,
        "rtsp_transport": getattr(c, "rtsp_transport", None) or settings.rtsp_transport,
        "stream_profiles": public_profiles(getattr(c, "stream_profiles", None) or {}),
        "framing": framing_from_profiles(getattr(c, "stream_profiles", None)),
        "media_capabilities": list(getattr(c, "media_capabilities", None) or []),
        "onvif": _camera_onvif_brief(c),
        "media": _camera_media_brief(c.id),
        "operator": {
            "camera": "Online" if c.status in (CameraStatus.SDK_CONNECTED.value, CameraStatus.VIDEO_CONNECTED.value) else "Offline",
        },
        "last_error": c.last_error, "last_seen_at": c.last_seen_at, "enabled": c.enabled,
        # The Site Server may expose all records for management, but the
        # browser must not automatically open another node's local producer.
        # Direct media endpoints enforce the same boundary independently.
        "stream_allowed": bool(camera_active_on_this_installation(c, db=db)),
    }


def _management_camera_rows(db: Session) -> list[Camera]:
    """Rows visible in this installation's camera management plane."""
    from app.services.node_scope import camera_visible_in_management

    rows = db.scalars(
        select(Camera).options(joinedload(Camera.gate)).order_by(Camera.id)
    ).all()
    return [camera for camera in rows if camera_visible_in_management(camera, db=db)]


def _camera_onvif_brief(c: Camera) -> dict:
    """Public-safe ONVIF summary (no credentials in URIs)."""
    profile = dict(getattr(c, "onvif_profile", None) or {})
    if not profile:
        return {}
    caps = dict(profile.get("capabilities") or {})
    from app.services import onvif_runtime
    return {
        "media_version": profile.get("media_version") or 0,
        "media2": bool(caps.get("media2")),
        "events": bool(caps.get("events")),
        "profile_m": bool(caps.get("profile_m")),
        "plate_metadata": bool(caps.get("plate_metadata")),
        "plate_topics": list(caps.get("plate_topics") or [])[:10],
        "snapshot_uri": profile.get("snapshot_uri_redacted") or "",
        "events_enabled": bool(profile.get("events_enabled")),
        "events_url_present": bool(profile.get("events_url")),
        "discovered_at": profile.get("discovered_at"),
        "poller": onvif_runtime.stats_for(c.id),
    }


def _camera_media_brief(camera_id: int) -> dict:
    from app.services.media_gateway import gateway
    row = gateway.session(camera_id)
    if row is None:
        return {"connection_state": "DISCONNECTED", "viewers": viewers_for(camera_id), "frozen": False}
    health = gateway.health_sync(camera_id)
    return {
        "connection_state": health.get("connection_state") or "DISCONNECTED",
        "viewers": viewers_for(camera_id),
        "live_frame_age_ms": health.get("live_frame_age_ms"),
        "ai_frame_age_ms": health.get("ai_frame_age_ms"),
        "detect_frame_age_ms": health.get("detect_frame_age_ms"),
        "fps": health.get("fps") or 0,
        "ai_fps": health.get("ai_processed_fps") or 0,
        "codec": health.get("codec") or "",
        "transport": health.get("transport") or "",
        "ffmpeg_profile": health.get("ffmpeg_profile") or "",
        "reconnects": health.get("reconnects") or 0,
        "warnings": list(health.get("warnings") or []),
        "frozen": bool(health.get("frozen")),
        "duplicate_frames": int(health.get("duplicate_frames") or 0),
        "frames_changed": int(health.get("frames_changed") or 0),
        "frames_received": int(health.get("frames_received") or 0),
        "queue_depth": health.get("queue_depth") or 0,
        "detect_queue_depth": health.get("detect_queue_depth") or 0,
        "decoder_restarts": int(health.get("decoder_restarts") or 0),
        "source_fps": health.get("source_fps") or 0,
    }


def gate_dict(g: Gate):
    cameras = list(g.cameras or [])
    return {
        "id": g.id, "name": g.name, "mode": g.mode, "enabled": g.enabled,
        "physical_control_verified": g.physical_control_verified,
        "cameras": [
            {
                "id": c.id,
                "name": c.name,
                "ip_address": c.ip_address,
                "lane_name": g.name,
                "side": side_label(c.lane_direction),
                "lane_direction": c.lane_direction,
                "controller_ip": c.controller_ip or "",
                "display_ip": c.display_ip or "",
                "status": c.status,
            }
            for c in cameras
        ],
    }


def commit_or_conflict(db: Session, message: str):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # Do not hide PostgreSQL foreign-key/site failures behind the old
        # duplicate-name message.  The browser displays this detail and the
        # redacted constraint is also written to the Site Service log, making
        # failed manual commissioning diagnosable on Windows.
        detail = str(getattr(exc, "orig", None) or exc).replace("\n", " ")[:500]
        log.warning("database integrity conflict: %s; detail=%s", message, detail)
        lowered = detail.lower()
        if "duplicate" in lowered or "unique" in lowered:
            raise HTTPException(409, message)
        if "foreign key" in lowered or "violates" in lowered:
            raise HTTPException(409, "Camera references a site or gate that no longer exists. Refresh the gates and try again.")
        raise HTTPException(409, f"Could not save camera: {detail}")


def get_camera_or_404(db: Session, camera_id: int) -> Camera:
    c = db.get(Camera, camera_id)
    if not c:
        raise HTTPException(404, "Camera not found")
    return c


async def live_snapshot(c: Camera) -> dict:
    return await snapshot_for_camera(
        c.id,
        c.ip_address,
        c.username,
        c.password_secret,
        c.rtsp_url,
        sdk_handle=c.sdk_handle,
        adapter_id=c.adapter_id,
    )


def get_gate_or_404(db: Session, gate_id: int) -> Gate:
    g = db.get(Gate, gate_id)
    if not g:
        raise HTTPException(404, "Gate not found")
    return g
