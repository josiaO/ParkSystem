"""Process identity, startup states, instance lock, crash capture.

Site Service, HVX host, and Desktop are separate failure domains. Parking
truth lives in the database, not in these in-memory flags.
"""

from __future__ import annotations

import atexit
import os
import sys
import threading
import time
import traceback
from pathlib import Path

STARTING = "STARTING"
READY_CORE = "READY_CORE"
READY_HARDWARE = "READY_HARDWARE"
DEGRADED = "DEGRADED"
OFFLINE = "OFFLINE"

_started_at = time.time()
_state = STARTING
_process_name = "SmartPark"
_last_crash = ""
_restart_count = int(os.environ.get("SMARTPARK_RESTART_COUNT") or 0)
_lock_handle = None
_lock_path: Path | None = None


def process_name() -> str:
    return _process_name


def set_process_name(name: str) -> None:
    global _process_name
    _process_name = name or _process_name


def started_at() -> float:
    return _started_at


def uptime_seconds() -> float:
    return round(time.time() - _started_at, 1)


def startup_state() -> str:
    return _state


def set_startup_state(state: str) -> None:
    global _state
    if state in {STARTING, READY_CORE, READY_HARDWARE, DEGRADED, OFFLINE}:
        _state = state


def mark_core_ready() -> None:
    if _state == STARTING:
        set_startup_state(READY_CORE)


def mark_hardware(ok: bool) -> None:
    if ok and _state in {STARTING, READY_CORE, DEGRADED}:
        set_startup_state(READY_HARDWARE)
    elif not ok and _state in {READY_HARDWARE, READY_CORE}:
        set_startup_state(DEGRADED)


def restart_count() -> int:
    return _restart_count


def last_crash_reason() -> str:
    return _last_crash


def data_dir() -> Path:
    from app.config import settings
    return settings.data_dir


def logs_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def app_version() -> str:
    from app.config import settings
    return getattr(settings, "app_version", "0.2.0")


def write_crash(reason: str, *, tb: str = "") -> Path:
    global _last_crash
    _last_crash = (reason or "unknown")[:400]
    dest = logs_dir() / f"crash-{process_name().replace(' ', '-')}.log"
    body = (
        f"process={process_name()}\n"
        f"module={__name__}\n"
        f"version={app_version()}\n"
        f"pid={os.getpid()}\n"
        f"time={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
        f"reason={_last_crash}\n\n"
        f"{tb or ''}"
    )
    dest.write_text(body, encoding="utf-8")
    return dest


def install_crash_hooks(name: str = "") -> None:
    if name:
        set_process_name(name)

    def _hook(exc_type, exc, tb):
        write_crash(f"{exc_type.__name__}: {exc}", tb="".join(traceback.format_exception(exc_type, exc, tb)))
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _hook

    def _thread_hook(args):
        write_crash(
            f"{getattr(args.exc_type, '__name__', 'error')}: {args.exc_value}",
            tb="".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)),
        )

    if hasattr(threading, "excepthook"):
        threading.excepthook = _thread_hook


def acquire_instance_lock(name: str) -> bool:
    """One Site Service / HVX host / Desktop. Returns False if another copy owns it."""
    global _lock_handle, _lock_path
    if os.environ.get("SMARTPARK_SKIP_INSTANCE_LOCK"):
        return True
    folder = data_dir() / "locks"
    folder.mkdir(parents=True, exist_ok=True)
    _lock_path = folder / f"{name}.lock"
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
            kernel.CreateMutexW.restype = wintypes.HANDLE
            handle = kernel.CreateMutexW(None, True, f"Global\\SmartPark-{name}")
            if not handle:
                return False
            if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
                return False
            _lock_handle = handle
            _lock_path.write_text(str(os.getpid()), encoding="utf-8")
            atexit.register(release_instance_lock)
            return True
        except Exception:
            pass
    try:
        fh = open(_lock_path, "a+", encoding="utf-8")
        if os.name != "nt":
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fh.seek(0)
        fh.truncate()
        fh.write(str(os.getpid()))
        fh.flush()
        _lock_handle = fh
        atexit.register(release_instance_lock)
        return True
    except OSError:
        return False


def release_instance_lock() -> None:
    global _lock_handle
    handle = _lock_handle
    _lock_handle = None
    if handle is None:
        return
    try:
        if os.name == "nt" and not hasattr(handle, "close"):
            import ctypes
            ctypes.WinDLL("kernel32").CloseHandle(handle)
        else:
            handle.close()
    except Exception:
        pass


def process_metrics() -> dict:
    rss = 0
    threads = threading.active_count()
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            GetCurrentProcess = ctypes.windll.kernel32.GetCurrentProcess
            GetProcessMemoryInfo = ctypes.windll.psapi.GetProcessMemoryInfo
            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            if GetProcessMemoryInfo(GetCurrentProcess(), ctypes.byref(counters), counters.cb):
                rss = int(counters.WorkingSetSize)
        else:
            page = os.sysconf("SC_PAGE_SIZE")
            with open("/proc/self/statm", encoding="ascii") as fh:
                rss = int(fh.read().split()[1]) * page
    except Exception:
        rss = 0
    cpu_pct = 0.0
    try:
        if hasattr(os, "times"):
            cpu_pct = round(sum(os.times()[:2]) / max(uptime_seconds(), 0.1) * 100, 1)
    except Exception:
        cpu_pct = 0.0
    return {
        "pid": os.getpid(),
        "name": process_name(),
        "version": app_version(),
        "uptime_seconds": uptime_seconds(),
        "rss_bytes": rss,
        "thread_count": threads,
        "restart_count": restart_count(),
        "last_crash": last_crash_reason(),
        "state": startup_state(),
    }
