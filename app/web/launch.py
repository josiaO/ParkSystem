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
    from app.config import settings
    from app.services.logging_setup import configure_logging
    from app.services.platform_capabilities import platform_snapshot
    from app.services.runtime import acquire_instance_lock, install_crash_hooks

    install_crash_hooks("SmartParkWeb")
    configure_logging("web")
    snap = platform_snapshot()
    url = f"http://{settings.api_host}:{settings.api_port}/"
    print(f"SmartPark Edge web UI — {snap['os']}")
    print(f"Open {url}")
    print(snap["note"])
    if not snap["hvx_host_supported"]:
        print("Recommended camera adapter for IP cams:", snap["recommended_camera_adapter"])

    if _port_open(settings.api_port):
        print("Site Service already running; opening browser.")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        return 0

    if not acquire_instance_lock("site-service"):
        print("SmartPark Site Service is already starting.", file=sys.stderr)
        _open_browser(url)
        time.sleep(2.0)
        return 0

    from app.desktop.launch import install_root, start_hvx_host

    root = install_root()
    start_hvx_host(root)
    _open_browser(url)

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
