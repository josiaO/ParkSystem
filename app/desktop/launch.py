"""Installed Windows entry: start HVX host + local API, then the desktop app."""

from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.request


def install_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    here = Path(__file__).resolve()
    # app/desktop/launch.py -> install root. python64/python.exe -> parent.
    if here.parent.name == "desktop":
        return here.parents[2]
    return Path(sys.executable).resolve().parent.parent


def _prepend_path(*folders: Path) -> None:
    parts = [str(p) for p in folders if p and p.is_dir()]
    if not parts:
        return
    current = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join(parts + [current]) if current else os.pathsep.join(parts)
    if os.name == "nt":
        add = getattr(os, "add_dll_directory", None)
        if add:
            for folder in parts:
                try:
                    add(folder)
                except Exception:
                    pass


def _prepare_env(root: Path) -> None:
    os.chdir(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    os.environ["PYTHONPATH"] = str(root)
    os.environ["SMARTPARK_HOME"] = str(root)
    vendor = root / "vendor"
    py64 = root / "python64"
    site = py64 / "Lib" / "site-packages"
    pyside = site / "PySide6"
    shiboken = site / "shiboken6"
    plugins = pyside / "plugins"
    platforms = plugins / "platforms"
    _prepend_path(py64, py64 / "Scripts", pyside, shiboken, vendor)
    if vendor.is_dir():
        os.environ["SMARTPARK_HVX_VENDOR_DIR"] = str(vendor)
    if plugins.is_dir():
        os.environ["QT_PLUGIN_PATH"] = str(plugins)
    if platforms.is_dir():
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(platforms)


def _log_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("PROGRAMDATA") or Path.home()) / "SmartParkEdge" / "logs"
    else:
        base = Path.home() / ".local" / "share" / "smartpark-edge" / "logs"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def start_hvx_host(root: Path) -> None:
    if _port_open(8765):
        return
    py32 = root / "python32" / "python.exe"
    host = root / "tools" / "hvx_sdk_host" / "hvx_host.py"
    if not py32.is_file() or not host.is_file():
        return
    flags = 0x08000000 if os.name == "nt" else 0
    env = os.environ.copy()
    vendor = root / "vendor"
    if vendor.is_dir():
        env["SMARTPARK_HVX_VENDOR_DIR"] = str(vendor)
        env["PATH"] = str(vendor) + os.pathsep + env.get("PATH", "")
    subprocess.Popen(
        [str(py32), str(host)],
        cwd=str(host.parent),
        env=env,
        creationflags=flags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_for_api(timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8760/health/live", timeout=1) as resp:
                if resp.status == 200:
                    return
        except Exception:
            try:
                with urllib.request.urlopen("http://127.0.0.1:8760/health", timeout=1) as resp:
                    if resp.status == 200:
                        return
            except Exception:
                time.sleep(0.2)
                continue
            return
        time.sleep(0.2)
    raise RuntimeError("SmartPark API did not start on http://127.0.0.1:8760")


def start_site_service(root: Path) -> None:
    """Run FastAPI in its own process so a UI crash cannot take parking down."""
    if _port_open(8760):
        return
    py = root / "python64" / "python.exe"
    if not py.is_file():
        py = Path(sys.executable)
    flags = 0
    if os.name == "nt":
        flags = 0x00000200 | 0x08000000  # CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)
    env["SMARTPARK_HOME"] = str(root)
    subprocess.Popen(
        [str(py), "-m", "app.site_service"],
        cwd=str(root),
        env=env,
        creationflags=flags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=os.name != "nt",
    )


def start_api() -> None:
    """In-process fallback used only if the Site Service process cannot spawn."""
    if _port_open(8760):
        return
    import uvicorn
    from app.api_main import app

    uvicorn.run(app, host="127.0.0.1", port=8760, log_level="warning", access_log=False, reload=False, workers=1)


def ensure_background_services(root: Path | None = None) -> None:
    root = root or install_root()
    start_hvx_host(root)
    if _port_open(8760):
        return
    start_site_service(root)
    try:
        wait_for_api(timeout=12.0)
        return
    except RuntimeError:
        pass
    threading.Thread(target=start_api, name="smartpark-api", daemon=True).start()
    wait_for_api()


def _fail(exc: BaseException) -> int:
    text = traceback.format_exc()
    log = _log_dir() / "launch.log"
    log.write_text(text, encoding="utf-8")
    message = f"SmartPark Edge failed to start.\n\n{exc}\n\nDetails: {log}"
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, "SmartPark Edge", 0x10)
        except Exception:
            print(message, file=sys.stderr)
    else:
        print(message, file=sys.stderr)
    return 1


def main() -> int:
    from app.services.logging_setup import configure_logging
    from app.services.runtime import acquire_instance_lock, install_crash_hooks, set_process_name

    root = install_root()
    _prepare_env(root)
    set_process_name("SmartParkDesktop")
    install_crash_hooks("SmartParkDesktop")
    configure_logging("desktop")
    if not acquire_instance_lock("desktop"):
        message = "SmartPark Edge is already open."
        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, message, "SmartPark Edge", 0x40)
            except Exception:
                print(message, file=sys.stderr)
        else:
            print(message, file=sys.stderr)
        return 0
    try:
        ensure_background_services(root)
        from app.desktop.main import main as desktop_main
        return int(desktop_main() or 0)
    except Exception as exc:
        return _fail(exc)


if __name__ == "__main__":
    raise SystemExit(main())
