from __future__ import annotations

import ctypes
from collections import deque
from contextlib import contextmanager
from io import BytesIO
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

# E_ConnState from Net_Interface.h.  The SDK's public query function is
# slightly counter-intuitive: it returns 0 when the internal connection byte
# is 2 (connected).  Keep the older symbolic value 2 as a compatibility
# state because some QY builds expose the internal value directly.
CONN_STATE_CONNECTED = 0
CONN_STATE_UNKNOW = 0
CONN_STATE_TRYING = 1
CONN_STATE_SUCC = 2
CONN_STATE_DIS = 3
CONN_STATE_CONNECTED_VALUES = frozenset({CONN_STATE_CONNECTED, CONN_STATE_SUCC})

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
    0: "CONN_STATE_SUCC",
    1: "CONN_STATE_TRYING",
    2: "CONN_STATE_SUCC",
    3: "CONN_STATE_DIS",
}

# OcxConfig asks the camera for an 800-byte function list immediately after
# login.  Its first byte indicates a valid response and the DWORD at +0x04
# advertises which PlaySdk stream types the firmware supports.  The OCX picks
# the highest-priority supported type in this order; the gate cameras in the
# supplied site fixture are the reason a hard-coded 0/1 choice is unreliable.
FUNCTION_LIST_BYTES = 800
FUNCTION_LIST_FLAGS_OFFSET = 4
STREAM_TYPE_FLAGS = (
    (4, 0x20000),
    (3, 0x8000),
    (2, 0x10000),
    (1, 0x200),
)


def stream_type_from_function_list(blob: bytes | bytearray | memoryview) -> int:
    """Return the PlaySdk stream type selected by OcxConfig's bit tests."""
    raw = bytes(blob or b"")
    if len(raw) <= FUNCTION_LIST_FLAGS_OFFSET or raw[0] == 0:
        return 0
    flags = struct.unpack_from("<I", raw, FUNCTION_LIST_FLAGS_OFFSET)[0]
    for stream_type, bit in STREAM_TYPE_FLAGS:
        if flags & bit:
            return stream_type
    return 0


def function_list_flags(blob: bytes | bytearray | memoryview) -> int:
    raw = bytes(blob or b"")
    if len(raw) < FUNCTION_LIST_FLAGS_OFFSET + 4 or raw[:1] == b"\x00":
        return 0
    return int(struct.unpack_from("<I", raw, FUNCTION_LIST_FLAGS_OFFSET)[0])

# QY connect sequence. Camera HTTP UI is port 80; SDK control is 30000.
SDK_CONNECT_SEQUENCE = [
    "Net_Init()",
    "Net_AddCamera(ip)",
    "Net_RegReportMessEx(handle, cb)  # before connect",
    "Net_ConnCameraEx(handle, port=30000, timeout_seconds as unsigned short, user, pass)",
    "Net_ConnCamera(handle, port, timeout_seconds)  # fallback if Ex fails",
    "Net_QueryConnState(handle)  # 0 = connected in this NetSDK build",
    "Net_FuntionListRsp(handle, 800-byte buffer)  # choose stream type from +0x04 flags",
    "Net_RegOffLineClient(handle)",
    "Net_StartVideo(handle, selected stream type, HWND)  # OcxConfig PlaySdk path",
    "Net_SetDrawDataOut(handle, decoded bitmap callback)  # latest frame, no HWND capture",
    "Net_RegImageRecvEx2(handle, cb)  # native plate + JPEG",
    "Net_GetJpgBuffer(handle, ptr, size)  # compatibility fallback only",
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


def is_connected_state(state: int) -> bool:
    """Accept both public QY state encodings used by shipped NetSDK builds."""
    try:
        return int(state) in CONN_STATE_CONNECTED_VALUES
    except (TypeError, ValueError):
        return False


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
        self._live_frame_seq = {}
        self._live_requested_at = {}
        self._video_streams = {}
        self._function_lists = {}
        self._video_locks = {}
        self._video_diagnostics = {}
        self._video_recovery_at = {}
        self._last_event_jpeg = {}
        self._last_event_crop = {}
        self._pending_events = {}
        self._pending_reports = {}
        self._gpio_state = {}
        self._event_media = {}
        self._hwnds = {}
        # QY exposes the same decoded bitmap that PlaySdk paints through
        # Net_SetDrawDataOut. Keep the callback alive and copy only the latest
        # bitmap. This avoids PrintWindow/BitBlt (which is unreliable for
        # off-screen HWNDs) and avoids polling the vendor JPEG function that
        # crashes on some gate-camera firmware.
        self._draw_callbacks = {}
        self._draw_frames = {}
        self._draw_frame_seq = {}
        self._draw_encoded_seq = {}
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
        # Exported by the supplied QY NetSDK build.  The misspelling in the
        # vendor symbol (Funtion) is part of its ABI and is intentional.
        if hasattr(self.dll, "Net_FuntionListRsp"):
            self.dll.Net_FuntionListRsp.argtypes = [c_int, c_void_p]
            self.dll.Net_FuntionListRsp.restype = c_int
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

    def selected_stream_type(self, handle: int) -> int:
        with self._lock:
            row = dict(getattr(self, "_function_lists", {}).get(int(handle)) or {})
        return int(row.get("stream_type") or 0)

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

    def connection_sessions(self) -> list[dict]:
        with self._lock:
            rows = [{"handle": handle, "ip": session["ip"], "state": session["state"]}
                    for handle, session in self._recognition_sessions.items() if session.get("ip")]
        return [{**row, "video": self.video_status(row["handle"])} for row in rows]

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

    def state(self, handle: int):
        state = int(self.dll.Net_QueryConnState(handle))
        with self._lock:
            capture = dict(self._last_capture.get(int(handle)) or {})
        recognition = self._refresh_recognition(handle, observed_state=state)
        return {"state": state, "name": describe_state(state), "last_capture": capture or None,
                "recognition": recognition, "video": self.video_status(handle)}

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
            self._live_received_at.pop(handle, None)
            getattr(self, "_live_frame_seq", {}).pop(handle, None)
            self._live_requested_at.pop(handle, None)
            self._video_streams.pop(handle, None)
            getattr(self, "_function_lists", {}).pop(int(handle), None)
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

    def start_video(self, handle: int, stream_type: int | None = None) -> dict:
        """Start PlaySdk on OcxConfig's capability-selected stream and HWND."""
        if stream_type is None:
            stream_type = self.selected_stream_type(handle)
        def start():
            with self._video_control(handle):
                return self._start_video(handle, stream_type)
        try:
            return self._call_video_ui(start)
        except Exception as exc:
            self._note_video(handle, control_error=str(exc))
            raise

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

    def _note_video(self, handle: int, **fields) -> None:
        with self._lock:
            if not hasattr(self, "_video_diagnostics"):
                self._video_diagnostics = {}
            row = self._video_diagnostics.setdefault(int(handle), {})
            row.update(fields)

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
        self._note_video(
            handle,
            capture_mode="sdk_draw_data",
            draw_data_frames=seq,
            draw_data_width=width,
            draw_data_height=height,
            draw_data_bpp=bit_count,
            draw_data_error="",
        )

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

    def _draw_data_jpeg(self, handle: int) -> bytes:
        handle = int(handle)
        with self._lock:
            frame = self._draw_frames.get(handle)
            seq = int(self._draw_frame_seq.get(handle, 0))
            encoded_seq = int(self._draw_encoded_seq.get(handle, 0))
            cached = self._last_live_jpeg.get(handle, b"")
        if not frame or seq <= encoded_seq:
            return cached if cached[:2] == b"\xff\xd8" else b""
        raw, width, height, bit_count, stride, orientation = frame
        try:
            from PIL import Image

            mode = "BGR" if bit_count == 24 else "BGRX"
            image = Image.frombytes("RGB", (width, height), raw, "raw", mode, stride, orientation)
            output = BytesIO()
            image.save(output, format="JPEG", quality=82, optimize=False)
            jpeg = output.getvalue()
        except Exception as exc:
            self._note_video(handle, draw_data_error=type(exc).__name__)
            return b""
        with self._lock:
            if handle in self._video_handles:
                self._draw_encoded_seq[handle] = seq
                self._last_live_jpeg[handle] = jpeg
                self._live_received_at[handle] = time.monotonic()
                getattr(self, "_live_frame_seq", {})[handle] = seq
        self._note_video(handle, capture_mode="sdk_draw_data", window_capture_rc=None)
        return jpeg

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
        received_at = row.pop("last_jpeg_at", None)
        read_started = row.pop("jpeg_read_started_at", None)
        row["pending_read_ms"] = round(max(0.0, now - read_started) * 1000, 1) if row.get("jpeg_read_pending") and read_started is not None else None
        age = max(0.0, now - received_at) if received_at is not None else None
        row["frame_age_ms"] = round(age * 1000, 1) if age is not None else None
        row.setdefault("frames_received", 0)
        row["state"] = ("LIVE" if age is not None and age <= 5.0 else "START_FAILED"
                        if row.get("start_rc") not in (None, DC_NO_ERROR) else "NO_FRAMES")
        return row

    def live_frame_seq(self, handle: int) -> int:
        """Monotonic source-frame identity for the live JPEG endpoint."""
        with self._lock:
            return int(getattr(self, "_live_frame_seq", {}).get(int(handle), 0) or 0)

    def _start_video(self, handle: int, stream_type: int) -> dict:
        if not hasattr(self.dll, "Net_StartVideo"):
            return {"ok": False, "error": "Net_StartVideo not exported"}
        hwnd = self._hidden_hwnd(handle)
        selected = int(stream_type) if stream_type is not None else self.selected_stream_type(handle)
        self._note_video(handle, control_operation="STARTING", requested_stream=selected)
        rc = int(self.dll.Net_StartVideo(int(handle), selected, hwnd))
        used = selected
        if rc != DC_NO_ERROR:
            # Preserve recovery for cameras without a function-list response,
            # while keeping advertised gate-camera stream types primary.
            other = 0 if selected != 0 else 1
            used = other
            rc = int(self.dll.Net_StartVideo(int(handle), other, hwnd))
        if rc != DC_NO_ERROR and hwnd:
            rc = int(self.dll.Net_StartVideo(int(handle), used, None))
        region_rc = None
        if rc == DC_NO_ERROR and hasattr(self.dll, "Net_ShowPlateRegion"):
            region_rc = int(self.dll.Net_ShowPlateRegion(int(handle), 0))
        draw_data_rc = None
        if rc == DC_NO_ERROR and hasattr(self.dll, "Net_SetDrawDataOut"):
            # Register the decoded-frame callback immediately after the
            # decoder starts. It is independent of the display HWND and keeps
            # gate-camera video moving even when PrintWindow returns black.
            draw_data_rc = self._register_draw_data(int(handle))
        play_window_rc = None
        if rc == DC_NO_ERROR and hwnd and hasattr(self.dll, "Net_AddPlayWindow"):
            # OcxConfig adds its display window after Net_StartVideo.  Keep
            # that ordering: some gate-camera firmware only begins painting
            # after the PlaySdk window is registered explicitly.
            play_window_rc = int(self.dll.Net_AddPlayWindow(int(handle), hwnd))
        if rc != DC_NO_ERROR:
            logging.getLogger("smartpark.hvx").warning("Video start failed: handle=%s stream=%s rc=%s", handle, used, rc)
        self._note_video(handle, control_operation="IDLE", control_error="", start_rc=rc, start_rc_name=describe_rc(rc))
        with self._lock:
            self._video_streams[int(handle)] = used
            self._video_handles.add(int(handle))
            self._live_requested_at[int(handle)] = time.monotonic()
            getattr(self, "_video_recovery_at", {}).pop(int(handle), None)
        # PlaySdk starts its receive/decode workers asynchronously.  Do not
        # call GetJpgBuffer in the same scheduling slice as Net_StartVideo;
        # several QY firmware versions throw a C++ exception during that
        # warm-up window even though the decoder recovers moments later.
        self._note_video(handle, jpeg_not_before=time.monotonic() + 0.35,
                        native_decoder_fault=False)
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

    def stop_video(self, handle: int) -> int:
        def stop():
            with self._video_control(handle):
                with self._lock:
                    self._video_handles.discard(int(handle))
                    self._last_live_jpeg.pop(int(handle), None)
                    getattr(self, "_draw_frames", {}).pop(int(handle), None)
                    getattr(self, "_draw_frame_seq", {}).pop(int(handle), None)
                    getattr(self, "_draw_encoded_seq", {}).pop(int(handle), None)
                    self._live_received_at.pop(int(handle), None)
                    self._live_requested_at.pop(int(handle), None)
                if hasattr(self.dll, "Net_StopVideo"):
                    return int(self.dll.Net_StopVideo(int(handle)))
                return 0
        try:
            return self._call_video_ui(stop)
        except Exception as exc:
            self._note_video(handle, control_error=str(exc))
            return -1

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

    def _capture_window_jpeg(self, handle: int) -> bytes:
        """Capture the PlaySdk-rendered HWND used by OcxConfig for live video.

        The supplied OcxConfig does not poll ``Net_GetJpgBuffer`` for its
        display.  It opens PlaySdk into a real window and lets the decoder's
        paint path update that window.  Some gate-camera firmware builds
        throw a C++ exception from ``Net_GetJpgBuffer`` even though
        ``Net_StartVideo`` succeeded.  Capturing the rendered window keeps us
        on the same stable path as OcxConfig and leaves the recognition
        callback untouched.
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
            output = BytesIO()
            image.save(output, format="JPEG", quality=82, optimize=False)
            jpeg = output.getvalue()
            with self._lock:
                first_window_frame = not bool(self._video_diagnostics.get(int(handle), {}).get("window_capture_logged"))
            self._note_video(handle, capture_mode="play_sdk_hwnd", window_capture_rc=1,
                             window_capture_ms=round((time.monotonic() - started) * 1000, 1),
                             jpeg_error="", window_capture_logged=True,
                             window_capture_width=width, window_capture_height=height)
            self._note_video_read(handle, 0, len(jpeg), "", True)
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

    def _get_jpg_buffer(self, handle: int) -> bytes:
        # Prefer the decoded-frame callback. It is the same PlaySdk decoder
        # used by OcxConfig but does not depend on a hidden/off-screen HWND.
        # Keep the window path as a bounded compatibility fallback for older
        # vendor DLLs that export no draw-data callback or do not invoke it.
        if int(handle) in getattr(self, "_draw_callbacks", {}):
            jpeg = self._draw_data_jpeg(handle)
            if jpeg:
                return jpeg
            with self._lock:
                registered_at = float(self._video_diagnostics.get(int(handle), {}).get("draw_data_registered_at") or 0.0)
                received = int(self._video_diagnostics.get(int(handle), {}).get("draw_data_frames") or 0)
            if received or not registered_at or time.monotonic() - registered_at < 2.0:
                return b""
        # Native QY video is rendered by PlaySdk into the HWND passed to
        # Net_StartVideo, just as in OcxConfig. Do not call Net_GetJpgBuffer on
        # this path: gate-camera firmware can raise 0xe06d7363 there after a
        # successful video start and wedge every other camera's control call.
        if os.name == "nt" and self._hwnds.get(int(handle)):
            return self._capture_window_jpeg(handle)
        if not hasattr(self.dll, "Net_GetJpgBuffer"):
            self._note_video(handle, jpeg_error="API_UNAVAILABLE")
            return b""
        with self._video_lock(handle):
            with self._lock:
                if hasattr(self, "_video_handles") and int(handle) not in self._video_handles:
                    return b""
            buf = ctypes.POINTER(ctypes.c_ubyte)()
            size = ctypes.c_ulong(0)
            rc = None
            error = ""
            data = b""
            self._note_video(handle, jpeg_read_pending=True, jpeg_read_started_at=time.monotonic())
            try:
                rc = int(self.dll.Net_GetJpgBuffer(int(handle), ctypes.byref(buf), ctypes.byref(size)))
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
                    self._note_video(handle, native_decoder_fault=True, native_decoder_error=str(exc))
                    logging.getLogger("smartpark.hvx").error(
                        "Native JPEG decoder fault: handle=%s error=%s; automatic decoder restart disabled",
                        handle, exc,
                    )
            finally:
                if hasattr(self.dll, "Net_FreeBuffer") and buf:
                    try:
                        self.dll.Net_FreeBuffer(ctypes.cast(buf, ctypes.c_void_p))
                    except Exception:
                        logging.getLogger("smartpark.hvx").exception("Video buffer release failed: handle=%s", handle)
                self._note_video_read(handle, rc, int(size.value), error, bool(data))
            return data

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
        interval = 1.0 / max(1.0, min(20.0, float(os.environ.get("SMARTPARK_HVX_JPEG_FPS", "15"))))
        def publish(jpeg):
            with self._lock:
                if handle in self._video_handles:
                    previous = self._last_live_jpeg.get(handle, b"")
                    self._last_live_jpeg[handle] = jpeg
                    # Draw-data frames update freshness when they are encoded.
                    # For the legacy buffer path, only a changed JPEG is proof
                    # that the SDK delivered a new frame; repeated cache reads
                    # must not keep stale video alive.
                    if handle not in getattr(self, "_draw_callbacks", {}) and jpeg != previous:
                        self._live_received_at[handle] = time.monotonic()
                        seq = int(getattr(self, "_live_frame_seq", {}).get(handle, 0) or 0) + 1
                        getattr(self, "_live_frame_seq", {})[handle] = seq
        while self._video_running:
            started = time.monotonic()
            with self._lock:
                if handle not in self._video_handles:
                    break
                requested = self._live_requested_at.get(handle, started)
                not_before = float(getattr(self, "_video_diagnostics", {}).get(handle, {}).get("jpeg_not_before") or 0.0)
            if started - requested > 5.0:
                retry_at = started + 5.0
                time.sleep(.25)
                continue
            if started < not_before:
                time.sleep(min(0.1, not_before - started))
                continue
            jpeg = self._get_jpg_buffer(handle)
            if jpeg:
                publish(jpeg)
                self._note_video(handle, decoder_recovery_attempts=0, recovery_state="STABLE")
                idle = 0
                retry_at = time.monotonic() + 5.0
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
                if window_capture:
                    # Window capture is deliberately non-destructive. Do not
                    # call Net_StopVideo just because PrintWindow has not yet
                    # received a paint; that can wedge PlaySdk on the same
                    # firmware that made Net_GetJpgBuffer unsafe.
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
        with self._lock:
            handles = list(self._video_handles)
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
