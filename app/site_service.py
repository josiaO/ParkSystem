"""Site Service: FastAPI + camera events. No Qt UI. No NetSDK in-process."""

from __future__ import annotations

import sys
import socket
import os


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", int(port))) == 0


def main() -> int:
    from app.services.logging_setup import configure_logging
    from app.services.runtime import acquire_instance_lock, install_crash_hooks
    from app.services.platform_capabilities import platform_snapshot

    install_crash_hooks("SmartParkSiteService")
    configure_logging("site-service")
    if not acquire_instance_lock("site-service"):
        print("SmartPark Site Service is already running.", file=sys.stderr)
        return 0
    from app.config import settings
    from app.deployment import CONFIGURED, load_deployment_config
    from app.database_config import apply_runtime_database_config
    from app.desktop.launch import install_root, start_hvx_host

    deployment = load_deployment_config()
    if not deployment.is_server:
        print("Operator Workstation does not start SmartPark Site Service.", file=sys.stderr)
        return 2
    if not deployment.configured or deployment.state != CONFIGURED:
        print("SmartPark deployment is not configured; complete Deployment Configuration first.", file=sys.stderr)
        return 2
    apply_runtime_database_config(deployment.database)
    # Keep the offline detector/OCR cache with the Site Server data so the
    # scheduled task and the technician's desktop use the same model files.
    os.environ.setdefault("SMARTPARK_ALPR_CACHE_DIR", str(settings.data_dir / "model-cache"))
    os.environ.setdefault("SMARTPARK_ALPR_PREFLIGHT", "1")

    snap = platform_snapshot()
    if not snap["hvx_host_supported"]:
        print(f"Site Service on {snap['os']}: HVX host skipped. Prefer browser UI + rtsp adapters.")
    root = install_root()
    start_hvx_host(root)
    import uvicorn
    from app.api_main import app

    bind_host = deployment.server_bind_host if deployment.is_server else settings.api_host
    bind_port = int(deployment.server_bind_port or settings.api_port) if deployment.is_server else settings.api_port
    try:
        uvicorn.run(
            app,
            host=bind_host,
            port=bind_port,
            log_level="warning",
            access_log=False,
            reload=False,
            workers=1,
        )
    except SystemExit as exc:
        # Uvicorn reports a port race as SystemExit(3).  A second launcher may
        # already own the port; do not record that expected condition as a
        # Site Service crash.
        if int(getattr(exc, "code", 0) or 0) == 3 and _port_open(bind_port):
            print(f"SmartPark Site Service is already listening on port {bind_port}.", file=sys.stderr)
            return 0
        raise exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
