"""Clock skew between this PC and the site's time authority (Phase 2.6).

Gate PCs record entry and exit times with their own clocks, and a car may
enter at one site and leave at the other. Edge Nodes share the Site Server's
PostgreSQL, so the database server's clock is the common authority: skew is
measured against ``CURRENT_TIMESTAMP`` with half the round trip removed. A
local SQLite database runs on this computer, so there is nothing to compare.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

WARN_SECONDS = 2.0


def _as_epoch(value: Any) -> float | None:
    if isinstance(value, datetime):
        stamp = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return stamp.timestamp()
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return _as_epoch(parsed)
    return None


def _result(source: str, skew: float, round_trip: float) -> dict[str, Any]:
    ok = abs(skew) <= WARN_SECONDS
    direction = "ahead of" if skew > 0 else "behind"
    authority = "the database server" if source == "database" else "the Site Server"
    return {
        "source": source,
        "skew_seconds": round(skew, 3),
        "round_trip_ms": round(round_trip * 1000, 1),
        "ok": ok,
        "warning": "" if ok else (
            f"This computer's clock is {abs(skew):.1f} s {direction} {authority}. "
            "Entry/exit times and fees can be wrong; enable Windows time sync (w32tm) to the Site Server."
        ),
    }


def measure_database_skew(db) -> dict[str, Any]:
    """Positive skew: this computer's clock is ahead of the database server."""
    try:
        dialect = db.get_bind().dialect.name
    except Exception:
        dialect = ""
    if dialect == "sqlite":
        return {"source": "local-database", "skew_seconds": 0.0, "round_trip_ms": 0.0, "ok": True,
                "warning": "", "note": "The database runs on this computer; there is no second clock."}
    before = time.time()
    value = db.scalar(text("SELECT CURRENT_TIMESTAMP"))
    after = time.time()
    server = _as_epoch(value)
    if server is None:
        return {"source": "database", "ok": True, "warning": "", "skew_seconds": None,
                "note": "The database did not return a usable time."}
    return _result("database", (before + after) / 2 - server, after - before)


def skew_from_server_time(server_time: str, *, round_trip_seconds: float, received_at: float | None = None) -> dict[str, Any]:
    """Skew of this computer against a Site Server timestamp (e.g. /node/heartbeat)."""
    received = time.time() if received_at is None else received_at
    server = _as_epoch(server_time)
    if server is None:
        return {"source": "site-server", "ok": True, "warning": "", "skew_seconds": None}
    local_mid = received - max(0.0, round_trip_seconds) / 2
    return _result("site-server", local_mid - server, round_trip_seconds)


_cache: dict[str, Any] = {"at": 0.0, "value": None}


def cached_database_skew(ttl: float = 60.0) -> dict[str, Any]:
    """Health views refresh every few seconds; measure at most once a minute."""
    now = time.monotonic()
    if _cache["value"] is not None and now - _cache["at"] < ttl:
        return _cache["value"]
    from app.db import short_session

    try:
        with short_session() as db:
            value = measure_database_skew(db)
    except Exception as exc:
        value = {"source": "database", "ok": True, "warning": "", "skew_seconds": None,
                 "note": f"Clock check failed: {str(exc)[:160]}"}
    _cache.update(at=now, value=value)
    return value
