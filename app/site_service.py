"""Site Service: FastAPI + camera events. No Qt UI. No NetSDK in-process."""

from __future__ import annotations

import sys


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
    from app.desktop.launch import install_root, start_hvx_host

    snap = platform_snapshot()
    if not snap["hvx_host_supported"]:
        print(f"Site Service on {snap['os']}: HVX host skipped. Prefer browser UI + rtsp adapters.")
    root = install_root()
    start_hvx_host(root)
    import uvicorn
    from app.api_main import app

    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level="warning",
        access_log=False,
        reload=False,
        workers=1,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
