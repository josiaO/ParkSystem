"""Measure how late the Site Service event loop wakes up.

Everything time-critical shares one asyncio loop: HVX frame relay, plate
events, parking decisions and boom commands. Blocking work on that loop shows
up as frame gaps and slow decisions. This samples the wake-up lag every
100 ms, keeps a rolling window for /health, and logs stalls. With
SMARTPARK_LOOP_DIAGNOSTICS=1, asyncio's debug mode also logs the callback
that blocked (``Executing <...> took 0.4 seconds``).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque

log = logging.getLogger("smartpark")

SAMPLE_SECONDS = 0.1
STALL_LOG_MS = 250.0
_lags: deque[float] = deque(maxlen=3000)   # ~5 minutes of samples
_stalls = {"count": 0, "worst_ms": 0.0, "last_at": 0.0}


def stats() -> dict:
    values = sorted(_lags)
    if not values:
        return {"samples": 0}
    return {
        "samples": len(values),
        "p50_ms": round(values[len(values) // 2], 1),
        "p95_ms": round(values[int(len(values) * 0.95) - 1], 1),
        "max_ms": round(values[-1], 1),
        "stalls_over_250ms": _stalls["count"],
        "worst_stall_ms": round(_stalls["worst_ms"], 1),
    }


def enable_diagnostics_if_requested(loop: asyncio.AbstractEventLoop) -> bool:
    if str(os.environ.get("SMARTPARK_LOOP_DIAGNOSTICS", "")).strip().lower() not in {"1", "true", "yes", "on"}:
        return False
    loop.set_debug(True)
    loop.slow_callback_duration = 0.15
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    log.warning("LOOP diagnostics on: callbacks blocking the event loop > 150 ms are logged by asyncio")
    return True


async def monitor_loop() -> None:
    enable_diagnostics_if_requested(asyncio.get_running_loop())
    while True:
        started = time.perf_counter()
        await asyncio.sleep(SAMPLE_SECONDS)
        lag_ms = max(0.0, (time.perf_counter() - started - SAMPLE_SECONDS) * 1000.0)
        _lags.append(lag_ms)
        if lag_ms >= STALL_LOG_MS:
            _stalls["count"] += 1
            _stalls["worst_ms"] = max(_stalls["worst_ms"], lag_ms)
            now = time.monotonic()
            if now - _stalls["last_at"] >= 5.0:      # at most one line per 5 s
                _stalls["last_at"] = now
                log.warning("LOOP stall %.0f ms (event loop blocked; video, plate events and gates waited)", lag_ms)
