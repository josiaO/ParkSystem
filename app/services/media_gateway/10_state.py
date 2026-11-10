from __future__ import annotations

class _GatewayStateMixin:
    async def snapshot(self, camera_id: int) -> bytes:
        sample = self.peek_live(camera_id) or self.peek_detect(camera_id)
        return sample.jpeg if sample else b""

    def note_displayed(self, camera_id: int) -> None:
        row = self._sessions.get(camera_id)
        if row is not None:
            row.frames_displayed += 1

    def acquire_detect(self, spec: CameraLiveSpec) -> None:
        row = self._session_for(replace(spec, need_detect=True))
        row.detect_consumers = max(row.detect_consumers, 1)
        row.spec = replace(row.spec, need_detect=True)
        self.ensure_producer(row.spec)

    def pumping_spec(self, camera_id: int) -> CameraLiveSpec | None:
        row = self._sessions.get(camera_id)
        if row is None:
            return None
        if row.producer is not None and not row.producer.done():
            return row.spec
        return None

    def _stale_fresh(self, row: StreamSession, *, factor: float = 2.0) -> bool:
        age = self._fresh_age_s(row)
        if age is None:
            return False
        stale = float(getattr(settings, "stale_stream_seconds", 2.5) or 2.5)
        return age >= stale * factor

    async def health(self, camera_id: int) -> dict[str, Any]:
        return self.health_sync(camera_id)

    def stop_watchers(self) -> None:
        for task in (self._idle_task, self._watch_task):
            if task is not None:
                task.cancel()
        self._idle_task = None
        self._watch_task = None

    def session(self, camera_id: int) -> StreamSession | None:
        return self._sessions.get(camera_id)

    def peek_live(self, camera_id: int) -> FrameSample | None:
        row = self._sessions.get(camera_id)
        return row.live.latest() if row else None

    async def unregister_stream(self, camera_id: int) -> None:
        self.stop_producer(camera_id, force=True)
        self._sessions.pop(camera_id, None)

    def stop_producer(self, camera_id: int, *, force: bool = False) -> None:
        row = self._sessions.get(camera_id)
        if row is None:
            return
        if not force and row.wanted():
            return
        task = row.producer
        row.producer = None
        row.state = "DISCONNECTED"
        if task is not None and (force or not row.wanted()):
            self._invalidate_generation(row, "producer-stopped")
        if task is not None:
            task.cancel()
        pids = list(row.child_pids)
        row.child_pids.clear()
        row.ffmpeg_pid = None
        for pid in pids:
            _kill_pid(pid)

    def peek_detect(self, camera_id: int) -> FrameSample | None:
        row = self._sessions.get(camera_id)
        return row.detect.latest() if row else None

    def start_watchers(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._idle_task is None or self._idle_task.done():
            self._idle_task = loop.create_task(self._idle_watch(), name="media-idle")
        if self._watch_task is None or self._watch_task.done():
            self._watch_task = loop.create_task(self._stale_watch(), name="media-stale")

    def stop_all(self) -> None:
        self.stop_watchers()
        for camera_id in list(self._sessions):
            self.stop_producer(camera_id, force=True)
        self._sessions.clear()

    def touch_live(self, spec: CameraLiveSpec) -> None:
        row = self._session_for(spec)
        row.last_view_at = time.monotonic()
        self.ensure_producer(spec)

    def _invalidate_generation(self, row: StreamSession, reason: str) -> None:
        """Invalidate buffered media before a decoder is allowed to recover."""
        now = time.monotonic()
        row.generation += 1
        row.live = LatestFrameBuffer("live", maxsize=1)
        row.detect = LatestFrameBuffer("detect", maxsize=1)
        row.source_frame_seq = 0
        row.last_fresh_frame_at = 0.0
        row.last_frame_received_at = 0.0
        row.last_received_at = 0.0
        row.frozen = False
        row.recovery_reason = str(reason or "reconnect")[:200]
        row.last_reconnected_at = now
        row.last_reconnect_reason = row.recovery_reason
        row.connected_at = 0.0
        row.startup_started_at = now
        row.stream_startup_ms = None
        # Recovery must not import optional display or recognition modules.
        # Those consumers register observers when they are present.
        _notify_generation_observers(row.spec.id, row.generation)

    async def unregister_source(self, camera_id: int) -> None:
        await self.unregister_stream(camera_id)

    def ensure_producer(self, spec: CameraLiveSpec) -> None:
        self.start_watchers()
        row = self._session_for(spec)
        if not adapter_requires_native_stream(spec.adapter_id):
            from app.services.flags import direct_generic_media_allowed

            if not direct_generic_media_allowed():
                if row.producer is not None and not row.producer.done():
                    self._invalidate_generation(row, "production-requires-mediamtx")
                    row.producer.cancel()
                row.producer = None
                row.producer_spec = None
                row.state = "DEGRADED"
                row.last_error = "Production generic camera requires MediaMTX"
                return
        existing = row.producer
        if existing is not None and not existing.done() and row.producer_spec is not None and replace(row.producer_spec, need_detect=spec.need_detect) == spec:
            return
        if existing is not None and not existing.done():
            # Replacing a producer is a new physical connection attempt. A
            # cancelled task may still finish one await and publish bytes;
            # invalidate the buffers and generation before starting its
            # replacement so those bytes cannot masquerade as current.
            self._invalidate_generation(row, "producer-replaced")
            existing.cancel()
        row.spec = spec
        row.producer_spec = spec
        try:
            row.producer = asyncio.get_running_loop().create_task(
                self._produce(row), name=f"media-{spec.id}",
            )
        except RuntimeError:
            row.producer = None

    def viewers_for(self, camera_id: int) -> int:
        row = self._sessions.get(camera_id)
        return int(row.viewers) if row else 0

    async def get_live_endpoint(self, camera_id: int) -> dict[str, Any]:
        return {
            "camera_id": camera_id,
            "kind": "mjpeg",
            "path": f"/cameras/{camera_id}/live.mjpeg",
            "snapshot": f"/cameras/{camera_id}/snapshot.jpg",
        }

    def release_live(self, camera_id: int) -> None:
        row = self._sessions.get(camera_id)
        if row is None:
            return
        row.viewers = max(0, row.viewers - 1)
        row.last_view_at = time.monotonic()

    async def register_stream(self, camera_id: int, source: dict[str, Any]) -> dict[str, Any]:
        spec = source.get("spec")
        if not isinstance(spec, CameraLiveSpec):
            spec = CameraLiveSpec(
                id=int(camera_id),
                ip=str(source.get("ip") or ""),
                username=str(source.get("username") or ""),
                password=str(source.get("password") or ""),
                rtsp_url=str(source.get("rtsp_url") or source.get("uri") or ""),
                sdk_handle=source.get("sdk_handle"),
                ffmpeg_profile=str(source.get("ffmpeg_profile") or DEFAULT_PROFILE),
                transport=str(source.get("transport") or "TCP"),
                need_detect=bool(source.get("need_detect")),
                live_role=str(source.get("live_role") or ROLE_LIVE),
                stream_profiles=dict(source.get("stream_profiles") or {}),
                adapter_id=str(source.get("adapter_id") or "hvx").strip().lower() or "hvx",
                recognition_mode=str(source.get("recognition_mode") or ""),
            )
        row = self._session_for(spec)
        if source.get("need_detect"):
            row.detect_consumers = max(row.detect_consumers, 1)
            row.spec = replace(spec, need_detect=True)
        self.ensure_producer(row.spec)
        return await self.health(camera_id)

    def __init__(self) -> None:
        self._sessions: dict[int, StreamSession] = {}
        self._idle_task: asyncio.Task | None = None
        self._watch_task: asyncio.Task | None = None

    def release_detect(self, camera_id: int) -> None:
        row = self._sessions.get(camera_id)
        if row is None:
            return
        row.detect_consumers = 0
        row.spec = replace(row.spec, need_detect=False)
        # A direct fallback producer is only useful while a detector or viewer
        # owns it. Once DETECT moves to MediaMTX (or the worker takes over),
        # release the old FFmpeg/RTSP process instead of leaving it running.
        if row.producer is not None and not row.wanted():
            self.stop_producer(camera_id)

    async def get_detect_endpoint(self, camera_id: int) -> dict[str, Any]:
        sample = self.peek_detect(camera_id) or self.peek_live(camera_id)
        return {
            "camera_id": camera_id,
            "kind": "latest-frame",
            "seq": sample.seq if sample else 0,
            "age_ms": sample.age_ms() if sample else None,
        }

    def peek_detect_recent(self, camera_id: int, n: int = 3) -> list[FrameSample]:
        row = self._sessions.get(camera_id)
        return row.detect.recent(n) if row else []

    async def metrics(self, camera_id: int) -> dict[str, Any]:
        return await self.health(camera_id)

    def stream_contract(self, camera_id: int) -> CameraStreamStatus:
        """Return the normalized stream contract for either camera family."""
        row = self._sessions.get(int(camera_id))
        if row is None:
            return CameraStreamStatus(
                camera_id=int(camera_id), state="DISCONNECTED", latest_frame=None,
                frame_timestamp=None, frame_age_seconds=None, generation=0,
                fps=0.0, reconnect_count=0, startup_duration_ms=None,
                time_since_reconnect_seconds=None, last_successful_frame_at=None,
                decoder_health={"running": False}, last_error="camera stream not registered",
                healthy=False, source="",
            )
        sample = row.live.latest()
        age = self._fresh_age_s(row)
        latest = None
        if sample is not None:
            latest = {
                "sequence": sample.seq,
                "generation": sample.generation,
                "source": sample.source,
                "timestamp": sample.source_ts,
                "age_ms": sample.age_ms(),
            }
        stale = float(getattr(settings, "stale_stream_seconds", 2.5) or 2.5)
        healthy = bool(sample is not None and age is not None and age < stale and not row.frozen)
        now = time.monotonic()
        return CameraStreamStatus(
            camera_id=int(camera_id),
            state=str(row.state or "DISCONNECTED"),
            latest_frame=latest,
            frame_timestamp=sample.source_ts if sample is not None else None,
            frame_age_seconds=age,
            generation=int(row.generation),
            fps=float(row.live_fps or 0.0),
            reconnect_count=int(row.reconnects),
            startup_duration_ms=row.stream_startup_ms,
            time_since_reconnect_seconds=(
                round(now - row.last_reconnected_at, 3)
                if row.last_reconnected_at > 0 else None
            ),
            last_successful_frame_at=row.last_successful_frame_at or None,
            decoder_health={
                "running": bool(row.producer is not None and not row.producer.done()),
                "ffmpeg_pid": row.ffmpeg_pid,
                "child_pids": sorted(row.child_pids),
                "decode_errors": row.decode_errors,
            },
            last_error=str(row.last_error or ""),
            healthy=healthy,
            source=str(row.source or (sample.source if sample else "")),
        )

    def live_metrics(self) -> list[dict[str, Any]]:
        return [self._health_row(row) for _, row in sorted(self._sessions.items())]

    def note_ai_sample(self, camera_id: int, *, infer_ms: float = 0.0, dropped: bool = False) -> None:
        row = self._sessions.get(camera_id)
        if row is None:
            return
        now = time.monotonic()
        if dropped:
            row.frames_dropped_ai += 1
            return
        row.frames_sampled_ai += 1
        row.ai_infer_ms = float(infer_ms)
        row.ai_last_at = now
        sample = row.detect.latest() or row.live.latest()
        if sample:
            row.ai_last_seq = sample.seq
        if row._ai_fps_at <= 0:
            row._ai_fps_at = now
        row._ai_fps_n += 1
        elapsed = now - row._ai_fps_at
        if elapsed >= 1.0:
            row.ai_fps = round(row._ai_fps_n / elapsed, 1)
            row._ai_fps_at = now
            row._ai_fps_n = 0

    def acquire_live(self, spec: CameraLiveSpec) -> None:
        row = self._session_for(spec)
        row.viewers += 1
        row.last_view_at = time.monotonic()
        self.ensure_producer(spec)

    def health_sync(self, camera_id: int) -> dict[str, Any]:
        row = self._sessions.get(camera_id)
        if row is None:
            return {
                "camera_id": camera_id,
                "connection_state": "DISCONNECTED",
                "ok": False,
                "frozen": False,
            }
        return self._health_row(row)

    async def register_source(self, camera_id: int, source_config: dict[str, Any]) -> dict[str, Any]:
        return await self.register_stream(camera_id, source_config)

    def _session_for(self, spec: CameraLiveSpec) -> StreamSession:
        row = self._sessions.get(spec.id)
        if row is None:
            row = StreamSession(spec=spec)
            self._sessions[spec.id] = row
        else:
            row.spec = spec
        row.ffmpeg_profile = normalize_profile(spec.ffmpeg_profile)
        row.transport = normalize_transport(spec.transport)
        return row

    def child_pids(self) -> list[int]:
        pids: list[int] = []
        for row in self._sessions.values():
            pids.extend(sorted(row.child_pids))
        return pids

    def _fresh_age_s(self, row: StreamSession, now: float | None = None) -> float | None:
        if row.last_fresh_frame_at <= 0:
            return None
        return (now if now is not None else time.monotonic()) - row.last_fresh_frame_at

    async def get_snapshot(self, camera_id: int) -> bytes:
        return await self.snapshot(camera_id)

    def _health_row(self, row: StreamSession) -> dict[str, Any]:
        now = time.monotonic()
        live = row.live.latest()
        detect = row.detect.latest()
        pumping = row.producer is not None and not row.producer.done()
        fresh_s = self._fresh_age_s(row, now)
        received_s = (now - row.last_received_at) if row.last_received_at else None
        age = round(fresh_s, 3) if fresh_s is not None else None
        stale_s = float(getattr(settings, "stale_stream_seconds", 2.5) or 2.5)
        frozen = bool(
            fresh_s is not None
            and fresh_s >= stale_s
            and received_s is not None
            and received_s < stale_s
            and row.duplicate_frames > 0
        )
        if frozen:
            row.frozen = True
        elif fresh_s is not None and fresh_s < stale_s:
            row.frozen = False
        profiles = row.spec.stream_profiles or (hvx_profiles(row.spec.sdk_handle) if row.spec.sdk_handle is not None else {})
        warnings = profile_warnings(
            profiles,
            upstream_consumers=1 if pumping else 0,
            decoder_overloaded=row.live_fps > 0 and row.live_fps < 4 and pumping,
        )
        if frozen:
            warnings = [*warnings, "Same frame is repeating; live picture is not fresh"]
        state = row.state if pumping or row.state != "DISCONNECTED" else (
            "STREAMING" if pumping else ("cached" if live else "idle")
        )
        if frozen and state == "STREAMING":
            state = "DEGRADED"
        intervals = [value * 1000.0 for value in row.frame_intervals]
        live_age = round(fresh_s * 1000.0, 1) if fresh_s is not None else (live.age_ms(now) if live else None)
        detect_age = detect.age_ms(now) if detect else None
        fresh_ok = fresh_s is not None and fresh_s < stale_s and not frozen
        since_reconnect = (
            round(now - row.last_reconnected_at, 3)
            if row.last_reconnected_at > 0 else None
        )
        result = {
            "camera_id": row.spec.id,
            "media_generation": row.generation,
            "adapter_id": row.spec.adapter_id,
            "connection_state": state,
            "ok": bool(live) and fresh_ok,
            "viewers": row.viewers,
            "detect_consumers": row.detect_consumers,
            "pumping": pumping,
            "source": row.source or (live.source if live else ""),
            "fps": row.live_fps,
            "source_fps": row.source_fps,
            "source_frame_seq": row.source_frame_seq,
            "live_fps": row.live_fps,
            "ai_processed_fps": row.ai_fps,
            "ai_samples_dropped": row.frames_dropped_ai,
            "ai_frame_age_ms": detect_age,
            "detect_frame_age_ms": detect_age,
            "live_frame_age_ms": live_age,
            "frozen": frozen,
            "duplicate_frames": row.duplicate_frames,
            "frames_changed": row.frames_changed,
            "decoder_restarts": row.decoder_restarts,
            "last_received_age_ms": round(received_s * 1000.0, 1) if received_s is not None else None,
            "frame_interval_avg_ms": round(sum(intervals) / len(intervals), 1) if intervals else None,
            "frame_interval_p50_ms": _percentile(intervals, 0.50),
            "frame_interval_p95_ms": _percentile(intervals, 0.95),
            "frame_interval_max_ms": round(max(intervals), 1) if intervals else None,
            "seq": live.seq if live else 0,
            "live_frame_seq": live.seq if live else 0,
            "detect_frame_seq": detect.seq if detect else 0,
            "age_seconds": age,
            "queue_depth": row.live.depth(),
            "detect_queue_depth": row.detect.depth(),
            "rtsp": (row.url or "").startswith("rtsp://"),
            "sdk": row.source == "sdk" or row.spec.sdk_handle is not None or adapter_requires_native_stream(row.spec.adapter_id),
            "stream_backend": (
                "ocxconfig_netsdk"
                if row.source == "sdk" or row.spec.sdk_handle is not None or adapter_requires_native_stream(row.spec.adapter_id)
                else "rtsp_gateway"
            ),
            "native_stream_required": bool(
                adapter_requires_native_stream(row.spec.adapter_id)
                or row.spec.sdk_handle is not None
                or any(
                    str(profile.get("protocol") or "").lower() == "sdk"
                    for profile in (row.spec.stream_profiles or {}).values()
                    if isinstance(profile, dict)
                )
            ),
            "codec": row.codec or ((profiles.get(ROLE_LIVE) or profiles.get(ROLE_SUB) or {}).get("codec") if isinstance(profiles, dict) else ""),
            "width": row.width,
            "height": row.height,
            "gop": row.gop,
            "transport": row.transport,
            "ffmpeg_profile": row.ffmpeg_profile,
            "using_fallback": row.using_fallback,
            "ffmpeg_pid": row.ffmpeg_pid,
            "child_pids": sorted(row.child_pids),
            "reconnects": row.reconnects,
            "decode_errors": row.decode_errors,
            "frames_received": row.frames_arrived,
            "frames_decoded": row.live.received,
            "frames_displayed": row.frames_displayed,
            "frames_dropped_live": row.live.dropped,
            "frames_sampled_ai": row.frames_sampled_ai,
            "frames_dropped_ai": row.frames_dropped_ai,
            "last_keyframe_age": round(now - row.last_keyframe_at, 3) if row.last_keyframe_at else None,
            "last_frame_received_at": row.last_frame_received_at,
            "last_successful_frame_at": row.last_successful_frame_at or None,
            "stream_startup_ms": row.stream_startup_ms,
            "time_since_reconnect_seconds": since_reconnect,
            "last_reconnect_reason": row.last_reconnect_reason,
            "bitrate_bps": row.bitrate_bps,
            "ai_infer_ms": row.ai_infer_ms,
            "url_redacted": redact_url(row.url) if row.url else "",
            "stream_profiles": public_profiles(profiles),
            "warnings": warnings,
            "last_error": row.last_error,
            "sdk_diagnostics": dict(row.sdk_diagnostics),
            "callback_progress": {
                "frames": row.sdk_diagnostics.get("callback_frames"),
                "fps": row.sdk_diagnostics.get("callback_fps"),
                "age_ms": row.sdk_diagnostics.get("callback_age_ms"),
            } if row.sdk_diagnostics else None,
            "jpeg_production": {
                "fps": row.sdk_diagnostics.get("jpeg_production_fps"),
                "age_ms": row.sdk_diagnostics.get("jpeg_age_ms"),
                "frames": row.sdk_diagnostics.get("frames_received"),
                "encode_ms": row.sdk_diagnostics.get("jpeg_encode_ms"),
            } if row.sdk_diagnostics else None,
            "consumer_demand_age_ms": row.sdk_diagnostics.get("consumer_demand_age_ms") if row.sdk_diagnostics else None,
            "pump_liveness": row.sdk_diagnostics.get("pump_liveness") if row.sdk_diagnostics else None,
            "request_duration_ms": row.request_duration_ms,
            "request_status": row.request_status,
            "request_error": row.request_error,
            "recovery_reason": row.recovery_reason or row.sdk_diagnostics.get("recovery_reason", ""),
            "effective_ocr_owner": _effective_ocr_owner(row.spec.recognition_mode),
            "stall_classification": _classify_sdk_stall(row, now),
        }
        result["stream_contract"] = self.stream_contract(row.spec.id).as_dict()
        return result
