"""What happened to each camera vehicle event: read, no plate found, rejected.

A camera event (the camera's vehicle trigger) that never becomes a capture
used to leave no trace; an event whose frame had no detectable plate was
dropped before it was even counted. Every event now ends in one outcome:

    read            FastALPR read a plate and the capture was saved
    native          the camera's own plate was used (native mode / fallback)
    no_plate_box    the detector found no plate in the event image
    unread          a plate box was found but no text could be read
    rejected:<why>  read, but not saved (duplicate, policy, stale ...)
    calibration_refused  a plate was found, but the camera's calibration
                    refused it before reading
    not_run         no read happened (camera busy, scope, worker-owned)

Counts per camera go into the runtime heartbeat; the trace gets one
``recognition.event_outcome`` row per event; and the images of events that
were not read are kept (newest ``KEEP_MISSES``) under ``media/misses`` so
someone can look at what the camera saw.
"""

from __future__ import annotations

import collections
import logging
import threading
import time
from pathlib import Path

log = logging.getLogger("smartpark")

KEEP_MISSES = 300
KEEP_IMAGE_FOR = {"no_plate_box", "unread", "not_run", "calibration_refused"}
_lock = threading.Lock()
_counts: dict[int, collections.Counter] = collections.defaultdict(collections.Counter)


def classify(result: dict | None) -> str:
    """Outcome of one ``_run_event_alpr`` result."""
    if result is None:
        return "not_run"
    if result.get("read_budget") == "skipped":
        return "skipped_already_read"
    if result.get("persist_skipped"):
        return "rejected:" + str(result["persist_skipped"])[:40]
    if result.get("ok") is False:
        return "not_run" if result.get("error") in {"busy", "timeout"} else "unread"
    if result.get("calibration_refused"):
        # A plate was found but the camera's calibration refused it. Its
        # detail says "no plate inside this camera's calibration", which was
        # counted as no_plate_box and hid calibration refusals among empty
        # pictures (29 of 44 camera-4 "no plate" pictures one morning).
        return "calibration_refused"
    if not result.get("best"):
        return "no_plate_box" if "no plate" in str(result.get("detail") or "") else "unread"
    return "read"


def note(camera_id: int, outcome: str, *, visit_id: str = "", jpeg: bytes = b"", detail: str = "") -> None:
    key = outcome.split(":", 1)[0]
    with _lock:
        _counts[int(camera_id)][key] += 1
    try:
        from app.core import latency_trace

        latency_trace.emit("recognition.event_outcome", camera=int(camera_id), visit_id=visit_id or None,
                           outcome=outcome, detail=(detail or "")[:120] or None)
    except Exception:
        pass
    if key in KEEP_IMAGE_FOR and jpeg[:2] == b"\xff\xd8":
        try:
            _keep_image(int(camera_id), key, jpeg)
        except Exception:
            log.debug("could not keep missed-event image", exc_info=True)


def stats() -> dict[str, dict[str, int]]:
    with _lock:
        return {str(cam): dict(counter) for cam, counter in sorted(_counts.items())}


def misses_dir() -> Path:
    from app.config import settings

    return settings.media_dir / "misses"


def _keep_image(camera_id: int, outcome: str, jpeg: bytes) -> None:
    folder = misses_dir()
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    (folder / f"cam{camera_id}-{stamp}-{int(time.time() * 1000) % 1000:03d}-{outcome}.jpg").write_bytes(jpeg)
    files = sorted(folder.glob("*.jpg"), key=lambda p: p.stat().st_mtime)
    for old in files[:-KEEP_MISSES]:
        old.unlink(missing_ok=True)
