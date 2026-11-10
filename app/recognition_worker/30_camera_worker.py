from __future__ import annotations

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
    from app.services.camera_framing import best_arrival_box, gate_for

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
            phase = arrival.observe(best_arrival_box(boxes, detect_roi=detect_roi), time.monotonic())
            stats["arrival"] = phase
            if phase == "new_vehicle":
                # The previous car was published but no empty detector frame
                # arrived before this car entered. Reset both temporal tracks
                # so the new plate cannot be suppressed as a duplicate.
                now = time.monotonic()
                track.reset(now)
                lane.visit.reset(now)
                lane.visit.observe(presence=True, now=now)
                confirmed_visit_id = ""
                stats["last_plate"] = ""
                stats["ocr_paused"] = False
                stats["timeline"] = {
                    "visit_id": lane.visit.visit_id,
                    "camera_id": camera_id,
                    "direction": camera.get("lane_direction", "ENTRY"),
                }
                phase = "moving"
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
                "decoded_bgr": located.get("_decoded_bgr"),
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
                event["detect_roi"] = detect_roi
                event["detect_zoom"] = detect_zoom
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
        # A timed-out ONNX call cannot be cancelled safely. Drain it before
        # releasing the lane so a restart never overlaps the old native model
        # thread or leaves the scheduler believing ownership is available.
        if pending_inference is not None and not pending_inference.done():
            await asyncio.gather(pending_inference, return_exceptions=True)
        runtime.scheduler.release(camera_id)
