from __future__ import annotations

class _HVXVideoMixin:
    @staticmethod
    def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
        """Read a bounded integer without allowing a bad Windows env to kill a pump."""
        try:
            value = int(os.environ.get(name, str(default)))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    @classmethod
    def _display_jpeg_options(cls) -> tuple[int, int]:
        """Return the bounded display-only JPEG profile.

        Recognition continues to use the native SDK callbacks.  These limits
        apply only to the operator preview, where full camera resolution is
        unnecessary and expensive for the 32-bit Windows bridge.
        """
        max_width = cls._env_int(
            "SMARTPARK_HVX_JPEG_MAX_WIDTH", 1280, minimum=0, maximum=4096,
        )
        quality = cls._env_int(
            "SMARTPARK_HVX_JPEG_QUALITY", 78, minimum=45, maximum=95,
        )
        return max_width, quality

    @classmethod
    def _display_jpeg_fps(cls) -> float:
        try:
            value = float(os.environ.get("SMARTPARK_HVX_JPEG_FPS", "15"))
        except (TypeError, ValueError):
            value = 15.0
        return max(1.0, min(20.0, value))

    def _hidden_hwnd(self, handle: int):
        """Create the PlaySdk HWND on the dedicated UI thread (OcxConfig pattern)."""
        handle = int(handle)
        existing = self._hwnds.get(handle)
        if existing:
            return existing
        if threading.current_thread() is self._ui_thread:
            return self._create_hidden_hwnd(handle)
        self._video_running = True
        self._ensure_ui_thread()
        ready = self._hwnd_ready.get(handle)
        if ready is None:
            ready = threading.Event()
            self._hwnd_ready[handle] = ready
            self._hwnd_queue.put(handle)
        ready.wait(1.5)
        return self._hwnds.get(handle)

    def _draw_data_jpeg(self, handle: int) -> bytes:
        handle = int(handle)
        with self._lock:
            frame = self._draw_frames.get(handle)
            seq = int(self._draw_frame_seq.get(handle, 0))
            encoded_seq = int(self._draw_encoded_seq.get(handle, 0))
        # A callback is an edge, not a cache. Returning the previously encoded
        # JPEG here makes a stalled decoder look healthy to the HTTP bridge.
        # The caller must receive an empty result until a newer DIB arrives.
        if not frame or seq <= encoded_seq:
            return b""
        raw, width, height, bit_count, stride, orientation = frame
        encode_started = time.monotonic()
        max_width, quality = self._display_jpeg_options()
        try:
            from PIL import Image

            mode = "BGR" if bit_count == 24 else "BGRX"
            image = Image.frombytes("RGB", (width, height), raw, "raw", mode, stride, orientation)
            source_width, source_height = image.size
            if max_width and image.width > max_width:
                output_height = max(1, round(image.height * max_width / image.width))
                image = image.resize((max_width, output_height), Image.Resampling.BILINEAR)
            output = BytesIO()
            image.save(output, format="JPEG", quality=quality, optimize=False)
            jpeg = output.getvalue()
        except Exception as exc:
            self._note_video(handle, draw_data_error=type(exc).__name__)
            return b""
        encode_ms = round((time.monotonic() - encode_started) * 1000.0, 1)
        now = time.monotonic()
        with self._lock:
            if handle in self._video_handles:
                self._draw_encoded_seq[handle] = seq
                self._last_live_jpeg[handle] = jpeg
                self._live_received_at[handle] = now
                getattr(self, "_live_frame_seq", {})[handle] = seq
                diagnostics = getattr(self, "_video_diagnostics", {}).setdefault(handle, {})
                frames_received = int(diagnostics.get("frames_received") or 0) + 1
                first = float(diagnostics.get("jpeg_window_at") or now)
                count = int(diagnostics.get("jpeg_window_frames") or 0) + 1
                diagnostics.update(
                    jpeg_encode_ms=encode_ms,
                    jpeg_source_width=source_width,
                    jpeg_source_height=source_height,
                    jpeg_output_width=image.width,
                    jpeg_output_height=image.height,
                    jpeg_quality=quality,
                    jpeg_production_fps=round(count / max(now - first, 0.001), 1),
                    jpeg_window_at=first,
                    jpeg_window_frames=count,
                )
            else:
                frames_received = 0
            condition = getattr(self, "_live_condition", None)
            if condition is not None:
                condition.notify_all()
        self._note_video(
            handle,
            capture_mode="sdk_draw_data",
            frame_delivery="sdk_draw_data",
            last_jpeg_at=now,
            frames_received=frames_received,
            window_capture_rc=None,
        )
        return jpeg

    def _recover_video_decoder(self, handle: int) -> bool:
        """Reopen one PlaySdk decoder after a native JPEG exception.

        The QY SDK exposes no decoder-reset function.  OcxConfig's own
        recovery path closes and reopens the PlaySdk camera while preserving
        the NetSDK control/recognition session.  Keep this operation on the
        HWND owner thread and bound the caller wait so one broken camera does
        not block the other lane.
        """
        handle = int(handle)
        with self._lock:
            if handle not in self._video_handles:
                return False
            attempts = int(self._video_diagnostics.get(handle, {}).get("decoder_recovery_attempts") or 0)
            if attempts >= 3:
                return False
            self._video_diagnostics.setdefault(handle, {})["decoder_recovery_attempts"] = attempts + 1
            current = self._video_streams.get(handle)
            if current is None:
                current = self.selected_stream_type(handle)
            current = int(current or 0)

        def reopen():
            with self._video_control(handle):
                with self._lock:
                    if handle not in self._video_handles:
                        return {"ok": False, "reason": "video handle was released"}
                stop_rc = int(self.dll.Net_StopVideo(handle)) if hasattr(self.dll, "Net_StopVideo") else 0
                if stop_rc != DC_NO_ERROR:
                    return {"ok": False, "stop_rc": stop_rc, "reason": describe_rc(stop_rc)}
                result = self._start_video(handle, current)
                return {"ok": bool(result.get("ok")), "stop_rc": stop_rc, **result}

        try:
            result = self._call_video_ui(reopen)
        except Exception as exc:
            self._note_video(handle, recovery_error=str(exc), recovery_state="FAILED")
            logging.getLogger("smartpark.hvx").warning(
                "Native JPEG decoder recovery failed: handle=%s error=%s", handle, exc,
            )
            return False
        if not result or not result.get("ok"):
            self._note_video(handle, recovery_error=str(result.get("reason") or result.get("error") or "start failed"),
                             recovery_state="FAILED")
            logging.getLogger("smartpark.hvx").warning(
                "Native JPEG decoder recovery failed: handle=%s stop_rc=%s start_rc=%s",
                handle, result.get("stop_rc"), result.get("rc"),
            )
            return False
        self._note_video(
            handle,
            native_decoder_fault=False,
            recovery_error="",
            recovery_state="RECOVERED",
            decoder_restarts=int(self._video_diagnostics.get(handle, {}).get("decoder_restarts") or 0) + 1,
        )
        logging.getLogger("smartpark.hvx").warning(
            "Recovered native JPEG decoder: handle=%s stream=%s", handle, result.get("stream_type"),
        )
        return True

    def _video_lock(self, handle: int):
        with self._lock:
            return self._video_locks.setdefault(int(handle), threading.RLock())

    def _call_video_ui(self, operation, *, handle: int | None = None, action: str = "video-control"):
        started = time.monotonic()

        def note(**fields):
            if handle is None:
                return
            self._note_video(
                int(handle),
                control_action=action,
                control_duration_ms=round(max(0.0, time.monotonic() - started) * 1000, 1),
                **fields,
            )

        if threading.current_thread() is self._ui_thread:
            try:
                value = operation()
            except Exception as exc:
                note(control_result="error", control_error=str(exc)[:240])
                raise
            note(control_result="ok")
            return value
        self._ensure_ui_thread()
        ready = threading.Event()
        result = {}
        with self._ui_submit_lock:
            now = time.monotonic()
            if now < self._ui_control_not_before:
                note(control_result="busy", control_error="recovery holdoff")
                raise HVXSDKError("Video control is busy; previous decoder recovery is still unwinding")
            try:
                self._ui_commands.put_nowait((operation, ready, result))
            except queue.Full:
                self._ui_control_not_before = now + 2.0
                note(control_result="busy", control_error="control queue full")
                raise HVXSDKError("Video control is busy")
            if not ready.wait(5.0):
                # The UI thread may still be inside a vendor call. Mark this
                # command cancelled and hold off new submissions long enough
                # for it to be discarded; never stack another Net_StartVideo.
                result["cancelled"] = True
                self._ui_control_not_before = time.monotonic() + 6.0
                note(control_result="timeout", control_error="UI thread did not finish within 5 seconds")
                raise HVXSDKError("Video control timed out; see hvx-host.log")
            if "error" in result:
                note(control_result="error", control_error=str(result["error"])[:240])
                raise result["error"]
            note(control_result="ok")
            return result.get("value")

    def _register_draw_data(self, handle: int) -> int | None:
        if not hasattr(self.dll, "Net_SetDrawDataOut"):
            return None
        handle = int(handle)
        callback = self._draw_callbacks.get(handle)
        if callback is None:
            callback = self._FDrawDataOut(self._on_draw_data)
            self._draw_callbacks[handle] = callback
        rc = int(self.dll.Net_SetDrawDataOut(handle, callback, None))
        self._note_video(handle, draw_data_rc=rc, draw_data_registered_at=time.monotonic())
        return rc

    def _get_jpg_buffer(self, handle: int) -> bytes:
        # Prefer the continuous decoded-frame callback used by ParkWatch.
        # This avoids treating Net_GetJpgBuffer's current cache as a stream
        # and keeps display delivery independent from capture/OCR callbacks.
        handle = int(handle)
        draw_registered = False
        if handle in getattr(self, "_draw_callbacks", {}):
            with self._lock:
                diagnostics = getattr(self, "_video_diagnostics", {}).get(handle, {})
                draw_rc = diagnostics.get("draw_data_rc")
                registered_at = float(diagnostics.get("draw_data_registered_at") or 0.0)
                received = int(diagnostics.get("draw_data_frames") or 0)
            draw_registered = draw_rc == DC_NO_ERROR
            jpeg = self._draw_data_jpeg(handle)
            if jpeg:
                return jpeg
            # During warm-up, wait for the callback instead of opening a
            # second read path. Once at least one callback has arrived, keep
            # this lane authoritative; a later silence must trigger recovery.
            if draw_registered and (received or not registered_at or time.monotonic() - registered_at < 2.0):
                return b""
            # A few older DLL builds accept the registration but never invoke
            # it. After a bounded warm-up, permit the legacy latest-JPEG API
            # rather than leaving that camera permanently blank.
            if draw_registered and not received:
                draw_registered = False
        # Compatibility fallback for old QY DLL builds that reject or do not
        # export Net_SetDrawDataOut. It is deliberately unreachable after a
        # healthy draw callback has delivered its first frame.
        if not draw_registered:
            jpeg = self._get_native_jpg_buffer(handle)
            if jpeg:
                return jpeg
        # Native QY video is also rendered by PlaySdk into the HWND passed to
        # Net_StartVideo, just as in OcxConfig. Use it only after the direct
        # callback and compatibility JPEG API have not supplied a frame.
        if os.name == "nt" and self._hwnds.get(int(handle)):
            return self._capture_window_jpeg(handle)
        return b""

    def video_status(self, handle: int) -> dict:
        now = time.monotonic()
        with self._lock:
            row = dict(getattr(self, "_video_diagnostics", {}).get(int(handle), {}))
            row["stream_type"] = getattr(self, "_video_streams", {}).get(int(handle))
            row["hwnd"] = int(getattr(self, "_hwnds", {}).get(int(handle)) or 0)
            function_list = dict(getattr(self, "_function_lists", {}).get(int(handle)) or {})
        row["function_list_flags"] = int(function_list.get("flags") or 0)
        row["capability_stream_type"] = int(function_list.get("stream_type") or 0)
        row["function_list_rc"] = function_list.get("rc")
        received_at = row.get("last_jpeg_at")
        read_started = row.get("jpeg_read_started_at")
        row["pending_read_ms"] = round(max(0.0, now - read_started) * 1000, 1) if row.get("jpeg_read_pending") and read_started is not None else None
        age = max(0.0, now - received_at) if received_at is not None else None
        row["frame_age_ms"] = round(age * 1000, 1) if age is not None else None
        callback_at = row.get("callback_last_at")
        jpeg_at = row.get("last_jpeg_at")
        demand_at = row.get("consumer_demand_at")
        pump_at = row.get("pump_last_iteration_at")
        row["callback_age_ms"] = round(max(0.0, now - callback_at) * 1000, 1) if callback_at else None
        row["jpeg_age_ms"] = round(max(0.0, now - jpeg_at) * 1000, 1) if jpeg_at else None
        row["consumer_demand_age_ms"] = round(max(0.0, now - demand_at) * 1000, 1) if demand_at else None
        row["pump_last_iteration_age_ms"] = round(max(0.0, now - pump_at) * 1000, 1) if pump_at else None
        row["pump_liveness"] = bool(pump_at and now - pump_at <= 2.0)
        row["callback_frames"] = int(row.get("callback_frames") or row.get("draw_data_frames") or 0)
        row["callback_fps"] = float(row.get("callback_fps") or 0.0)
        row["jpeg_production_fps"] = float(row.get("jpeg_production_fps") or 0.0)
        max_width, quality = self._display_jpeg_options()
        row.setdefault("jpeg_max_width", max_width)
        row.setdefault("jpeg_quality", quality)
        row["jpeg_target_fps"] = round(self._display_jpeg_fps(), 1)
        row["recovery_reason"] = str(row.get("recovery_reason") or row.get("recovery_error") or "")[:200]
        for private_key in (
            "last_jpeg_at", "jpeg_read_started_at", "callback_last_at",
            "consumer_demand_at", "pump_last_iteration_at", "callback_window_at",
            "jpeg_window_at",
        ):
            row.pop(private_key, None)
        row.setdefault("frames_received", 0)
        row["state"] = ("LIVE" if age is not None and age <= 5.0 else "START_FAILED"
                        if row.get("start_rc") not in (None, DC_NO_ERROR) else "NO_FRAMES")
        row["stream_backend"] = "ocxconfig_netsdk"
        row["frame_delivery"] = row.get("frame_delivery") or row.get("capture_mode") or "pending"
        row["bounded_latest_frame"] = True
        return row

    def live_frame_seq(self, handle: int) -> int:
        """Monotonic source-frame identity for the live JPEG endpoint."""
        with self._lock:
            return max(
                int(getattr(self, "_live_frame_seq", {}).get(int(handle), 0) or 0),
                int(getattr(self, "_window_frame_seq", {}).get(int(handle), 0) or 0),
            )

    def stop_video(self, handle: int) -> int:
        def stop():
            with self._video_control(handle):
                with self._lock:
                    self._video_handles.discard(int(handle))
                    getattr(self, "_video_retry_handles", set()).discard(int(handle))
                    getattr(self, "_video_retry_at", {}).pop(int(handle), None)
                    self._last_live_jpeg.pop(int(handle), None)
                    getattr(self, "_draw_frames", {}).pop(int(handle), None)
                    getattr(self, "_draw_frame_seq", {}).pop(int(handle), None)
                    getattr(self, "_draw_encoded_seq", {}).pop(int(handle), None)
                    getattr(self, "_window_frame_seq", {}).pop(int(handle), None)
                    getattr(self, "_window_last_jpeg", {}).pop(int(handle), None)
                    getattr(self, "_native_jpeg_disabled_until", {}).pop(int(handle), None)
                    self._live_received_at.pop(int(handle), None)
                    self._live_requested_at.pop(int(handle), None)
                if hasattr(self.dll, "Net_StopVideo"):
                    return int(self.dll.Net_StopVideo(int(handle)))
                return 0
        try:
            try:
                return self._call_video_ui(stop, handle=handle, action="stop_video")
            except TypeError as exc:
                if "unexpected keyword argument" not in str(exc):
                    raise
                return self._call_video_ui(stop)
        except Exception as exc:
            self._note_video(handle, control_error=str(exc))
            return -1

    def _ensure_camera_pump(self, handle: int):
        """One GetJpgBuffer thread per camera so a stalled lane cannot freeze the others."""
        handle = int(handle)
        self._ensure_ui_thread()
        with self._lock:
            existing = self._video_threads.get(handle)
            if existing is not None and existing.is_alive():
                return
            self._video_running = True
            thread = threading.Thread(
                target=self._camera_video_loop,
                args=(handle,),
                name=f"hvx-live-{handle}",
                daemon=True,
            )
            self._video_threads[handle] = thread
            thread.start()

    def _note_video_read(self, handle: int, rc, size: int, error: str, received: bool) -> None:
        now = time.monotonic()
        with self._lock:
            row = self._video_diagnostics.setdefault(int(handle), {})
            previous = row.get("jpeg_error")
            started = row.get("jpeg_read_started_at", now)
            row.update(jpeg_rc=rc, jpeg_bytes=size, jpeg_error=error, jpeg_read_pending=False)
            row["jpeg_read_ms"] = round(max(0.0, now - started) * 1000, 1)
            row["jpeg_attempts"] = int(row.get("jpeg_attempts", 0)) + 1
            if received:
                row["frames_received"] = int(row.get("frames_received", 0)) + 1
                row["last_jpeg_at"] = now
            report = bool(error) and (error != previous or now - row.get("last_error_logged_at", 0) >= 30.0)
            if report:
                row["last_error_logged_at"] = now
        if report:
            logging.getLogger("smartpark.hvx").warning(
                "Video JPEG unavailable: handle=%s rc=%s bytes=%s reason=%s", handle, rc, size, error,
            )

    def _camera_video_loop(self, handle: int):
        """Consume one continuous decoded callback lane per camera.

        The loop only converts a newly-arrived DIB (or reads the legacy
        current-JPEG API when the callback is unavailable). It never drains a
        frame queue and never republishes the previous JPEG as progress.
        """
        handle = int(handle)
        idle = 0
        retry_at = time.monotonic() + 5.0
        interval = 1.0 / self._display_jpeg_fps()
        last_progress_at = time.monotonic()
        previous_jpeg = b""
        previous_seq = 0
        def publish(jpeg):
            with self._lock:
                if handle in self._video_handles:
                    previous = self._last_live_jpeg.get(handle, b"")
                    self._last_live_jpeg[handle] = jpeg
                    # A changed JPEG is proof that the SDK delivered a new
                    # frame. Draw-data frames normally update this before the
                    # pump publishes; direct OcxConfig reads update it here.
                    if jpeg != previous:
                        self._live_received_at[handle] = time.monotonic()
                        seq = int(getattr(self, "_live_frame_seq", {}).get(handle, 0) or 0) + 1
                        getattr(self, "_live_frame_seq", {})[handle] = seq
                        condition = getattr(self, "_live_condition", None)
                        if condition is not None:
                            condition.notify_all()
        while self._video_running:
            started = time.monotonic()
            with self._lock:
                diagnostics = getattr(self, "_video_diagnostics", {}).setdefault(handle, {})
                diagnostics["pump_last_iteration_at"] = started
                diagnostics["pump_iterations"] = int(diagnostics.get("pump_iterations") or 0) + 1
            with self._lock:
                active = handle in self._video_handles
                retrying = handle in getattr(self, "_video_retry_handles", set())
                retry_at = float(getattr(self, "_video_retry_at", {}).get(handle, 0.0) or 0.0)
                if not active and not retrying:
                    break
                current_stream = self._video_streams.get(handle)
            if not active and retrying:
                if started < retry_at:
                    time.sleep(min(0.25, retry_at - started))
                    continue
                try:
                    result = self.start_video(handle, current_stream)
                    if result.get("ok"):
                        idle = 0
                        last_progress_at = time.monotonic()
                        continue
                except Exception as exc:
                    self._note_video(handle, control_error=str(exc))
                with self._lock:
                    getattr(self, "_video_retry_at", {})[handle] = time.monotonic() + min(30.0, 2.0 ** min(idle + 1, 4))
                idle = min(idle + 1, 4)
                continue
            with self._lock:
                requested = float(getattr(self, "_live_requested_at", {}).get(handle, started) or started)
                not_before = float(getattr(self, "_video_diagnostics", {}).get(handle, {}).get("jpeg_not_before") or 0.0)
            # Do not keep reading/encoding a camera that no longer has a live
            # consumer. This is the native equivalent of ParkWatch owning one
            # display worker per active camera instead of leaving old readers
            # behind after a viewer disconnects.
            if started - requested > 5.0:
                retry_at = started + 5.0
                time.sleep(0.25)
                continue
            if started < not_before:
                time.sleep(min(0.1, not_before - started))
                continue
            jpeg = self._get_jpg_buffer(handle)
            with self._lock:
                current_seq = max(
                    int(getattr(self, "_live_frame_seq", {}).get(handle, 0) or 0),
                    int(getattr(self, "_window_frame_seq", {}).get(handle, 0) or 0),
                )
                draw_seq = int(getattr(self, "_draw_frame_seq", {}).get(handle, 0) or 0)
                encoded_seq = int(getattr(self, "_draw_encoded_seq", {}).get(handle, 0) or 0)
            new_frame = bool(jpeg) and (jpeg != previous_jpeg or current_seq > previous_seq or draw_seq > encoded_seq)
            if jpeg and not new_frame:
                # A cached draw/window JPEG is not progress. Route it through
                # the normal no-frame recovery path so a frozen PlaySdk port
                # is reopened instead of being served forever as "live".
                jpeg = b""
            if jpeg:
                if new_frame:
                    publish(jpeg)
                    previous_jpeg = jpeg
                    previous_seq = max(previous_seq, current_seq)
                    last_progress_at = time.monotonic()
                    self._note_video(handle, decoder_recovery_attempts=0, recovery_state="STABLE")
                    idle = 0
                    retry_at = time.monotonic() + 5.0
                else:
                    # _draw_data_jpeg intentionally returns its cached JPEG
                    # between callbacks. Treating that cache as a new frame
                    # hid frozen cameras and made the UI appear connected.
                    idle = min(idle + 1, 8)
            else:
                idle = min(idle + 1, 8)
                # A native access violation is not an empty network frame.
                # Net_StopVideo can deadlock inside PlaySdk after this fault,
                # wedging the shared UI command thread for every other camera.
                with self._lock:
                    diagnostics = getattr(self, "_video_diagnostics", {}).get(handle, {})
                    native_fault = diagnostics.get("native_decoder_fault", False)
                    window_capture = diagnostics.get("capture_mode") == "play_sdk_hwnd"
                if native_fault:
                    recovered = self._recover_video_decoder(handle)
                    if recovered:
                        idle = 0
                        retry_at = time.monotonic() + 5.0
                        continue
                    logging.getLogger("smartpark.hvx").error(
                        "Stopping faulty JPEG pump for handle=%s after bounded recovery; recognition callbacks remain registered",
                        handle,
                    )
                    break
                if window_capture and time.monotonic() - last_progress_at < 5.0:
                    # Window capture is deliberately non-destructive during
                    # the normal paint warm-up. Once it has been stale for a
                    # bounded interval, the same close/reopen recovery used by
                    # OcxConfig is required to recover a wedged PlaySdk port.
                    time.sleep(max(0.05, interval))
                    continue
                if time.monotonic() - last_progress_at < 5.0:
                    time.sleep(max(0.05, interval))
                    continue
                if time.monotonic() >= retry_at:
                    retry_at = time.monotonic() + 30.0
                    try:
                        def restart():
                            with self._video_control(handle):
                                with self._lock:
                                    active = handle in self._video_handles
                                if not active:
                                    return None
                                logging.getLogger("smartpark.hvx").warning("Restarting empty video decoder: handle=%s", handle)
                                if hasattr(self.dll, "Net_StopVideo"):
                                    self.dll.Net_StopVideo(handle)
                                current = self._video_streams.get(handle)
                                if current is None:
                                    current = self.selected_stream_type(handle)
                                current = int(current or 0)
                                fallback = self.selected_stream_type(handle) if current in (0, 1) else current
                                if fallback == current:
                                    fallback = 0 if current != 0 else 1
                                return self._start_video(handle, fallback)
                        self._call_video_ui(restart)
                    except Exception as exc:
                        self._note_video(handle, control_error=str(exc))
                        logging.getLogger("smartpark.hvx").warning("Video recovery failed: handle=%s error=%s", handle, exc)
            time.sleep(max(0.002, interval - (time.monotonic() - started)))
        with self._lock:
            if self._video_threads.get(handle) is threading.current_thread():
                self._video_threads.pop(handle, None)

    def _pump_messages(self):
        try:
            user32 = ctypes.windll.user32
        except Exception:
            return
        class MSG(ctypes.Structure):
            _fields_ = [
                ("hwnd", ctypes.c_void_p),
                ("message", ctypes.c_uint),
                ("wParam", ctypes.c_uint),
                ("lParam", ctypes.c_long),
                ("time", ctypes.c_uint),
                ("pt_x", ctypes.c_long),
                ("pt_y", ctypes.c_long),
            ]
        m = MSG()
        while user32.PeekMessageW(ctypes.byref(m), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(m))
            user32.DispatchMessageW(ctypes.byref(m))

    def _video_loop(self):
        """Legacy single-thread pump kept for tests that patch this name."""
        while self._video_running:
            with self._lock:
                handles = list(self._video_handles)
            if not handles:
                time.sleep(0.2)
                continue
            for handle in handles:
                self._ensure_camera_pump(handle)
            time.sleep(0.2)
        self._video_thread = None

    def _note_video(self, handle: int, **fields) -> None:
        with self._lock:
            if not hasattr(self, "_video_diagnostics"):
                self._video_diagnostics = {}
            row = self._video_diagnostics.setdefault(int(handle), {})
            row.update(fields)

    def _ensure_video_thread(self):
        """Compatibility wrapper — live video is now one pump per camera."""
        with self._lock:
            handles = list(self._video_handles)
        for handle in handles:
            self._ensure_camera_pump(handle)

    def _get_native_jpg_buffer(self, handle: int) -> bytes:
        """Read the latest decoded PlaySdk JPEG through the OcxConfig API.

        OcxConfig starts PlaySdk, attaches its window, and reads the bounded
        latest JPEG buffer. Keep the call serialized per camera and temporarily
        fall back after a firmware-specific native exception so one QY camera
        cannot wedge the shared 32-bit host.
        """
        handle = int(handle)
        if not hasattr(self.dll, "Net_GetJpgBuffer"):
            self._note_video(handle, jpeg_error="API_UNAVAILABLE")
            return b""
        disabled_until = float(getattr(self, "_native_jpeg_disabled_until", {}).get(handle, 0.0) or 0.0)
        if disabled_until > time.monotonic():
            return b""
        with self._video_lock(handle):
            with self._lock:
                if hasattr(self, "_video_handles") and handle not in self._video_handles:
                    return b""
            buf = ctypes.POINTER(ctypes.c_ubyte)()
            size = ctypes.c_ulong(0)
            rc = None
            error = ""
            data = b""
            self._note_video(handle, jpeg_read_pending=True, jpeg_read_started_at=time.monotonic())
            try:
                rc = int(self.dll.Net_GetJpgBuffer(handle, ctypes.byref(buf), ctypes.byref(size)))
                if rc != DC_NO_ERROR:
                    error = "SDK_ERROR"
                elif not size.value or not buf:
                    error = "EMPTY_BUFFER"
                elif size.value > 4_000_000:
                    error = "BUFFER_TOO_LARGE"
                else:
                    data = ctypes.string_at(buf, int(size.value))
                    if data[:2] != b"\xff\xd8":
                        error = "INVALID_JPEG"
                        data = b""
            except Exception as exc:
                error = type(exc).__name__
                if isinstance(exc, OSError):
                    until = time.monotonic() + 30.0
                    getattr(self, "_native_jpeg_disabled_until", {})[handle] = until
                    self._note_video(handle, native_decoder_fault=True,
                                     native_decoder_error=str(exc),
                                     native_jpeg_disabled_until=until)
                    logging.getLogger("smartpark.hvx").error(
                        "Native JPEG decoder fault: handle=%s error=%s; using bounded fallback for 30s",
                        handle, exc,
                    )
            finally:
                if hasattr(self.dll, "Net_FreeBuffer") and buf:
                    try:
                        self.dll.Net_FreeBuffer(ctypes.cast(buf, ctypes.c_void_p))
                    except Exception:
                        logging.getLogger("smartpark.hvx").exception("Video buffer release failed: handle=%s", handle)
            self._note_video_read(handle, rc, int(size.value), error, bool(data))
            if data:
                self._note_video(handle, capture_mode="netsdk_jpg_buffer", window_capture_rc=None)
            return data

    @contextmanager
    def _video_control(self, handle: int):
        lock = self._video_lock(handle)
        if not lock.acquire(timeout=1.0):
            self._note_video(handle, control_error="Decoder operation busy")
            raise HVXSDKError("Video decoder is busy; see hvx-host.log and /info video diagnostics")
        try:
            yield
        finally:
            lock.release()

    def start_video(self, handle: int, stream_type: int | None = None) -> dict:
        """Start PlaySdk on OcxConfig's capability-selected stream and HWND."""
        if stream_type is None:
            stream_type = self.selected_stream_type(handle)
        def start():
            with self._video_control(handle):
                return self._start_video(handle, stream_type)
        try:
            try:
                return self._call_video_ui(start, handle=handle, action="start_video")
            except TypeError as exc:
                # Keep lightweight test/maintenance shims that implement the
                # old one-argument hook compatible with the timed diagnostics
                # hook added above.
                if "unexpected keyword argument" not in str(exc):
                    raise
                return self._call_video_ui(start)
        except Exception as exc:
            self._note_video(handle, control_error=str(exc))
            raise

    def _ui_loop(self):
        while self._video_running or not self._hwnd_queue.empty():
            try:
                operation, ready, result = self._ui_commands.get_nowait()
            except queue.Empty:
                pass
            else:
                try:
                    if not result.get("cancelled"):
                        result["value"] = operation()
                except Exception as exc:
                    result["error"] = exc
                finally:
                    ready.set()
            while True:
                try:
                    handle = int(self._hwnd_queue.get_nowait())
                except queue.Empty:
                    break
                try:
                    self._create_hidden_hwnd(handle)
                except Exception:
                    self._hwnds.setdefault(handle, None)
                ready = self._hwnd_ready.get(handle)
                if ready is not None:
                    ready.set()
            self._pump_messages()
            time.sleep(0.01)

    def _start_video(self, handle: int, stream_type: int) -> dict:
        if not hasattr(self.dll, "Net_StartVideo"):
            return {"ok": False, "error": "Net_StartVideo not exported"}
        hwnd = self._hidden_hwnd(handle)
        selected = int(stream_type) if stream_type is not None else self.selected_stream_type(handle)
        self._note_video(handle, control_operation="STARTING", requested_stream=selected)
        rc = int(self.dll.Net_StartVideo(int(handle), selected, hwnd))
        used = selected
        if rc != DC_NO_ERROR:
            # Some PlaySdk builds leave a partially opened receive port after
            # a failed stream selection.  ParkWatch closes that player before
            # trying the alternate stream; doing the same prevents two native
            # decoder states from competing for one camera connection.
            if hasattr(self.dll, "Net_StopVideo"):
                try:
                    self.dll.Net_StopVideo(int(handle))
                except Exception:
                    logging.getLogger("smartpark.hvx").debug(
                        "Failed to clean up rejected PlaySdk stream: handle=%s",
                        handle,
                        exc_info=True,
                    )
            # Preserve recovery for cameras without a function-list response,
            # while keeping advertised gate-camera stream types primary.
            other = 0 if selected != 0 else 1
            used = other
            rc = int(self.dll.Net_StartVideo(int(handle), other, hwnd))
        if rc != DC_NO_ERROR and hwnd:
            if hasattr(self.dll, "Net_StopVideo"):
                try:
                    self.dll.Net_StopVideo(int(handle))
                except Exception:
                    logging.getLogger("smartpark.hvx").debug(
                        "Failed to clean up rejected PlaySdk stream: handle=%s",
                        handle,
                        exc_info=True,
                    )
            rc = int(self.dll.Net_StartVideo(int(handle), used, None))
        region_rc = None
        if rc == DC_NO_ERROR and hasattr(self.dll, "Net_ShowPlateRegion"):
            region_rc = int(self.dll.Net_ShowPlateRegion(int(handle), 0))
        play_window_rc = None
        if rc == DC_NO_ERROR and hwnd and hasattr(self.dll, "Net_AddPlayWindow"):
            # OcxConfig adds its display window after Net_StartVideo.  Keep
            # that ordering: some gate-camera firmware only begins painting
            # after the PlaySdk window is registered explicitly.
            play_window_rc = int(self.dll.Net_AddPlayWindow(int(handle), hwnd))
        draw_data_rc = None
        if rc == DC_NO_ERROR and hasattr(self.dll, "Net_SetDrawDataOut"):
            # ParkWatch registers its decoded-frame callback after the window
            # is attached. Make this the primary delivery lane. The callback
            # copies one DIB and the camera pump encodes only that new DIB;
            # it never asks the SDK for the same cached JPEG on every tick.
            draw_data_rc = self._register_draw_data(int(handle))
        if rc != DC_NO_ERROR:
            logging.getLogger("smartpark.hvx").warning("Video start failed: handle=%s stream=%s rc=%s", handle, used, rc)
        self._note_video(
            handle,
            control_operation="IDLE",
            control_error="",
            start_rc=rc,
            start_rc_name=describe_rc(rc),
            frame_delivery=("sdk_draw_data" if draw_data_rc == DC_NO_ERROR else "netsdk_jpg_buffer"),
            draw_data_primary=draw_data_rc == DC_NO_ERROR,
        )
        with self._lock:
            self._video_streams[int(handle)] = used
            if rc == DC_NO_ERROR:
                self._video_handles.add(int(handle))
                getattr(self, "_video_retry_handles", set()).discard(int(handle))
                getattr(self, "_video_retry_at", {}).pop(int(handle), None)
                self._live_requested_at[int(handle)] = time.monotonic()
                getattr(self, "_video_recovery_at", {}).pop(int(handle), None)
            else:
                self._video_handles.discard(int(handle))
                getattr(self, "_video_retry_handles", set()).add(int(handle))
                getattr(self, "_video_retry_at", {})[int(handle)] = time.monotonic() + 2.0
        # PlaySdk starts its receive/decode workers asynchronously.  Do not
        # call GetJpgBuffer in the same scheduling slice as Net_StartVideo;
        # several QY firmware versions throw a C++ exception during that
        # warm-up window even though the decoder recovers moments later.
        self._note_video(handle, jpeg_not_before=time.monotonic() + 0.35,
                        native_decoder_fault=False)
        # Keep a retry pump for a failed start, but never add that handle to
        # the active-video set until Net_StartVideo actually succeeds.
        self._ensure_camera_pump(int(handle))
        return {
            "ok": rc == DC_NO_ERROR,
            "rc": rc,
            "rc_name": describe_rc(rc),
            "stream_type": used,
            "hwnd": int(hwnd) if hwnd else 0,
            "plate_region_rc": region_rc,
            "draw_data_rc": draw_data_rc,
            "play_window_rc": play_window_rc,
        }

    def _capture_window_jpeg(self, handle: int) -> bytes:
        """Capture the PlaySdk-rendered HWND used by OcxConfig for live video.

        This is the compatibility path for a PlaySdk build where the direct
        latest-JPEG API is unavailable or temporarily faults. OcxConfig still
        opens PlaySdk into a real window, so this keeps a valid fallback while
        the primary recognition lane remains the bounded Net_GetJpgBuffer
        source.
        """
        hwnd = self._hwnds.get(int(handle))
        if not hwnd or os.name != "nt":
            return b""
        started = time.monotonic()
        user32 = gdi32 = None
        hdc = memdc = bitmap = old_bitmap = None
        try:
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32

            class RECT(ctypes.Structure):
                _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                            ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ("biSize", ctypes.c_uint32),
                    ("biWidth", ctypes.c_int32),
                    ("biHeight", ctypes.c_int32),
                    ("biPlanes", ctypes.c_uint16),
                    ("biBitCount", ctypes.c_uint16),
                    ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32),
                    ("biXPelsPerMeter", ctypes.c_int32),
                    ("biYPelsPerMeter", ctypes.c_int32),
                    ("biClrUsed", ctypes.c_uint32),
                    ("biClrImportant", ctypes.c_uint32),
                ]

            rect = RECT()
            if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
                raise OSError("GetClientRect failed")
            width = max(1, int(rect.right - rect.left))
            height = max(1, int(rect.bottom - rect.top))
            hdc = user32.GetDC(hwnd)
            if not hdc:
                raise OSError("GetDC failed")
            memdc = gdi32.CreateCompatibleDC(hdc)
            bitmap = gdi32.CreateCompatibleBitmap(hdc, width, height)
            if not memdc or not bitmap:
                raise OSError("CreateCompatibleBitmap failed")
            old_bitmap = gdi32.SelectObject(memdc, bitmap)

            # PW_RENDERFULLCONTENT is required by several PlaySdk builds;
            # BitBlt is a useful fallback for older Windows paint paths.
            painted = bool(user32.PrintWindow(hwnd, memdc, 2))
            if not painted:
                painted = bool(gdi32.BitBlt(memdc, 0, 0, width, height, hdc, 0, 0, 0x00CC0020 | 0x40000000))
            if not painted:
                raise OSError("PrintWindow/BitBlt failed")

            stride = ((width * 3 + 3) // 4) * 4
            pixels = (ctypes.c_ubyte * (stride * height))()
            info = BITMAPINFOHEADER(
                ctypes.sizeof(BITMAPINFOHEADER), width, -height, 1, 24, 0,
                stride * height, 0, 0, 0, 0,
            )
            rows = int(gdi32.GetDIBits(hdc, bitmap, 0, height, ctypes.byref(pixels), ctypes.byref(info), 0))
            if rows != height:
                raise OSError(f"GetDIBits returned {rows}/{height}")
            raw = bytes(pixels)
            if not any(raw):
                raise OSError("PlaySdk window is still black")

            from PIL import Image
            image = Image.frombytes("RGB", (width, height), raw, "raw", "BGR", stride, 1)
            max_width, quality = self._display_jpeg_options()
            source_width, source_height = image.size
            if max_width and image.width > max_width:
                output_height = max(1, round(image.height * max_width / image.width))
                image = image.resize((max_width, output_height), Image.Resampling.BILINEAR)
            output = BytesIO()
            image.save(output, format="JPEG", quality=quality, optimize=False)
            jpeg = output.getvalue()
            with self._lock:
                previous = getattr(self, "_window_last_jpeg", {}).get(int(handle), b"")
                changed = jpeg != previous
                getattr(self, "_window_last_jpeg", {})[int(handle)] = jpeg
                if changed:
                    window_seq = int(getattr(self, "_window_frame_seq", {}).get(int(handle), 0) or 0) + 1
                    getattr(self, "_window_frame_seq", {})[int(handle)] = window_seq
                    self._live_received_at[int(handle)] = time.monotonic()
                first_window_frame = not bool(self._video_diagnostics.get(int(handle), {}).get("window_capture_logged"))
                if changed:
                    condition = getattr(self, "_live_condition", None)
                    if condition is not None:
                        condition.notify_all()
            self._note_video(handle, capture_mode="play_sdk_hwnd", window_capture_rc=1,
                             window_capture_ms=round((time.monotonic() - started) * 1000, 1),
                             jpeg_error="", window_capture_logged=True,
                             window_duplicate=not changed,
                             window_capture_width=width, window_capture_height=height,
                             jpeg_source_width=source_width, jpeg_source_height=source_height,
                             jpeg_output_width=image.width, jpeg_output_height=image.height,
                             jpeg_quality=quality)
            self._note_video_read(handle, 0, len(jpeg), "", changed)
            if first_window_frame:
                logging.getLogger("smartpark.hvx").info(
                    "PlaySdk HWND live capture started: handle=%s size=%sx%s jpeg_bytes=%s",
                    handle, width, height, len(jpeg),
                )
            return jpeg
        except Exception as exc:
            self._note_video(handle, capture_mode="play_sdk_hwnd", window_capture_rc=0,
                             window_capture_error=str(exc),
                             window_capture_ms=round((time.monotonic() - started) * 1000, 1))
            self._note_video_read(handle, None, 0, type(exc).__name__, False)
            logging.getLogger("smartpark.hvx").warning(
                "PlaySdk window capture unavailable: handle=%s error=%s", handle, exc,
            )
            return b""
        finally:
            try:
                if old_bitmap and memdc and gdi32:
                    gdi32.SelectObject(memdc, old_bitmap)
                if bitmap and gdi32:
                    gdi32.DeleteObject(bitmap)
                if memdc and gdi32:
                    gdi32.DeleteDC(memdc)
                if hdc and user32:
                    user32.ReleaseDC(hwnd, hdc)
            except Exception:
                logging.getLogger("smartpark.hvx").debug("PlaySdk window capture cleanup failed", exc_info=True)

    def _ensure_ui_thread(self):
        """OcxConfig PlaySdk needs a thread that owns HWNDs and pumps messages."""
        with self._lock:
            if self._ui_thread and self._ui_thread.is_alive():
                return
            self._video_running = True
            self._ui_thread = threading.Thread(target=self._ui_loop, name="hvx-play-ui", daemon=True)
            self._ui_thread.start()

    def _latest_jpg_buffer(self, handle: int, on_frame=None) -> tuple[bytes, bool]:
        """Pull queued JPEGs and keep the newest.

        Returns ``(jpeg, backlog)``. ``backlog`` is true when the pull hit the
        batch cap, so the caller must drain again before sleeping. Stopping on
        an empty or repeated buffer avoids spinning when the SDK returns one
        cached snapshot.
        """
        latest = b""
        backlog = True
        for _ in range(8):
            jpeg = self._get_jpg_buffer(handle)
            if not jpeg or jpeg == latest:
                backlog = False
                break
            latest = jpeg
            if on_frame is not None:
                on_frame(jpeg)
        return latest, backlog

    def _on_draw_data(self, handle, hdd, bmi, data, width, height, user) -> None:
        """Copy the decoded PlaySdk bitmap without doing work in the SDK callback.

        The vendor callback supplies a Windows DIB.  The bitmap header tells us
        its orientation, bit depth and stride; copying that exact byte count is
        important because the callback buffer is owned by DecodeSdk and is only
        valid until this function returns.
        """
        handle = int(handle)
        width = int(width or 0)
        height_arg = int(height or 0)
        if width <= 0 or height_arg == 0 or not data:
            return
        height = abs(height_arg)
        bit_count = 24
        compression = 0
        bmi_height = height_arg
        image_size = 0
        try:
            if bmi:
                header = ctypes.string_at(bmi, 40)
                if len(header) >= 40:
                    _size, bmi_width, bmi_height, _planes, bit_count, compression, image_size, *_ = struct.unpack(
                        "<IiiHHIIiiII", header
                    )
                    width = abs(int(bmi_width or width))
                    height = abs(int(bmi_height or height))
        except Exception:
            # Some SDK builds pass a null/non-standard BITMAPINFO. The callback
            # dimensions remain sufficient for the common 24-bit DIB layout.
            bit_count = 24
            compression = 0
            bmi_height = height_arg
            image_size = 0
        if bit_count not in (24, 32) or compression not in (0, 3):
            self._note_video(handle, draw_data_error=f"unsupported bitmap {bit_count}bpp compression={compression}")
            return
        stride = ((width * bit_count + 31) // 32) * 4
        size = max(int(image_size or 0), stride * height)
        if size <= 0 or size > 32 * 1024 * 1024:
            self._note_video(handle, draw_data_error="invalid bitmap size")
            return
        try:
            raw = ctypes.string_at(data, size)
        except Exception as exc:
            self._note_video(handle, draw_data_error=type(exc).__name__)
            return
        if len(raw) < stride * height:
            self._note_video(handle, draw_data_error="short bitmap callback")
            return
        with self._lock:
            seq = int(self._draw_frame_seq.get(handle, 0)) + 1
            self._draw_frame_seq[handle] = seq
            self._draw_frames[handle] = (raw, width, height, bit_count, stride, -1 if int(bmi_height) > 0 else 1)
            diagnostics = getattr(self, "_video_diagnostics", {}).setdefault(handle, {})
            callback_now = time.monotonic()
            callback_first = float(diagnostics.get("callback_window_at") or callback_now)
            callback_count = int(diagnostics.get("callback_window_frames") or 0) + 1
            diagnostics.update(
                callback_last_at=callback_now,
                callback_frames=seq,
                callback_window_at=callback_first,
                callback_window_frames=callback_count,
                callback_fps=round(callback_count / max(callback_now - callback_first, 0.001), 1),
            )
        self._note_video(
            handle,
            capture_mode="sdk_draw_data",
            draw_data_frames=seq,
            draw_data_width=width,
            draw_data_height=height,
            draw_data_bpp=bit_count,
            draw_data_error="",
        )

    def _create_hidden_hwnd(self, handle: int):
        """Paint live video onto an HWND. One hidden popup per camera."""
        existing = self._hwnds.get(int(handle))
        if existing:
            return existing
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
        except Exception:
            return None
        # ctypes cannot marshal Python Unicode strings to untyped Win32 calls.
        # PlaySdk needs a real HWND even when its preview is hidden.
        kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
        kernel32.GetModuleHandleW.restype = ctypes.c_void_p
        user32.CreateWindowExW.argtypes = [
            ctypes.c_ulong, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_ulong,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ]
        user32.CreateWindowExW.restype = ctypes.c_void_p
        user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.DefWindowProcW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
        user32.DefWindowProcW.restype = ctypes.c_ssize_t
        if self._wndproc is None:
            WNDPROC = ctypes.WINFUNCTYPE(
                ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t
            )

            def _proc(hwnd, msg, wparam, lparam):
                if msg == 0x0002:
                    return 0
                return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

            self._wndproc = WNDPROC(_proc)

            class WNDCLASS(ctypes.Structure):
                _fields_ = [
                    ("style", ctypes.c_uint),
                    ("lpfnWndProc", WNDPROC),
                    ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int),
                    ("hInstance", ctypes.c_void_p),
                    ("hIcon", ctypes.c_void_p),
                    ("hCursor", ctypes.c_void_p),
                    ("hbrBackground", ctypes.c_void_p),
                    ("lpszMenuName", ctypes.c_wchar_p),
                    ("lpszClassName", ctypes.c_wchar_p),
                ]

            wc = WNDCLASS()
            wc.lpfnWndProc = self._wndproc
            wc.hInstance = kernel32.GetModuleHandleW(None)
            wc.lpszClassName = "SmartParkHVXVideo"
            if not user32.RegisterClassW(ctypes.byref(wc)):
                err = ctypes.get_last_error()
                if err not in (0, 1410):  # already registered
                    self._hwnds[int(handle)] = None
                    return None
            self._wndclass = wc
        user32.CreateWindowExW.restype = ctypes.c_void_p
        hwnd = user32.CreateWindowExW(
            0x80 | 0x00000008,  # WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
            "SmartParkHVXVideo",
            f"HVX {handle}",
            0x80000000 | 0x04000000,  # WS_POPUP | WS_CLIPSIBLINGS
            -32000, -32000, 1280, 720,
            None, None, kernel32.GetModuleHandleW(None), None,
        )
        if hwnd:
            # PlaySdk renders into this window. Keep it off-screen but shown:
            # several QY firmwares do not paint a SW_HIDE window, while
            # OcxConfig always gives PlaySdk a live child window.
            user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
            if hasattr(user32, "UpdateWindow"):
                user32.UpdateWindow.argtypes = [ctypes.c_void_p]
                user32.UpdateWindow.restype = ctypes.c_int
                user32.UpdateWindow(hwnd)
        self._hwnds[int(handle)] = hwnd or None
        return hwnd or None
