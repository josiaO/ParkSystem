"""SmartParkMediaService — optional MediaMTX owner. Parking does not depend on this process."""

from __future__ import annotations

import sys
import time
import json
import logging

log = logging.getLogger("smartpark")


def _service_step() -> dict:
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models import Camera, SiteSetting
    from app.services import mediamtx

    with SessionLocal() as db:
        db.execute(select(Camera).limit(0))
        db.execute(select(SiteSetting).limit(0))
    cfg = _effective_flags()
    if not cfg.get("media_gateway_enabled"):
        mediamtx.stop()
        return {"state": "DISABLED"}
    if not mediamtx.available():
        return {"state": "BINARY_MISSING"}
    synced = _sync_cameras_from_db()
    if not mediamtx.running():
        mediamtx.start()
    return {"state": "RUNNING" if mediamtx.running() else "START_FAILED", "cameras": synced,
            "last_error": mediamtx.health().get("last_error") or ""}


def _write_status(status: dict) -> None:
    from app.config import settings
    from app.db import engine
    from app.services.redaction import redact_text

    status = {**status, "updated_at": time.time(), "data_directory": str(settings.data_dir),
              "database": redact_text(engine.url.render_as_string(hide_password=True))}
    temporary = settings.data_dir / "media-service.json.tmp"
    temporary.write_text(json.dumps(status), encoding="utf-8")
    temporary.replace(settings.data_dir / "media-service.json")


def _effective_flags() -> dict:
    """Read migration flags from the authoritative site database.

    The UI stores rollout flags in SiteSetting. Reading flags() without a DB
    silently ignores those overrides and previously left MediaMTX disabled even
    after an operator enabled it.
    """
    from app.db import SessionLocal
    from app.services.flags import flags

    with SessionLocal() as db:
        return flags(db)


def _sync_cameras_from_db() -> list[dict]:
    from app.db import SessionLocal
    from app.models import Camera
    from app.services.flags import flags, media_mtx_for_camera
    from app.services.mediamtx_sources import sync_camera

    synced: list[dict] = []
    wanted_ids: set[int] = set()
    with SessionLocal() as db:
        cfg = flags(db)
        if not cfg.get("media_gateway_enabled"):
            return synced
        for camera in db.query(Camera).filter(Camera.enabled == True).all():
            from app.services.node_scope import camera_in_recognition_scope
            if not camera_in_recognition_scope(camera, db=db):
                continue
            if not media_mtx_for_camera(int(camera.id), db):
                continue
            wanted_ids.add(int(camera.id))
            try:
                synced.append(sync_camera(camera, db=db))
            except Exception as exc:
                synced.append({"camera_id": camera.id, "registered": False, "error": str(exc)[:200]})
    # A lane reassignment must release old camera pulls.  Otherwise the node
    # keeps serving both lanes even though recognition correctly changed scope.
    from app.services import mediamtx
    for camera_id in mediamtx.registered_camera_ids():
        if int(camera_id) not in wanted_ids:
            mediamtx.unregister_source(int(camera_id))
    if mediamtx.running() and not mediamtx.reconcile_paths():
        import logging
        logging.getLogger(__name__).warning("MediaMTX path reconciliation failed; local Control API is unavailable or rejected the assigned camera paths")
    return synced


def main() -> int:
    from app.services.logging_setup import configure_logging
    from app.services.runtime import acquire_instance_lock, install_crash_hooks, set_process_name

    install_crash_hooks("SmartParkMediaService")
    configure_logging("media-service")
    set_process_name("SmartParkMediaService")
    if not acquire_instance_lock("media-service"):
        print("SmartPark Media Service is already running.", file=sys.stderr)
        return 0
    from app.services import mediamtx

    from sqlalchemy.exc import OperationalError
    from app.db import engine
    from app.services.redaction import redact_text
    log.info("Media service database: %s", engine.url.render_as_string(hide_password=True))
    previous = None
    try:
        while True:
            try:
                status = _service_step()
            except OperationalError as exc:
                status = {"state": "WAITING_FOR_DATABASE", "last_error": redact_text(str(exc.orig))[:400],
                          "detail": "Waiting for Site Service schema setup. Check both services use the same database."}
            except Exception as exc:
                status = {"state": "RETRYING", "last_error": type(exc).__name__}
                log.exception("Media service cycle failed; retrying")
            _write_status(status)
            if status["state"] != previous:
                log.warning("Media service status: %s", status)
                previous = status["state"]
            time.sleep(5)
    except KeyboardInterrupt:
        mediamtx.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
