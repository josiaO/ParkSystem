"""System health snapshots for /health/live, /health/ready, /health/details."""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime, timezone

from app.services.cache import health_cache
from app.services.circuit import all_breakers, reconnect_for
from app.services.queues import queue_snapshots
from app.services.runtime import process_metrics, startup_state

_api_latencies: deque[float] = deque(maxlen=200)
_db_latencies: deque[float] = deque(maxlen=200)
_slow_queries: deque[dict] = deque(maxlen=20)
_gate_latencies: deque[float] = deque(maxlen=80)
_gate_ok = 0
_gate_fail = 0
_worker_failures: deque[dict] = deque(maxlen=40)
_camera_stats: dict[int, dict] = {}


def note_api_latency(ms: float) -> None:
    _api_latencies.append(float(ms))


def note_db_latency(ms: float, statement: str = "") -> None:
    _db_latencies.append(float(ms))
    if ms >= 200:
        _slow_queries.append({
            "ms": round(ms, 1),
            "sql": (statement or "")[:180],
            "at": datetime.now(timezone.utc).isoformat(),
        })


def note_gate(ok: bool, ms: float) -> None:
    global _gate_ok, _gate_fail
    _gate_latencies.append(float(ms))
    if ok:
        _gate_ok += 1
    else:
        _gate_fail += 1


def note_worker_failure(name: str, error: str) -> None:
    _worker_failures.append({
        "name": name,
        "error": (error or "")[:240],
        "at": datetime.now(timezone.utc).isoformat(),
    })


def note_camera(camera_id: int, **fields) -> None:
    row = _camera_stats.setdefault(camera_id, {
        "camera_id": camera_id,
        "reconnect_count": 0,
        "last_event_at": 0.0,
        "event_latency_ms": 0,
        "sdk_callback": "idle",
    })
    row.update(fields)


def _avg(values: deque[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 1)


def live() -> dict:
    return {
        "ok": True,
        "status": "live",
        "state": startup_state(),
        "time": datetime.now(timezone.utc).isoformat(),
        "process": process_metrics(),
    }


def ready() -> dict:
    from app.db import SessionLocal, is_sqlite
    from app.config import settings

    db_ok = False
    hvx_ok = False
    error = ""
    try:
        with SessionLocal() as db:
            db.execute(__import__("sqlalchemy").text("SELECT 1"))
            db_ok = True
    except Exception as exc:
        error = str(exc)
    try:
        import httpx
        r = httpx.get(f"{settings.hvx_host_url.rstrip('/')}/info", timeout=0.6)
        hvx_ok = r.status_code == 200
    except Exception:
        hvx_ok = False
    state = startup_state()
    core = db_ok
    payload = {
        "ok": core,
        "status": "ready" if core and hvx_ok else ("degraded" if core else "not_ready"),
        "state": state,
        "db": {"ok": db_ok, "sqlite": is_sqlite(), "error": error},
        "hvx_host": {"ok": hvx_ok},
        "time": datetime.now(timezone.utc).isoformat(),
    }
    return payload


def details() -> dict:
    cached = health_cache.get("details")
    if cached is not None:
        return cached
    from app.services.preview import live_metrics
    from app.services.ocr_policy import alpr_mode
    from app.config import settings

    process = process_metrics()
    cameras = live_metrics()
    for row in cameras:
        cid = int(row.get("camera_id") or 0)
        extra = _camera_stats.get(cid) or {}
        policy = reconnect_for(cid).snapshot()
        row.update({
            "reconnect_count": extra.get("reconnect_count", policy.get("attempts") or 0),
            "last_event_at": extra.get("last_event_at") or 0,
            "event_latency_ms": extra.get("event_latency_ms") or 0,
            "sdk_callback": extra.get("sdk_callback") or "idle",
            "reconnect": policy,
        })
    from app.services.hw_decode import cached_summary
    from app.services.media_gateway import gateway
    from app.services.flags import flags as migration_flags
    from app.services import mediamtx
    hvx = ready()["hvx_host"]
    domains = {
        "camera_connection": {"ok": bool(hvx.get("ok")), "detail": "HVX host" if hvx.get("ok") else "HVX host down"},
        "media_gateway": {"ok": True, "local_sessions": len(gateway.live_metrics()), "mediamtx": mediamtx.health()},
        "recognition": {"ok": True, "alpr_mode": alpr_mode(), "native_alpr_enabled": migration_flags().get("native_alpr_enabled")},
        "gate": {"ok": True, "opens_ok": _gate_ok, "opens_failed": _gate_fail},
        "database": {"ok": True, "avg_query_ms": _avg(_db_latencies)},
        "payment": {"ok": True},
    }
    body = {
        "ok": True,
        "state": startup_state(),
        "alpr_mode": alpr_mode(),
        "process": process,
        "hvx_host": hvx,
        "cameras": cameras,
        "domains": domains,
        "migration": migration_flags(),
        "media_gateway": {
            "child_pids": gateway.child_pids(),
            "sessions": len(gateway.live_metrics()),
            "mediamtx": mediamtx.health(),
        },
        "decode": cached_summary(),
        "gates": {
            "ok": _gate_ok,
            "failed": _gate_fail,
            "avg_latency_ms": _avg(_gate_latencies),
        },
        "database": {
            "avg_query_ms": _avg(_db_latencies),
            "slow_queries": list(_slow_queries),
        },
        "api": {"avg_latency_ms": _avg(_api_latencies)},
        "queues": queue_snapshots(),
        "circuit_breakers": all_breakers(),
        "worker_failures": list(_worker_failures),
        "disk": _disk(settings.data_dir),
        "time": datetime.now(timezone.utc).isoformat(),
    }
    return health_cache.set("details", body, ttl=1.0)


def _disk(path) -> dict:
    try:
        import shutil
        usage = shutil.disk_usage(path)
        return {
            "path": str(path),
            "free_bytes": usage.free,
            "total_bytes": usage.total,
            "used_ratio": round(1 - (usage.free / max(usage.total, 1)), 3),
        }
    except Exception:
        return {"path": str(path), "free_bytes": 0}
