"""SmartParkRecognitionWorker — FastALPR on the local MediaMTX RTSP path.

MediaMTX owns the camera connection and browser video. This process is only
a recognition consumer: one lightweight FFmpeg decoder per lane reads
``rtsp://127.0.0.1:8554/<detect-path>``, keeps the newest JPEG, and samples
a few frames per second. The detector watches the camera's zone. OCR runs
only after the plate holds still, on the cropped plate, then pauses until
the vehicle leaves. SDK cameras remain on the Site Service camera-event loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
import time


from app.core.consensus import ConsensusTrack, TrackDecision


log = logging.getLogger("smartpark")


class PlateTrack(ConsensusTrack):
    """Per-camera temporal consensus (similarity + confidence weighted)."""


def note_reading(
    track: PlateTrack,
    plate: str,
    now: float,
    *,
    hold_seconds: float = 20.0,
    consensus_seconds: float = 2.0,
    confidence: float = 1.0,
) -> bool:
    """Publish once per visit after agreeing reads; never re-publish while visible."""
    track.hold_seconds = float(hold_seconds)
    track.window_seconds = float(consensus_seconds)
    return track.observe(plate, now, confidence=confidence).publish


def note_reading_detail(track: PlateTrack, plate: str, now: float, *, confidence: float = 1.0, allow_single: bool = True) -> TrackDecision:
    return track.observe(plate, now, confidence=confidence, allow_single=allow_single)


def strong_read(event: dict, plate_policy: dict) -> bool:
    from app.core.plate import apply_site_plate

    box = event.get("bbox") or {}
    crop = box.get("crop") or {}
    valid = apply_site_plate(str(event.get("normalized_plate") or ""),
                             validation=str(plate_policy.get("plate_validation") or "NONE"))
    return (float(event.get("detector_confidence") or 0) >= 0.85
            and int(crop.get("x2", 0)) - int(crop.get("x1", 0)) >= 80
            and int(crop.get("y2", 0)) - int(crop.get("y1", 0)) >= 20
            and bool(valid.get("validation_ok")))


_owns_cache: dict[int, tuple[float, bool]] = {}


def worker_health() -> dict:
    """Read a process-safe heartbeat; stale/missing files never confer ownership."""
    from app.config import settings

    try:
        body = json.loads((settings.data_dir / "recognition-worker.json").read_text(encoding="utf-8"))
        if not isinstance(body, dict) or not isinstance(body.get("cameras"), list):
            raise ValueError("Invalid worker heartbeat")
        age = time.time() - float(body.get("updated_at", 0))
        healthy = bool(body.get("enabled")) and 0 <= age <= 6.0
        return {**body, "ok": healthy, "heartbeat_age_seconds": round(age, 2)}
    except (OSError, ValueError, TypeError, AttributeError):
        return {"ok": False, "enabled": False, "cameras": [], "state": "OFFLINE"}


def _worker_ready(camera_id: int) -> bool:
    from app.config import settings

    health = worker_health()
    if not health.get("ok"):
        return False
    for row in health.get("cameras") or []:
        if not isinstance(row, dict):
            continue
        if row.get("camera_id") == camera_id and row.get("state") == "READY":
            try:
                age = time.time() - float(row.get("last_frame_at") or 0)
                inference_age = time.time() - float(row.get("last_inference_at") or 0)
            except (TypeError, ValueError):
                return False
            return (0 <= age <= settings.stale_stream_seconds
                    and 0 <= inference_age <= max(6.0, settings.alpr_timeout_seconds))
    return False


def _worker_claim_has_live_frames(camera_id: int, health: dict) -> bool:
    """Keep ownership with a stalled worker while its decoder is still live.

    The worker reports ``STALLED`` while a slow/native inference call drains.
    Falling back in that window starts a second ONNX owner and makes both
    recognition and camera timing worse. A transitional claim is accepted only
    when the worker has actually delivered a recent frame; a frame-less worker
    still permits the Site Service fallback.
    """
    from app.config import settings

    if not health.get("ok"):
        return False
    claimed = {int(value) for value in (health.get("claimed_camera_ids") or []) if str(value).isdigit()}
    if int(camera_id) not in claimed:
        return False
    for row in health.get("cameras") or []:
        if not isinstance(row, dict) or int(row.get("camera_id") or -1) != int(camera_id):
            continue
        if str(row.get("state") or "") not in {"STREAMING", "STALLED", "DEGRADED"}:
            return False
        try:
            age = time.time() - float(row.get("last_frame_at") or 0)
        except (TypeError, ValueError):
            return False
        return 0 <= age <= 2.0 * max(float(settings.stale_stream_seconds), 2.0)
    return False


def worker_owns_software_reads(camera_id: int) -> bool:
    """True when this worker, not the Site Service loop, should run FastALPR."""
    camera_id = int(camera_id)
    cached = _owns_cache.get(camera_id)
    now = time.monotonic()
    if cached is not None and (now - cached[0]) < 1.0:
        return cached[1]
    from app.db import SessionLocal
    from app.infrastructure.media.registry import mediamtx_detect_active
    from app.services.flags import flags

    health = worker_health()
    with SessionLocal() as db:
        from app.models import Camera
        camera = db.get(Camera, camera_id)
        enabled = (bool(flags(db).get("fastalpr_new_pipeline_enabled"))
                   and camera is not None and _software_camera(camera, db)
                   and mediamtx_detect_active(camera_id, db)
                   and (_worker_ready(camera_id) or _worker_claim_has_live_frames(camera_id, health)))
    _owns_cache[camera_id] = (now, enabled)
    return enabled


def publish_recognition(event: dict) -> dict:
    from app.domain.events import from_recognition_dict
    from app.services.events import publish

    return publish(from_recognition_dict(event))


def _publish_frame(event: dict, jpeg: bytes) -> dict:
    """Archive evidence once per consensus event, not on each decoder frame."""
    from app.config import settings
    from app.services.captures import _crop_from_bbox

    identifier = str(event["event_id"])
    if not identifier.isalnum() or len(identifier) > 64:
        raise ValueError("Invalid recognition event ID")
    relative = f"snapshots/recognition-{identifier}.jpg"
    path = settings.media_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(jpeg)
    event["image_ref"] = f"/media/{relative}"
    crop = _crop_from_bbox(jpeg, event.get("bbox"))
    if crop:
        relative_crop = f"crops/recognition-{identifier}.jpg"
        crop_path = settings.media_dir / relative_crop
        crop_path.parent.mkdir(parents=True, exist_ok=True)
        crop_path.write_bytes(crop)
        event["plate_crop_ref"] = f"/media/{relative_crop}"
    return publish_recognition(event)


WORKER_MODES = frozenset({"LOCAL_ONLY", "NATIVE_WITH_LOCAL_VERIFY"})


def _software_camera(camera, db) -> bool:
    """Cameras whose FastALPR reads this worker owns.

    LOCAL_ONLY cameras publish accepted plates. HYBRID cameras publish FastALPR
    *candidates*; the Site Service fuses them with the native reading through
    ``services.hybrid_fusion`` so one vehicle yields one capture. NATIVE_ONLY
    cameras never run software reads here.
    """
    from app.services.modules import is_enabled, load_config
    from app.services.ocr_policy import camera_recognition_mode
    # Recognition policy owns this choice. An HVX camera may have native LPR
    # capability without delivering callbacks (country/trigger configuration).
    # FASTALPR_ONLY must keep detecting on video independently of those events.
    return (bool(camera.enabled) and is_enabled("recognition.alpr", db)
            and load_config(db).get("recognition_default") != "VIDEO_ONLY"
            and camera_recognition_mode(camera) in WORKER_MODES)


def _camera_rows() -> list[dict]:
    from app.db import SessionLocal
    from app.models import Camera
    from app.services.flags import media_mtx_for_camera
    from app.infrastructure.media.registry import _sdk_camera
    from app.services.site_policy import site_policy

    rows: list[dict] = []
    with SessionLocal() as db:
        for camera in db.query(Camera).filter(Camera.enabled == True).all():  # noqa: E712
            if _sdk_camera(int(camera.id), db):
                continue
            if not media_mtx_for_camera(int(camera.id), db) or not _software_camera(camera, db):
                continue
            from app.services.node_scope import camera_active_on_this_installation
            if not camera_active_on_this_installation(camera, db=db):
                continue
            from app.services.ocr_policy import camera_recognition_mode

            from app.services.camera_framing import framing_from_profiles

            profiles = dict(camera.stream_profiles or {})
            framing = framing_from_profiles(profiles)
            rows.append({
                "id": int(camera.id),
                "lane_direction": str(camera.lane_direction or "ENTRY"),
                "name": str(camera.name or ""),
                "lane_id": camera.lane_id,
                "site_id": camera.site_id,
                "plate_policy": site_policy(db),
                "recognition_mode": camera_recognition_mode(camera),
                "detect_roi": framing["detect_roi"],
                "detect_zoom": framing["detect_zoom"],
            })
    return rows


def _write_health(body: dict) -> None:
    from app.config import settings

    from app.services.process_metrics import snapshot
    body["resources"] = {**snapshot(), "decoder_count": sum(bool(row.get("decoder_pid")) for row in body.get("cameras", []))}
    path = settings.data_dir / "recognition-worker.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Windows can have the previous fixed ``recognition-worker.tmp`` held by
    # a second scheduled worker or by a health reader.  A unique temp file
    # prevents one stale process from crashing the recognition worker; if the
    # final replace is temporarily denied, keep the last good heartbeat and
    # let the next loop retry.
    temporary: str | None = None
    try:
        fd, temporary = tempfile.mkstemp(prefix="recognition-worker-", suffix=".tmp", dir=str(path.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({**body, "updated_at": time.time()}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except (OSError, PermissionError) as exc:
        log.warning("recognition health write skipped: %s", exc)
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _configure_worker_runtime() -> bool:
    """Apply the installed deployment before importing the ORM/model graph.

    The Site and Media services already do this. The recognition worker is a
    separate process, so without the same step it silently opens the default
    SQLite database even when the setup wizard selected another database.
    """
    from app.database_config import apply_runtime_database_config
    from app.deployment import load_deployment_config
    from app.config import settings

    deployment = load_deployment_config()
    if not deployment.is_server or not deployment.configured:
        print("Recognition Worker is disabled until a configured Site Server exists.", file=sys.stderr)
        return False
    apply_runtime_database_config(deployment.database)
    os.environ.setdefault("SMARTPARK_ALPR_CACHE_DIR", str(settings.data_dir / "model-cache"))
    return True


def _warmup_retry_delay(failures: int) -> float:
    """Bound detector retry pressure while retaining eventual recovery."""
    return min(60.0, float(2 ** min(max(1, int(failures)), 6)))


def _fatal_native_load_error(exc: BaseException) -> bool:
    """A broken ORT/DLL load cannot recover by re-importing in this process."""
    detail = f"{type(exc).__name__}: {exc}".lower()
    return isinstance(exc, (ImportError, OSError)) and (
        "onnxruntime" in detail or "dll load failed" in detail or "pybind11_state" in detail
    )


async def _infer_camera(
    camera: dict,
    stop: asyncio.Event,
    stats: dict,
    inference_limiter: asyncio.Semaphore | None = None,
) -> None:
    from app.services.inference_thread import run_inference
    from app.infrastructure.recognition import recognition_provider_for
    from app.services.recognition_decoder import iter_jpegs, require_local_mediamtx
    from app.infrastructure.media.registry import get_detect_endpoint
    from app.config import settings

    camera_id = int(camera["id"])
    endpoint = await get_detect_endpoint(camera_id)
    if endpoint.get("provider") != "MEDIAMTX":
        stats["state"] = "DEGRADED"
        stats["last_error"] = "MediaMTX detect endpoint unavailable"
        return
    url = str(endpoint.get("rtsp") or "")
    try:
        require_local_mediamtx(url)
    except ValueError as exc:
        stats["state"] = "DEGRADED"
        stats["last_error"] = str(exc)
        return
    from app.domain.recognition_engine import policy_from_settings

    provider = recognition_provider_for("fastalpr")
    rec_policy = policy_from_settings()
    sample_fps = float(getattr(settings, "recognition_sample_fps", 3.0) or 3.0)
    departure_every = float(getattr(settings, "recognition_departure_check_seconds", 1.0) or 1.0)
    detect_roi = str(camera.get("detect_roi") or "") or None
    detect_zoom = camera.get("detect_zoom")
    from app.services.camera_framing import gate_for

    arrival = gate_for(camera_id)
    track = PlateTrack(
        window_seconds=rec_policy.consensus_window_seconds,
        hold_seconds=rec_policy.hold_seconds,
        absence_reset_seconds=rec_policy.absence_reset_seconds,
        min_reads=rec_policy.min_reads,
        min_agreeing=rec_policy.min_agreeing,
        min_share=rec_policy.min_share,
        similarity=rec_policy.similarity,
        high_confidence=rec_policy.high_min,
    )
    from app.services.recognition_runtime import runtime
    from app.services.lane_timing import mark, observe_duration
    lane = runtime.lane(camera_id)
    lane.inflight = None
    runtime.scheduler.release(camera_id)
    frames = lane.mailbox
    ready = asyncio.Event()
    interval = 1.0 / max(sample_fps, 1.0)
    backoff = 1.0
    stats.update(
        sample_fps=sample_fps,
        decoder_role="recognition-consumer",
        media_owner="mediamtx",
        queue_depth=0,
        ocr_paused=False,
        decoder_pid=None,
    )

    def _note_pid(pid: int) -> None:
        stats["decoder_pid"] = pid

    async def _decode() -> None:
        nonlocal backoff
        while not stop.is_set():
            stream = None
            decoder_started = time.monotonic()
            first_frame = True
            stats["decoder_started_at"] = time.time()
            try:
                stream = iter_jpegs(url, sample_fps=sample_fps, scale=960, on_pid=_note_pid)
                async for jpeg in stream:
                    if stop.is_set():
                        break
                    lane.offer_frame(jpeg, source="mediamtx")
                    if first_frame:
                        stats["decoder_first_frame_ms"] = round((time.monotonic() - decoder_started) * 1000, 1)
                        first_frame = False
                    ready.set()
                    if stats.get("state") not in {"READY", "DEGRADED"}:
                        stats["state"] = "STREAMING"
                    sampled = int(stats.get("frames_sampled") or 0) + 1
                    elapsed = max(time.time() - float(stats.get("started_at") or time.time()), 0.001)
                    stats.update(
                        decoder_uptime_seconds=round(time.monotonic() - decoder_started, 1),
                        last_frame_at=time.time(),
                        frame_buffer=frames.snapshot(),
                        frame_seq=frames.seq,
                        frames_sampled=sampled,
                        sampled_fps=round(sampled / elapsed, 2),
                        queue_depth=frames.depth(),
                    )
                    backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                stats["last_error"] = str(exc)[:300] or type(exc).__name__
                log.warning("camera=%s recognition decoder failed: %s", camera_id, stats["last_error"])
            finally:
                if stream is not None:
                    try:
                        await stream.aclose()
                    except Exception:
                        pass
            stats["decoder_pid"] = None
            if not stop.is_set():
                stats["state"] = "RECONNECTING"
                stats["reconnects"] = int(stats.get("reconnects", 0)) + 1
                log.warning("camera=%s recognition decoder reconnecting attempt=%s backoff_s=%.1f", camera_id, stats["reconnects"], backoff)
                await asyncio.sleep(backoff)
                backoff = min(8.0, backoff * 2)

    last_probe = 0.0
    probe_failures = 0
    confirmed_visit_id = lane.visit.visit_id if lane.visit.state == "EVENT_PUBLISHED" else ""
    pending_inference: asyncio.Task | None = None

    async def _with_limiter(call, captured_at: float = 0.0):
        async def fresh_call():
            if captured_at and (time.monotonic() - captured_at) * 1000 > rec_policy.stale_frame_ms:
                call.close()
                stats["stale_dropped"] = int(stats.get("stale_dropped", 0)) + 1
                raise ValueError("stale-input-frame")
            return await call
        try:
            if inference_limiter is None:
                return await fresh_call()
            async with inference_limiter:
                return await fresh_call()
        finally:
            call.close()

    async def _infer() -> None:
        nonlocal last_probe, probe_failures, confirmed_visit_id, pending_inference
        stall = float(getattr(settings, "recognition_worker_stall_seconds", 5.0) or 5.0)
        while not stop.is_set():
            # A timeout cannot stop an ONNX call already running in a native
            # thread. Keep that call owned by this lane and wait for it to
            # drain before admitting another frame; this bounds CPU pressure
            # without freezing the decoder or the other camera lanes.
            if pending_inference is not None:
                if not pending_inference.done():
                    stats["state"] = "STALLED"
                    await asyncio.sleep(0.05)
                    continue
                try:
                    pending_inference.result()
                except Exception as exc:
                    stats["last_error"] = type(exc).__name__
                pending_inference = None
                stats["recognition_inflight"] = False
                if not stop.is_set():
                    stats["state"] = "READY"
            try:
                await asyncio.wait_for(ready.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            if confirmed_visit_id and lane.visit.visit_id == confirmed_visit_id:
                stats["ocr_paused"] = True
                now_m = time.monotonic()
                if now_m - last_probe < departure_every:
                    await asyncio.sleep(0.02)
                    continue
                last_probe = now_m
                ticket = runtime.begin_if_idle(camera_id, stale_frame_ms=rec_policy.stale_frame_ms)
                if ticket is None or ticket.jpeg[:2] != b"\xff\xd8":
                    if ticket is not None:
                        runtime.finish(ticket, plate="")
                    ready.clear()
                    continue
                ready.clear()
                from app.services.alpr import plate_still_present

                async def _probe_present():
                    return await _with_limiter(run_inference(
                        plate_still_present, ticket.jpeg, detect_roi=detect_roi, detect_zoom=detect_zoom,
                    ), ticket.captured_at)

                probe = asyncio.create_task(_probe_present())
                try:
                    present = await asyncio.shield(probe)
                except asyncio.CancelledError:
                    # Cancellation cannot stop the model thread. Drain it before
                    # a replacement lane can start another detector call.
                    try:
                        await probe
                    finally:
                        runtime.finish(ticket, plate="")
                    raise
                except Exception as exc:
                    runtime.finish(ticket, plate="")
                    stats["last_error"] = type(exc).__name__
                    continue
                runtime.finish(
                    ticket,
                    plate=lane.visit.published_plate if present is not False else "",
                )
                stats["departure_checks"] = int(stats.get("departure_checks") or 0) + 1
                stats["recognition_inflight"] = False
                # Detector-only work is recognition progress while OCR is paused.
                stats["last_inference_at"] = time.time()
                if present is None:
                    probe_failures += 1
                    stats["state"] = "DEGRADED"
                    stats["last_error"] = "departure-detector-unavailable"
                    # A stuck detector must not freeze the lane. Resume OCR
                    # without clearing the published plate or opening a new visit.
                    if probe_failures >= 3:
                        confirmed_visit_id = ""
                        stats["ocr_paused"] = False
                        arrival.reset()
                    continue
                probe_failures = 0
                stats["state"] = "READY"
                if present:
                    if lane.visit.state == "VEHICLE_DEPARTING":
                        lane.visit.state = "EVENT_PUBLISHED"
                        lane.visit.vehicle_present = True
                        lane.visit.last_empty_at = 0.0
                    else:
                        lane.visit.observe(presence=True, plate=lane.visit.published_plate or "")
                    continue
                decision = note_reading_detail(track, "", time.monotonic())
                stats["consensus"] = decision.as_dict()
                lane.visit.observe(
                    presence=False,
                    plate="",
                    absence_seconds=rec_policy.absence_reset_seconds,
                )
                if lane.visit.state == "IDLE":
                    lane.clear_current_plate()
                    stats["last_plate"] = ""
                    stats["ocr_paused"] = False
                    arrival.reset()
                continue
            stats["ocr_paused"] = False
            ticket = runtime.begin_if_idle(camera_id, stale_frame_ms=rec_policy.stale_frame_ms)
            if ticket is None:
                ready.clear()
                await asyncio.sleep(0.02)
                continue
            if ticket.jpeg[:2] != b"\xff\xd8":
                runtime.finish(ticket, plate="")
                continue
            ready.clear()
            stats["input_frame_age_ms"] = ticket.frame_age_ms()
            stats["recognition_generation"] = ticket.generation
            stats["recognition_inflight"] = True
            stats["recognition_frame_seq"] = ticket.frame_seq
            from app.services.alpr import locate_plate_boxes

            locate_task = asyncio.create_task(_with_limiter(run_inference(
                locate_plate_boxes, ticket.jpeg, detect_roi=detect_roi, detect_zoom=detect_zoom,
            ), ticket.captured_at))
            try:
                boxes, located = await asyncio.shield(locate_task)
            except asyncio.CancelledError:
                # Cancelling the waiter does not cancel the model thread.
                try:
                    await locate_task
                finally:
                    runtime.finish(ticket, plate="")
                raise
            except Exception as exc:
                runtime.finish(ticket, plate="")
                stats["last_error"] = type(exc).__name__
                stats["recognition_inflight"] = False
                await asyncio.sleep(interval)
                continue
            if not located.get("available"):
                # Do not OCR the live frame when the detector cannot crop a plate.
                stats.update(state="DEGRADED", last_inference_at=time.time(), recognition_inflight=False,
                             last_error="plate detector unavailable")
                stats["arrival"] = "detector-wait"
                runtime.finish(ticket, plate="")
                await asyncio.sleep(interval)
                continue
            if ticket.frame_age_ms() > rec_policy.stale_frame_ms:
                runtime.finish(ticket, plate="", stale_frame_ms=rec_policy.stale_frame_ms)
                stats["stale_dropped"] = int(stats.get("stale_dropped", 0)) + 1
                stats["last_inference_at"] = time.time()
                continue
            # A healthy empty-lane detector is progress, even without OCR.
            # Otherwise the supervisor restarts idle lanes every few seconds.
            stats.update(state="READY", last_inference_at=time.time())
            observe_duration(stats, "detector", located.get("detector_ms", 0))
            if boxes:
                lane.visit.observe(presence=True)
                if stats.get("timeline", {}).get("visit_id") != lane.visit.visit_id:
                    stats["timeline"] = {"visit_id": lane.visit.visit_id, "camera_id": camera_id,
                                         "direction": camera.get("lane_direction", "ENTRY")}
                    mark("vehicle_seen", stats["timeline"], at=ticket.captured_at)
            phase = arrival.observe(boxes[0] if boxes else None, time.monotonic())
            stats["arrival"] = phase
            if phase == "absent":
                runtime.finish(ticket, plate="")
                decision = note_reading_detail(track, "", time.monotonic())
                stats["consensus"] = decision.as_dict()
                lane.visit.observe(presence=False, plate="")
                if lane.visit.state == "IDLE":
                    stats["last_plate"] = ""
                    arrival.reset()
                stats["recognition_inflight"] = False
                await asyncio.sleep(interval)
                continue
            if phase != "ready":
                runtime.finish(ticket, plate="")
                lane.visit.observe(presence=True, plate="")
                stats["recognition_inflight"] = False
                stats["last_inference_at"] = time.time()
                await asyncio.sleep(interval)
                continue
            started = time.monotonic()
            timeline = stats.get("timeline", {})
            mark("frame_decoded", timeline, at=ticket.captured_at)
            mark("frame_selected", timeline, at=ticket.recognition_started_at)
            mark("detector_started", timeline, at=located.get("detector_started_at", ticket.recognition_started_at))
            mark("detector_complete", timeline, at=located.get("detector_finished_at"))
            provider_task = asyncio.create_task(_with_limiter(provider.process({
                "jpeg": ticket.jpeg,
                "camera_id": camera_id,
                "site_id": camera.get("site_id"),
                "camera_label": f"worker-{camera_id}",
                "lane_id": camera.get("lane_id"),
                "plate_policy": camera.get("plate_policy") or {},
                "detect_roi": detect_roi,
                "detect_zoom": detect_zoom,
                "plate_boxes": boxes if located.get("available") else None,
            }), ticket.captured_at))
            try:
                # Shield is intentional: timeout must not cancel the provider,
                # whose underlying ONNX thread cannot be stopped safely.
                event = await asyncio.wait_for(asyncio.shield(provider_task), timeout=stall)
            except asyncio.CancelledError:
                if not provider_task.done():
                    await provider_task
                raise
            except asyncio.TimeoutError:
                stats["last_error"] = "stall-timeout"
                stats["state"] = "STALLED"
                log.warning("camera=%s recognition inference stalled after %.1fs; draining native call before retry", camera_id, stall)
                pending_inference = provider_task
                runtime.recover(camera_id)
                arrival.rearm()
                stats["recognition_stalls"] = int(stats.get("recognition_stalls") or 0) + 1
                stats["recognition_restarts"] = int(stats.get("recognition_restarts") or 0) + 1
                continue
            except Exception as exc:
                runtime.finish(ticket, plate="")
                arrival.rearm()
                stats["last_error"] = type(exc).__name__
                stats["state"] = "DEGRADED"
                log.warning("camera=%s recognition inference failed: %s", camera_id, stats["last_error"])
                await asyncio.sleep(interval)
                continue
            plate = str(event.get("normalized_plate") or "")
            accepted = runtime.finish(ticket, plate=plate, stale_frame_ms=rec_policy.stale_frame_ms)
            stats.update(state="READY", last_inference_at=time.time(), recognition_inflight=False)
            stats["infer_ms"] = round((time.monotonic() - started) * 1000.0, 1)
            stats["last_plate"] = plate
            stats["visit_id"] = lane.visit.visit_id
            if not accepted:
                arrival.rearm()
                stats["stale_dropped"] = int(stats.get("stale_dropped", 0)) + 1
                continue
            timing = event.get("timings") or {}
            for stage in ("crop", "ocr"):
                if timing.get(f"{stage}_ms") is not None:
                    observe_duration(stats, stage, timing[f"{stage}_ms"])
            for stage, key in (("crop_ready", "crop_ready_at"), ("ocr_started", "ocr_started_at"), ("ocr_complete", "ocr_finished_at")):
                if timing.get(key) is not None:
                    mark(stage, timeline, at=timing[key])
            observe_duration(stats, "recognition", lane.last_infer_ms)
            strong = strong_read(event, camera.get("plate_policy") or {})
            if event.get("ok") is False and not plate:
                arrival.rearm()
                await asyncio.sleep(interval)
                continue
            decision = note_reading_detail(
                track, plate, time.monotonic(), confidence=float(event.get("confidence") or 0), allow_single=strong,
            )
            stats["consensus"] = decision.as_dict()
            if not plate:
                arrival.note_ocr(published=False)
                lane.visit.observe(presence=bool(boxes), plate="")
                if lane.visit.state == "IDLE":
                    stats["last_plate"] = ""
                await asyncio.sleep(max(0, interval - (time.monotonic() - started)))
                continue
            lane.visit.observe(presence=True, plate=plate)
            if (
                lane.visit.state == "EVENT_PUBLISHED"
                and lane.visit.visit_id
                and plate == (lane.visit.published_plate or "")
            ):
                confirmed_visit_id = lane.visit.visit_id
            if not decision.publish:
                arrival.note_ocr(published=False)
                await asyncio.sleep(max(0, interval - (time.monotonic() - started)))
                continue
            if lane.visit.event_published:
                lane.note_duplicate()
                confirmed_visit_id = lane.visit.visit_id
                continue
            try:
                mark("consensus_confirmed", timeline)
                observe_duration(stats, "vehicle_to_plate", timeline["stages_ms"]["consensus_confirmed"])
                event["timeline"] = timeline
                event["frame_plate"] = event.get("normalized_plate")
                event["frame_confidence"] = event.get("confidence")
                event["normalized_plate"] = decision.plate
                event["plate_text"] = decision.plate
                event["confidence"] = decision.confidence
                event["recognition_confidence"] = decision.confidence
                event["consensus"] = decision.as_dict()
                event["recognition_mode"] = camera.get("recognition_mode") or "LOCAL_ONLY"
                event["fusion_role"] = "candidate" if camera.get("recognition_mode") == "NATIVE_WITH_LOCAL_VERIFY" else "accepted"
                event["needs_review"] = bool(event.get("needs_review") or decision.confidence < .75)
                event["visit_id"] = lane.visit.visit_id
                event["frame_seq"] = ticket.frame_seq
                event["generation"] = ticket.generation
                await run_inference(_publish_frame, event, ticket.jpeg)
                mark("event_persisted", timeline)
                stats["published"] = int(stats.get("published") or 0) + 1
                lane.note_published()
                lane.visit.mark_published(decision.plate)
                confirmed_visit_id = lane.visit.visit_id
                arrival.note_ocr(published=True)
            except Exception as exc:
                stats["last_error"] = type(exc).__name__
                track.release()
                arrival.rearm()
            await asyncio.sleep(max(0, interval - (time.monotonic() - started)))

    decode_task = asyncio.create_task(_decode(), name=f"detect-decode-{camera_id}")
    infer_task = asyncio.create_task(_infer(), name=f"detect-infer-{camera_id}")
    stop_task = asyncio.create_task(stop.wait())
    try:
        done, _ = await asyncio.wait([decode_task, infer_task, stop_task], return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    finally:
        decode_task.cancel()
        infer_task.cancel()
        stop_task.cancel()
        await asyncio.gather(decode_task, infer_task, stop_task, return_exceptions=True)
        runtime.scheduler.release(camera_id)


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


def main() -> int:
    from app.services.logging_setup import configure_logging
    from app.services.runtime import acquire_instance_lock, install_crash_hooks, set_process_name

    install_crash_hooks("SmartParkRecognitionWorker")
    configure_logging("recognition-worker")
    set_process_name("SmartParkRecognitionWorker")
    if not acquire_instance_lock("recognition-worker"):
        print("SmartPark Recognition Worker is already running.", file=sys.stderr)
        return 0
    if not _configure_worker_runtime():
        return 2
    print("Recognition worker reads MediaMTX cam{id}_detect when fastalpr_new_pipeline_enabled=true.")
    asyncio.run(_loop())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
