"""SmartParkMediaService — optional MediaMTX owner. Parking does not depend on this process."""

from __future__ import annotations

import sys
import time


def _sync_cameras_from_db() -> list[dict]:
    from app.db import SessionLocal
    from app.models import Camera
    from app.services.flags import flags, media_mtx_for_camera
    from app.services.mediamtx_sources import sync_camera

    synced: list[dict] = []
    with SessionLocal() as db:
        cfg = flags(db)
        if not cfg.get("media_gateway_enabled"):
            return synced
        for camera in db.query(Camera).filter(Camera.enabled == True).all():
            if not media_mtx_for_camera(int(camera.id), db):
                continue
            try:
                synced.append(sync_camera(camera, db=db))
            except Exception as exc:
                synced.append({"camera_id": camera.id, "registered": False, "error": str(exc)[:200]})
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
    from app.services.flags import flags
    from app.services import mediamtx

    cfg = flags()
    if not cfg.get("media_gateway_enabled"):
        print("media_gateway_enabled is off. MediaMTX sidecar not started. LocalMediaGateway remains authoritative.")
        while True:
            time.sleep(30)
            cfg = flags()
            if cfg.get("media_gateway_enabled") and mediamtx.available():
                break
    if mediamtx.available():
        print(mediamtx.start())
        print("Synced cameras:", _sync_cameras_from_db())
    else:
        print("MediaMTX binary not found. Live view stays on LocalMediaGateway.")
    try:
        while True:
            time.sleep(5)
            if flags().get("media_gateway_enabled") and mediamtx.available() and not mediamtx.running():
                mediamtx.start()
                _sync_cameras_from_db()
    except KeyboardInterrupt:
        mediamtx.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
