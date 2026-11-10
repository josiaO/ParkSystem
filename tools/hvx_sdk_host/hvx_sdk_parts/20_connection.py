from __future__ import annotations

class _HVXConnectionMixin:
    def video_detect_config(self, handle: int) -> dict:
        with self._lock:
            return dict(self._video_detect_configs.get(int(handle)) or {})

    def selected_stream_type(self, handle: int) -> int:
        with self._lock:
            row = dict(getattr(self, "_function_lists", {}).get(int(handle)) or {})
        return int(row.get("stream_type") or 0)

    def state(self, handle: int):
        state = int(self.dll.Net_QueryConnState(handle))
        with self._lock:
            capture = dict(self._last_capture.get(int(handle)) or {})
            # Lightweight test/compatibility hosts may be constructed without
            # running __init__.  Treat the optional diagnostic map as empty;
            # health reporting must not fail just because that map has not
            # been initialized yet.
            video_detect = dict(getattr(self, "_video_detect_configs", {}).get(int(handle)) or {})
        recognition = self._refresh_recognition(handle, observed_state=state)
        return {"state": state, "name": describe_state(state), "last_capture": capture or None,
                "recognition": recognition, "video": self.video_status(handle),
                "video_detect": video_detect or None}

    def connection_sessions(self) -> list[dict]:
        with self._lock:
            rows = [{"handle": handle, "ip": session["ip"], "state": session["state"]}
                    for handle, session in self._recognition_sessions.items() if session.get("ip")]
        return [{**row, "video": self.video_status(row["handle"])} for row in rows]

    def __init__(self, vendor_dir: Path):
        if os.name != "nt":
            raise HVXSDKError("HVX NetSDK is Windows-only")
        if struct.calcsize("P") * 8 != 32:
            raise HVXSDKError("NetSDK.dll is x86. Start this host with 32-bit Python.")
        self.vendor_dir = vendor_dir
        dll = vendor_dir / "NetSDK.dll"
        if not dll.exists():
            raise HVXSDKError(f"Missing {dll}")
        os.add_dll_directory(str(vendor_dir))
        os.environ["PATH"] = str(vendor_dir) + os.pathsep + os.environ.get("PATH", "")
        self.dll = ctypes.WinDLL(str(dll))  # stdcall
        self._report_cbs = {}
        self._image_cbs = {}
        self._recognition_sessions = {}
        self._connection_locks = {}
        self._connection_results = {}
        self._last_capture = {}
        self._last_live_jpeg = {}
        self._live_received_at = {}
        self._live_frame_seq = {}
        self._live_requested_at = {}
        self._video_streams = {}
        self._function_lists = {}
        self._video_detect_configs = {}
        self._video_locks = {}
        self._video_diagnostics = {}
        self._video_recovery_at = {}
        self._video_recovery_inflight = set()
        self._last_event_jpeg = {}
        self._last_event_crop = {}
        self._pending_events = {}
        self._pending_reports = {}
        self._gpio_state = {}
        self._event_media = {}
        self._hwnds = {}
        # Keep the decoded-bitmap callback alive for the lifetime of the
        # camera. ParkWatch's PlaySdk path owns a continuous decoder and
        # exports decoded frames through a callback; polling a cached JPEG is
        # only a compatibility path for DLL builds that cannot register this
        # callback.
        self._draw_callbacks = {}
        self._draw_frames = {}
        self._draw_frame_seq = {}
        self._draw_encoded_seq = {}
        self._window_frame_seq = {}
        self._window_last_jpeg = {}
        self._native_jpeg_disabled_until = {}
        self._video_handles = set()
        # A failed PlaySdk start must not be reported as a live decoder, but
        # the connection watcher still needs a bounded retry path.  Keep the
        # two lifecycles separate so a dead video lane cannot look healthy or
        # cause a second SDK connection to be opened for the same camera.
        self._video_retry_handles = set()
        self._video_retry_at = {}
        self._video_threads = {}
        self._video_thread = None
        self._video_running = False
        self._ui_thread = None
        self._hwnd_queue = queue.Queue()
        self._ui_commands = queue.Queue(maxsize=8)
        # A timed-out HWND command remains in the queue until the owner thread
        # reaches it. Reject new controls briefly so a wedged PlaySdk decoder
        # cannot accumulate recovery commands and starve both camera lanes.
        self._ui_control_not_before = 0.0
        self._ui_submit_lock = threading.Lock()
        self._hwnd_ready = {}
        self._wndproc = None
        self._wndclass = None
        self._lock = threading.Lock()
        # The HTTP bridge is a latest-frame transport, not a request-per-frame
        # FIFO. A reader can wait for a source sequence newer than the one it
        # already displayed; this prevents Windows keep-alive timing from
        # turning repeated reads of the cached JPEG into visible stacking.
        self._live_condition = threading.Condition(self._lock)
        self._bind()
        rc = self.dll.Net_Init()
        if rc != DC_NO_ERROR:
            raise HVXSDKError(f"Net_Init failed rc={rc} ({describe_rc(rc)})")
        self.initialized = True

    @classmethod
    def _line_dict(cls, line: T_Line) -> dict[str, dict[str, int]]:
        return {
            "start": cls._point_dict(line.tStartPoint),
            "end": cls._point_dict(line.tEndPoint),
        }

    @staticmethod
    def _point_dict(point: T_Point) -> dict[str, int]:
        return {"x": int(point.sX), "y": int(point.sY)}

    def _register_image(self, handle: int) -> int:
        cb = self._image_cbs.get(handle)
        if cb is None:
            cb = self._FGetImageCbEx(self._on_image)
        self._image_cbs[handle] = cb
        # Ex2 is the callback used by the supplied OcxConfig build. Register
        # exactly one callback variant: registering Ex and then Ex2 can make
        # some firmware deliver every image twice, doubling queue pressure and
        # causing duplicate parking events. Fall back only when Ex2 is absent
        # or rejected by the DLL.
        if hasattr(self.dll, "Net_RegImageRecvEx2"):
            rc = int(self.dll.Net_RegImageRecvEx2(handle, cb, None))
            if rc != DC_NO_ERROR:
                rc = int(self.dll.Net_RegImageRecvEx(handle, cb, None))
        else:
            rc = int(self.dll.Net_RegImageRecvEx(handle, cb, None))
        return rc

    def query_video_detect(self, handle: int) -> dict:
        """Read OcxConfig's plate zone and trigger lines without changing them."""
        result = {
            "ok": False,
            "available": hasattr(self.dll, "Net_QueryVideoDetectSetup"),
            "rc": None,
            "plate_region": [],
            "stop_line": None,
            "capture_mode": None,
            "plate_width_flag": None,
            "min_score": None,
            "camera_height_cm": None,
            "road_length_cm": None,
            "road_width_cm": None,
            "total_distance_cm": None,
        }
        if not result["available"]:
            result["error"] = "Net_QueryVideoDetectSetup not exported"
        else:
            setup = T_VideoDetectParamSetup()
            try:
                rc = int(self.dll.Net_QueryVideoDetectSetup(int(handle), ctypes.byref(setup)))
                result.update({
                    "ok": rc == DC_NO_ERROR,
                    "rc": rc,
                    "plate_region": [self._point_dict(point) for point in setup.atPlateRegion],
                    "stop_line": self._line_dict(setup.aStopLine),
                    "capture_mode": int(setup.ucCpMode),
                    "plate_width_flag": int(setup.ucWidthFlag),
                    "min_score": int(setup.ucMinScore),
                    "lanes": int(setup.ucLanes),
                    "camera_height_cm": int(setup.usCameraHeight),
                    "road_length_cm": int(setup.usRectLength),
                    "road_width_cm": int(setup.usRectWidth),
                    "total_distance_cm": int(setup.usTotalDis),
                })
                if rc != DC_NO_ERROR:
                    result["error"] = describe_rc(rc)
            except Exception as exc:
                result["error"] = str(exc)

        # The vehicle-function query supplies the native plate-width window
        # that the camera is actually using.  It is optional across firmware
        # revisions, so failure here does not invalidate the zone query.
        if hasattr(self.dll, "Net_QueryVehicleVAFunSetup"):
            va = T_VehicleVAFunSetup()
            try:
                va_rc = int(self.dll.Net_QueryVehicleVAFunSetup(int(handle), ctypes.byref(va)))
                result["vehicle_config_rc"] = va_rc
                if va_rc == DC_NO_ERROR:
                    result["native_min_plate_width"] = int(va.usMinPlateW)
                    result["native_max_plate_width"] = int(va.usMaxPlateW)
                    result["capture_interval"] = int(va.ucCpTimeInterval)
                    result["vehicle_interval"] = int(va.ucVehicleInterval)
                    result["region_overlay_enabled"] = bool(va.ucRecRegShowEn)
            except Exception as exc:
                result["vehicle_config_error"] = str(exc)

        with self._lock:
            self._video_detect_configs[int(handle)] = dict(result)
        return result

    def _on_image(self, handle, image_id, pt_info, pt_pic, user):
        plate = ""
        score = None
        box = None
        jpeg = b""
        crop = b""
        width = 0
        height = 0
        have_vehicle = False
        snap_type = None
        if pt_info:
            parsed = {}
            try:
                address = ctypes.cast(pt_info, ctypes.c_void_p).value
                if address:
                    parsed = parse_image_user_info(ctypes.string_at(address, IMAGE_USER_INFO_BYTES))
            except Exception:
                parsed = {}
            if not parsed:
                info = pt_info.contents
                parsed = {
                    "plate_raw": bytes(info.szLprResult),
                    "plate_box": [int(info.usLpBox[i]) for i in range(4)],
                    "image_width": int(info.usWidth),
                    "image_height": int(info.usHeight),
                    "score": int(info.ucScore),
                    "have_vehicle": bool(int(info.ucHaveVehicle)),
                    "snap_type": int(info.ucSnapType),
                    "camera_timestamp": bytes(info.acSnapTime).split(b"\x00", 1)[0].decode("ascii", "ignore"),
                    "vehicle_id": int(info.uiVehicleId),
                    "snapshot_index": int(info.ucSnapshotIndex),
                }
            plate = _decode_plate(parsed.get("plate_raw") or b"")
            score = parsed.get("score")
            box = parsed.get("plate_box")
            width = int(parsed.get("image_width") or 0)
            height = int(parsed.get("image_height") or 0)
            have_vehicle = bool(parsed.get("have_vehicle")) or plate_box_usable(box)
            snap_type = parsed.get("snap_type")
        if pt_pic:
            pic = pt_pic.contents
            jpeg = self._copy_buffer(pic.ptPanoramaPicBuff, int(pic.uiPanoramaPicLen or 0))
            crop = self._copy_buffer(pic.ptVehiclePicBuff, int(pic.uiVehiclePicLen or 0))
            if not jpeg and crop[:2] == b"\xff\xd8":
                jpeg = crop
            if plate_box_usable(box) and (width <= 0 or height <= 0):
                width, height = jpeg_pixel_size(jpeg)
        row = {
            "image_id": int(image_id),
            "capture_token": uuid.uuid4().hex,
            "captured_at_epoch": time.time(),
            "plate": plate or None,
            "score": score,
            "plate_box": box,
            "image_width": width,
            "image_height": height,
            "jpeg_bytes": len(jpeg),
            "crop_bytes": len(crop),
            "have_vehicle": have_vehicle,
            "snap_type": snap_type,
            "camera_timestamp": parsed.get("camera_timestamp", "") if pt_info else "",
            "vehicle_id": int(parsed.get("vehicle_id") or 0) if pt_info else 0,
            "snapshot_index": int(parsed.get("snapshot_index") or 0) if pt_info else 0,
        }
        key = int(handle)
        with self._lock:
            video_detect = dict(getattr(self, "_video_detect_configs", {}).get(key) or {})
            if video_detect:
                # Keep the camera's native geometry with the transient event.
                # The server can use it for diagnostics and evidence audit,
                # while the native callback remains the only capture trigger.
                row["plate_region"] = video_detect.get("plate_region") or []
                row["stop_line"] = video_detect.get("stop_line")
                row["capture_mode"] = video_detect.get("capture_mode")
                row["native_min_plate_width"] = video_detect.get("native_min_plate_width")
                row["native_max_plate_width"] = video_detect.get("native_max_plate_width")
            # Every callback owns its geometry; a matching plate string
            # does not mean the car stayed in the same pixel position.
            self._last_capture[key] = row
            if jpeg[:2] == b"\xff\xd8":
                self._last_event_jpeg[key] = jpeg
            if crop[:2] == b"\xff\xd8":
                self._last_event_crop[key] = crop
            queue = self._pending_events.setdefault(key, deque(maxlen=64))
            queue.append(dict(row))
            # Vendor ID 0 is a realtime result type, not a unique image.
            self._event_media[(key, row["capture_token"])] = (int(image_id), jpeg, crop)
            media_bytes = sum(len(item[1]) + len(item[2]) for item in self._event_media.values())
            while len(self._event_media) > 128 or media_bytes > EVENT_MEDIA_MAX_BYTES:
                removed = self._event_media.pop(next(iter(self._event_media)))
                media_bytes -= len(removed[1]) + len(removed[2])
        return 0

    def _on_report(self, handle, msg_type, message, user):
        row = {"msg_type": int(msg_type), "at": time.time()}
        key = int(handle)
        if int(msg_type) == REPORT_LPRINFO_EXT and message:
            self._note_plate_report(key, message)
        with self._lock:
            queue = self._pending_reports.setdefault(key, deque(maxlen=64))
            queue.append(dict(row))
        return 0

    def _note_plate_report(self, handle: int, message) -> None:
        """REPORT_LPRINFO_EXT carries usLpBox at the same +0x18 offset, without a JPEG."""
        try:
            blob = ctypes.string_at(message, 0x20)
        except Exception:
            return
        parsed = parse_image_user_info(blob)
        box = parsed.get("plate_box")
        plate = _decode_plate(parsed.get("plate_raw") or b"")
        if not plate_box_usable(box) and not plate:
            return
        with self._lock:
            pending = self._pending_events.setdefault(handle, deque(maxlen=64))
            # A report containing only geometry is an enrichment for an image
            # callback already in the queue. It is not a new vehicle event.
            # Reusing ``previous.plate`` here made an empty-lane report create
            # another capture with the last car's plate.
            if not plate:
                if pending and not plate_box_usable(pending[-1].get("plate_box")):
                    pending[-1]["plate_box"] = list(box) if plate_box_usable(box) else pending[-1].get("plate_box")
                    pending[-1]["have_vehicle"] = bool(plate_box_usable(box))
                # A geometry-only report enriches the pending image callback;
                # it is not a new capture. Never refresh last_capture with the
                # previous car's plate and a new timestamp.
                return
            # A plate report has no image identity. It may enrich the newest
            # image callback, but it must never manufacture an event from
            # ``previous``: that reuses the last car's JPEG/crop and makes a
            # stale vehicle appear to be captured again when the lane is empty
            # or another vehicle is passing.
            if not pending:
                return
            target = pending[-1]
            if target.get("plate"):
                return
            target["plate"] = plate
            target["have_vehicle"] = True if plate_box_usable(box) else bool(target.get("have_vehicle"))
            if plate_box_usable(box):
                target["plate_box"] = list(box)
            self._last_capture[handle] = dict(target)
            return

    def close(self):
        with self._lock:
            # A failed start is still a live SDK session that may have a
            # retry task and a partially-created PlaySdk state. Close both
            # active and retrying handles before unloading NetSDK.
            handles = sorted(set(self._video_handles) | set(getattr(self, "_video_retry_handles", set())))
        stopped = True
        for handle in handles:
            try:
                if self.stop_video(handle) != DC_NO_ERROR:
                    stopped = False
            except Exception:
                stopped = False
                logging.getLogger("smartpark.hvx").exception("Video shutdown failed: handle=%s", handle)
        self._video_running = False
        # Do not unload NetSDK while a per-camera pump can still be inside
        # Net_GetJpgBuffer. A bounded join keeps shutdown safe without hanging
        # forever on a vendor DLL that ignores cancellation.
        threads = list(getattr(self, "_video_threads", {}).values())
        for thread in threads:
            if thread is not threading.current_thread():
                thread.join(1.5)
        ui_thread = getattr(self, "_ui_thread", None)
        if ui_thread is not None and ui_thread is not threading.current_thread():
            ui_thread.join(1.5)
        pumps_stopped = not any(thread.is_alive() for thread in threads)
        if stopped and pumps_stopped and getattr(self, "initialized", False):
            self.dll.Net_UNinit()
            self.initialized = False

    def _register_report(self, handle: int) -> int:
        cb = self._report_cbs.get(handle)
        if cb is None:
            cb = self._FGetReportCBEx(self._on_report)
        self._report_cbs[handle] = cb
        return int(self.dll.Net_RegReportMessEx(handle, cb, None))

    def _add_and_connect(self, ip: str, port: int, timeout: int, username: str, password: str):
        steps = []
        handle = self.dll.Net_AddCamera(ip.encode("ascii"))
        steps.append({"api": "Net_AddCamera", "handle": int(handle)})
        if handle == HANDLE_INVALID:
            return {
                "connected": False,
                "handle": handle,
                "error": "Net_AddCamera returned -1",
                "steps": steps,
            }

        report_rc = self._register_report(handle)
        steps.append({"api": "Net_RegReportMessEx", "rc": report_rc, "name": describe_rc(report_rc)})

        timeout_s = max(1, min(int(timeout or 3), 65535))
        port_s = int(port or 30000)
        user = (username or "").encode("utf-8")
        password_b = (password or "").encode("utf-8")

        # Try ConnCameraEx first because we have credentials, then fall back
        # to ConnCamera (no user/pass) if Ex fails.
        used = "Net_ConnCameraEx"
        rc = int(self.dll.Net_ConnCameraEx(handle, port_s, timeout_s, user, password_b))
        steps.append({"api": used, "rc": rc, "name": describe_rc(rc), "port": port_s, "timeout_seconds": timeout_s})
        if rc != DC_NO_ERROR:
            used = "Net_ConnCamera"
            rc = int(self.dll.Net_ConnCamera(handle, port_s, timeout_s))
            steps.append({"api": used, "rc": rc, "name": describe_rc(rc), "port": port_s, "timeout_seconds": timeout_s})

        time.sleep(0.25)
        state = int(self.dll.Net_QueryConnState(handle))
        steps.append({"api": "Net_QueryConnState", "state": state, "name": describe_state(state)})
        # QueryConnState returns 0 for connected in the supplied NetSDK build;
        # the return code is authoritative while this state is retained for
        # diagnostics and reconnect monitoring.
        connected = rc == DC_NO_ERROR

        offline_rc = None
        image_rc = None
        snap_rc = None
        function_list = self.query_function_list(handle) if connected else {
            "ok": False, "rc": None, "flags": 0, "stream_type": 0,
            "available": False, "error": "camera connection failed",
        }
        selected_stream = int(function_list.get("stream_type") or 0)
        if connected:
            steps.append({
                "api": "Net_FuntionListRsp",
                "rc": function_list.get("rc"),
                "name": describe_rc(function_list.get("rc") if function_list.get("rc") is not None else -1),
                "flags": function_list.get("flags", 0),
                "stream_type": selected_stream,
            })
        if connected:
            offline_rc = int(self.dll.Net_RegOffLineClient(handle))
            steps.append({"api": "Net_RegOffLineClient", "rc": offline_rc, "name": describe_rc(offline_rc)})
            # Read the same recognition polygon/trigger-line configuration
            # exposed by OcxConfig.  This is deliberately before video start
            # and query-only, so it cannot reconfigure a working camera or add
            # a per-frame control request to the hot path.
            video_detect = self.query_video_detect(handle)
            steps.append({
                "api": "Net_QueryVideoDetectSetup",
                "rc": video_detect.get("rc"),
                "name": describe_rc(video_detect.get("rc") if video_detect.get("rc") is not None else -1),
                "plate_region": video_detect.get("plate_region", []),
                "stop_line": video_detect.get("stop_line"),
                "capture_mode": video_detect.get("capture_mode"),
                "native_min_plate_width": video_detect.get("native_min_plate_width"),
                "native_max_plate_width": video_detect.get("native_max_plate_width"),
            })
            # OcxConfig starts PlaySdk after selecting the function-list stream
            # and only then registers Ex2 for native plate callbacks.  Keeping
            # this order matters on firmware that shares the decoder/control
            # session between live video and recognition.
            try:
                video = self.start_video(handle, selected_stream)
            except HVXSDKError as exc:
                video = {"ok": False, "error": str(exc)}
                logging.getLogger("smartpark.hvx").warning("Video setup unavailable: handle=%s error=%s", handle, exc)
            steps.append({"api": "Net_StartVideo", **{k: v for k, v in video.items() if k != "hwnd"}})
            image_rc = self._register_image(handle)
            steps.append({"api": "Net_RegImageRecvEx2", "rc": image_rc, "name": describe_rc(image_rc)})
            with self._lock:
                self._recognition_sessions[int(handle)] = {
                    "ip": ip,
                    "lock": threading.Lock(), "closed": False, "state": state,
                    "pending": image_rc != DC_NO_ERROR, "image_recv_rc": image_rc,
                    "next_check": 0.0, "retry_at": 0.0, "backoff": 1.0,
                    "rearms": 0, "last_error": "",
                }
            if video.get("ok"):
                snap_rc = int(self.snapshot_trigger(handle))
                steps.append({"api": "Net_ImageSnap", "rc": snap_rc, "name": describe_rc(snap_rc)})

        return {
            "connected": connected,
            "handle": handle,
            "connect_rc": rc,
            "connect_rc_name": describe_rc(rc),
            "connect_api": used,
            "query_state": state,
            "query_state_name": describe_state(state),
            "report_rc": report_rc,
            "function_list": {
                key: value for key, value in function_list.items() if key != "raw"
            },
            "selected_stream": selected_stream,
            "image_recv_rc": image_rc,
            "offline_rc": offline_rc,
            "image_snap_rc": snap_rc,
            "steps": steps,
        }

    def _copy_buffer(self, ptr, length: int) -> bytes:
        if not ptr or length <= 0:
            return b""
        length = min(int(length), 8_000_000)
        try:
            return ctypes.string_at(ptr, length)
        except Exception:
            return b""

    def discover(self, wait_seconds: float = 2.0):
        """Net_FindDeviceIp. Needs WinPcap on the Windows PC. Empty is not a failure of TCP reachability."""
        found: list[str] = []
        if not hasattr(self.dll, "Net_FindDeviceIp"):
            return {"ok": False, "ips": [], "error": "Net_FindDeviceIp not exported", "note": "Use TCP probe of port 30000"}

        def on_ip(ip, user):
            text = ""
            if ip:
                text = ip.decode("ascii", "ignore") if isinstance(ip, bytes) else str(ip)
            text = text.strip()
            if text and text not in found:
                found.append(text)

        cb = self._FindIpCB(on_ip)
        self._discover_cb = cb
        try:
            rc = int(self.dll.Net_FindDeviceIp(cb, None))
        except Exception as exc:
            return {"ok": False, "ips": [], "error": str(exc), "note": "WinPcap may be missing"}
        time.sleep(max(0.5, float(wait_seconds)))
        return {
            "ok": rc == DC_NO_ERROR,
            "rc": rc,
            "rc_name": describe_rc(rc),
            "ips": list(found),
            "note": "Vendor LAN search. Requires WinPcap. TCP port 30000 is the reliable fallback.",
        }

    def add_and_connect(self, ip: str, port: int, timeout: int, username: str, password: str):
        with self._lock:
            connection_lock = self._connection_locks.setdefault(ip, threading.RLock())
        signature = hashlib.sha256(repr((port, username, password)).encode()).digest()
        with connection_lock:
            previous = self._connection_results.get(ip)
            if previous is not None:
                try:
                    state = int(self.dll.Net_QueryConnState(previous["result"]["handle"]))
                    if previous["signature"] == signature and state in {
                        *CONN_STATE_CONNECTED_VALUES, CONN_STATE_TRYING,
                    }:
                        return {**previous["result"], "reused": True}
                except Exception:
                    pass
                self.disconnect(int(previous["result"]["handle"]), force=True)
            result = self._add_and_connect(ip, port, timeout, username, password)
            video_step = next(
                (row for row in result.get("steps", []) if row.get("api") == "Net_StartVideo"),
                {},
            )
            logging.getLogger("smartpark.hvx").info(
                "Camera connection: ip=%s handle=%s connected=%s rc=%s stream=%s "
                "video_start_rc=%s image_recv_rc=%s",
                ip,
                result.get("handle"),
                result.get("connected"),
                result.get("connect_rc"),
                result.get("selected_stream"),
                video_step.get("rc"),
                result.get("image_recv_rc"),
            )
            if result.get("connected"):
                self._connection_results[ip] = {"signature": signature, "result": dict(result)}
            return result

    def query_function_list(self, handle: int) -> dict:
        """Read the same stream capability record that OcxConfig reads.

        ``Net_FuntionListRsp`` is a query, not a configuration write.  The
        returned buffer is intentionally retained only as parsed diagnostics;
        credentials and image data never enter it.
        """
        dll = self.dll
        result = {
            "ok": False,
            "available": hasattr(dll, "Net_FuntionListRsp"),
            "rc": None,
            "flags": 0,
            "stream_type": 0,
        }
        if not result["available"]:
            result["error"] = "Net_FuntionListRsp not exported"
            with self._lock:
                getattr(self, "_function_lists", {}).setdefault(int(handle), {}).update(result)
            return result

        buffer = ctypes.create_string_buffer(FUNCTION_LIST_BYTES)
        try:
            rc = int(dll.Net_FuntionListRsp(int(handle), ctypes.cast(buffer, ctypes.c_void_p)))
        except Exception as exc:
            result["error"] = str(exc)
            with self._lock:
                getattr(self, "_function_lists", {}).setdefault(int(handle), {}).update(result)
            return result

        raw = bytes(buffer)
        result.update({
            "ok": rc == DC_NO_ERROR,
            "rc": rc,
            "flags": function_list_flags(raw),
            "stream_type": stream_type_from_function_list(raw) if rc == DC_NO_ERROR else 0,
            "valid": bool(raw[:1] and raw[0]),
        })
        if rc != DC_NO_ERROR:
            result["error"] = describe_rc(rc)
        with self._lock:
            getattr(self, "_function_lists", {}).setdefault(int(handle), {}).update(result)
        return result

    def _bind(self):
        c_int = ctypes.c_int
        c_ushort = ctypes.c_ushort
        c_char_p = ctypes.c_char_p
        c_void_p = ctypes.c_void_p

        # Official: Net_ConnCamera(DCHANDLE, unsigned short usPort, unsigned short usTimeout)
        # Timeout is seconds. usPort 0 => 30000.
        self.dll.Net_Init.argtypes = []
        self.dll.Net_Init.restype = c_int
        self.dll.Net_UNinit.argtypes = []
        self.dll.Net_UNinit.restype = c_int
        self.dll.Net_AddCamera.argtypes = [c_char_p]
        self.dll.Net_AddCamera.restype = c_int
        self.dll.Net_DelCamera.argtypes = [c_int]
        self.dll.Net_DelCamera.restype = c_int
        self.dll.Net_ConnCamera.argtypes = [c_int, c_ushort, c_ushort]
        self.dll.Net_ConnCamera.restype = c_int
        self.dll.Net_ConnCameraEx.argtypes = [c_int, c_ushort, c_ushort, c_char_p, c_char_p]
        self.dll.Net_ConnCameraEx.restype = c_int
        self.dll.Net_DisConnCamera.argtypes = [c_int]
        self.dll.Net_DisConnCamera.restype = c_int
        self.dll.Net_QueryConnState.argtypes = [c_int]
        self.dll.Net_QueryConnState.restype = c_int
        # Exported by the supplied QY NetSDK build.  The misspelling in the
        # vendor symbol (Funtion) is part of its ABI and is intentional.
        if hasattr(self.dll, "Net_FuntionListRsp"):
            self.dll.Net_FuntionListRsp.argtypes = [c_int, c_void_p]
            self.dll.Net_FuntionListRsp.restype = c_int
        if hasattr(self.dll, "Net_QueryVideoDetectSetup"):
            self.dll.Net_QueryVideoDetectSetup.argtypes = [c_int, ctypes.POINTER(T_VideoDetectParamSetup)]
            self.dll.Net_QueryVideoDetectSetup.restype = c_int
        if hasattr(self.dll, "Net_QueryVehicleVAFunSetup"):
            self.dll.Net_QueryVehicleVAFunSetup.argtypes = [c_int, ctypes.POINTER(T_VehicleVAFunSetup)]
            self.dll.Net_QueryVehicleVAFunSetup.restype = c_int
        self.dll.Net_ImageSnap.argtypes = [c_int, ctypes.POINTER(T_DCImageSnap)]
        self.dll.Net_ImageSnap.restype = c_int
        self.dll.Net_RegOffLineClient.argtypes = [c_int]
        self.dll.Net_RegOffLineClient.restype = c_int
        if hasattr(self.dll, "Net_WriteGPIOState"):
            self.dll.Net_WriteGPIOState.argtypes = [c_int, ctypes.c_ubyte, ctypes.c_ubyte]
            self.dll.Net_WriteGPIOState.restype = c_int
        if hasattr(self.dll, "Net_ReadGPIOState"):
            self.dll.Net_ReadGPIOState.argtypes = [c_int, ctypes.c_ubyte, ctypes.POINTER(ctypes.c_ubyte)]
            self.dll.Net_ReadGPIOState.restype = c_int
        if hasattr(self.dll, "Net_GateSetup"):
            self.dll.Net_GateSetup.argtypes = [c_int, ctypes.POINTER(T_ControlGate)]
            self.dll.Net_GateSetup.restype = c_int

        self._FGetReportCBEx = ctypes.WINFUNCTYPE(c_int, c_int, ctypes.c_ubyte, c_void_p, c_void_p)
        self._FGetImageCbEx = ctypes.WINFUNCTYPE(
            c_int, c_int, ctypes.c_uint, ctypes.POINTER(T_ImageUserInfo), ctypes.POINTER(T_PicInfo), c_void_p
        )
        self.dll.Net_RegReportMessEx.argtypes = [c_int, self._FGetReportCBEx, c_void_p]
        self.dll.Net_RegReportMessEx.restype = c_int
        self.dll.Net_RegImageRecvEx.argtypes = [c_int, self._FGetImageCbEx, c_void_p]
        self.dll.Net_RegImageRecvEx.restype = c_int
        # Official OcxConfig.ocx registers Ex2 (T_ImageUserInfo2). Prefix matches T_ImageUserInfo.
        if hasattr(self.dll, "Net_RegImageRecvEx2"):
            self.dll.Net_RegImageRecvEx2.argtypes = [c_int, self._FGetImageCbEx, c_void_p]
            self.dll.Net_RegImageRecvEx2.restype = c_int
        if hasattr(self.dll, "Net_StartVideo"):
            self.dll.Net_StartVideo.argtypes = [c_int, c_int, c_void_p]
            self.dll.Net_StartVideo.restype = c_int
        if hasattr(self.dll, "Net_StopVideo"):
            self.dll.Net_StopVideo.argtypes = [c_int]
            self.dll.Net_StopVideo.restype = c_int
        if hasattr(self.dll, "Net_GetJpgBuffer"):
            self.dll.Net_GetJpgBuffer.argtypes = [
                c_int,
                ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte)),
                ctypes.POINTER(ctypes.c_ulong),
            ]
            self.dll.Net_GetJpgBuffer.restype = c_int
        if hasattr(self.dll, "Net_FreeBuffer"):
            self.dll.Net_FreeBuffer.argtypes = [c_void_p]
            self.dll.Net_FreeBuffer.restype = c_int
        if hasattr(self.dll, "Net_ShowPlateRegion"):
            self.dll.Net_ShowPlateRegion.argtypes = [c_int, c_int]
            self.dll.Net_ShowPlateRegion.restype = c_int
        if hasattr(self.dll, "Net_AddPlayWindow"):
            self.dll.Net_AddPlayWindow.argtypes = [c_int, c_void_p]
            self.dll.Net_AddPlayWindow.restype = c_int
        if hasattr(self.dll, "Net_SetDrawDataOut"):
            callback_factory = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
            self._FDrawDataOut = callback_factory(
                None, c_int, c_void_p, c_void_p, ctypes.POINTER(ctypes.c_ubyte), c_int, c_int, c_void_p
            )
            self.dll.Net_SetDrawDataOut.argtypes = [c_int, self._FDrawDataOut, c_void_p]
            self.dll.Net_SetDrawDataOut.restype = c_int
        self._FindIpCB = ctypes.WINFUNCTYPE(None, c_char_p, c_void_p)
        if hasattr(self.dll, "Net_FindDeviceIp"):
            self.dll.Net_FindDeviceIp.argtypes = [self._FindIpCB, c_void_p]
            self.dll.Net_FindDeviceIp.restype = c_int

    def disconnect(self, handle: int, *, force: bool = False):
        stop_rc = self.stop_video(handle)
        if stop_rc != DC_NO_ERROR and not force:
            raise HVXSDKError("Video decoder did not stop; camera session was retained for safe recovery")
        if stop_rc != DC_NO_ERROR:
            # A native decoder exception can leave PlaySdk's HWND owner blocked
            # forever. Out-of-scope sessions must still be released or the
            # watcher will retry the same dead handle every five seconds.
            logging.getLogger("smartpark.hvx").warning(
                "Forcing SDK disconnect after video stop failure: handle=%s stop_rc=%s",
                handle, stop_rc,
            )
            with self._lock:
                self._video_handles.discard(int(handle))
                getattr(self, "_video_retry_handles", set()).discard(int(handle))
                getattr(self, "_video_retry_at", {}).pop(int(handle), None)
        for ip, connection in list(self._connection_results.items()):
            if int(connection["result"]["handle"]) == int(handle):
                self._connection_results.pop(ip, None)
        with self._lock:
            session = self._recognition_sessions.pop(int(handle), None)
        if session is not None:
            with session["lock"]:
                session["closed"] = True
        rc = self.dll.Net_DisConnCamera(handle)
        self._report_cbs.pop(handle, None)
        self._image_cbs.pop(handle, None)
        with self._lock:
            self._last_capture.pop(handle, None)
            self._last_live_jpeg.pop(handle, None)
            getattr(self, "_draw_frames", {}).pop(handle, None)
            getattr(self, "_draw_frame_seq", {}).pop(handle, None)
            getattr(self, "_draw_encoded_seq", {}).pop(handle, None)
            getattr(self, "_window_frame_seq", {}).pop(handle, None)
            getattr(self, "_window_last_jpeg", {}).pop(handle, None)
            getattr(self, "_native_jpeg_disabled_until", {}).pop(handle, None)
            self._live_received_at.pop(handle, None)
            getattr(self, "_live_frame_seq", {}).pop(handle, None)
            self._live_requested_at.pop(handle, None)
            self._video_streams.pop(handle, None)
            getattr(self, "_function_lists", {}).pop(int(handle), None)
            getattr(self, "_video_detect_configs", {}).pop(int(handle), None)
            getattr(self, "_video_diagnostics", {}).pop(int(handle), None)
            self._last_event_jpeg.pop(handle, None)
            self._last_event_crop.pop(handle, None)
            self._pending_events.pop(handle, None)
            self._pending_reports.pop(handle, None)
            self._gpio_state.pop(handle, None)
            for key in [item for item in self._event_media if item[0] == int(handle)]:
                self._event_media.pop(key, None)
        try:
            self.dll.Net_DelCamera(handle)
        except Exception:
            pass
        return rc
