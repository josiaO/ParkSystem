"""Installed Windows entry with role-aware server/client startup."""

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

from app.branding import PRODUCT_NAME


# First startup can include Alembic migrations, database bootstrap and an
# offline FastALPR model warm-up.  Twelve seconds is enough for a warm dev
# process, but routinely too short for a Windows USB installation.
SITE_SERVICE_START_TIMEOUT_SECONDS = 90.0
_site_service_process: subprocess.Popen | None = None


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
    """Start the 32-bit NetSDK sidecar. No-op outside Windows (DLL is PE32 only)."""
    if os.name != "nt":
        return
    if _port_open(8765):
        return
    py32 = root / "python32" / "python.exe"
    host = root / "tools" / "hvx_sdk_host" / "hvx_host.py"
    if not py32.is_file() or not host.is_file():
        return
    env = os.environ.copy()
    vendor = root / "vendor"
    if vendor.is_dir():
        env["SMARTPARK_HVX_VENDOR_DIR"] = str(vendor)
        env["PATH"] = str(vendor) + os.pathsep + env.get("PATH", "")
    subprocess.Popen(
        [str(py32), str(host)],
        cwd=str(host.parent),
        env=env,
        creationflags=0x08000000,  # CREATE_NO_WINDOW
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _site_service_launch_tail() -> str:
    try:
        path = _log_dir() / "site-service-launch.log"
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        useful = [line.strip() for line in lines if line.strip()]
        if useful:
            return " Last output: " + " | ".join(useful[-8:])[-1200:]
    except Exception:
        pass
    return ""


def wait_for_api(timeout: float = 60.0, base_url: str = "http://127.0.0.1:8760", process=None) -> None:
    base_url = base_url.rstrip("/")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process is not None:
            return_code = process.poll()
            if return_code is not None:
                raise RuntimeError(
                    f"{PRODUCT_NAME} Site Service exited with code {return_code} before becoming ready."
                    f"{_site_service_launch_tail()}"
                )
        try:
            with urllib.request.urlopen(f"{base_url}/health/live", timeout=1) as resp:
                if resp.status == 200:
                    return
        except Exception:
            try:
                with urllib.request.urlopen(f"{base_url}/health", timeout=1) as resp:
                    if resp.status == 200:
                        return
            except Exception:
                time.sleep(0.2)
                continue
            return
        time.sleep(0.2)
    raise RuntimeError(f"{PRODUCT_NAME} API did not start on {base_url}")


def start_site_service(root: Path, config=None) -> bool:
    """Run FastAPI in its own process so a UI crash cannot take parking down.

    The return value distinguishes a successful process spawn from the case
    where the in-process fallback is still appropriate.  A spawned service
    must never be followed by a second API process merely because startup is
    slow or another launcher won the port race.
    """
    global _site_service_process
    port = int(getattr(config, "server_bind_port", None) or 8760)
    if _port_open(port):
        _site_service_process = None
        return True
    py = root / "python64" / "python.exe"
    if not py.is_file():
        py = Path(sys.executable)
    if not py.is_file():
        return False
    flags = 0
    if os.name == "nt":
        flags = 0x00000200 | 0x08000000  # CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)
    env["SMARTPARK_HOME"] = str(root)
    if config is not None:
        env["SMARTPARK_API_HOST"] = str(config.server_bind_host or "127.0.0.1")
        env["SMARTPARK_API_PORT"] = str(int(config.server_bind_port or 8760))
    # Keep the child console hidden on Windows, but preserve its early
    # interpreter/import errors.  The structured site-service log is created
    # later by the application; this companion log covers failures before
    # logging is configured and makes a packaged install supportable.
    launch_log = _log_dir() / "site-service-launch.log"
    try:
        with launch_log.open("ab") as output:
            _site_service_process = subprocess.Popen(
                [str(py), "-m", "app.site_service"],
                cwd=str(root),
                env=env,
                creationflags=flags,
                stdout=output,
                stderr=output,
                start_new_session=os.name != "nt",
            )
    except OSError:
        _site_service_process = None
        return False
    return True


def start_api(config=None) -> None:
    """In-process fallback used only if the Site Service process cannot spawn."""
    port = int(getattr(config, "server_bind_port", None) or 8760)
    if _port_open(port):
        return
    if config is not None:
        from app.database_config import apply_runtime_database_config

        apply_runtime_database_config(config.database)
    from app.config import settings
    os.environ.setdefault("SMARTPARK_ALPR_CACHE_DIR", str(settings.data_dir / "model-cache"))
    os.environ.setdefault("SMARTPARK_ALPR_PREFLIGHT", "1")
    import uvicorn
    from app.api_main import app

    host = str(getattr(config, "server_bind_host", None) or "127.0.0.1")
    try:
        uvicorn.run(app, host=host, port=port, log_level="warning", access_log=False, reload=False, workers=1)
    except SystemExit as exc:
        # Uvicorn uses exit code 3 for an address already in use.  Another
        # SmartPark launcher may have won the race; that is not a desktop
        # crash if the expected API is now accepting connections.
        if int(getattr(exc, "code", 0) or 0) == 3 and _port_open(port):
            return
        raise exc


def start_pipeline_services(root: Path) -> None:
    """Launch service owners; their instance locks reject duplicate launches."""
    python = root / "python64" / "python.exe"
    if not python.is_file():
        python = Path(sys.executable)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)
    env["SMARTPARK_HOME"] = str(root)
    for module, name in (("app.media_service", "media-service"), ("app.recognition_worker", "recognition-worker")):
        with (_log_dir() / f"{name}-launch.log").open("ab") as output:
            subprocess.Popen(
                [str(python), "-m", module], cwd=str(root), env=env,
                creationflags=(0x00000200 | 0x08000000) if os.name == "nt" else 0,
                stdout=output, stderr=output, start_new_session=os.name != "nt",
            )


def _scheduled_site_service_exists() -> bool:
    """Return whether the installer registered the Windows Site Service task."""
    if os.name != "nt":
        return False
    try:
        result = subprocess.run(
            ["schtasks.exe", "/Query", "/TN", "SmartPark Site Service"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _start_scheduled_site_service() -> bool:
    """Ask Windows to start the registered task; never create a duplicate API."""
    try:
        result = subprocess.run(
            ["schtasks.exe", "/Run", "/TN", "SmartPark Site Service"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def ensure_background_services(root: Path | None = None, config=None) -> None:
    from app.deployment import SITE_SERVER, load_deployment_config

    root = root or install_root()
    config = config or load_deployment_config()
    if config.role not in {SITE_SERVER, "EDGE_NODE"}:
        # Operator workstations are thin clients. They must never start a
        # local API, database, camera SDK, MediaMTX or recognition process.
        return
    start_hvx_host(root)
    port = int(config.server_bind_port or 8760)
    local_url = f"http://127.0.0.1:{port}"
    # The installer owns the Windows scheduled task.  The desktop may open
    # immediately after installation or after the wizard saves deployment.json
    # while that task is still booting.  Starting a second Python API here can
    # win the instance-lock race, leave the real task without the port, and
    # produce WinError 10061.  Prefer the task and wait for its one API owner.
    if os.name == "nt" and _scheduled_site_service_exists():
        _start_scheduled_site_service()
        wait_for_api(timeout=SITE_SERVICE_START_TIMEOUT_SECONDS, base_url=local_url)
        start_pipeline_services(root)
        return
    if _port_open(port):
        # A TCP listener is not proof that the Zirp API owns the port.  Verify
        # the health endpoint before showing the login dialog; otherwise a
        # stale process or a transient port race can lead to WinError 10061
        # on the first login request.
        wait_for_api(timeout=SITE_SERVICE_START_TIMEOUT_SECONDS, base_url=local_url)
        start_pipeline_services(root)
        return
    spawned = start_site_service(root, config=config)
    try:
        wait_for_api(
            timeout=SITE_SERVICE_START_TIMEOUT_SECONDS,
            base_url=local_url,
            process=_site_service_process if spawned else None,
        )
        start_pipeline_services(root)
        return
    except RuntimeError:
        if spawned:
            raise RuntimeError(
                f"{PRODUCT_NAME} Site Service was started but did not become ready on {local_url}. "
                "Check the Site Service log and site-service-launch.log in the SmartParkEdge logs folder; "
                "no second API process was started."
            )
    threading.Thread(target=start_api, args=(config,), name="smartpark-api", daemon=True).start()
    wait_for_api(base_url=local_url)
    start_pipeline_services(root)


def disable_background_services() -> None:
    """Remove transitional server tasks from an Operator Workstation."""
    if os.name != "nt":
        return
    for name in (
        "SmartPark Site Service",
        "SmartPark Recognition Worker",
        "SmartPark HVX Host",
        "SmartPark Media Service",
    ):
        try:
            subprocess.run(["schtasks.exe", "/Delete", "/TN", name, "/F"], check=False, capture_output=True)
        except OSError:
            pass


def _fail(exc: BaseException) -> int:
    text = traceback.format_exc()
    log = _log_dir() / "launch.log"
    log.write_text(text, encoding="utf-8")
    message = f"{PRODUCT_NAME} failed to start.\n\n{exc}\n\nDetails: {log}"
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, PRODUCT_NAME, 0x10)
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
        message = f"{PRODUCT_NAME} is already open."
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, PRODUCT_NAME, 0x40)
        except Exception:
            print(message, file=sys.stderr)
        return 0
    try:
        from app.desktop.main import main as desktop_main
        return int(desktop_main() or 0)
    except Exception as exc:
        return _fail(exc)


if __name__ == "__main__":
    raise SystemExit(main())
