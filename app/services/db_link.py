"""State of the link to the parking database (Phase 5.2).

On an Edge Node the database is the Site Server's PostgreSQL, 400 m away. When
that link is down a lane cannot look up sessions, so it must say so at once
instead of hanging: requests fail within seconds (see app.db connect/pool
timeouts) with HTTP 503 and a fallback instruction, the desktop shows a red
banner, and queued recognition events wait for the link instead of being
dead-lettered.

The state is held in memory and never needs the database to be read, so
``/health/live`` can always report it.
"""

from __future__ import annotations

import asyncio
import threading
import time

OPERATOR_MESSAGE = (
    "Server link down: this lane cannot check parking sessions. "
    "Barriers will not open automatically. Pay or exit with the receipt QR at the kiosk, "
    "or call an operator to open the gate manually."
)


def is_link_error(exc: BaseException) -> bool:
    """True for "cannot reach / talk to the database", not for bad data."""
    from sqlalchemy.exc import DBAPIError, OperationalError, TimeoutError as PoolTimeout

    if isinstance(exc, PoolTimeout):
        return True
    if isinstance(exc, DBAPIError) and getattr(exc, "connection_invalidated", False):
        return True
    if isinstance(exc, OperationalError):
        text = str(getattr(exc, "orig", None) or exc).lower()
        return any(marker in text for marker in _LINK_MARKERS)
    return isinstance(exc, (ConnectionError, TimeoutError))


# Connection-level failures only. Schema errors ("no such table") and SQLite
# lock contention are OperationalError too, but they are not a link outage.
_LINK_MARKERS = (
    "could not connect", "connection refused", "connection timed out", "timeout expired",
    "server closed the connection", "terminating connection", "connection to server",
    "no route to host", "network is unreachable", "could not translate host name",
    "canceling statement due to statement timeout", "connection is closed", "ssl syscall",
    "the connection is lost", "consuming input failed",
)


class LinkMonitor:
    def __init__(self, *, slow_ms: float = 1000.0) -> None:
        self.slow_ms = float(slow_ms)
        self._lock = threading.Lock()
        self._state = "UNKNOWN"
        self._since = time.time()
        self._last_error = ""
        self._latency_ms: float | None = None
        self._last_ok_at: float | None = None
        self._failures = 0

    def _set(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self._since = time.time()

    def note_ok(self, latency_ms: float) -> None:
        with self._lock:
            self._latency_ms = round(float(latency_ms), 1)
            self._last_ok_at = time.time()
            self._failures = 0
            self._set("SLOW" if latency_ms > self.slow_ms else "UP")

    def note_failure(self, exc: BaseException | str) -> None:
        with self._lock:
            self._failures += 1
            self._last_error = str(exc)[:300]
            self._set("DOWN")

    @property
    def down(self) -> bool:
        return self._state == "DOWN"

    def snapshot(self) -> dict:
        with self._lock:
            state = self._state
            return {
                "state": state,
                "since": self._since,
                "seconds_in_state": round(time.time() - self._since, 1),
                "latency_ms": self._latency_ms,
                "last_ok_at": self._last_ok_at,
                "consecutive_failures": self._failures,
                "last_error": self._last_error if state == "DOWN" else "",
                "operator_message": OPERATOR_MESSAGE if state == "DOWN" else "",
            }


_monitor = LinkMonitor()


def monitor() -> LinkMonitor:
    return _monitor


def handle_outbox_failure(box, item: dict, exc: BaseException) -> str:
    """Outbox policy: a link outage is not a poison message.

    Returns "link-down" (event kept, no attempt counted; the caller should
    pause), "recorded" (attempt counted) or "dead-lettered".
    """
    if is_link_error(exc):
        _monitor.note_failure(exc)
        return "link-down"
    return "dead-lettered" if box.record_failure(item["id"], f"{type(exc).__name__}: {exc}") else "recorded"


def _probe() -> float:
    from sqlalchemy import text

    from app.db import engine

    started = time.perf_counter()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1")).scalar()
    return (time.perf_counter() - started) * 1000.0


async def probe_once(timeout_seconds: float = 8.0, probe=None) -> dict:
    """One probe in a worker thread so a hung connect can never block the event loop."""
    try:
        latency = await asyncio.wait_for(asyncio.to_thread(probe or _probe), timeout=timeout_seconds)
        _monitor.note_ok(latency)
    except asyncio.CancelledError:
        raise
    except asyncio.TimeoutError:
        _monitor.note_failure(f"database did not answer within {timeout_seconds:g} s")
    except Exception as exc:
        _monitor.note_failure(exc)
    return _monitor.snapshot()


async def probe_loop(interval_seconds: float = 5.0, timeout_seconds: float = 8.0) -> None:
    while True:
        await probe_once(timeout_seconds)
        await asyncio.sleep(interval_seconds)
