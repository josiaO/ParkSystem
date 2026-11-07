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


def _onvif_events_stats() -> dict:
    try:
        from app.services.onvif_runtime import stats

        return stats()
    except Exception as exc:  # health must never fail because of a stats helper
        return {"error": str(exc)[:120]}


def _ai_review_stats() -> dict:
    try:
        from app.services.ai_review import health

        body = health()
        return {
            "enabled": body.get("enabled"),
            "provider": (body.get("provider") or {}).get("provider_id"),
            "available": (body.get("provider") or {}).get("available"),
            "budget": body.get("budget"),
            "pending": body.get("pending"),
            "stats": body.get("stats"),
        }
    except Exception as exc:  # health must never fail because of a stats helper
        return {"enabled": False, "error": str(exc)[:120]}


def _camera_freshness() -> dict:
    """Expose live-camera freshness separately from process readiness.

    `/health/ready` remains a core startup probe so an unconfigured site can
    finish setup, while this section prevents a healthy HTTP process from
    being mistaken for healthy camera lanes.
    """
    try:
        from app.services.preview import live_metrics

        rows = live_metrics()
        required_ids: set[int] = set()
        try:
            from app.db import SessionLocal
            from app.models import Camera
            from app.services.node_scope import camera_active_on_this_installation

            with SessionLocal() as db:
                for camera in db.query(Camera).filter(Camera.enabled == True).all():  # noqa: E712
                    if camera_active_on_this_installation(camera, db=db):
                        required_ids.add(int(camera.id))
        except Exception:
            # Health must remain available during first-run/migration. An
            # unavailable registry means operational requirements are unknown,
            # not that every lane is healthy.
            required_ids = set()
        observed = [row for row in rows if row.get("pumping") or row.get("viewers")]
        stale = [
            row for row in observed
            if row.get("frozen") or row.get("connection_state") not in {"STREAMING", "READY"}
            or row.get("live_frame_age_ms") is None
            or float(row.get("live_frame_age_ms") or 0) > 5000
        ]
        by_id = {int(row.get("camera_id")): row for row in rows if row.get("camera_id") is not None}
        required_stale = [
            camera_id for camera_id in sorted(required_ids)
            if camera_id not in by_id
            or camera_id not in {int(row.get("camera_id")) for row in observed}
            or int(camera_id) in {int(row.get("camera_id")) for row in stale}
        ]
        operational_status = (
            "degraded" if required_stale or stale
            else "healthy" if required_ids or observed
            else "not_observed"
        )
        return {
            "status": operational_status,
            "observed_count": len(observed),
            "stale_camera_ids": [row.get("camera_id") for row in stale],
            "required_camera_ids": sorted(required_ids),
            "required_stale_camera_ids": required_stale,
            "operational_ready": not required_stale and bool(required_ids or observed),
            "rows": [
                {
                    "camera_id": row.get("camera_id"),
                    "required": int(row.get("camera_id") or 0) in required_ids,
                    "state": row.get("connection_state"),
                    "frame_age_ms": row.get("live_frame_age_ms"),
                    "fps": row.get("fps"),
                    "frozen": bool(row.get("frozen")),
                    "stall_classification": row.get("stall_classification"),
                }
                for row in observed
            ],
        }
    except Exception as exc:
        return {
            "status": "unknown", "observed_count": 0, "stale_camera_ids": [],
            "required_camera_ids": [], "required_stale_camera_ids": [],
            "operational_ready": False, "error": str(exc)[:160],
        }


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


def camera_stats(camera_id: int) -> dict:
    row = _camera_stats.get(int(camera_id)) or {}
    policy = reconnect_for(int(camera_id)).snapshot()
    return {
        "reconnect_count": row.get("reconnect_count", policy.get("attempts") or 0),
        "last_event_at": row.get("last_event_at") or 0,
        "event_latency_ms": row.get("event_latency_ms") or 0,
        "sdk_callback": row.get("sdk_callback") or "idle",
    }


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
    camera_freshness = _camera_freshness()
    try:
        from app.recognition_worker import worker_health

        recognition = worker_health()
        recognition_summary = {
            "ok": bool(recognition.get("ok")),
            "state": recognition.get("state"),
            "heartbeat_age_seconds": recognition.get("heartbeat_age_seconds"),
        }
    except Exception as exc:
        recognition_summary = {"ok": False, "state": "UNKNOWN", "error": str(exc)[:160]}
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
        "db": {**database_health(), "ok": db_ok, "sqlite": is_sqlite(), "error": error},
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
        "camera_freshness": camera_freshness,
        "recognition": recognition_summary,
        "time": datetime.now(timezone.utc).isoformat(),
    }
    return payload


def database_health() -> dict:
    """Safe database metadata for technicians; never returns credentials."""
    from app.db import SessionLocal, engine, is_sqlite
    from app.migrations.runner import status

    started = time.perf_counter()
    try:
        with SessionLocal() as db:
            db.execute(__import__("sqlalchemy").text("SELECT 1"))
        return {
            "engine": "SQLite" if is_sqlite() else "PostgreSQL",
            "state": "HEALTHY",
            "revision": status(engine).get("revision"),
            "head": status(engine).get("head"),
            "up_to_date": status(engine).get("up_to_date", False),
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    except Exception as exc:
        return {
            "engine": "SQLite" if is_sqlite() else "PostgreSQL",
            "state": "UNHEALTHY",
            "revision": status(engine).get("revision"),
            "head": status(engine).get("head"),
            "up_to_date": False,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "error": str(exc)[:200],
        }


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
    from app.services.recognition_runtime import runtime
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
            "onvif_events": _onvif_events_stats(),
            "ai_review": _ai_review_stats(),
        },
        "gate": {"ok": True, "opens_ok": _gate_ok, "opens_failed": _gate_fail},
        "database": {"ok": True, "avg_query_ms": _avg(_db_latencies), "schema": _schema_status()},
        "payment": _payments_stats(),
        "secret_store": _secrets_status(),
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
            "schema": _schema_status(),
        },
        "api": {"avg_latency_ms": _avg(_api_latencies)},
        "queues": queue_snapshots(),
        "circuit_breakers": all_breakers(),
        "worker_failures": list(_worker_failures),
        "recognition_worker": worker_health(),
        "recognition_runtime": {"scheduler": runtime.scheduler.snapshot(), "cameras": runtime.snapshot()},
        "disk": _disk(settings.data_dir),
        "time": datetime.now(timezone.utc).isoformat(),
    }
    from app.services.redaction import redact_obj

    return health_cache.set("details", redact_obj(body), ttl=1.0)


def _schema_status() -> dict:
    try:
        from app.db import engine
        from app.migrations.runner import status

        return status(engine)
    except Exception as exc:
        return {"error": str(exc)[:200], "up_to_date": False}


def _secrets_status() -> dict:
    try:
        from app.infrastructure.secrets import describe

        return describe()
    except Exception as exc:
        return {"backend": "unknown", "error": str(exc)[:200]}


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
