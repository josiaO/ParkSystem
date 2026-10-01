"""Site Service glue for process-safe native + FastALPR fusion.

Native candidates come from the HVX callback loop in this process; FastALPR
candidates come from the Recognition Worker through the SQLite outbox. Both are
offered to one ``FusionCoordinator`` per Site Service, and the resulting
decision is persisted through the same capture/session path the legacy fusion
used, so parking, gates and audit see exactly one capture per vehicle event.

Routing is gated: a camera is handled here only when
``recognition_worker.worker_owns_software_reads`` is true (new pipeline flag,
MediaMTX detect path, fresh worker heartbeat) and the camera mode is HYBRID.
Everything else keeps the established in-process fusion.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.core.fusion import DEFAULT_FUSION
from app.core.hybrid import SOURCE_LOCAL, SOURCE_NATIVE, Candidate, FusionCoordinator, FusionOutcome

PersistFn = Callable[[Any, Any, dict | None, bytes, bytes], Awaitable[dict | None]]

_coordinator = FusionCoordinator(settings=dict(DEFAULT_FUSION))
_persist: PersistFn | None = None
_stats: dict[str, int] = {"native_offered": 0, "local_offered": 0, "decided": 0, "paired": 0,
                          "suppressed": 0, "held": 0, "persist_errors": 0}
_recent: list[dict[str, Any]] = []
RECENT_LIMIT = 50


@dataclass
class _Evidence:
    jpeg: bytes = b""
    crop: bytes = b""
    capture: dict[str, Any] = field(default_factory=dict)


def coordinator() -> FusionCoordinator:
    return _coordinator


def set_persist(fn: PersistFn | None) -> None:
    """Inject the capture/session persistence coroutine (owned by api_main)."""
    global _persist
    _persist = fn


def stats() -> dict[str, Any]:
    pending = {cid: {k: (v.plate if v else None) for k, v in _coordinator.pending(cid).items()}
               for cid in list(_coordinator._lanes)}
    return {**_stats, "pending": pending, "recent": list(_recent[-10:])}


def _hybrid_mode(camera) -> bool:
    from app.services.ocr_policy import NATIVE_WITH_LOCAL_VERIFY, camera_recognition_mode

    return camera_recognition_mode(camera) == NATIVE_WITH_LOCAL_VERIFY


def routes_camera(camera, db=None) -> bool:
    """True when this camera's native and software reads are fused here."""
    if camera is None or not _hybrid_mode(camera):
        return False
    from app.recognition_worker import worker_owns_software_reads

    return worker_owns_software_reads(int(camera.id))


def native_counterpart_available(camera) -> bool:
    from app.infrastructure.hardware.cameras import adapter_has_native_plates

    try:
        return bool(adapter_has_native_plates(camera))
    except Exception:
        return False


def local_counterpart_available(camera_id: int) -> bool:
    from app.recognition_worker import _worker_ready

    return bool(_worker_ready(int(camera_id)))


def _remember(outcome: FusionOutcome) -> None:
    _recent.append({"at": time.time(), **outcome.as_dict()})
    if len(_recent) > RECENT_LIMIT:
        del _recent[: len(_recent) - RECENT_LIMIT]


async def _apply(camera, outcome: FusionOutcome, evidence: _Evidence, db) -> dict | None:
    from app.services.camera_lpr import capture_from_readings

    _stats["decided"] += 1
    if outcome.paired:
        _stats["paired"] += 1
    if outcome.decision.needs_review:
        _stats["held"] += 1
    _remember(outcome)
    if outcome.suppressed:
        _stats["suppressed"] += 1
        return None
    if not outcome.plate or _persist is None:
        return None
    native = dict((outcome.native.payload if outcome.native else {}) or {})
    local = dict((outcome.local.payload if outcome.local else {}) or {})
    capture = capture_from_readings(native, local, outcome.decision, image_id=int(native.get("image_id") or 0))
    capture["fusion"] = {**capture.get("fusion", {}), "paired": outcome.paired, "coordinator": "site-service"}
    capture["source"] = "hybrid"
    event_id = str(local.get("event_id") or native.get("event_id") or "")
    if event_id:
        capture["event_id"] = event_id
    if not capture.get("image_id"):
        capture["image_id"] = int(time.time() * 1000) % 2_000_000_000
    try:
        return await _persist(db, camera, capture, evidence.jpeg, evidence.crop)
    except Exception:
        _stats["persist_errors"] += 1
        raise


async def offer_native(db, camera, native: dict, *, jpeg: bytes = b"", crop: bytes = b"", capture: dict | None = None) -> list[dict | None]:
    """Offer a native (camera ALPR) reading; persists any ready decision."""
    camera_id = int(camera.id)
    _stats["native_offered"] += 1
    payload = {**(native or {}), "event_id": str((capture or {}).get("event_id") or "")}
    candidate = Candidate(SOURCE_NATIVE, str(native.get("plate") or ""), float(native.get("confidence") or 0), time.monotonic(), payload)
    _evidence[camera_id] = _Evidence(jpeg=jpeg or b"", crop=crop or b"", capture=dict(capture or {}))
    outcomes = _coordinator.offer(camera_id, candidate, now=time.monotonic(),
                                  counterpart_available=local_counterpart_available(camera_id))
    return [await _apply(camera, o, _evidence.get(camera_id) or _Evidence(), db) for o in outcomes]


async def offer_local(db, camera, recognized: dict, *, jpeg: bytes = b"", crop: bytes = b"") -> list[dict | None]:
    """Offer a worker FastALPR reading unwrapped from the outbox."""
    camera_id = int(camera.id)
    _stats["local_offered"] += 1
    consensus = recognized.get("consensus") if isinstance(recognized.get("consensus"), dict) else {}
    payload = {
        "plate": recognized.get("plate") or recognized.get("normalized_plate") or "",
        "plate_raw": recognized.get("raw_plate") or recognized.get("plate_text_raw") or "",
        "confidence": float(recognized.get("confidence") or recognized.get("recognition_confidence") or 0),
        "bbox": recognized.get("bbox"),
        "source": "fastalpr",
        "event_id": str(recognized.get("event_id") or ""),
        "consensus": consensus,
    }
    candidate = Candidate(SOURCE_LOCAL, str(payload["plate"]), payload["confidence"], time.monotonic(), payload,
                          consensus=bool(consensus.get("publish") or int(consensus.get("agreeing") or 0) >= 2))
    existing = _evidence.get(camera_id)
    if existing is None:
        _evidence[camera_id] = _Evidence(jpeg=jpeg or b"", crop=crop or b"")
    else:
        if jpeg[:2] == b"\xff\xd8" and existing.jpeg[:2] != b"\xff\xd8":
            existing.jpeg = jpeg
        if crop[:2] == b"\xff\xd8":
            existing.crop = crop
    outcomes = _coordinator.offer(camera_id, candidate, now=time.monotonic(),
                                  counterpart_available=native_counterpart_available(camera))
    return [await _apply(camera, o, _evidence.get(camera_id) or _Evidence(), db) for o in outcomes]


async def flush(db_factory) -> int:
    """Decide candidates whose counterpart never arrived. Returns decisions made."""
    outcomes = _coordinator.flush(time.monotonic())
    if not outcomes:
        return 0
    from app.models import Camera

    applied = 0
    for outcome in outcomes:
        with db_factory() as db:
            camera = db.get(Camera, int(outcome.camera_id))
            if camera is None:
                continue
            await _apply(camera, outcome, _evidence.get(int(outcome.camera_id)) or _Evidence(), db)
            applied += 1
    return applied


_evidence: dict[int, _Evidence] = {}


def reset() -> None:
    """Test hook."""
    _coordinator.reset()
    _evidence.clear()
    _recent.clear()
    for key in _stats:
        _stats[key] = 0
