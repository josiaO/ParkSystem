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


def _hybrid_fusion_stats() -> dict:
    try:
        from app.services.hybrid_fusion import stats

        body = stats()
        return {k: v for k, v in body.items() if k != "recent"}
    except Exception as exc:  # health must never fail because of a stats helper
        return {"error": str(exc)[:120]}


def _payments_stats() -> dict:
    try:
        from app.services.mobile_payments import payments_health

        body = payments_health()
        providers = body.get("providers") or {}
        return {
            "ok": True,
            "active_mobile_provider": body.get("active_mobile_provider"),
            "providers": {pid: {"mode": p.get("mode"), "available": p.get("available"), "reason": p.get("reason")}
                          for pid, p in providers.items()},
            "stats": body.get("stats"),
        }
    except Exception as exc:  # health must never fail because of a stats helper
        return {"ok": True, "error": str(exc)[:120]}


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
    from app.services.platform_capabilities import hvx_host_supported, platform_snapshot

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
    hvx_required = hvx_host_supported()
    if core and (hvx_ok or not hvx_required):
        status = "ready"
    elif core:
        status = "degraded"
    else:
        status = "not_ready"
    payload = {
        "ok": core,
        "status": status,
        "state": state,
        "db": {"ok": db_ok, "sqlite": is_sqlite(), "error": error},
        "hvx_host": {
            "ok": hvx_ok,
            "required": hvx_required,
            "supported": hvx_required,
            "note": (
                None if hvx_ok
                else (
                    "HVX NetSDK host is Windows-only; desktop and Site Service run without it. "
                    "Use rtsp/dahua/hikvision adapters for generic IP cameras."
                    if not hvx_required
                    else "HVX host not answering; SDK login and camera GPIO need the 32-bit host."
                )
            ),
        },
        "platform": platform_snapshot(),
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
    from app.services.modules import module_health
    from app.recognition_worker import worker_health
    from app.db import short_session
    with short_session() as _db:
        modules_snapshot = module_health(_db)
    ready_snap = ready()
    hvx = ready_snap["hvx_host"]
    platform = ready_snap.get("platform") or {}
    hvx_ok = bool(hvx.get("ok"))
    if hvx_ok:
        camera_detail = "HVX host"
    elif hvx.get("supported"):
        camera_detail = "HVX host down"
    else:
        camera_detail = "HVX Windows-only; use rtsp adapters on this OS"
    domains = {
        "camera_connection": {"ok": hvx_ok or not hvx.get("required", True), "detail": camera_detail},
        "media_gateway": {"ok": True, "local_sessions": len(gateway.live_metrics()), "mediamtx": mediamtx.health()},
        "recognition": {
            "ok": True,
            "alpr_mode": alpr_mode(),
            "native_alpr_enabled": migration_flags().get("native_alpr_enabled"),
            "hybrid_fusion": _hybrid_fusion_stats(),
        },
        "gate": {"ok": True, "opens_ok": _gate_ok, "opens_failed": _gate_fail},
        "database": {"ok": True, "avg_query_ms": _avg(_db_latencies)},
        "payment": _payments_stats(),
    }
    body = {
        "ok": True,
        "state": startup_state(),
        "status": ready_snap.get("status"),
        "alpr_mode": alpr_mode(),
        "process": process,
        "hvx_host": hvx,
        "platform": platform,
        "cameras": cameras,
        "domains": domains,
        "modules": modules_snapshot,
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
        "recognition_worker": worker_health(),
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
