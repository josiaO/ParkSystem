"""Process CPU and resident memory without an optional monitoring dependency."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_previous: tuple[float, float] | None = None


def _resident_bytes() -> int | None:
    if sys.platform.startswith("linux"):
        try:
            return int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
        except (OSError, ValueError, IndexError):
            return None
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class MemoryCounters(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("page_faults", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in (
                    "peak_working_set", "working_set", "peak_paged_pool", "paged_pool",
                    "peak_nonpaged_pool", "nonpaged_pool", "pagefile", "peak_pagefile",
                )
            ]
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(MemoryCounters), wintypes.DWORD]
        counters = MemoryCounters()
        counters.size = ctypes.sizeof(counters)
        if kernel.K32GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.size):
            return counters.working_set
    return None


def snapshot() -> dict:
    global _previous
    now = time.monotonic()
    clocks = os.times()
    cpu = clocks.user + clocks.system
    percent = None
    if _previous is not None and now > _previous[0]:
        percent = round(max(0, cpu - _previous[1]) / (now - _previous[0]) * 100, 1)
    _previous = (now, cpu)
    return {"cpu_percent_one_core": percent, "ram_bytes": _resident_bytes(), "pid": os.getpid()}
