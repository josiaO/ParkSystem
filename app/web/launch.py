"""Browser entry: Site Service + browser UI on any OS.

The PySide desktop (`python -m app.desktop.launch`) also runs on Linux.
The HVX NetSDK host stays Windows-only.
"""

from __future__ import annotations

import socket
import sys
import threading
import time
import webbrowser


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _open_browser(url: str, delay: float = 1.2) -> None:
    def _run() -> None:
        deadline = time.time() + 30.0
        while time.time() < deadline:
            if _port_open(8760):
                try:
                    webbrowser.open(url)
                except Exception:
                    pass
                return
            time.sleep(0.25)

    threading.Thread(target=_run, name="smartpark-open-browser", daemon=True).start()
    # Keep delay unused but documented for callers that want a sync wait later.
    _ = delay


def main() -> int:
    from app.branding import PRODUCT_NAME
    from app.config import settings
    from app.deployment import load_deployment_config
    from app.services.logging_setup import configure_logging
    from app.services.platform_capabilities import platform_snapshot
    from app.services.runtime import acquire_instance_lock, install_crash_hooks

    install_crash_hooks("SmartParkWeb")
    configure_logging("web")
    snap = platform_snapshot()
    deployment = load_deployment_config()
    if deployment.is_operator_client:
        url = f"{deployment.server_base_url}/"
        print(f"Operator Workstation: using Site Server at {url}")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        return 0
    bind_host = deployment.server_bind_host or settings.api_host
    bind_port = int(deployment.server_bind_port or settings.api_port)
    url = f"http://{bind_host}:{bind_port}/"
    print(f"{PRODUCT_NAME} web UI — {snap['os']}")
    print(f"Open {url}")
    print(snap["note"])
    if not snap["hvx_host_supported"]:
        print("Recommended camera adapter for IP cams:", snap["recommended_camera_adapter"])

    if _port_open(bind_port):
        print("Site Service already running; opening browser.")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        return 0

    if not acquire_instance_lock("site-service"):
        print(f"{PRODUCT_NAME} Site Service is already starting.", file=sys.stderr)
        _open_browser(url)
        time.sleep(2.0)
        return 0

    from app.desktop.launch import install_root, start_hvx_host

    root = install_root()
    start_hvx_host(root)
    _open_browser(url)

    import uvicorn
    from app.api_main import app

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
        if int(getattr(exc, "code", 0) or 0) == 3 and _port_open(bind_port):
            print(f"{PRODUCT_NAME} Site Service is already listening on port {bind_port}.", file=sys.stderr)
            return 0
        raise exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
