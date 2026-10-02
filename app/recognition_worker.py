"""SmartParkRecognitionWorker — FastALPR on the MediaMTX detect RTSP path.

This process does not share the Site Service media gateway. It reads
``rtsp://127.0.0.1:8554/cam{id}_detect`` with one persistent decoder per
camera, keeps the newest JPEG, and publishes a normalized PlateRecognized
event. The Site Service camera-event loop stays authoritative until
``fastalpr_new_pipeline_enabled`` is turned on.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time


from app.core.consensus import ConsensusTrack, TrackDecision


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


def note_reading_detail(track: PlateTrack, plate: str, now: float, *, confidence: float = 1.0) -> TrackDecision:
    return track.observe(plate, now, confidence=confidence)


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

    with SessionLocal() as db:
        from app.models import Camera
        camera = db.get(Camera, camera_id)
        enabled = (bool(flags(db).get("fastalpr_new_pipeline_enabled"))
                   and camera is not None and _software_camera(camera, db)
                   and mediamtx_detect_active(camera_id, db) and _worker_ready(camera_id))
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
    from app.infrastructure.hardware.cameras import adapter_has_native_plates

    # Native-LPR cameras already deliver a vehicle-trigger JPEG/metadata event.
    # Re-read that JPEG once in Site Service (ParkWatch pattern) instead of
    # continuously decoding their RTSP stream in the worker. Generic cameras
    # without event LPR keep the continuous DETECT worker.
    return (bool(camera.enabled) and is_enabled("recognition.alpr", db)
            and load_config(db).get("recognition_default") != "VIDEO_ONLY"
            and not adapter_has_native_plates(camera)
            and camera_recognition_mode(camera) in WORKER_MODES)


def _camera_rows() -> list[dict]:
    from app.db import SessionLocal
    from app.models import Camera
    from app.services.flags import media_mtx_for_camera
    from app.services.site_policy import site_policy

    rows: list[dict] = []
    with SessionLocal() as db:
        for camera in db.query(Camera).filter(Camera.enabled == True).all():  # noqa: E712
            if not media_mtx_for_camera(int(camera.id), db) or not _software_camera(camera, db):
                continue
            from app.services.ocr_policy import camera_recognition_mode

            rows.append({
                "id": int(camera.id),
                "lane_direction": str(camera.lane_direction or "ENTRY"),
                "name": str(camera.name or ""),
                "lane_id": camera.lane_id,
                "site_id": camera.site_id,
                "plate_policy": site_policy(db),
                "recognition_mode": camera_recognition_mode(camera),
            })
    return rows


def _write_health(body: dict) -> None:
    from app.config import settings

    path = settings.data_dir / "recognition-worker.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({**body, "updated_at": time.time()}), encoding="utf-8")
    temporary.replace(path)


async def _infer_camera(camera: dict, stop: asyncio.Event, stats: dict, inference_lock: asyncio.Lock | None = None) -> None:
    from app.infrastructure.recognition import recognition_provider_for
    from app.services.media_gateway import LocalMediaGateway
    from app.infrastructure.media.registry import get_detect_endpoint
    from app.services.latest_frame import LatestFrameBuffer
    from app.config import settings

    camera_id = int(camera["id"])
    endpoint = await get_detect_endpoint(camera_id)
    if endpoint.get("provider") != "MEDIAMTX":
        stats["state"] = "DEGRADED"
        stats["last_error"] = "MediaMTX detect endpoint unavailable"
        return
    url = str(endpoint.get("rtsp") or "")
    from app.domain.recognition_engine import policy_from_settings

    provider = recognition_provider_for("fastalpr")
    decoder = LocalMediaGateway()
    rec_policy = policy_from_settings()
    track = PlateTrack(
        window_seconds=rec_policy.consensus_window_seconds,
        hold_seconds=rec_policy.hold_seconds,
        min_reads=rec_policy.min_reads,
        min_agreeing=rec_policy.min_agreeing,
        min_share=rec_policy.min_share,
        similarity=rec_policy.similarity,
    )
    frames = LatestFrameBuffer(f"worker-{camera_id}", maxsize=1)
    ready = asyncio.Event()
    inference_lock = inference_lock or asyncio.Lock()
    interval = 1.0 / settings.detect_fps
    backoff = 1.0

    async def _decode() -> None:
        nonlocal backoff
        while not stop.is_set():
            stream = None
            try:
                stream = decoder.ffmpeg_jpeg_stream(
                    url,
                    scale=960,
                    output_fps=float(settings.detect_fps),
                    transport="TCP",
                )
                async for jpeg in stream:
                    if stop.is_set():
                        break
                    frames.put(jpeg, source="mediamtx")
                    ready.set()
                    if stats.get("state") not in {"READY", "DEGRADED"}:
                        stats["state"] = "STREAMING"
                    stats.update(last_frame_at=time.time(), frame_buffer=frames.snapshot())
                    backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                stats["last_error"] = type(exc).__name__
            finally:
                if stream is not None:
                    try:
                        await stream.aclose()
                    except Exception:
                        pass
            if not stop.is_set():
                stats["state"] = "RECONNECTING"
                stats["reconnects"] = int(stats.get("reconnects", 0)) + 1
                await asyncio.sleep(backoff)
                backoff = min(8.0, backoff * 2)

    async def _infer() -> None:
        while not stop.is_set():
            try:
                await asyncio.wait_for(ready.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            async with inference_lock:
                ready.clear()
                sample = frames.take()
                if sample is None or sample.jpeg[:2] != b"\xff\xd8":
                    continue
                stats["input_frame_age_ms"] = sample.age_ms()
                if sample.age_ms() > rec_policy.stale_frame_ms:
                    stats["stale_dropped"] = int(stats.get("stale_dropped", 0)) + 1
                    continue
                started = time.monotonic()
                try:
                    event = await provider.process({
                        "jpeg": sample.jpeg,
                        "camera_id": camera_id,
                        "site_id": camera.get("site_id"),
                        "camera_label": f"worker-{camera_id}",
                        "lane_id": camera.get("lane_id"),
                        "plate_policy": camera.get("plate_policy") or {},
                    })
                except Exception as exc:
                    stats["last_error"] = type(exc).__name__
                    stats["state"] = "DEGRADED"
                    await asyncio.sleep(interval)
                    continue
            stats.update(state="READY", last_inference_at=time.time())
            stats["infer_ms"] = round((time.monotonic() - started) * 1000.0, 1)
            stats["last_plate"] = str(event.get("normalized_plate") or "")
            if event.get("ok") is False:
                stats["state"] = "DEGRADED"
                await asyncio.sleep(interval)
                continue
            decision = note_reading_detail(
                track, stats["last_plate"], time.monotonic(), confidence=float(event.get("confidence") or 0),
            )
            stats["consensus"] = decision.as_dict()
            if not decision.publish:
                await asyncio.sleep(max(0, interval - (time.monotonic() - started)))
                continue
            try:
                # Consensus text/confidence replace the single-frame read; the raw
                # frame read stays in the payload as evidence.
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
                await asyncio.to_thread(_publish_frame, event, sample.jpeg)
                stats["published"] = int(stats.get("published") or 0) + 1
            except Exception as exc:
                stats["last_error"] = type(exc).__name__
                # A failed durable write must be eligible for retry on the next
                # agreeing frame; only successful publication owns the hold.
                track.release()
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


async def _loop() -> None:
    from app.db import SessionLocal
    from app.services.flags import flags

    tasks: dict[int, tuple[asyncio.Event, asyncio.Task, dict]] = {}
    configurations: dict[int, dict] = {}
    inference_lock = asyncio.Lock()
    try:
        while True:
            with SessionLocal() as db:
                enabled = bool(flags(db).get("fastalpr_new_pipeline_enabled"))
            wanted = _camera_rows() if enabled else []
            wanted_by_id = {int(row["id"]): row for row in wanted}
            for camera_id in list(tasks):
                stop, task, stats = tasks[camera_id]
                if camera_id not in wanted_by_id or configurations[camera_id] != wanted_by_id[camera_id] or task.done():
                    tasks.pop(camera_id)
                    configurations.pop(camera_id)
                    stop.set()
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
            for camera_id, row in wanted_by_id.items():
                if camera_id in tasks:
                    continue
                stop = asyncio.Event()
                stats = {"camera_id": camera_id, "state": "STARTING", "published": 0}
                configurations[camera_id] = row
                tasks[camera_id] = (
                    stop,
                    asyncio.create_task(_infer_camera(row, stop, stats, inference_lock), name=f"worker-cam-{camera_id}"),
                    stats,
                )
            _write_health({"enabled": enabled, "cameras": [tasks[cid][2] for cid in sorted(tasks)]})
            await asyncio.sleep(2.0)
    finally:
        for stop, task, _stats in tasks.values():
            stop.set()
            task.cancel()
        await asyncio.gather(*(task for _, task, _ in tasks.values()), return_exceptions=True)
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
    print("Recognition worker reads MediaMTX cam{id}_detect when fastalpr_new_pipeline_enabled=true.")
    asyncio.run(_loop())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
