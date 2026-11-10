from __future__ import annotations

def _health_paths():
    """Return shared and Windows per-user heartbeat locations.

    Some Windows upgrades preserve an ACL that blocks the scheduled-task
    account from replacing a ProgramData file. The per-user fallback keeps
    ownership observable while the installer repairs the shared directory.
    """
    from app.config import settings

    primary = settings.data_dir / "recognition-worker.json"
    if os.name != "nt":
        return (primary,)
    local_appdata = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    fallback = local_appdata / "SmartParkEdge" / "recognition-worker.json"
    return (primary, fallback) if fallback != primary else (primary,)

def worker_health() -> dict:
    """Read a process-safe heartbeat; stale/missing files never confer ownership."""
    from app.config import settings

    candidates = []
    for path in _health_paths():
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(body, dict) and isinstance(body.get("cameras"), list):
                candidates.append(body)
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    if not candidates:
        return {"ok": False, "enabled": False, "cameras": [], "state": "OFFLINE"}
    def _timestamp(item: dict) -> float:
        try:
            value = float(item.get("updated_at", 0) or 0)
        except (TypeError, ValueError):
            return 0.0
        return value if value >= 0 else 0.0

    body = max(candidates, key=_timestamp)
    age = time.time() - _timestamp(body)
    healthy = bool(body.get("enabled")) and 0 <= age <= 6.0
    return {**body, "ok": healthy, "heartbeat_age_seconds": round(age, 2)}

def _worker_ready(camera_id: int) -> bool:
    from app.config import settings

    health = worker_health()
    if not health.get("ok"):
        return False
    for row in health.get("cameras") or []:
        if not isinstance(row, dict):
            continue
        if row.get("camera_id") == camera_id and row.get("state") == "READY":
            try:
                age = time.time() - float(row.get("last_frame_at") or 0)
                inference_age = time.time() - float(row.get("last_inference_at") or 0)
            except (TypeError, ValueError):
                return False
            return (0 <= age <= settings.stale_stream_seconds
                    and 0 <= inference_age <= max(6.0, settings.alpr_timeout_seconds))
    return False

def _worker_claim_has_live_frames(camera_id: int, health: dict) -> bool:
    """Keep ownership with a stalled worker while its decoder is still live.

    The worker reports ``STALLED`` while a slow/native inference call drains.
    Falling back in that window starts a second ONNX owner and makes both
    recognition and camera timing worse. A transitional claim is accepted only
    when the worker has actually delivered a recent frame; a frame-less worker
    still permits the Site Service fallback.
    """
    from app.config import settings

    if not health.get("ok"):
        return False
    claimed = {int(value) for value in (health.get("claimed_camera_ids") or []) if str(value).isdigit()}
    if int(camera_id) not in claimed:
        return False
    for row in health.get("cameras") or []:
        if not isinstance(row, dict) or int(row.get("camera_id") or -1) != int(camera_id):
            continue
        if str(row.get("state") or "") not in {"STREAMING", "STALLED", "DEGRADED"}:
            return False
        try:
            age = time.time() - float(row.get("last_frame_at") or 0)
        except (TypeError, ValueError):
            return False
        return 0 <= age <= 2.0 * max(float(settings.stale_stream_seconds), 2.0)
    return False

def worker_owns_software_reads(camera_id: int) -> bool:
    """True when this worker, not the Site Service loop, should run FastALPR."""
    camera_id = int(camera_id)
    cached = _owns_cache.get(camera_id)
    now = time.monotonic()
    if cached is not None and (now - cached[0]) < 1.0:
        return cached[1]
    from app.db import SessionLocal
    from app.infrastructure.media.registry import mediamtx_detect_active
    from app.services.flags import flags

    health = worker_health()
    with SessionLocal() as db:
        from app.models import Camera
        camera = db.get(Camera, camera_id)
        from app.services.developer import recognition_enabled
        enabled = (bool(flags(db).get("fastalpr_new_pipeline_enabled"))
                   and recognition_enabled(db)
                   and camera is not None and _software_camera(camera, db)
                   and mediamtx_detect_active(camera_id, db)
                   and (_worker_ready(camera_id) or _worker_claim_has_live_frames(camera_id, health)))
    _owns_cache[camera_id] = (now, enabled)
    return enabled

def _camera_rows() -> list[dict]:
    from app.db import SessionLocal
    from app.models import Camera
    from app.services.flags import media_mtx_for_camera
    from app.infrastructure.media.registry import _sdk_camera
    from app.services.site_policy import site_policy

    rows: list[dict] = []
    with SessionLocal() as db:
        for camera in db.query(Camera).filter(Camera.enabled == True).all():  # noqa: E712
            if _sdk_camera(int(camera.id), db):
                continue
            if not media_mtx_for_camera(int(camera.id), db) or not _software_camera(camera, db):
                continue
            from app.services.node_scope import camera_active_on_this_installation
            if not camera_active_on_this_installation(camera, db=db):
                continue
            from app.services.ocr_policy import camera_recognition_mode

            from app.services.camera_framing import framing_from_profiles

            profiles = dict(camera.stream_profiles or {})
            framing = framing_from_profiles(profiles)
            rows.append({
                "id": int(camera.id),
                "lane_direction": str(camera.lane_direction or "ENTRY"),
                "name": str(camera.name or ""),
                "lane_id": camera.lane_id,
                "site_id": camera.site_id,
                "plate_policy": site_policy(db),
                "recognition_mode": camera_recognition_mode(camera),
                "detect_roi": framing["detect_roi"],
                "detect_zoom": framing["detect_zoom"],
            })
    return rows

def _write_health(body: dict) -> None:
    from app.config import settings

    from app.services.process_metrics import snapshot
    body["resources"] = {**snapshot(), "decoder_count": sum(bool(row.get("decoder_pid")) for row in body.get("cameras", []))}
    paths = _health_paths()
    # Windows can have the previous fixed ``recognition-worker.tmp`` held by
    # a second scheduled worker or by a health reader.  A unique temp file
    # prevents one stale process from crashing the recognition worker; if the
    # final replace is temporarily denied, keep the last good heartbeat and
    # let the next loop retry.
    last_error = None
    for path in paths:
        temporary: str | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix="recognition-worker-", suffix=".tmp", dir=str(path.parent))
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({**body, "updated_at": time.time()}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            temporary = None
            return
        except (OSError, PermissionError) as exc:
            last_error = exc
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
    if last_error is not None:
        log.warning("recognition health write skipped: %s", last_error)

def _configure_worker_runtime() -> bool:
    """Apply the installed deployment before importing the ORM/model graph.

    The Site and Media services already do this. The recognition worker is a
    separate process, so without the same step it silently opens the default
    SQLite database even when the setup wizard selected another database.
    """
    from app.database_config import apply_runtime_database_config
    from app.deployment import load_deployment_config
    from app.config import settings

    deployment = load_deployment_config()
    if not getattr(deployment, "runs_local_gate_runtime", getattr(deployment, "is_server", False)) or not deployment.configured:
        print("Recognition Worker is disabled until a configured Site Server exists.", file=sys.stderr)
        return False
    apply_runtime_database_config(deployment.database)
    os.environ.setdefault("SMARTPARK_ALPR_CACHE_DIR", str(settings.data_dir / "model-cache"))
    return True

def _warmup_retry_delay(failures: int) -> float:
    """Bound detector retry pressure while retaining eventual recovery."""
    return min(60.0, float(2 ** min(max(1, int(failures)), 6)))

def _fatal_native_load_error(exc: BaseException) -> bool:
    """A broken ORT/DLL load cannot recover by re-importing in this process."""
    detail = f"{type(exc).__name__}: {exc}".lower()
    return isinstance(exc, (ImportError, OSError)) and (
        "onnxruntime" in detail or "dll load failed" in detail or "pybind11_state" in detail
    )
