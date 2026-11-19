"""Evidence photos written after the access decision (operational path).

docs/ZIRP_HIGH_THROUGHPUT_ARCHITECTURE.md step 3. A live camera capture is
committed with *reserved* photo names and ``evidence_state='PENDING'``; the
decision runs at once. Cropping the zone snapshot and the plate crop (about
150 ms p50 and over 1 s at worst on SERVER01) and writing the files happen
here, on a small dedicated thread pool that never shares threads with plate
inference. The row then becomes ``STORED``. A row still PENDING after
``PENDING_MISSING_MINUTES`` (process died with the bytes in memory) is marked
``MISSING`` by the lane sweeper, so a lost photo is visible, never silent.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

log = logging.getLogger("smartpark")

PENDING = "PENDING"
STORED = "STORED"
MISSING = "MISSING"
PENDING_MISSING_MINUTES = 10
WORKERS = 2

_executor: ThreadPoolExecutor | None = None
_lock = threading.Lock()
_stats = {"submitted": 0, "stored": 0, "failed": 0, "in_flight": 0, "max_in_flight": 0}


@dataclass
class EvidenceJob:
    """Everything needed to produce the photos once the decision is made."""

    capture_id: int
    snapshot_ref: str            # reserved "snapshots/<name>" or ""
    crop_ref: str                # reserved "crops/<name>" or ""
    make_snapshot: Callable[[], bytes]
    make_crop: Callable[[], bytes]
    extra: dict[str, Any] = field(default_factory=dict)


def _pool() -> ThreadPoolExecutor:
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="evidence")
        return _executor


def stats() -> dict[str, int]:
    with _lock:
        return dict(_stats)


def _write(ref: str, data: bytes) -> bool:
    from app.config import settings

    if not ref or not data or data[:2] != b"\xff\xd8":
        return False
    dest = Path(settings.media_dir) / ref
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(dest)
    return True


def run_job(job: EvidenceJob, session_factory: Callable[[], Session] | None = None) -> str:
    """Produce and write the photos, then record the outcome. Returns the state."""
    from app.models import VehicleCapture

    snapshot_ok = crop_ok = False
    try:
        snapshot_ok = _write(job.snapshot_ref, job.make_snapshot()) if job.snapshot_ref else False
    except Exception:
        log.warning("evidence snapshot failed capture=%s", job.capture_id, exc_info=True)
    try:
        crop_ok = _write(job.crop_ref, job.make_crop()) if job.crop_ref else False
    except Exception:
        log.warning("evidence crop failed capture=%s", job.capture_id, exc_info=True)
    state = STORED if (snapshot_ok or crop_ok) else MISSING
    values: dict[str, Any] = {"evidence_state": state}
    # Never leave a reference to a file that was not produced.
    if job.snapshot_ref and not snapshot_ok:
        values["snapshot_path"] = ""
    if job.crop_ref and not crop_ok:
        values["crop_path"] = ""
    if session_factory is None:
        from app.db import short_session as session_factory
    with session_factory() as db:
        db.execute(update(VehicleCapture).where(VehicleCapture.id == job.capture_id).values(**values))
        db.commit()
    with _lock:
        _stats["stored" if state == STORED else "failed"] += 1
    return state


_pending_refs: dict[str, threading.Event] = {}


def wait_for(ref: str, timeout: float = 2.0) -> bool:
    """Wait (outside the event loop) for a photo this process is still writing.

    Live screens ask for a car's photo as soon as its plate shows, which can
    be before the evidence writer has finished. Returns False at once for
    anything not pending here.
    """
    with _lock:
        done = _pending_refs.get(ref)
    return bool(done and done.wait(timeout))


def submit(job: EvidenceJob, session_factory: Callable[[], Session] | None = None) -> Future:
    refs = [ref for ref in (job.snapshot_ref, job.crop_ref) if ref]
    done = threading.Event()
    with _lock:
        _stats["submitted"] += 1
        _stats["in_flight"] += 1
        _stats["max_in_flight"] = max(_stats["max_in_flight"], _stats["in_flight"])
        for ref in refs:
            _pending_refs[ref] = done

    def _run() -> str:
        try:
            return run_job(job, session_factory)
        except Exception:
            log.warning("evidence job failed capture=%s", job.capture_id, exc_info=True)
            with _lock:
                _stats["failed"] += 1
            return MISSING
        finally:
            with _lock:
                _stats["in_flight"] -= 1
                for ref in refs:
                    if _pending_refs.get(ref) is done:
                        _pending_refs.pop(ref, None)
            done.set()

    return _pool().submit(_run)


def mark_stale_pending(db: Session, *, now: datetime | None = None,
                       older_than_minutes: float = PENDING_MISSING_MINUTES) -> int:
    """PENDING rows whose writer never finished (restart, crash) become MISSING."""
    from app.models import VehicleCapture

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=older_than_minutes)
    ids = db.scalars(
        select(VehicleCapture.id)
        .where(VehicleCapture.evidence_state == PENDING, VehicleCapture.created_at < cutoff)
        .limit(500)
    ).all()
    if not ids:
        return 0
    from app.config import settings

    for capture_id in ids:
        row = db.get(VehicleCapture, capture_id)
        if row is None:
            continue
        snapshot_ok = bool(row.snapshot_path) and (Path(settings.media_dir) / row.snapshot_path).is_file()
        crop_ok = bool(row.crop_path) and (Path(settings.media_dir) / row.crop_path).is_file()
        if not snapshot_ok:
            row.snapshot_path = ""
        if not crop_ok:
            row.crop_path = ""
        row.evidence_state = STORED if (snapshot_ok or crop_ok) else MISSING
    db.commit()
    return len(ids)
