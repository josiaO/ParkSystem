from __future__ import annotations

"""SmartParkRecognitionWorker — FastALPR on the local MediaMTX RTSP path.

MediaMTX owns the camera connection and browser video. This process is only
a recognition consumer: one lightweight FFmpeg decoder per lane reads
``rtsp://127.0.0.1:8554/<detect-path>``, keeps the newest JPEG, and samples
a few frames per second. The detector watches the camera's zone. OCR runs
only after the plate holds still, on the cropped plate, then pauses until
the vehicle leaves. SDK cameras remain on the Site Service camera-event loop.
"""

import asyncio

import json

import logging

import os

from pathlib import Path

import sys

import tempfile

import time

from app.core.consensus import ConsensusTrack, TrackDecision

log = logging.getLogger("smartpark")

class PlateTrack(ConsensusTrack):
    """Per-camera temporal consensus (similarity + confidence weighted)."""

_owns_cache: dict[int, tuple[float, bool]] = {}

WORKER_MODES = frozenset({"LOCAL_ONLY", "NATIVE_WITH_LOCAL_VERIFY"})

async def _loop() -> None:
    from app.db import SessionLocal
    from app.services.flags import flags
    from app.config import settings

    tasks: dict[int, tuple[asyncio.Event, asyncio.Task, dict]] = {}
    configurations: dict[int, dict] = {}
    # The runtime scheduler is the single admission controller for native
    # recognition.  Do not add a process-wide asyncio semaphore here: a native
    # call that stalls cannot be cancelled safely and would keep that semaphore
    # occupied, delaying unrelated cameras.  FairInferenceScheduler admits at
    # most one call per camera and releases a stalled lane through the watchdog,
    # so other cameras keep decoding and recognizing independently.
    from app.services.recognition_runtime import runtime
    retiring: dict[int, asyncio.Task] = {}
    warmup_task: asyncio.Task | None = None
    warmup_status: dict = {"ready": False}
    warmup_failures = 0
    warmup_retry_at = 0.0
    from sqlalchemy.exc import OperationalError
    try:
        while True:
            try:
                with SessionLocal() as db:
                    enabled = bool(flags(db).get("fastalpr_new_pipeline_enabled"))
                    from app.services.developer import recognition_enabled
                    enabled = enabled and recognition_enabled(db)
                    from app.services.node_scope import describe_recognition_scope
                    scope = describe_recognition_scope(db)
                wanted = _camera_rows() if enabled else []
            except OperationalError:
                _write_health({"enabled": False, "state": "WAITING_FOR_DATABASE", "cameras": []})
                await asyncio.sleep(1.0)
                continue
            candidate_camera_ids = [int(row["id"]) for row in wanted]
            if wanted and warmup_task is None and time.monotonic() >= warmup_retry_at:
                from app.services.alpr import warmup
                warmup_task = asyncio.create_task(asyncio.to_thread(warmup))
            if warmup_task is not None and warmup_task.done():
                try:
                    warmup_status = warmup_task.result()
                    warmup_failures = 0
                    warmup_retry_at = 0.0
                except Exception as exc:
                    warmup_failures += 1
                    fatal_native_error = _fatal_native_load_error(exc)
                    delay = None if fatal_native_error else _warmup_retry_delay(warmup_failures)
                    warmup_retry_at = float("inf") if fatal_native_error else time.monotonic() + delay
                    warmup_status = {
                        "ready": False,
                        "error": type(exc).__name__,
                        "detail": str(exc)[:400],
                        "retry_in_seconds": delay,
                        "restart_required": fatal_native_error,
                    }
                    if fatal_native_error:
                        log.exception("FastALPR native runtime failed; recognition disabled until worker restart")
                    else:
                        log.exception("FastALPR warm-up failed; retrying in %.1fs", delay)
                    try:
                        from app.services.alpr import unload_engine
                        unload_engine()
                    except Exception:
                        log.debug("Could not unload the failed FastALPR engine", exc_info=True)
                    warmup_task = None
            if not warmup_status.get("ready"):
                wanted = []
            claimed_camera_ids = candidate_camera_ids
            for camera_id, old_task in list(retiring.items()):
                if old_task.done():
                    await asyncio.gather(old_task, return_exceptions=True)
                    retiring.pop(camera_id)
            wanted_by_id = {int(row["id"]): row for row in wanted}
            now_wall = time.time()
            for camera_id in list(tasks):
                stop, task, stats = tasks[camera_id]
                last_frame = float(stats.get("last_frame_at") or 0)
                last_infer = float(stats.get("last_inference_at") or 0)
                started_at = float(stats.get("started_at") or now_wall)
                fresh_frames = last_frame > 0 and (now_wall - last_frame) <= max(
                    float(settings.stale_stream_seconds) * 2.0, 2.0
                )
                inference_stalled = (
                    fresh_frames
                    and (now_wall - (last_infer or started_at)) > float(settings.recognition_worker_stall_seconds)
                )
                if camera_id not in wanted_by_id or configurations[camera_id] != wanted_by_id[camera_id] or task.done() or inference_stalled:
                    if inference_stalled:
                        runtime.recover(camera_id)
                        stats["recognition_stalls"] = int(stats.get("recognition_stalls") or 0) + 1
                        stats["recognition_restarts"] = int(stats.get("recognition_restarts") or 0) + 1
                    tasks.pop(camera_id)
                    configurations.pop(camera_id)
                    stop.set()
                    task.cancel()
                    retiring[camera_id] = task
            for camera_id, row in wanted_by_id.items():
                if camera_id in tasks or camera_id in retiring:
                    continue
                stop = asyncio.Event()
                stats = {
                    "camera_id": camera_id,
                    "state": "STARTING",
                    "published": 0,
                    "started_at": time.time(),
                }
                configurations[camera_id] = row
                tasks[camera_id] = (
                    stop,
                    asyncio.create_task(_infer_camera(row, stop, stats), name=f"worker-cam-{camera_id}"),
                    stats,
                )
            _write_health({"enabled": enabled, "warmup": warmup_status, "scope": scope,
                           "claimed_camera_ids": claimed_camera_ids,
                           "state": ("DISABLED" if not enabled else "NODE NOT ASSIGNED TO GATE" if scope["mode"] == "unassigned"
                                     else "IDLE" if not claimed_camera_ids else "DEGRADED" if not tasks
                                     else "READY" if warmup_status.get("ready") else "WARMING"),
                           "retiring_cameras": sorted(retiring),
                           "cameras": [{key: value for key, value in tasks[cid][2].items() if key != "latency_samples"} for cid in sorted(tasks)]})
            # The heartbeat is considered stale after six seconds. Keep the
            # idle worker cadence below that threshold as well; a worker with
            # no assigned cameras must still prove that its control loop is
            # alive and able to notice configuration changes.
            await asyncio.sleep(2.0)
    finally:
        for stop, task, _stats in tasks.values():
            stop.set()
            task.cancel()
        await asyncio.gather(*(task for _, task, _ in tasks.values()), return_exceptions=True)
        await asyncio.gather(*retiring.values(), return_exceptions=True)
        if warmup_task is not None:
            await asyncio.gather(warmup_task, return_exceptions=True)
        _write_health({"enabled": False, "cameras": [], "state": "STOPPED"})
