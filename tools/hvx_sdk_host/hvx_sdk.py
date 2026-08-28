from __future__ import annotations

import ctypes
from collections import deque
import os
from pathlib import Path
import struct
import threading
import time


class HVXSDKError(RuntimeError):
    pass


# E_ReturnCode from QY Net_Setup.h
DC_NO_ERROR = 0
DC_HANDLE_INVALID = 1
DC_CONN_FAIL = 2
DC_CMD_INVALID = 5
DC_PARA_INVALID = 6
DC_REQ_TIMEOUT = 7
DC_NOT_CONN = 12
DC_CONNECT_AUTH = 18
DC_USER_NOT_EXIST = 19
DC_PASSWD_ERROR = 20
HANDLE_INVALID = -1

# E_ConnState from Net_Interface.h
CONN_STATE_UNKNOW = 0
CONN_STATE_TRYING = 1
CONN_STATE_SUCC = 2
CONN_STATE_DIS = 3

RETURN_CODES = {
    0: "DC_NO_ERROR",
    1: "DC_HANDLE_INVALID",
    2: "DC_CONN_FAIL",
    3: "DC_OBJ_BUSY",
    4: "DC_OBJ_UNEXIST",
    5: "DC_CMD_INVALID",
    6: "DC_PARA_INVALID",
    7: "DC_REQ_TIMEOUT",
    8: "DC_MEMORY_LACK",
    9: "DC_SEND_FAIL",
    10: "DC_RECV_FAIL",
    11: "DC_OPT_FAIL",
    12: "DC_NOT_CONN",
    13: "DC_BEYOND_MAX_CLIENT",
    18: "DC_CONNECT_AUTH",
    19: "DC_USER_NOT_EXIST",
    20: "DC_PASSWD_ERROR",
    -1: "DC_UNDEFINED_ERROR",
    1000: "DC_CONN_PORT_NEGO_FAIL",
    1006: "DC_CONN_SERVER_ERROR",
    1007: "DC_CONN_RESPONSE_CODE_AUTHORITY_LIMIT",
}

CONN_STATES = {
    0: "CONN_STATE_UNKNOW",
    1: "CONN_STATE_TRYING",
    2: "CONN_STATE_SUCC",
    3: "CONN_STATE_DIS",
}

# QY connect sequence. Camera HTTP UI is port 80; SDK control is 30000.
SDK_CONNECT_SEQUENCE = [
    "Net_Init()",
    "Net_AddCamera(ip)",
    "Net_RegReportMessEx(handle, cb)  # before connect",
    "Net_ConnCameraEx(handle, port=30000, timeout_seconds as unsigned short, user, pass)",
    "Net_ConnCamera(handle, port, timeout_seconds)  # fallback if Ex fails",
    "Net_QueryConnState(handle)  # 2 = CONN_STATE_SUCC",
    "Net_RegOffLineClient(handle)",
    "Net_RegImageRecvEx(handle, cb)  # native plate + JPEG",
    "Net_StartVideo(handle, stream=0/1, HWND)  # live video, then Net_GetJpgBuffer",
]


class T_DCImageSnap(ctypes.Structure):
    _fields_ = [
        ("uiImageId", ctypes.c_uint),
        ("ucLightIndex", ctypes.c_ubyte),
        ("ucLightMode", ctypes.c_ubyte),
        ("usGroupId", ctypes.c_ushort),
    ]


class T_ImageUserInfo(ctypes.Structure):
    _fields_ = [
        ("usWidth", ctypes.c_ushort),
        ("usHeight", ctypes.c_ushort),
        ("ucVehicleColor", ctypes.c_ubyte),
        ("ucVehicleBrand", ctypes.c_ubyte),
        ("ucVehicleSize", ctypes.c_ubyte),
        ("ucPlateColor", ctypes.c_ubyte),
        ("szLprResult", ctypes.c_char * 16),
        ("usLpBox", ctypes.c_ushort * 4),
        ("ucLprType", ctypes.c_ubyte),
        ("usSpeed", ctypes.c_ushort),
        ("ucSnapType", ctypes.c_ubyte),
        ("ucHaveVehicle", ctypes.c_ubyte),
        ("acSnapTime", ctypes.c_char * 18),
        ("ucViolateCode", ctypes.c_ubyte),
        ("ucLaneNo", ctypes.c_ubyte),
        ("uiVehicleId", ctypes.c_uint),
        ("ucScore", ctypes.c_ubyte),
        ("ucDirection", ctypes.c_ubyte),
        ("ucTotalNum", ctypes.c_ubyte),
        ("ucSnapshotIndex", ctypes.c_ubyte),
    ]


class T_ControlGate(ctypes.Structure):
    _fields_ = [
        ("ucState", ctypes.c_ubyte),
        ("ucIndex", ctypes.c_ubyte),
        ("ucGateDefSta", ctypes.c_ubyte),
        ("ucReserved", ctypes.c_ubyte),
    ]


GATE_STATE_OPEN = 1
GATE_STATE_CLOSE = 2
GATE_STATE_STOP = 3
# Net_WriteGPIOState: 0 = open circuit, 1 = short. Pulse short then open for a barrier.
GPIO_OPEN_CIRCUIT = 0
GPIO_SHORT = 1


class T_PicInfo(ctypes.Structure):
    _fields_ = [
        ("uiPanoramaPicLen", ctypes.c_uint),
        ("uiVehiclePicLen", ctypes.c_uint),
        ("ptPanoramaPicBuff", ctypes.c_void_p),
        ("ptVehiclePicBuff", ctypes.c_void_p),
    ]


def describe_rc(rc: int) -> str:
    return RETURN_CODES.get(int(rc), f"unknown_{rc}")


def describe_state(state: int) -> str:
    return CONN_STATES.get(int(state), f"unknown_{state}")


def _decode_plate(raw: bytes) -> str:
    text = raw.split(b"\x00", 1)[0].strip()
    if not text:
        return ""
    for encoding in ("gb2312", "gbk", "utf-8", "latin-1"):
        try:
            plate = text.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
        if plate:
            return plate
    return ""


class HVXSDK:
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
        self._last_capture = {}
        self._last_live_jpeg = {}
        self._last_event_jpeg = {}
        self._last_event_crop = {}
        self._pending_events = {}
        self._event_media = {}
        self._hwnds = {}
        self._video_handles = set()
        self._video_thread = None
        self._video_running = False
        self._wndproc = None
        self._wndclass = None
        self._lock = threading.Lock()
        self._bind()
        rc = self.dll.Net_Init()
        if rc != DC_NO_ERROR:
            raise HVXSDKError(f"Net_Init failed rc={rc} ({describe_rc(rc)})")
        self.initialized = True

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
        self._FindIpCB = ctypes.WINFUNCTYPE(None, c_char_p, c_void_p)
        if hasattr(self.dll, "Net_FindDeviceIp"):
            self.dll.Net_FindDeviceIp.argtypes = [self._FindIpCB, c_void_p]
            self.dll.Net_FindDeviceIp.restype = c_int

    def _on_report(self, handle, msg_type, message, user):
        return 0

    def _copy_buffer(self, ptr, length: int) -> bytes:
        if not ptr or length <= 0:
            return b""
        length = min(int(length), 8_000_000)
        try:
            return ctypes.string_at(ptr, length)
        except Exception:
            return b""

    def _on_image(self, handle, image_id, pt_info, pt_pic, user):
        plate = ""
        score = None
        box = None
        jpeg = b""
        crop = b""
        width = 0
        height = 0
        if pt_info:
            info = pt_info.contents
            plate = _decode_plate(bytes(info.szLprResult))
            score = int(info.ucScore)
            box = [int(info.usLpBox[i]) for i in range(4)]
            width = int(info.usWidth)
            height = int(info.usHeight)
        if pt_pic:
            pic = pt_pic.contents
            jpeg = self._copy_buffer(pic.ptPanoramaPicBuff, int(pic.uiPanoramaPicLen or 0))
            crop = self._copy_buffer(pic.ptVehiclePicBuff, int(pic.uiVehiclePicLen or 0))
            if not jpeg and crop[:2] == b"\xff\xd8":
                jpeg = crop
        row = {
            "image_id": int(image_id),
            "plate": plate or None,
            "score": score,
            "plate_box": box,
            "image_width": width,
            "image_height": height,
            "jpeg_bytes": len(jpeg),
            "crop_bytes": len(crop),
        }
        key = int(handle)
        with self._lock:
            self._last_capture[key] = row
            if jpeg[:2] == b"\xff\xd8":
                self._last_event_jpeg[key] = jpeg
            if crop[:2] == b"\xff\xd8":
                self._last_event_crop[key] = crop
            queue = self._pending_events.setdefault(key, deque(maxlen=64))
            queue.append(dict(row))
            self._event_media[(key, int(image_id))] = (jpeg, crop)
            while len(self._event_media) > 128:
                self._event_media.pop(next(iter(self._event_media)))
        return 0

    def _register_report(self, handle: int) -> int:
        cb = self._FGetReportCBEx(self._on_report)
        self._report_cbs[handle] = cb
        return int(self.dll.Net_RegReportMessEx(handle, cb, None))

    def _register_image(self, handle: int) -> int:
        cb = self._FGetImageCbEx(self._on_image)
        self._image_cbs[handle] = cb
        # OcxConfig.ocx uses Ex2. Register Ex first to match live cameras.
        rc = int(self.dll.Net_RegImageRecvEx(handle, cb, None))
        if rc == DC_NO_ERROR:
            return rc
        if hasattr(self.dll, "Net_RegImageRecvEx2"):
            return int(self.dll.Net_RegImageRecvEx2(handle, cb, None))
        return rc

    def add_and_connect(self, ip: str, port: int, timeout: int, username: str, password: str):
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
        # CONN_STATE_UNKNOW (0) immediately after a successful login is normal.
        connected = rc == DC_NO_ERROR

        offline_rc = None
        image_rc = None
        snap_rc = None
        if connected:
            offline_rc = int(self.dll.Net_RegOffLineClient(handle))
            steps.append({"api": "Net_RegOffLineClient", "rc": offline_rc, "name": describe_rc(offline_rc)})
            image_rc = self._register_image(handle)
            steps.append({"api": "Net_RegImageRecvEx", "rc": image_rc, "name": describe_rc(image_rc)})
            video = self.start_video(handle)
            steps.append({"api": "Net_StartVideo", **{k: v for k, v in video.items() if k != "hwnd"}})
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
            "image_recv_rc": image_rc,
            "offline_rc": offline_rc,
            "image_snap_rc": snap_rc,
            "steps": steps,
        }

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

    def last_captures(self):
        with self._lock:
            return {str(handle): dict(row) for handle, row in self._last_capture.items()}

    def jpeg_for(self, handle: int) -> bytes:
        """Live video frame from Net_GetJpgBuffer only. Never the last car still."""
        with self._lock:
            live = self._last_live_jpeg.get(int(handle), b"")
            return live if live[:2] == b"\xff\xd8" else b""

    def live_jpeg_for(self, handle: int) -> bytes:
        return self.jpeg_for(handle)

    def drain_events(self, handle: int) -> list[dict]:
        with self._lock:
            queue = self._pending_events.get(int(handle))
            if not queue:
                return []
            items = list(queue)
            queue.clear()
            return items

    def event_jpeg_for(self, handle: int, image_id: int | None = None) -> bytes:
        with self._lock:
            if image_id is not None:
                pair = self._event_media.get((int(handle), int(image_id)))
                if pair and pair[0][:2] == b"\xff\xd8":
                    return pair[0]
            return self._last_event_jpeg.get(int(handle), b"")

    def event_crop_for(self, handle: int, image_id: int | None = None) -> bytes:
        with self._lock:
            if image_id is not None:
                pair = self._event_media.get((int(handle), int(image_id)))
                if pair and pair[1][:2] == b"\xff\xd8":
                    return pair[1]
            return self._last_event_crop.get(int(handle), b"")

    def state(self, handle: int):
        state = int(self.dll.Net_QueryConnState(handle))
        with self._lock:
            capture = dict(self._last_capture.get(int(handle)) or {})
        return {"state": state, "name": describe_state(state), "last_capture": capture or None}

    def disconnect(self, handle: int):
        self.stop_video(handle)
        rc = self.dll.Net_DisConnCamera(handle)
        self._report_cbs.pop(handle, None)
        self._image_cbs.pop(handle, None)
        with self._lock:
            self._last_capture.pop(handle, None)
            self._last_live_jpeg.pop(handle, None)
            self._last_event_jpeg.pop(handle, None)
            self._last_event_crop.pop(handle, None)
            self._pending_events.pop(handle, None)
            for key in [item for item in self._event_media if item[0] == int(handle)]:
                self._event_media.pop(key, None)
        try:
            self.dll.Net_DelCamera(handle)
        except Exception:
            pass
        return rc

    def snapshot_trigger(self, handle: int):
        snap = T_DCImageSnap()
        snap.uiImageId = 0
        snap.ucLightIndex = 0
        snap.ucLightMode = 0
        snap.usGroupId = 0
        return self.dll.Net_ImageSnap(handle, ctypes.byref(snap))

    def _hidden_hwnd(self, handle: int):
        """Paint live video onto an HWND. One hidden popup per camera."""
        existing = self._hwnds.get(int(handle))
        if existing:
            return existing
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
        except Exception:
            return None
        if self._wndproc is None:
            WNDPROC = ctypes.WINFUNCTYPE(
                ctypes.c_long, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_long
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
            0,
            "SmartParkHVXVideo",
            f"HVX {handle}",
            0x80000000,  # WS_POPUP
            0, 0, 320, 240,
            None, None, kernel32.GetModuleHandleW(None), None,
        )
        if hwnd:
            user32.ShowWindow(hwnd, 0)
        self._hwnds[int(handle)] = hwnd or None
        return hwnd or None

    def start_video(self, handle: int, stream_type: int = 0) -> dict:
        """Net_StartVideo then JPEG frames via Net_GetJpgBuffer. Stream 0=main, 1=sub."""
        if not hasattr(self.dll, "Net_StartVideo"):
            return {"ok": False, "error": "Net_StartVideo not exported"}
        hwnd = self._hidden_hwnd(handle)
        rc = int(self.dll.Net_StartVideo(int(handle), int(stream_type), hwnd))
        used = stream_type
        if rc != DC_NO_ERROR and stream_type == 0:
            used = 1
            rc = int(self.dll.Net_StartVideo(int(handle), 1, hwnd))
        if rc != DC_NO_ERROR and hwnd:
            rc = int(self.dll.Net_StartVideo(int(handle), used, None))
        region_rc = None
        if rc == DC_NO_ERROR and hasattr(self.dll, "Net_ShowPlateRegion"):
            region_rc = int(self.dll.Net_ShowPlateRegion(int(handle), 1))
        if rc == DC_NO_ERROR:
            with self._lock:
                self._video_handles.add(int(handle))
            self._ensure_video_thread()
        return {
            "ok": rc == DC_NO_ERROR,
            "rc": rc,
            "rc_name": describe_rc(rc),
            "stream_type": used,
            "hwnd": int(hwnd) if hwnd else 0,
            "plate_region_rc": region_rc,
        }

    def stop_video(self, handle: int) -> int:
        with self._lock:
            self._video_handles.discard(int(handle))
        if hasattr(self.dll, "Net_StopVideo"):
            try:
                return int(self.dll.Net_StopVideo(int(handle)))
            except Exception:
                return -1
        return 0

    def _ensure_video_thread(self):
        if self._video_thread and self._video_thread.is_alive():
            return
        self._video_running = True
        self._video_thread = threading.Thread(target=self._video_loop, name="hvx-live-jpeg", daemon=True)
        self._video_thread.start()

    def _get_jpg_buffer(self, handle: int) -> bytes:
        if not hasattr(self.dll, "Net_GetJpgBuffer"):
            return b""
        buf = ctypes.POINTER(ctypes.c_ubyte)()
        size = ctypes.c_ulong(0)
        try:
            rc = int(self.dll.Net_GetJpgBuffer(int(handle), ctypes.byref(buf), ctypes.byref(size)))
        except Exception:
            return b""
        if rc != DC_NO_ERROR or not size.value or not buf:
            return b""
        try:
            data = ctypes.string_at(buf, min(int(size.value), 4_000_000))
        finally:
            if hasattr(self.dll, "Net_FreeBuffer") and buf:
                try:
                    self.dll.Net_FreeBuffer(ctypes.cast(buf, ctypes.c_void_p))
                except Exception:
                    pass
        return data if data[:2] == b"\xff\xd8" else b""

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
        while self._video_running:
            with self._lock:
                handles = list(self._video_handles)
            for handle in handles:
                jpeg = self._get_jpg_buffer(handle)
                if jpeg:
                    with self._lock:
                        self._last_live_jpeg[handle] = jpeg
            self._pump_messages()
            time.sleep(0.03 if handles else 0.2)
        self._video_thread = None

    def write_gpio(self, handle: int, index: int, value: int) -> int:
        if not hasattr(self.dll, "Net_WriteGPIOState"):
            raise HVXSDKError("Net_WriteGPIOState not exported")
        return int(self.dll.Net_WriteGPIOState(int(handle), index & 0xFF, value & 0xFF))

    def gate_setup(self, handle: int, state: int = GATE_STATE_OPEN, index: int = 0) -> int:
        if not hasattr(self.dll, "Net_GateSetup"):
            raise HVXSDKError("Net_GateSetup not exported")
        cmd = T_ControlGate()
        cmd.ucState = state & 0xFF
        cmd.ucIndex = index & 0xFF
        cmd.ucGateDefSta = 0
        cmd.ucReserved = 0
        return int(self.dll.Net_GateSetup(int(handle), ctypes.byref(cmd)))

    def gpio_pulse(self, handle: int, index: int = 0, pulse_ms: int = 500) -> dict:
        steps = []
        gate_rc = None
        if hasattr(self.dll, "Net_GateSetup"):
            gate_rc = self.gate_setup(handle, GATE_STATE_OPEN, index)
            steps.append({"api": "Net_GateSetup", "rc": gate_rc, "name": describe_rc(gate_rc), "state": GATE_STATE_OPEN, "index": index})
        on_rc = self.write_gpio(handle, index, GPIO_SHORT)
        steps.append({"api": "Net_WriteGPIOState", "rc": on_rc, "name": describe_rc(on_rc), "index": index, "value": GPIO_SHORT})
        time.sleep(max(0.05, min(int(pulse_ms), 5000) / 1000.0))
        off_rc = self.write_gpio(handle, index, GPIO_OPEN_CIRCUIT)
        steps.append({"api": "Net_WriteGPIOState", "rc": off_rc, "name": describe_rc(off_rc), "index": index, "value": GPIO_OPEN_CIRCUIT})
        ok = on_rc == DC_NO_ERROR or gate_rc == DC_NO_ERROR
        return {
            "ok": ok,
            "handle": int(handle),
            "index": int(index),
            "pulse_ms": int(pulse_ms),
            "gate_setup_rc": gate_rc,
            "write_on_rc": on_rc,
            "write_off_rc": off_rc,
            "steps": steps,
            "message": "GPIO pulse on live camera relay" if ok else "GPIO pulse failed",
        }

    def close(self):
        self._video_running = False
        with self._lock:
            handles = list(self._video_handles)
        for handle in handles:
            self.stop_video(handle)
        if getattr(self, "initialized", False):
            self.dll.Net_UNinit()
            self.initialized = False
