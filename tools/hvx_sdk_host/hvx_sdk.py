from __future__ import annotations

import ctypes
from collections import deque
import os
from pathlib import Path
import queue
import struct
import threading
import hashlib
import logging
import time
import uuid


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
    "Net_StartVideo(handle, stream=1/0, HWND)  # live video (sub then main), then Net_GetJpgBuffer",
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


# E_ReportMess.REPORT_LPRINFO_EXT — plate text and usLpBox, no picture.
REPORT_LPRINFO_EXT = 20
# DCCSendPictureByCallBackEx memset size for T_ImageUserInfo.
IMAGE_USER_INFO_BYTES = 0x44


def plate_box_usable(box) -> bool:
    try:
        return int(box[2]) > int(box[0]) and int(box[3]) > int(box[1])
    except (TypeError, ValueError, IndexError):
        return False


def parse_image_user_info(blob: bytes) -> dict:
    """Read the callback prefix the OcxConfig NetSDK fills.

    DCCSendPictureByCallBackEx copies 0x44 bytes into the Ex/Ex2 argument.
    FUN_1000a470 writes the plate at +8 and the four usLpBox ushorts at
    +0x18, +0x1a, +0x1c and +0x1e. OcxConfig's image callback reads the same
    words. Score is the byte at +0x40.
    """
    if not blob or len(blob) < 0x20:
        return {}
    width, height = struct.unpack_from("<HH", blob, 0)
    box = [int(value) for value in struct.unpack_from("<HHHH", blob, 0x18)]
    return {
        "plate_raw": bytes(blob[8:24]),
        "plate_box": box,
        "image_width": int(width),
        "image_height": int(height),
        "score": int(blob[0x40]) if len(blob) > 0x40 else None,
        "have_vehicle": bool(blob[0x25]) if len(blob) > 0x25 else False,
        "snap_type": int(blob[0x24]) if len(blob) > 0x24 else None,
    }


def jpeg_pixel_size(blob: bytes) -> tuple[int, int]:
    if not blob or blob[:2] != b"\xff\xd8":
        return 0, 0
    index = 2
    limit = len(blob)
    while index + 8 < limit:
        if blob[index] != 0xFF:
            index += 1
            continue
        marker = blob[index + 1]
        if marker in (0xD8, 0xD9):
            index += 2
            continue
        if index + 4 > limit:
            break
        length = int.from_bytes(blob[index + 2:index + 4], "big")
        if marker in (0xC0, 0xC1, 0xC2, 0xC3) and index + 8 < limit:
            height = int.from_bytes(blob[index + 5:index + 7], "big")
            width = int.from_bytes(blob[index + 7:index + 9], "big")
            if width > 0 and height > 0:
                return width, height
        if length < 2:
            break
        index += 2 + length
    return 0, 0


def retain_plate_box(previous: dict | None, row: dict, *, now: float | None = None) -> dict:
    """Do not let a later empty callback erase a box for the same picture."""
    if plate_box_usable(row.get("plate_box")):
        return row
    prev = previous or {}
    if not plate_box_usable(prev.get("plate_box")):
        return row
    moment = time.time() if now is None else float(now)
    try:
        age = moment - float(prev.get("captured_at_epoch") or 0)
    except (TypeError, ValueError):
        return row
    if age < 0 or age > 3.0:
        return row
    same_image = int(row.get("image_id") or 0) != 0 and int(row.get("image_id") or 0) == int(prev.get("image_id") or 0)
    same_plate = bool(row.get("plate")) and row.get("plate") == prev.get("plate")
    if not same_image and not same_plate:
        return row
    kept = dict(row)
    kept["plate_box"] = list(prev["plate_box"])
    if not int(kept.get("image_width") or 0):
        kept["image_width"] = int(prev.get("image_width") or 0)
        kept["image_height"] = int(prev.get("image_height") or 0)
    kept["have_vehicle"] = True
    return kept


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


EVENT_MEDIA_MAX_BYTES = 64 * 1024 * 1024


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
        self._recognition_sessions = {}
        self._connection_locks = {}
        self._connection_results = {}
        self._last_capture = {}
        self._last_live_jpeg = {}
        self._live_received_at = {}
        self._live_requested_at = {}
        self._video_streams = {}
        self._video_locks = {}
        self._last_event_jpeg = {}
        self._last_event_crop = {}
        self._pending_events = {}
        self._pending_reports = {}
        self._gpio_state = {}
        self._event_media = {}
        self._hwnds = {}
        self._video_handles = set()
        self._video_threads = {}
        self._video_thread = None
        self._video_running = False
        self._ui_thread = None
        self._hwnd_queue = queue.Queue()
        self._ui_commands = queue.Queue(maxsize=8)
        self._hwnd_ready = {}
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
            previous = dict(self._last_capture.get(handle) or {})
            event = {
                "image_id": int(previous.get("image_id") or 0),
                "captured_at_epoch": time.time(),
                "plate": plate or previous.get("plate"),
                "score": previous.get("score"),
                "plate_box": list(box) if plate_box_usable(box) else previous.get("plate_box"),
                "image_width": int(previous.get("image_width") or 0),
                "image_height": int(previous.get("image_height") or 0),
                "jpeg_bytes": previous.get("jpeg_bytes") or 0,
                "crop_bytes": previous.get("crop_bytes") or 0,
                "have_vehicle": True if plate_box_usable(box) else bool(previous.get("have_vehicle")),
                "snap_type": previous.get("snap_type"),
            }
            event = retain_plate_box(previous, event)
            self._last_capture[handle] = event
            pending = self._pending_events.setdefault(handle, deque(maxlen=64))
            if pending and not plate_box_usable(pending[-1].get("plate_box")):
                pending[-1]["plate_box"] = list(event["plate_box"]) if event.get("plate_box") else pending[-1].get("plate_box")
                pending[-1]["have_vehicle"] = bool(event.get("have_vehicle"))
                if plate and not pending[-1].get("plate"):
                    pending[-1]["plate"] = plate
            elif not pending and plate_box_usable(event.get("plate_box")):
                pending.append(dict(event))

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
        }
        key = int(handle)
        with self._lock:
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

    def _register_report(self, handle: int) -> int:
        cb = self._report_cbs.get(handle)
        if cb is None:
            cb = self._FGetReportCBEx(self._on_report)
        self._report_cbs[handle] = cb
        return int(self.dll.Net_RegReportMessEx(handle, cb, None))

    def _register_image(self, handle: int) -> int:
        cb = self._image_cbs.get(handle)
        if cb is None:
            cb = self._FGetImageCbEx(self._on_image)
        self._image_cbs[handle] = cb
        rc = int(self.dll.Net_RegImageRecvEx(handle, cb, None))
        if hasattr(self.dll, "Net_RegImageRecvEx2"):
            rc2 = int(self.dll.Net_RegImageRecvEx2(handle, cb, None))
            if rc != DC_NO_ERROR:
                rc = rc2
        return rc

    def add_and_connect(self, ip: str, port: int, timeout: int, username: str, password: str):
        with self._lock:
            connection_lock = self._connection_locks.setdefault(ip, threading.RLock())
        signature = hashlib.sha256(repr((port, username, password)).encode()).digest()
        with connection_lock:
            previous = self._connection_results.get(ip)
            if previous is not None:
                try:
                    state = int(self.dll.Net_QueryConnState(previous["result"]["handle"]))
                    if previous["signature"] == signature and state in {CONN_STATE_UNKNOW, CONN_STATE_TRYING, CONN_STATE_SUCC}:
                        return {**previous["result"], "reused": True}
                except Exception:
                    pass
                self.disconnect(int(previous["result"]["handle"]))
            result = self._add_and_connect(ip, port, timeout, username, password)
            logging.getLogger("smartpark.hvx").info("Camera connection: ip=%s handle=%s connected=%s rc=%s", ip, result.get("handle"), result.get("connected"), result.get("connect_rc"))
            if result.get("connected"):
                self._connection_results[ip] = {"signature": signature, "result": dict(result)}
            return result

    def connection_sessions(self) -> list[dict]:
        with self._lock:
            return [{"handle": handle, "ip": session["ip"], "state": session["state"]}
                    for handle, session in self._recognition_sessions.items() if session.get("ip")]

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
            with self._lock:
                self._recognition_sessions[int(handle)] = {
                    "ip": ip,
                    "lock": threading.Lock(), "closed": False, "state": state,
                    "pending": image_rc != DC_NO_ERROR, "image_recv_rc": image_rc,
                    "next_check": 0.0, "retry_at": 0.0, "backoff": 1.0,
                    "rearms": 0, "last_error": "",
                }
            try:
                video = self.start_video(handle)
            except HVXSDKError as exc:
                video = {"ok": False, "error": str(exc)}
                logging.getLogger("smartpark.hvx").warning("Video setup unavailable: handle=%s error=%s", handle, exc)
            steps.append({"api": "Net_StartVideo", **{k: v for k, v in video.items() if k != "hwnd"}})
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
            received_at = self._live_received_at.get(int(handle), 0.0)
            if time.monotonic() - received_at > 5.0:
                return b""
            live = self._last_live_jpeg.get(int(handle), b"")
            return live if live[:2] == b"\xff\xd8" else b""

    def live_jpeg_for(self, handle: int) -> bytes:
        with self._lock:
            self._live_requested_at[int(handle)] = time.monotonic()
        return self.jpeg_for(handle)

    def drain_events(self, handle: int) -> list[dict]:
        self._refresh_recognition(handle)
        with self._lock:
            queue = self._pending_events.get(int(handle))
            if not queue:
                return []
            items = list(queue)
            queue.clear()
            return items

    def drain_reports(self, handle: int) -> list[dict]:
        with self._lock:
            queue = self._pending_reports.get(int(handle))
            if not queue:
                return []
            items = list(queue)
            queue.clear()
            return items

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
            latest = self._last_event_jpeg if index == 1 else self._last_event_crop
            return latest.get(int(handle), b"")

    def event_jpeg_for(self, handle: int, image_id: int | None = None, *, capture_token=None) -> bytes:
        return self._event_image(handle, image_id, capture_token, 1)

    def event_crop_for(self, handle: int, image_id: int | None = None, *, capture_token=None) -> bytes:
        return self._event_image(handle, image_id, capture_token, 2)

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
                    if state in {CONN_STATE_DIS, CONN_STATE_TRYING}:
                        session["pending"] = True
                    if state == CONN_STATE_SUCC and previous in {CONN_STATE_DIS, CONN_STATE_TRYING}:
                        session["pending"] = True
                        session["retry_at"] = 0.0
                    if state == CONN_STATE_SUCC and session["pending"] and now >= session["retry_at"]:
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
                "ready": session["state"] == CONN_STATE_SUCC and not session["pending"],
                "image_recv_rc": session["image_recv_rc"],
                "rearms": session["rearms"],
                "retry_pending": session["pending"],
                "last_error": session["last_error"],
            }

    def state(self, handle: int):
        state = int(self.dll.Net_QueryConnState(handle))
        with self._lock:
            capture = dict(self._last_capture.get(int(handle)) or {})
        recognition = self._refresh_recognition(handle, observed_state=state)
        return {"state": state, "name": describe_state(state), "last_capture": capture or None,
                "recognition": recognition}

    def disconnect(self, handle: int):
        for ip, connection in list(self._connection_results.items()):
            if int(connection["result"]["handle"]) == int(handle):
                self._connection_results.pop(ip, None)
        with self._lock:
            session = self._recognition_sessions.pop(int(handle), None)
        if session is not None:
            with session["lock"]:
                session["closed"] = True
        self.stop_video(handle)
        rc = self.dll.Net_DisConnCamera(handle)
        self._report_cbs.pop(handle, None)
        self._image_cbs.pop(handle, None)
        with self._lock:
            self._last_capture.pop(handle, None)
            self._last_live_jpeg.pop(handle, None)
            self._live_received_at.pop(handle, None)
            self._live_requested_at.pop(handle, None)
            self._video_streams.pop(handle, None)
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

    def snapshot_trigger(self, handle: int):
        snap = T_DCImageSnap()
        snap.uiImageId = 0
        snap.ucLightIndex = 0
        snap.ucLightMode = 0
        snap.usGroupId = 0
        return self.dll.Net_ImageSnap(handle, ctypes.byref(snap))

    def read_gpio(self, handle: int, index: int = 1) -> dict:
        if not hasattr(self.dll, "Net_ReadGPIOState"):
            raise HVXSDKError("Net_ReadGPIOState not exported")
        value = ctypes.c_ubyte(0)
        rc = int(self.dll.Net_ReadGPIOState(int(handle), index & 0xFF, ctypes.byref(value)))
        row = {
            "ok": rc == DC_NO_ERROR,
            "rc": rc,
            "rc_name": describe_rc(rc),
            "handle": int(handle),
            "index": int(index),
            "value": int(value.value),
        }
        with self._lock:
            self._gpio_state[(int(handle), int(index))] = row
        return row

    def gpio_states(self, handle: int, indexes: list[int] | None = None) -> list[dict]:
        rows = []
        for index in indexes or [1, 2]:
            try:
                rows.append(self.read_gpio(handle, index))
            except Exception as exc:
                rows.append({"ok": False, "handle": int(handle), "index": int(index), "error": str(exc)})
        return rows

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
        """Use the legacy player's main stream, with the substream as fallback."""
        with self._video_lock(handle):
            return self._call_video_ui(lambda: self._start_video(handle, stream_type))

    def _call_video_ui(self, operation):
        if threading.current_thread() is self._ui_thread:
            return operation()
        self._ensure_ui_thread()
        ready = threading.Event()
        result = {}
        try:
            self._ui_commands.put_nowait((operation, ready, result))
        except queue.Full:
            raise HVXSDKError("Video control is busy")
        if not ready.wait(5.0):
            result["cancelled"] = True
            raise HVXSDKError("Video control timed out; see hvx-host.log")
        if "error" in result:
            raise result["error"]
        return result.get("value")

    def _video_lock(self, handle: int):
        with self._lock:
            return self._video_locks.setdefault(int(handle), threading.RLock())

    def _start_video(self, handle: int, stream_type: int) -> dict:
        if not hasattr(self.dll, "Net_StartVideo"):
            return {"ok": False, "error": "Net_StartVideo not exported"}
        hwnd = self._hidden_hwnd(handle)
        rc = int(self.dll.Net_StartVideo(int(handle), int(stream_type), hwnd))
        used = stream_type
        if rc != DC_NO_ERROR:
            other = 0 if int(stream_type) == 1 else 1
            used = other
            rc = int(self.dll.Net_StartVideo(int(handle), other, hwnd))
        if rc != DC_NO_ERROR and hwnd:
            rc = int(self.dll.Net_StartVideo(int(handle), used, None))
        region_rc = None
        if rc == DC_NO_ERROR and hasattr(self.dll, "Net_ShowPlateRegion"):
            region_rc = int(self.dll.Net_ShowPlateRegion(int(handle), 0))
        if rc != DC_NO_ERROR:
            logging.getLogger("smartpark.hvx").warning("Video start failed: handle=%s stream=%s rc=%s", handle, used, rc)
        with self._lock:
            self._video_streams[int(handle)] = used
            self._video_handles.add(int(handle))
            self._live_requested_at[int(handle)] = time.monotonic()
        self._ensure_camera_pump(int(handle))
        return {
            "ok": rc == DC_NO_ERROR,
            "rc": rc,
            "rc_name": describe_rc(rc),
            "stream_type": used,
            "hwnd": int(hwnd) if hwnd else 0,
            "plate_region_rc": region_rc,
        }

    def stop_video(self, handle: int) -> int:
        with self._video_lock(handle):
            with self._lock:
                self._video_handles.discard(int(handle))
                self._last_live_jpeg.pop(int(handle), None)
                self._live_received_at.pop(int(handle), None)
                self._live_requested_at.pop(int(handle), None)
            if hasattr(self.dll, "Net_StopVideo"):
                try:
                    return self._call_video_ui(lambda: int(self.dll.Net_StopVideo(int(handle))))
                except Exception:
                    return -1
            return 0

    def _ensure_ui_thread(self):
        """OcxConfig PlaySdk needs a thread that owns HWNDs and pumps messages."""
        with self._lock:
            if self._ui_thread and self._ui_thread.is_alive():
                return
            self._video_running = True
            self._ui_thread = threading.Thread(target=self._ui_loop, name="hvx-play-ui", daemon=True)
            self._ui_thread.start()

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

    def _ensure_video_thread(self):
        """Compatibility wrapper — live video is now one pump per camera."""
        with self._lock:
            handles = list(self._video_handles)
        for handle in handles:
            self._ensure_camera_pump(handle)

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

    def _camera_video_loop(self, handle: int):
        """Sample the SDK's current frame at a bounded rate, not as a frame queue."""
        handle = int(handle)
        idle = 0
        retry_at = time.monotonic() + 5.0
        interval = 1.0 / max(1.0, min(20.0, float(os.environ.get("SMARTPARK_HVX_JPEG_FPS", "10"))))
        def publish(jpeg):
            with self._lock:
                if handle in self._video_handles:
                    self._last_live_jpeg[handle] = jpeg
                    self._live_received_at[handle] = time.monotonic()
        while self._video_running:
            started = time.monotonic()
            with self._lock:
                if handle not in self._video_handles:
                    break
                requested = self._live_requested_at.get(handle, started)
            if started - requested > 5.0:
                retry_at = started + 5.0
                time.sleep(.25)
                continue
            jpeg = self._get_jpg_buffer(handle)
            if jpeg:
                publish(jpeg)
                idle = 0
                retry_at = time.monotonic() + 5.0
            else:
                idle = min(idle + 1, 8)
                if time.monotonic() >= retry_at:
                    retry_at = time.monotonic() + 30.0
                    try:
                        with self._video_lock(handle):
                            with self._lock:
                                active = handle in self._video_handles
                            if not active:
                                break
                            logging.getLogger("smartpark.hvx").warning("Restarting empty video decoder: handle=%s", handle)
                            def restart():
                                if hasattr(self.dll, "Net_StopVideo"):
                                    self.dll.Net_StopVideo(handle)
                                return self._start_video(handle, 0 if self._video_streams.get(handle, 0) == 1 else 1)
                            self._call_video_ui(restart)
                    except Exception:
                        pass
            time.sleep(max(0.002, interval - (time.monotonic() - started)))
        with self._lock:
            if self._video_threads.get(handle) is threading.current_thread():
                self._video_threads.pop(handle, None)

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
