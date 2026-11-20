"""Write to desktop.log what the desktop is busy with when it uses a lot of CPU.

Every ``interval`` seconds the process CPU share is measured. When it is
above ``threshold`` (1.0 = one full core) the Python stacks of every thread
are sampled for a couple of seconds and the busiest places are logged. Cost
when idle: one time measurement per interval.
"""

from __future__ import annotations

import collections
import logging
import sys
import threading
import time

LOG = logging.getLogger("smartpark.desktop.cpu")


def _where(frame) -> str:
    """Innermost frame in app code (else the innermost frame), as file:line function."""
    chosen = frame
    walk = frame
    while walk is not None:
        if "/app/" in walk.f_code.co_filename.replace("\\", "/"):
            chosen = walk
            break
        walk = walk.f_back
    code = chosen.f_code
    name = code.co_filename.replace("\\", "/").rsplit("/", 2)[-2:]
    return f"{'/'.join(name)}:{chosen.f_lineno} {code.co_name}"


def thread_cpu_seconds() -> dict[int, float]:
    """CPU seconds used so far by every thread of this process (Windows), by native thread id.

    Includes threads Python does not know about (Qt, the JPEG decoder, sockets).
    """
    if sys.platform != "win32":
        return {}
    import ctypes
    from ctypes import wintypes

    class THREADENTRY32(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ThreadID", wintypes.DWORD),
                    ("th32OwnerProcessID", wintypes.DWORD), ("tpBasePri", wintypes.LONG),
                    ("tpDeltaPri", wintypes.LONG), ("dwFlags", wintypes.DWORD)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.OpenThread.restype = wintypes.HANDLE
    pid = kernel.GetCurrentProcessId()
    snap = kernel.CreateToolhelp32Snapshot(0x00000004, 0)        # TH32CS_SNAPTHREAD
    out: dict[int, float] = {}
    if not snap or snap == wintypes.HANDLE(-1).value:
        return out
    try:
        entry = THREADENTRY32()
        entry.dwSize = ctypes.sizeof(entry)
        ok = kernel.Thread32First(snap, ctypes.byref(entry))
        while ok:
            if entry.th32OwnerProcessID == pid:
                handle = kernel.OpenThread(0x0800, False, entry.th32ThreadID)   # THREAD_QUERY_LIMITED_INFORMATION
                if handle:
                    times = [wintypes.FILETIME() for _ in range(4)]
                    if kernel.GetThreadTimes(handle, *[ctypes.byref(t) for t in times]):
                        kernel_t = (times[2].dwHighDateTime << 32) | times[2].dwLowDateTime
                        user_t = (times[3].dwHighDateTime << 32) | times[3].dwLowDateTime
                        out[int(entry.th32ThreadID)] = (kernel_t + user_t) / 1e7
                    kernel.CloseHandle(handle)
            ok = kernel.Thread32Next(snap, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snap)
    return out


def busiest_threads(seconds: float = 2.0) -> list[tuple[str, int]]:
    """(thread, % of one core) for the threads that used the most CPU over the window."""
    before = thread_cpu_seconds()
    time.sleep(seconds)
    after = thread_cpu_seconds()
    frames = sys._current_frames()
    by_native = {t.native_id: t for t in threading.enumerate()}
    rows = []
    for tid, used in after.items():
        share = (used - before.get(tid, used)) / seconds
        if share < 0.05:
            continue
        thread = by_native.get(tid)
        if thread is not None and thread.ident in frames:
            label = f"{thread.name} @ {_where(frames[thread.ident])}"
        else:
            label = f"native thread {tid} (not Python: Qt, decoder or socket)"
        rows.append((label, round(share * 100)))
    return sorted(rows, key=lambda row: -row[1])[:10]


def sample_stacks(seconds: float = 2.0, every: float = 0.02) -> list[tuple[str, int]]:
    """Most frequent (thread name, place) over the sampling window."""
    names = {t.ident: t.name for t in threading.enumerate()}
    me = threading.get_ident()
    counts: collections.Counter = collections.Counter()
    end = time.monotonic() + seconds
    samples = 0
    while time.monotonic() < end:
        for ident, frame in sys._current_frames().items():
            if ident == me:
                continue
            counts[f"{names.get(ident, ident)} @ {_where(frame)}"] += 1
        samples += 1
        time.sleep(every)
    return [(place, round(100 * n / max(1, samples))) for place, n in counts.most_common(10)]


class CpuWatch(threading.Thread):
    def __init__(self, *, interval: float = 30.0, threshold: float = 1.0, summary_every: float = 600.0):
        super().__init__(name="cpu-watch", daemon=True)
        self.interval = interval
        self.threshold = threshold
        self.summary_every = summary_every
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        cpu, wall = time.process_time(), time.monotonic()
        summary_at = wall
        while not self._stop.wait(self.interval):
            now_cpu, now = time.process_time(), time.monotonic()
            share = (now_cpu - cpu) / max(0.001, now - wall)
            cpu, wall = now_cpu, now
            if share >= self.threshold:
                try:
                    threads = busiest_threads()
                except Exception as exc:          # never let diagnostics hurt the app
                    threads = [(f"thread times failed: {exc}", 0)]
                try:
                    top = sample_stacks()
                except Exception as exc:
                    top = [(f"sampling failed: {exc}", 0)]
                LOG.warning("desktop CPU %.0f%% of one core over %.0fs; threads by CPU (%% of a core): %s; "
                            "where Python threads are (share of samples): %s",
                            share * 100, self.interval, "; ".join(f"{p} {n}%" for p, n in threads),
                            "; ".join(f"{p} {n}%" for p, n in top))
                cpu, wall = time.process_time(), time.monotonic()
            elif now - summary_at >= self.summary_every:
                summary_at = now
                LOG.info("desktop CPU %.0f%% of one core over %.0fs", share * 100, self.interval)


_watch: CpuWatch | None = None


def start() -> CpuWatch:
    global _watch
    if _watch is None or not _watch.is_alive():
        _watch = CpuWatch()
        _watch.start()
    return _watch
