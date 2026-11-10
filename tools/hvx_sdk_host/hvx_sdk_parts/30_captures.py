from __future__ import annotations

class _HVXCaptureMixin:
    def last_captures(self):
        with self._lock:
            return {str(handle): dict(row) for handle, row in self._last_capture.items()}

    def _event_image(self, handle, image_id, capture_token, index):
        with self._lock:
            if capture_token is not None:
                record = self._event_media.get((int(handle), str(capture_token)))
                return record[index] if record else b""
            if image_id is not None:
                # Compatibility for old clients: ambiguous IDs must fail closed.
                records = [value for (camera, _), value in self._event_media.items()
                           if camera == int(handle) and value[0] == int(image_id)]
                return records[0][index] if len(records) == 1 else b""
            # A missing identity must fail closed.  Returning the latest car
            # image here can bind one callback's plate to another callback's
            # media, especially because QY uses image_id=0 for realtime reads.
            return b""

    def jpeg_for(self, handle: int) -> bytes:
        """Live video frame from Net_GetJpgBuffer only. Never the last car still."""
        with self._lock:
            received_at = self._live_received_at.get(int(handle), 0.0)
            if time.monotonic() - received_at > 5.0:
                return b""
            live = self._last_live_jpeg.get(int(handle), b"")
            return live if live[:2] == b"\xff\xd8" else b""

    def snapshot_trigger(self, handle: int):
        snap = T_DCImageSnap()
        snap.uiImageId = 0
        snap.ucLightIndex = 0
        snap.ucLightMode = 0
        snap.usGroupId = 0
        return self.dll.Net_ImageSnap(handle, ctypes.byref(snap))

    def live_jpeg_for(self, handle: int) -> bytes:
        # Compatibility API for callers that need an immediate snapshot.
        return self.live_frame_for(handle)[0]

    def live_frame_for(self, handle: int, *, after_seq: int = 0, wait_ms: int = 0) -> tuple[bytes, int]:
        """Return the newest live JPEG, optionally waiting for a newer source frame.

        ``Net_StartVideo``/PlaySdk owns the decoder and this method only
        exposes its one-item latest cache. Waiting on the source sequence is
        important: returning the same cached response at 15--20 requests per
        second lets a downstream Windows reader accumulate old HTTP responses
        even though the native decoder itself is latest-only.
        """
        handle = int(handle)
        after = max(0, int(after_seq or 0))
        timeout = max(0.0, min(int(wait_ms or 0), 1500)) / 1000.0
        deadline = time.monotonic() + timeout
        condition = getattr(self, "_live_condition", None)
        with self._lock:
            self._live_requested_at[handle] = time.monotonic()
            diagnostics = getattr(self, "_video_diagnostics", {}).setdefault(handle, {})
            diagnostics["consumer_demand_at"] = self._live_requested_at[handle]
            while condition is not None:
                current = max(
                    int(getattr(self, "_live_frame_seq", {}).get(handle, 0) or 0),
                    int(getattr(self, "_window_frame_seq", {}).get(handle, 0) or 0),
                )
                if current > after or timeout <= 0:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                condition.wait(timeout=remaining)
            seq = max(
                int(getattr(self, "_live_frame_seq", {}).get(handle, 0) or 0),
                int(getattr(self, "_window_frame_seq", {}).get(handle, 0) or 0),
            )
            received_at = self._live_received_at.get(handle, 0.0)
            jpeg = self._last_live_jpeg.get(handle, b"")
            if time.monotonic() - received_at > 5.0 or jpeg[:2] != b"\xff\xd8":
                return b"", seq
            if after and seq <= after:
                return b"", seq
            return jpeg, seq

    def event_crop_for(self, handle: int, image_id: int | None = None, *, capture_token=None) -> bytes:
        return self._event_image(handle, image_id, capture_token, 2)

    def drain_events(self, handle: int) -> list[dict]:
        self._refresh_recognition(handle)
        with self._lock:
            queue = self._pending_events.get(int(handle))
            if not queue:
                return []
            items = list(queue)
            queue.clear()
            return items

    def _refresh_recognition(self, handle: int, observed_state=None) -> dict:
        """Re-arm existing callbacks after an observed SDK reconnect.

        Called by background event polling, never by the JPEG pump. SDK ABI,
        login, video and gate operations stay on their existing paths.
        """
        handle = int(handle)
        with self._lock:
            session = self._recognition_sessions.get(handle)
        if session is None:
            return {"ready": False, "reason": "no active SDK session"}
        with session["lock"]:
            now = time.monotonic()
            if session["closed"]:
                return {"ready": False, "reason": "SDK session closed"}
            if observed_state is not None or now >= session["next_check"]:
                session["next_check"] = now + 1.0
                try:
                    state = int(observed_state if observed_state is not None
                                else self.dll.Net_QueryConnState(handle))
                    previous = session["state"]
                    session["state"] = state
                    connected = is_connected_state(state)
                    previous_connected = is_connected_state(previous)
                    if state in {CONN_STATE_DIS, CONN_STATE_TRYING}:
                        session["pending"] = True
                    if connected and not previous_connected and previous in {CONN_STATE_DIS, CONN_STATE_TRYING}:
                        session["pending"] = True
                        session["retry_at"] = 0.0
                    if connected and session["pending"] and now >= session["retry_at"]:
                        # Keep the same ctypes callback objects alive across re-registration.
                        self._register_report(handle)
                        rc = self._register_image(handle)
                        session["image_recv_rc"] = rc
                        session["pending"] = rc != DC_NO_ERROR
                        session["last_error"] = "" if rc == DC_NO_ERROR else describe_rc(rc)
                        if rc == DC_NO_ERROR:
                            session["rearms"] += 1
                            session["backoff"] = 1.0
                        else:
                            session["retry_at"] = now + session["backoff"]
                            session["backoff"] = min(8.0, session["backoff"] * 2)
                except Exception as exc:
                    session["pending"] = True
                    session["last_error"] = type(exc).__name__
                    session["retry_at"] = now + session["backoff"]
                    session["next_check"] = session["retry_at"]
                    session["backoff"] = min(8.0, session["backoff"] * 2)
            return {
                "ready": is_connected_state(session["state"]) and not session["pending"],
                "image_recv_rc": session["image_recv_rc"],
                "rearms": session["rearms"],
                "retry_pending": session["pending"],
                "last_error": session["last_error"],
            }

    def drain_reports(self, handle: int) -> list[dict]:
        with self._lock:
            queue = self._pending_reports.get(int(handle))
            if not queue:
                return []
            items = list(queue)
            queue.clear()
            return items

    def event_jpeg_for(self, handle: int, image_id: int | None = None, *, capture_token=None) -> bytes:
        return self._event_image(handle, image_id, capture_token, 1)
