def validate_gate_mode(mode: str) -> str:
    allowed = {item.value for item in GateMode}
    if mode not in allowed:
        raise HTTPException(400, f"Invalid gate mode. Use one of: {', '.join(sorted(allowed))}")
    return mode


@app.get("/cameras/{camera_id}")
def get_camera(camera_id: int, db: Session = Depends(get_db), _: User = Depends(require("cameras.view"))):
    return camera_dict(_camera_for_node(db, camera_id, action="camera-read"), db=db)


@app.post("/cameras")
def create_camera(payload: CameraCreate, db: Session = Depends(get_db), user: User = Depends(require("cameras.manage"))):
    # Camera rows are site-scoped in PostgreSQL.  Do this at the boundary as
    # well as during application startup so manual adds also work when a
    # service was started from a maintenance command or a partially upgraded
    # database.
    from app.services.topology import ensure_default_site

    site = ensure_default_site(db)
    node_gate_ids = _processing_node_gate_ids(db)
    requested_gate_id = payload.gate_id
    if node_gate_ids:
        if requested_gate_id is None and len(node_gate_ids) == 1:
            requested_gate_id = next(iter(node_gate_ids))
        if requested_gate_id is not None and int(requested_gate_id) not in node_gate_ids:
            raise HTTPException(403, "A Processing Node can add cameras only to its assigned gate.")
        if requested_gate_id is None:
            raise HTTPException(409, "Select one of this node's assigned gates for the camera.")
    gate = None
    if requested_gate_id is not None:
        gate = get_gate_or_404(db, requested_gate_id)
        if int(gate.site_id or DEFAULT_SITE_ID) != int(site.id):
            raise HTTPException(409, "Selected gate belongs to a different site. Refresh the gate list and try again.")
    if str(getattr(settings, "deployment_profile", "DEVELOPMENT")).upper() != "DEVELOPMENT" and (payload.password or "").strip().lower() in {"", "admin"}:
        raise HTTPException(422, "Set the real camera password before adding cameras in a non-development deployment.")
    c = Camera(
        name=payload.name, ip_address=payload.ip_address, sdk_port=payload.sdk_port,
        username=payload.username, password_secret=payload.password or settings.default_camera_password, gate_id=requested_gate_id,
        site_id=int(gate.site_id if gate is not None else site.id),
        lane_direction=payload.lane_direction, controller_ip=payload.controller_ip, display_ip=payload.display_ip,
        rtsp_url=payload.rtsp_url, adapter_id=payload.adapter_id or "hvx",
        connection_mode=(payload.connection_mode or "DIRECT").upper(),
        ffmpeg_profile=payload.ffmpeg_profile or settings.ffmpeg_profile,
        rtsp_transport=(payload.rtsp_transport or settings.rtsp_transport).upper(),
        stream_profiles=payload.stream_profiles or {},
        recognition_mode=(payload.recognition_mode or "").strip().upper(),
        vendor=payload.vendor or "",
        model_name=payload.model_name or "",
        serial=payload.serial or "",
        timezone=payload.timezone or "",
        camera_type=payload.camera_type or "",
        status=CameraStatus.DISCOVERED.value,
    )
    db.add(c)
    commit_or_conflict(db, "A camera with that name already exists")
    db.refresh(c)
    write_audit(db, user, "camera.create", "camera", str(c.id), f"Created {c.name} {c.ip_address}")
    return camera_dict(c, db=db)


@app.patch("/cameras/{camera_id}")
def update_camera(camera_id: int, payload: CameraUpdate, db: Session = Depends(get_db), user: User = Depends(require("cameras.manage"))):
    c = _camera_mutation_for_node(db, camera_id, action="camera-update")
    node_gate_ids = _processing_node_gate_ids(db)
    data = payload.model_dump(exclude_unset=True)
    if data.get("password") in (None, ""):
        data.pop("password", None)
    else:
        data["password_secret"] = data.pop("password")
    if "rtsp_url" in data and data["rtsp_url"] and data["rtsp_url"] == redact_text(c.rtsp_url or ""):
        data.pop("rtsp_url")  # masked value round-tripped from the edit form; keep the stored URL
    if node_gate_ids and "gate_id" in data and data["gate_id"] in (None, "", 0, "0"):
        raise HTTPException(403, "A Processing Node cannot remove a camera from its assigned gate.")
    if node_gate_ids and "gate_id" in data and int(data["gate_id"]) not in node_gate_ids:
        raise HTTPException(403, "A Processing Node cannot move a camera to another gate.")
    if "gate_id" in data and data["gate_id"] is not None:
        gate = get_gate_or_404(db, data["gate_id"])
        if int(gate.site_id or DEFAULT_SITE_ID) != int(c.site_id or DEFAULT_SITE_ID):
            raise HTTPException(409, "Selected gate belongs to a different site. Refresh the gate list and try again.")
    if data.get("adapter_id"):
        data["adapter_id"] = str(data["adapter_id"]).strip().lower()
    if data.get("connection_mode"):
        data["connection_mode"] = str(data["connection_mode"]).strip().upper()
        if data["connection_mode"] not in {"DIRECT", "EDGE_AGENT"}:
            raise HTTPException(400, "connection_mode must be DIRECT or EDGE_AGENT")
    if data.get("ffmpeg_profile"):
        from app.services.ffmpeg_profiles import normalize_profile
        data["ffmpeg_profile"] = normalize_profile(data["ffmpeg_profile"])
    if data.get("rtsp_transport"):
        from app.services.ffmpeg_profiles import normalize_transport
        data["rtsp_transport"] = normalize_transport(data["rtsp_transport"])
    if data.get("recognition_mode"):
        data["recognition_mode"] = str(data["recognition_mode"]).strip().upper()
    if data.get("stream_profiles"):
        from app.services.stream_roles import merge_profiles
        data["stream_profiles"] = merge_profiles(c.stream_profiles, data["stream_profiles"])
    for k, v in data.items():
        setattr(c, k, v)
    commit_or_conflict(db, "A camera with that name already exists")
    db.refresh(c)
    write_audit(db, user, "camera.update", "camera", str(c.id), "Camera settings updated")
    return camera_dict(c, db=db)


@app.delete("/cameras/{camera_id}")
async def delete_camera(camera_id: int, db: Session = Depends(get_db), user: User = Depends(require("cameras.manage"))):
    c = _camera_mutation_for_node(db, camera_id, action="camera-delete")
    name = c.name
    ref = getattr(c, "credentials_ref", "") or ""
    # Removing a row must also release its physical/session owners. Otherwise
    # an SDK handle, decoder, or MediaMTX path can survive as an orphan.
    try:
        from app.services.mediamtx_detect import stop_detect_consumer
        from app.services.mediamtx_live import stop_live_consumer
        from app.services.media_gateway import gateway
        detect_task = stop_detect_consumer(c.id)
        live_task = stop_live_consumer(c.id)
        await asyncio.gather(
            *(task for task in (detect_task, live_task) if task is not None),
            return_exceptions=True,
        )
        gateway.stop_producer(c.id, force=True)
        await gateway.unregister_stream(c.id)
        if c.sdk_handle is not None:
            try:
                await HVXHostClient().disconnect(int(c.sdk_handle), force=True)
            except Exception as exc:
                log.warning("camera %s SDK disconnect during delete failed: %s", c.id, exc)
        from app.infrastructure.media.registry import unregister_camera_source
        unregister_camera_source(c.id)
    except Exception as exc:
        # Cleanup is best effort: an unavailable host/sidecar must not prevent
        # removal of a stale camera record.
        log.warning("camera %s media cleanup failed during delete: %s", c.id, exc)
    try:
        db.delete(c)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        detail = str(getattr(exc, "orig", None) or exc).replace("\n", " ")[:500]
        log.warning("camera delete blocked camera_id=%s: %s", camera_id, detail)
        raise HTTPException(
            409,
            "This camera has parking history and cannot be deleted. Disable it or edit its address instead.",
        ) from None
    if ref:
        from app.infrastructure.secrets import secret_store
        try:
            secret_store().delete(ref)
        except Exception as exc:
            log.warning("camera %s: could not delete stored credential %s: %s", camera_id, ref, exc)
    write_audit(db, user, "camera.delete", "camera", str(camera_id), f"Deleted {name}")
    return {"ok": True}


@app.get("/hardware/hvx/info")
async def hvx_info(_: User = Depends(require("hardware.view"))):
    package = vendor_inventory()
    alpr = alpr_status()
    try:
        host = await HVXHostClient().info()
    except HVXHostUnavailable as exc:
        host = {"available": False, "error": str(exc)}
    return {
        "available": bool(host.get("available")),
        "vendor_sdk_loaded": bool(host.get("available")),
        "vendor_package": package,
        "host": host,
        "alpr": alpr,
        "states": {
            "vendor_package_present": package["present"] and not package["missing"],
            "vendor_sdk_x86": bool(package.get("pe", {}).get("x86")),
            "sdk_host_reachable": bool(host.get("available")),
            "fastalpr_installed": alpr["installed"],
        },
        "edge_agent": edge_agent_status(),
    }


@app.get("/devices")
def list_registered_devices(db: Session = Depends(get_db), _: User = Depends(require("hardware.view"))):
    """Projection of cameras/gates. Not a second hardware store."""
    devices = devices_as_dicts(db)
    from app.services.node_scope import is_processing_node
    node_gate_id = _processing_node_gate_id(db, required=False)
    if is_processing_node():
        devices = [row for row in devices if int(row.get("gate_id") or 0) == node_gate_id]
    return {"devices": devices, "edge_agent": edge_agent_status()}


@app.get("/camera-adapters")
def camera_adapter_catalog(_: User = Depends(require("cameras.view"))):
    """Return the installed camera-engine adapters and their ownership model."""
    from app.infrastructure.hardware.cameras import adapter_catalog

    return {
        "adapters": adapter_catalog(),
        "contract": {
            "control": ["connect", "disconnect", "health", "capabilities"],
            "media": ["live_sources", "latest_frame", "snapshot"],
            "recognition": "FastALPR remains application-side unless an adapter reports native plate events",
            "isolation": "Native vendor SDKs run behind a bounded host/process boundary",
        },
    }


@app.post("/cameras/{camera_id}/sdk/connect")
async def sdk_connect(camera_id: int, db: Session = Depends(get_db), user: User = Depends(require("cameras.connect"))):
    c = _camera_for_node(db, camera_id, action="sdk-connect")
    from app.services.developer import camera_connections_enabled
    if not camera_connections_enabled(db):
        raise HTTPException(409, "Developer mode has camera connections disabled. No SDK connection was opened.")
    return await apply_camera_connect(c, db, user, raise_on_host_error=False)


@app.post("/cameras/{camera_id}/sdk/disconnect")
async def sdk_disconnect(camera_id: int, db: Session = Depends(get_db), user: User = Depends(require("cameras.connect"))):
    c = _camera_for_node(db, camera_id, action="sdk-disconnect")
    if not c: raise HTTPException(404, "Camera not found")
    if c.sdk_handle is not None:
        try: await HVXHostClient().disconnect(c.sdk_handle, force=True)
        except Exception: pass
    release_detect(c.id)
    stop_live_pump(c.id)
    from app.services.media_gateway import gateway
    try:
        await gateway.unregister_stream(c.id)
    except Exception:
        pass
    c.sdk_handle = None
    c.status = CameraStatus.DISCOVERED.value
    db.commit()
    write_audit(db, user, "camera.sdk_disconnect", "camera", str(c.id), "Disconnected SDK session")
    return camera_dict(c)


async def _read_upload_limited(file: UploadFile, *, maximum_bytes: int = 12 * 1024 * 1024) -> bytes:
    """Read an image upload with a hard memory bound."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(min(1024 * 1024, maximum_bytes - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > maximum_bytes:
            raise HTTPException(413, "Image upload is too large")
        chunks.append(chunk)
    return b"".join(chunks)


def _require_development_simulation() -> None:
    if str(getattr(settings, "deployment_profile", "DEVELOPMENT") or "DEVELOPMENT").upper() != "DEVELOPMENT":
        raise HTTPException(404, "Simulation endpoints are disabled outside the development profile")


@app.post("/cameras/{camera_id}/rtsp/probe")
async def rtsp_probe(camera_id: int, db: Session = Depends(get_db), _: User = Depends(require("cameras.connect"))):
    c = _camera_for_node(db, camera_id, action="rtsp-probe")
    sdk = await _sdk_probe_status(c)
    http = await grab_http_snapshot(c.ip_address, c.username, c.password_secret)
    if http.get("ok"):
        persist_video(db, c)
    results=[]
    for url in vendor_candidates(c.ip_address, c.username, c.password_secret, c.rtsp_url):
        r=await probe(url)
        results.append(r.__dict__)
        if r.ok:
            c.rtsp_url=url
            from app.services.stream_roles import default_capabilities, recommend_roles
            c.stream_profiles = recommend_roles([{
                "uri": url,
                "protocol": "rtsp",
                "codec": r.codec or "",
                "width": r.width or 0,
                "height": r.height or 0,
                "fps": r.fps or 0,
            }])
            c.media_capabilities = default_capabilities(native_alpr=c.sdk_handle is not None, sdk=c.sdk_handle is not None, rtsp=True)
            if c.status == CameraStatus.SDK_CONNECTED.value:
                c.status=CameraStatus.VIDEO_CONNECTED.value
            db.commit()
            try:
                from app.services.mediamtx_sources import sync_camera
                sync_camera(c, db=db)
            except Exception:
                pass
            break
    return {
        "camera_id": c.id,
        "note": (
            "MediaMTX uses the detected RTSP stream for live video and FastALPR. "
            "The vendor SDK remains connected for camera events, configuration, and gate I/O."
        ),
        "sdk": sdk,
        "http": {k: v for k, v in http.items() if k != "jpeg"},
        "results": results,
    }


@app.get("/cameras/{camera_id}/streams")
async def camera_streams(camera_id: int, db: Session = Depends(get_db), _: User = Depends(require("cameras.view"))):
    c = _camera_for_node(db, camera_id, action="stream-telemetry")
    from app.services.media_gateway import gateway
    from app.services.stream_roles import profile_warnings, public_profiles
    from app.services.ffmpeg_profiles import list_profiles
    profiles = getattr(c, "stream_profiles", None) or {}
    health = await gateway.health(c.id)
    from app.infrastructure.media import registry as media_registry
    live_endpoint = await media_registry.get_live_endpoint(c.id, db)
    detect_endpoint = await media_registry.get_detect_endpoint(c.id, db)
    evidence_endpoint = await media_registry.get_evidence_endpoint(c.id, db)
    mediamtx_telemetry = (
        media_registry.media_telemetry(c.id)
        if media_registry.mediamtx_detect_active(c.id, db) or media_registry.mediamtx_live_active(c.id, db)
        else None
    )
    warnings = profile_warnings(profiles, upstream_consumers=1 if health.get("pumping") else 0)
    if mediamtx_telemetry:
        compat = mediamtx_telemetry.get("webrtc") or {}
        if compat.get("compatible") is False and compat.get("reason"):
            warnings.append(str(compat["reason"]))
        for role, row in (mediamtx_telemetry.get("roles") or {}).items():
            lost = int(((row.get("rtp") or {}).get("packets_lost")) or 0)
            if lost:
                warnings.append(f"{role}: {lost} RTP packets lost")
    return {
        "camera": camera_dict(c),
        "ffmpeg_profile": getattr(c, "ffmpeg_profile", None) or settings.ffmpeg_profile,
        "rtsp_transport": getattr(c, "rtsp_transport", None) or settings.rtsp_transport,
        "stream_profiles": public_profiles(profiles),
        "media_capabilities": list(getattr(c, "media_capabilities", None) or []),
        "warnings": warnings,
        "media": {**health, "mediamtx": mediamtx_telemetry},
        "profiles": list_profiles(),
        "live_url": f"/cameras/{c.id}/live.mjpeg",
        "main_url": f"/cameras/{c.id}/live.mjpeg?role=MAIN",
        "live_endpoint": live_endpoint,
        "detect": detect_endpoint,
        "evidence": evidence_endpoint,
    }


@app.patch("/cameras/{camera_id}/streams")
async def update_camera_streams(
    camera_id: int,
    payload: StreamProfilesUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require("cameras.manage")),
):
    c = _camera_for_node(db, camera_id, action="stream-profile-update")
    from app.services.ffmpeg_profiles import normalize_profile, normalize_transport
    from app.services.stream_roles import ROLE_DETECT, ROLE_LIVE, merge_profiles
    if payload.ffmpeg_profile:
        c.ffmpeg_profile = normalize_profile(payload.ffmpeg_profile)
    if payload.rtsp_transport:
        c.rtsp_transport = normalize_transport(payload.rtsp_transport)
    profiles = dict(c.stream_profiles or {})
    if payload.stream_profiles:
        profiles = merge_profiles(profiles, payload.stream_profiles)
    if payload.live_role:
        profiles[ROLE_LIVE] = {**(profiles.get(ROLE_LIVE) or {}), "source": payload.live_role.upper(), "role": ROLE_LIVE}
    if payload.detect_source:
        profiles[ROLE_DETECT] = {**(profiles.get(ROLE_DETECT) or {}), "source": payload.detect_source.upper(), "role": ROLE_DETECT}
    if payload.ai_fps is not None:
        profiles[ROLE_DETECT] = {**(profiles.get(ROLE_DETECT) or {}), "ai_fps": payload.ai_fps, "role": ROLE_DETECT}
    c.stream_profiles = profiles
    db.commit()
    write_audit(db, user, "camera.streams", "camera", str(c.id), f"profile={c.ffmpeg_profile} transport={c.rtsp_transport}")
    spec = _live_spec(c)
    if pumping_spec(c.id) is not None or viewers_for(c.id) > 0:
        start_live_pump(spec)
    return await camera_streams(c.id, db)


@app.put("/cameras/{camera_id}/framing")
def update_camera_framing(
    camera_id: int,
    payload: CameraFramingUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require("cameras.manage")),
):
    """Save the detection zone and zoom for any camera, not only HVX/OcxConfig."""
    from app.services.camera_framing import apply_framing, framing_from_profiles

    camera = _camera_for_node(db, camera_id, action="framing-update")
    try:
        camera.stream_profiles = apply_framing(
            camera.stream_profiles,
            detect_roi=payload.detect_roi,
            detect_zoom=payload.detect_zoom,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.commit()
    write_audit(db, user, "camera.framing", "camera", str(camera.id), payload.detect_roi or "site default")
    return {"camera": camera_dict(camera), "framing": framing_from_profiles(camera.stream_profiles)}


@app.post("/cameras/{camera_id}/onvif/discover")
async def camera_onvif_discover(camera_id: int, db: Session = Depends(get_db), user: User = Depends(require("cameras.connect"))):
    c = _camera_for_node(db, camera_id, action="onvif-discover")
    from app.services.stream_discover import discover_camera_streams
    from app.services.stream_roles import merge_profiles
    from app.services.onvif_profile import apply_discovery
    found = await discover_camera_streams(c.ip_address, c.username, c.password_secret, c.rtsp_url or "")
    if found.get("stream_profiles"):
        c.stream_profiles = merge_profiles(c.stream_profiles, found["stream_profiles"])
    apply_discovery(c, found.get("onvif") or {})
    db.commit()
    write_audit(db, user, "camera.onvif_discover", "camera", str(c.id), found.get("source") or "")
    from app.services.stream_roles import public_profiles
    public = {k: v for k, v in found.items() if k not in {"onvif", "discovered", "stream_profiles"}}
    public["discovered"] = _strip_credential_uris(found.get("discovered") or [])
    public["stream_profiles"] = public_profiles(found.get("stream_profiles") or {})
    public["onvif"] = _public_onvif_discovery(found.get("onvif") or {})
    return {"camera": camera_dict(c), **public}


def _strip_credential_uris(rows: list) -> list:
    return [{k: v for k, v in dict(row).items() if k not in {"uri", "url", "snapshot_uri"}} for row in rows]


def _public_onvif_discovery(onvif: dict) -> dict:
    """Discovery payload without credential-bearing URIs."""
    out = {k: v for k, v in onvif.items() if k not in {"profiles", "snapshot_uri"}}
    out["profiles"] = _strip_credential_uris(onvif.get("profiles") or [])
    return out


@app.patch("/cameras/{camera_id}/onvif/events")
async def camera_onvif_events_toggle(camera_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require("cameras.connect"))):
    """Enable/disable Profile M plate-event pulling for a camera that advertises it."""
    c = _camera_for_node(db, camera_id, action="onvif-events-toggle")
    from app.services.onvif_profile import set_events_enabled
    try:
        set_events_enabled(c, bool(payload.get("enabled")))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    db.commit()
    write_audit(db, user, "camera.onvif_events", "camera", str(c.id), "on" if payload.get("enabled") else "off")
    return camera_dict(c)


@app.post("/cameras/{camera_id}/onvif/events/pull")
async def camera_onvif_events_pull(camera_id: int, db: Session = Depends(get_db), user: User = Depends(require("cameras.connect"))):
    """Hardware-lab diagnostic: one subscribe → pull → unsubscribe round trip."""
    c = _camera_for_node(db, camera_id, action="onvif-events-pull")
    profile = dict(c.onvif_profile or {})
    events_url = str(profile.get("events_url") or "")
    if not events_url:
        raise HTTPException(409, "Camera did not advertise an ONVIF Events service; run ONVIF discovery first.")
    from app.services.onvif_events import ONVIFPullPoint, event_to_capture
    from app.services.onvif_discover import ONVIFError
    pullpoint = ONVIFPullPoint(events_url, c.username or "", c.password_secret or "", timeout=6.0)
    try:
        await pullpoint.subscribe()
        events = await pullpoint.pull(wait="PT3S", limit=20)
    except ONVIFError as exc:
        raise HTTPException(502, str(exc))
    finally:
        await pullpoint.unsubscribe()
    write_audit(db, user, "camera.onvif_events_pull", "camera", str(c.id), f"{len(events)} messages")
    return {
        "ok": True,
        "messages": len(events),
        "events": [{**e, "capture": event_to_capture(e)} for e in events[:20]],
    }


@app.get("/media/gateway")
async def media_gateway_health(db: Session = Depends(get_db), _: User = Depends(require("hardware.view"))):
    from app.services.media_gateway import gateway
    from app.services.ffmpeg_profiles import list_profiles
    from app.services.hw_decode import detect_decode_path
    from app.services import mediamtx
    from app.services.flags import flags as migration_flags
    sessions = gateway.live_metrics()
    pids = gateway.child_pids()
    mediamtx_health = mediamtx.health()
    mediamtx_paths: dict = {}
    if mediamtx_health.get("running"):
        try:
            from app.services.mediamtx_telemetry import refresh as mediamtx_refresh
            mediamtx_paths = dict(mediamtx_refresh().get("paths") or {})
        except Exception as exc:
            mediamtx_paths = {"error": str(exc)[:200]}
    return {
        "cameras": sessions,
        "child_pids": pids,
        "ffmpeg_profiles": list_profiles(),
        "decode": await detect_decode_path(),
        "local": {"sessions": sessions, "child_pids": pids},
        "mediamtx": mediamtx_health,
        "mediamtx_paths": mediamtx_paths,
        "flags": migration_flags(db),
        "rollback": {
            "live_view_provider": ["DIRECT_LEGACY", "MEDIAMTX"],
            "recognition_pipeline": ["FASTALPR_LEGACY", "FASTALPR_NEW"],
        },
    }
