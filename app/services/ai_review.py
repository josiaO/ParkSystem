"""Optional AI second opinion for plate captures (Codex §9).

Guarantees:

* Off unless ``SMARTPARK_AI_ENABLED=true`` **and** the recognition module is on.
* Never on the gate path: reviews run as background tasks after the capture is
  persisted; the plate decision, session and gate command are already made.
* Never every frame: only low-confidence reads, native/FastALPR disagreement,
  operator requests, and (opt-in) vehicle attributes; per-camera minimum
  interval; bounded concurrency; daily request cap; circuit breaker; one
  attempt, no retries.
* Privacy: real imagery is only sent once ``ai_data_treatment_accepted`` is
  true; simulated/synthetic captures are always allowed.
* The result is stored on ``vehicle_captures.ai_review`` and shown to the
  operator as supporting/conflicting evidence. It never rewrites the plate.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.domain.ai_review import (
    REASON_DISAGREEMENT,
    REASON_LOW_CONFIDENCE,
    REASON_MANUAL,
    IncidentSummaryRequest,
    VehicleReview,
    VehicleReviewRequest,
)
from app.models import VehicleCapture

log = logging.getLogger("smartpark")

SYNTHETIC_SOURCES = ("simulation", "simulated", "synthetic", "test", "fixture")

_stats: dict[str, Any] = {}
_last_by_camera: dict[int, float] = {}
_pending: set[asyncio.Task] = set()
_semaphore: asyncio.Semaphore | None = None
_semaphore_loop: asyncio.AbstractEventLoop | None = None
_recent: list[dict] = []
RECENT_LIMIT = 20


class DailyBudget:
    def __init__(self, cap: int):
        self.cap = int(cap)
        self.day = ""
        self.used = 0

    def _roll(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self.day:
            self.day, self.used = today, 0

    def remaining(self) -> int:
        self._roll()
        return max(0, self.cap - self.used)

    def take(self) -> bool:
        self._roll()
        if self.cap <= 0 or self.used >= self.cap:
            return False
        self.used += 1
        return True

    def snapshot(self) -> dict:
        self._roll()
        return {"cap": self.cap, "used": self.used, "remaining": self.remaining(), "day": self.day}


_budget = DailyBudget(int(settings.ai_daily_request_cap or 0))


def reset() -> None:
    """Tests."""
    global _budget, _semaphore, _semaphore_loop
    _stats.clear()
    _stats.update(
        requested=0, sent=0, supporting=0, conflicting=0, unreadable=0, unavailable=0,
        skipped_disabled=0, skipped_privacy=0, skipped_interval=0, skipped_budget=0, skipped_busy=0,
        persist_errors=0,
    )
    _last_by_camera.clear()
    _recent.clear()
    _budget = DailyBudget(int(settings.ai_daily_request_cap or 0))
    _semaphore = None
    _semaphore_loop = None


reset()


def stats() -> dict:
    return dict(_stats)


def recent() -> list[dict]:
    return list(_recent)


def enabled(db: Session | None = None) -> bool:
    if not bool(settings.ai_enabled):
        return False
    try:
        from app.services.modules import is_enabled

        return is_enabled("recognition.alpr", db)
    except Exception:
        return False


def privacy_allows(synthetic: bool) -> bool:
    return bool(synthetic) or bool(settings.ai_data_treatment_accepted)


def is_synthetic(capture: dict | VehicleCapture | None) -> bool:
    if capture is None:
        return False
    source = capture.get("source") if isinstance(capture, dict) else getattr(capture, "source", "")
    return str(source or "").lower() in SYNTHETIC_SOURCES


def review_reason(capture: dict | None) -> str:
    """Why a persisted capture deserves a second opinion, or '' for none."""
    if not capture:
        return ""
    if capture.get("needs_review") or capture.get("pending_confirmation"):
        native = str(capture.get("native_plate") or "")
        local = str(capture.get("local_plate") or "")
        if native and local and native != local:
            return REASON_DISAGREEMENT
        return REASON_LOW_CONFIDENCE
    try:
        confidence = float(capture.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    if capture.get("plate") and confidence < float(settings.ai_low_confidence_below or 0):
        return REASON_LOW_CONFIDENCE
    return ""


def _sem() -> asyncio.Semaphore:
    global _semaphore, _semaphore_loop
    loop = asyncio.get_running_loop()
    if _semaphore is None or _semaphore_loop is not loop:
        _semaphore = asyncio.Semaphore(max(1, int(settings.ai_max_concurrency or 1)))
        _semaphore_loop = loop
    return _semaphore


def _candidates(capture: dict) -> list[str]:
    out = []
    for key in ("plate", "native_plate", "local_plate", "plate_raw"):
        value = str(capture.get(key) or "")
        if value:
            out.append(value)
    return out


def _downscale(jpeg: bytes, max_px: int) -> bytes:
    if not jpeg:
        return b""
    try:
        from io import BytesIO

        from PIL import Image

        img = Image.open(BytesIO(jpeg)).convert("RGB")
        if max(img.size) > max_px:
            img.thumbnail((max_px, max_px))
        out = BytesIO()
        img.save(out, format="JPEG", quality=80)
        return out.getvalue()
    except Exception:
        return b""


def _read_media(rel: str) -> bytes:
    if not rel:
        return b""
    try:
        return (Path(settings.media_dir) / rel).read_bytes()
    except OSError:
        return b""


def _remember(camera_id: int, capture_id: int | None, review: VehicleReview) -> None:
    _recent.append({"camera_id": camera_id, "capture_id": capture_id, **review.as_dict()})
    if len(_recent) > RECENT_LIMIT:
        del _recent[: len(_recent) - RECENT_LIMIT]
    verdict = review.verdict if review.verdict in ("supporting", "conflicting", "unreadable") else "unavailable"
    _stats[verdict] = _stats.get(verdict, 0) + 1


def _persist_review(capture_id: int | None, review: VehicleReview) -> None:
    if not capture_id:
        return
    from app.db import short_session

    try:
        with short_session() as db:
            row = db.get(VehicleCapture, int(capture_id))
            if row is None:
                return
            row.ai_review = review.as_dict()
            db.commit()
    except Exception as exc:
        _stats["persist_errors"] += 1
        log.warning("ai review: could not store result for capture %s: %s", capture_id, exc)


async def run_review(request: VehicleReviewRequest, *, persist: bool = True) -> VehicleReview:
    """Perform one review with all limits applied. Safe to await from API handlers."""
    from app.infrastructure.ai import provider_for

    _stats["requested"] += 1
    if not privacy_allows(request.synthetic):
        _stats["skipped_privacy"] += 1
        review = VehicleReview(readable=False, plate_candidate="", reason=request.reason,
                               error="data treatment not accepted for real imagery", verdict="unavailable", at=time.time())
        _remember(request.camera_id, request.capture_id, review)
        return review
    if not _budget.take():
        _stats["skipped_budget"] += 1
        review = VehicleReview(readable=False, plate_candidate="", reason=request.reason,
                               error="daily AI request cap reached", verdict="unavailable", at=time.time())
        _remember(request.camera_id, request.capture_id, review)
        return review
    provider = provider_for()
    if settings.ai_send_vehicle_image and request.vehicle_jpeg:
        request.vehicle_jpeg = _downscale(request.vehicle_jpeg, int(settings.ai_vehicle_image_max_px or 640))
        request.want_vehicle_attributes = True
    else:
        request.vehicle_jpeg = b""
        request.want_vehicle_attributes = False
    async with _sem():
        _stats["sent"] += 1
        try:
            review = await asyncio.wait_for(
                provider.review_vehicle_event(request), timeout=float(settings.ai_timeout_seconds or 4.0) + 1.0
            )
        except asyncio.TimeoutError:
            review = VehicleReview(readable=False, plate_candidate="", provider=getattr(provider, "provider_id", ""),
                                   reason=request.reason, error="timeout", verdict="unavailable")
        except Exception as exc:  # provider bug: never propagate into capture handling
            review = VehicleReview(readable=False, plate_candidate="", provider=getattr(provider, "provider_id", ""),
                                   reason=request.reason, error=f"{type(exc).__name__}", verdict="unavailable")
    review.at = review.at or time.time()
    _remember(request.camera_id, request.capture_id, review)
    if persist:
        _persist_review(request.capture_id, review)
    return review


def schedule_capture_review(capture: dict | None, *, crop: bytes, jpeg: bytes, db: Session | None = None,
                            reason: str | None = None) -> asyncio.Task | None:
    """Fire-and-forget after a capture is persisted. Returns the task or None when skipped."""
    if not capture or not capture.get("id"):
        return None
    if not enabled(db):
        _stats["skipped_disabled"] += 1
        return None
    reason = reason or review_reason(capture)
    if not reason:
        return None
    camera_id = int(capture.get("camera_id") or 0)
    synthetic = is_synthetic(capture)
    if not privacy_allows(synthetic):
        _stats["skipped_privacy"] += 1
        return None
    now = time.monotonic()
    last = _last_by_camera.get(camera_id, 0.0)
    if now - last < float(settings.ai_min_interval_seconds or 0):
        _stats["skipped_interval"] += 1
        return None
    live = {t for t in _pending if not t.done()}
    _pending.intersection_update(live)
    if len(live) >= max(1, int(settings.ai_max_concurrency or 1)) * 2:
        _stats["skipped_busy"] += 1
        return None
    if _budget.remaining() <= 0:
        _stats["skipped_budget"] += 1
        return None
    _last_by_camera[camera_id] = now
    request = VehicleReviewRequest(
        camera_id=camera_id,
        capture_id=int(capture["id"]),
        reason=reason,
        plate_candidates=_candidates(capture),
        crop_jpeg=crop or b"",
        vehicle_jpeg=jpeg or b"",
        synthetic=synthetic,
    )
    try:
        task = asyncio.get_running_loop().create_task(run_review(request), name=f"ai-review-{capture['id']}")
    except RuntimeError:
        return None  # no running loop (sync test path): skip silently
    _pending.add(task)
    task.add_done_callback(_pending.discard)
    return task


async def review_capture(db: Session, capture_id: int, *, reason: str = REASON_MANUAL) -> VehicleReview:
    """Operator-requested second opinion. Awaited; result stored on the capture."""
    row = db.get(VehicleCapture, int(capture_id))
    if row is None:
        raise LookupError("capture not found")
    from app.services.captures import capture_dict

    payload = capture_dict(row)
    request = VehicleReviewRequest(
        camera_id=int(row.camera_id or 0),
        capture_id=int(row.id),
        reason=reason,
        plate_candidates=_candidates(payload),
        crop_jpeg=_read_media(row.crop_path),
        vehicle_jpeg=_read_media(row.snapshot_path),
        synthetic=is_synthetic(row),
    )
    review = await run_review(request, persist=False)
    row.ai_review = review.as_dict()
    db.commit()
    return review


def _event_row(row: VehicleCapture) -> dict:
    return {
        "capture_id": row.id,
        "at": row.created_at.isoformat() if row.created_at else None,
        "camera_id": row.camera_id,
        "gate_id": row.gate_id,
        "direction": row.lane_direction,
        "plate": row.plate,
        "confidence": float(row.confidence or 0),
        "source": row.source,
        "needs_review": bool((row.bbox or {}).get("needs_review")) if isinstance(row.bbox, dict) else False,
    }


async def summarize_incident(db: Session, *, capture_ids: list[int] | None = None, plate: str | None = None,
                             limit: int = 30, question: str = "") -> dict:
    """Natural-language incident summary. Facts from the ledger, prose from the model."""
    from app.infrastructure.ai import provider_for

    if not enabled(db):
        return {"ok": False, "reason": "ai_disabled", "text": ""}
    stmt = select(VehicleCapture).order_by(VehicleCapture.id.desc())
    if capture_ids:
        stmt = stmt.where(VehicleCapture.id.in_([int(c) for c in capture_ids][:limit]))
    elif plate:
        stmt = stmt.where(VehicleCapture.plate == plate)
    rows = list(db.scalars(stmt.limit(limit)).all())
    events = [_event_row(r) for r in rows]
    synthetic = bool(rows) and all(is_synthetic(r) for r in rows)
    if not privacy_allows(synthetic):
        _stats["skipped_privacy"] += 1
        return {"ok": False, "reason": "data_treatment_not_accepted", "text": "", "events": len(events)}
    if not _budget.take():
        _stats["skipped_budget"] += 1
        return {"ok": False, "reason": "daily_cap", "text": "", "events": len(events)}
    provider = provider_for()
    async with _sem():
        _stats["sent"] += 1
        try:
            summary = await asyncio.wait_for(
                provider.summarize_incident(IncidentSummaryRequest(events=events, question=question, synthetic=synthetic)),
                timeout=float(settings.ai_timeout_seconds or 4.0) + 1.0,
            )
        except asyncio.TimeoutError:
            return {"ok": False, "reason": "timeout", "text": "", "events": len(events)}
    body = summary.as_dict()
    body.update(ok=not summary.error, events=len(events), reason=summary.error or "")
    return body


def health(db: Session | None = None) -> dict:
    from app.infrastructure.ai import provider_for

    on = enabled(db)
    provider = provider_for() if bool(settings.ai_enabled) else None
    return {
        "enabled": on,
        "ai_enabled_setting": bool(settings.ai_enabled),
        "provider": provider.health() if provider else {"provider_id": "none", "available": False, "reason": "disabled"},
        "model": str(settings.ai_model or ""),
        "data_treatment_accepted": bool(settings.ai_data_treatment_accepted),
        "budget": _budget.snapshot(),
        "limits": {
            "timeout_seconds": float(settings.ai_timeout_seconds or 0),
            "max_concurrency": int(settings.ai_max_concurrency or 0),
            "min_interval_seconds": float(settings.ai_min_interval_seconds or 0),
            "low_confidence_below": float(settings.ai_low_confidence_below or 0),
            "send_vehicle_image": bool(settings.ai_send_vehicle_image),
        },
        "pending": len([t for t in _pending if not t.done()]),
        "stats": stats(),
        "gate_authority": False,
    }
