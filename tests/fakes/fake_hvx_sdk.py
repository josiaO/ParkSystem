"""Deterministic fake of the QY/HVX NetSDK.dll for Ubuntu tests.

This fakes the DLL boundary only. The real ``HVXSDK`` class (callbacks,
locks, latest-frame cache, JPEG encode, event queue, GPIO pulse) runs on top
of it, so instrumentation and queueing behaviour are exercised as on Windows.
Win32 parts (hidden HWND, message pump, PrintWindow capture) are skipped by the
host code itself when ``ctypes.windll`` is missing.

Signatures follow ``tools/hvx_sdk_host/hvx_sdk_parts/20_connection.py::_bind``
and the plate-callback byte layout in ``15_protocol.py``. Nothing here is a
claim about how the vendor DLL behaves; delays and faults are knobs.

Usage from a test::

    sdk, dll = make_sdk_and_dll(HVXSDK, vendor_dir, fps=25)
    handle = sdk.add_and_connect("10.0.0.5", 30000, 3, "", "")["handle"]
    dll.emit_plate(handle, "T123ABC")
    dll.gpio_write_delay_ms = 40

Usage from the host (developer machine only)::

    python tools/hvx_sdk_host/hvx_host.py --fake-sdk
"""

from __future__ import annotations

import ctypes
import os
import struct
import threading
import time
from io import BytesIO

if not hasattr(ctypes, "WINFUNCTYPE"):
    # stdcall only exists on 32-bit Windows; cdecl is what Linux ctypes has.
    ctypes.WINFUNCTYPE = ctypes.CFUNCTYPE  # type: ignore[attr-defined]

DC_NO_ERROR = 0
DC_HANDLE_INVALID = 1
DC_REQ_TIMEOUT = 7
IMAGE_USER_INFO_BYTES = 0x44
FUNCTION_LIST_BYTES = 800


class _Fn:
    """A DLL export: callable, accepts argtypes/restype, records calls."""

    def __init__(self, name: str, impl, owner: "FakeNetSDK"):
        self.__name__ = name
        self._impl = impl
        self._owner = owner
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        delay = float(self._owner.delays_ms.get(self.__name__, 0.0) or 0.0)
        if delay:
            time.sleep(delay / 1000.0)
        fault = self._owner.faults.get(self.__name__)
        with self._owner.lock:
            self._owner.calls.append((time.perf_counter_ns(), self.__name__, args))
        if fault is not None:
            return int(fault)
        return self._impl(*args)


def _solid_jpeg(width: int, height: int, shade: int) -> bytes:
    from PIL import Image

    image = Image.new("RGB", (width, height), (shade % 256, 80, 160))
    output = BytesIO()
    image.save(output, format="JPEG", quality=70)
    return output.getvalue()


class _Camera:
    def __init__(self, handle: int, ip: str):
        self.handle = handle
        self.ip = ip
        self.connected = False
        self.video = False
        self.draw_cb = None
        self.image_cb = None
        self.report_cb = None
        self.thread: threading.Thread | None = None
        self.stop = threading.Event()
        self.frozen = threading.Event()
        self.frames = 0
        self.gpio: dict[int, int] = {}
        self.image_id = 0


class FakeNetSDK:
    """Per-camera frame threads at a fixed schedule, plus fault injection."""

    _EXPORTS = (
        "Net_Init", "Net_UNinit", "Net_AddCamera", "Net_DelCamera", "Net_ConnCamera",
        "Net_ConnCameraEx", "Net_DisConnCamera", "Net_QueryConnState", "Net_FuntionListRsp",
        "Net_RegReportMessEx", "Net_RegImageRecvEx", "Net_RegImageRecvEx2", "Net_RegOffLineClient",
        "Net_StartVideo", "Net_StopVideo", "Net_ShowPlateRegion", "Net_AddPlayWindow",
        "Net_SetDrawDataOut", "Net_ImageSnap", "Net_WriteGPIOState", "Net_ReadGPIOState",
        "Net_GateSetup",
    )

    def __init__(self, *, fps: float = 25.0, width: int = 640, height: int = 360,
                 stream_flags: int = 0x20000):
        self.fps = float(fps)
        self.width = int(width)
        self.height = int(height)
        self.stream_flags = int(stream_flags)
        self.lock = threading.Lock()
        self.calls: list = []
        self.cameras: dict[int, _Camera] = {}
        self._next_handle = 1
        # Knobs. ``delays_ms`` sleeps before an export runs; ``faults``
        # replaces its return code. ``callback_delay_ms`` delays the frame
        # callback on the vendor thread (a slow decoder).
        self.delays_ms: dict[str, float] = {}
        self.faults: dict[str, int] = {}
        self.callback_delay_ms = 0.0
        stride = ((self.width * 24 + 31) // 32) * 4
        self._stride = stride
        self._bitmap = ctypes.create_string_buffer(stride * self.height)
        self._bmi = ctypes.create_string_buffer(struct.pack(
            "<IiiHHIIiiII", 40, self.width, self.height, 1, 24, 0, stride * self.height, 0, 0, 0, 0,
        ))
        for name in self._EXPORTS:
            setattr(self, name, _Fn(name, getattr(self, "_" + name), self))

    # -- convenience knobs ---------------------------------------------
    @property
    def gpio_write_delay_ms(self) -> float:
        return float(self.delays_ms.get("Net_WriteGPIOState", 0.0))

    @gpio_write_delay_ms.setter
    def gpio_write_delay_ms(self, value: float) -> None:
        self.delays_ms["Net_WriteGPIOState"] = float(value)

    @property
    def gate_setup_delay_ms(self) -> float:
        return float(self.delays_ms.get("Net_GateSetup", 0.0))

    @gate_setup_delay_ms.setter
    def gate_setup_delay_ms(self, value: float) -> None:
        self.delays_ms["Net_GateSetup"] = float(value)

    def freeze(self, handle: int) -> None:
        self.cameras[int(handle)].frozen.set()

    def resume(self, handle: int) -> None:
        self.cameras[int(handle)].frozen.clear()

    def calls_named(self, name: str) -> list:
        with self.lock:
            return [row for row in self.calls if row[1] == name]

    def shutdown(self) -> None:
        for camera in list(self.cameras.values()):
            camera.stop.set()
        for camera in list(self.cameras.values()):
            if camera.thread is not None:
                camera.thread.join(1.0)

    # -- exports -------------------------------------------------------
    def _Net_Init(self):
        return DC_NO_ERROR

    def _Net_UNinit(self):
        self.shutdown()
        return DC_NO_ERROR

    def _Net_AddCamera(self, ip):
        text = ip.decode("ascii", "ignore") if isinstance(ip, bytes) else str(ip)
        with self.lock:
            handle = self._next_handle
            self._next_handle += 1
            self.cameras[handle] = _Camera(handle, text)
        return handle

    def _camera(self, handle) -> _Camera | None:
        return self.cameras.get(int(handle))

    def _Net_DelCamera(self, handle):
        camera = self.cameras.pop(int(handle), None)
        if camera is not None:
            camera.stop.set()
        return DC_NO_ERROR

    def _Net_ConnCamera(self, handle, port, timeout):
        camera = self._camera(handle)
        if camera is None:
            return DC_HANDLE_INVALID
        camera.connected = True
        return DC_NO_ERROR

    def _Net_ConnCameraEx(self, handle, port, timeout, user, password):
        return self._Net_ConnCamera(handle, port, timeout)

    def _Net_DisConnCamera(self, handle):
        camera = self._camera(handle)
        if camera is not None:
            camera.connected = False
        return DC_NO_ERROR

    def _Net_QueryConnState(self, handle):
        camera = self._camera(handle)
        return 0 if camera is not None and camera.connected else 3

    def _Net_FuntionListRsp(self, handle, buffer):
        if buffer:
            ctypes.memmove(buffer, struct.pack("<II", 0, self.stream_flags), 8)
        return DC_NO_ERROR

    def _Net_RegReportMessEx(self, handle, cb, user):
        camera = self._camera(handle)
        if camera is not None:
            camera.report_cb = cb
        return DC_NO_ERROR

    def _Net_RegImageRecvEx(self, handle, cb, user):
        camera = self._camera(handle)
        if camera is not None:
            camera.image_cb = cb
        return DC_NO_ERROR

    def _Net_RegImageRecvEx2(self, handle, cb, user):
        return self._Net_RegImageRecvEx(handle, cb, user)

    def _Net_RegOffLineClient(self, handle):
        return DC_NO_ERROR

    def _Net_StartVideo(self, handle, stream_type, hwnd):
        camera = self._camera(handle)
        if camera is None:
            return DC_HANDLE_INVALID
        camera.video = True
        if camera.thread is None or not camera.thread.is_alive():
            camera.stop.clear()
            camera.thread = threading.Thread(target=self._frame_loop, args=(camera,),
                                             name=f"fake-netsdk-video-{camera.handle}", daemon=True)
            camera.thread.start()
        return DC_NO_ERROR

    def _Net_StopVideo(self, handle):
        camera = self._camera(handle)
        if camera is not None:
            camera.video = False
            camera.stop.set()
            if camera.thread is not None and camera.thread is not threading.current_thread():
                camera.thread.join(1.0)
            camera.thread = None
        return DC_NO_ERROR

    def _Net_ShowPlateRegion(self, handle, show):
        return DC_NO_ERROR

    def _Net_AddPlayWindow(self, handle, hwnd):
        return DC_NO_ERROR

    def _Net_SetDrawDataOut(self, handle, cb, user):
        camera = self._camera(handle)
        if camera is None:
            return DC_HANDLE_INVALID
        camera.draw_cb = cb
        return DC_NO_ERROR

    def _Net_ImageSnap(self, handle, snap):
        return DC_NO_ERROR

    def _Net_WriteGPIOState(self, handle, index, value):
        camera = self._camera(handle)
        if camera is None:
            return DC_HANDLE_INVALID
        camera.gpio[int(index)] = int(value)
        return DC_NO_ERROR

    def _Net_ReadGPIOState(self, handle, index, out):
        camera = self._camera(handle)
        if camera is None:
            return DC_HANDLE_INVALID
        try:
            out._obj.value = camera.gpio.get(int(index), 0)  # byref(c_ubyte)
        except AttributeError:
            pass
        return DC_NO_ERROR

    def _Net_GateSetup(self, handle, command):
        return DC_NO_ERROR if self._camera(handle) is not None else DC_HANDLE_INVALID

    # -- vendor threads ------------------------------------------------
    def _frame_loop(self, camera: _Camera) -> None:
        """Deliver frames on a fixed schedule (start + n / fps), like a decoder."""
        interval = 1.0 / max(self.fps, 0.1)
        started = time.perf_counter()
        n = 0
        data = ctypes.cast(self._bitmap, ctypes.POINTER(ctypes.c_ubyte))
        while not camera.stop.is_set():
            n += 1
            target = started + n * interval
            delay = target - time.perf_counter()
            if delay > 0:
                camera.stop.wait(delay)
            if camera.stop.is_set():
                return
            if camera.frozen.is_set() or not camera.video or camera.draw_cb is None:
                continue
            if self.callback_delay_ms:
                time.sleep(self.callback_delay_ms / 1000.0)
            camera.frames += 1
            # Encode the frame number into the first pixel row so a test can
            # tell frames apart after JPEG encoding (coarse, 8-level).
            ctypes.memset(self._bitmap, (camera.frames * 32) % 256, self._stride)
            try:
                camera.draw_cb(camera.handle, 0, ctypes.addressof(self._bmi), data,
                               self.width, self.height, None)
            except Exception:
                pass

    def emit_plate(self, handle: int, plate: str, *, score: int = 90,
                   box=(100, 200, 260, 240), jpeg: bytes | None = None) -> int:
        """Call the registered plate callback synchronously, as the vendor thread would."""
        camera = self.cameras[int(handle)]
        if camera.image_cb is None:
            raise RuntimeError("no image callback registered")
        camera.image_id += 1
        info = ctypes.create_string_buffer(max(IMAGE_USER_INFO_BYTES, 128))
        struct.pack_into("<HH", info, 0, self.width, self.height)
        info[8:24] = plate.encode("ascii")[:16].ljust(16, b"\x00")
        struct.pack_into("<HHHH", info, 0x18, *box)
        info[0x24] = 1
        info[0x25] = 1
        info[0x40] = int(score) & 0xFF
        picture = jpeg if jpeg is not None else _solid_jpeg(self.width, self.height, camera.image_id * 40)
        pic_buffer = ctypes.create_string_buffer(picture, len(picture))
        pic = ctypes.create_string_buffer(32)
        # T_PicInfo: uiPanoramaPicLen, uiVehiclePicLen, ptPanoramaPicBuff, ptVehiclePicBuff
        pointer_size = ctypes.sizeof(ctypes.c_void_p)
        struct.pack_into("<II", pic, 0, len(picture), 0)
        struct.pack_into("<Q" if pointer_size == 8 else "<I", pic, 8, ctypes.addressof(pic_buffer))
        # Cast to the pointer types the host registered (T_ImageUserInfo*, T_PicInfo*).
        argtypes = camera.image_cb._argtypes_
        camera.image_cb(camera.handle, camera.image_id, ctypes.cast(info, argtypes[2]),
                        ctypes.cast(pic, argtypes[3]), None)
        return camera.image_id


def _check_pic_layout() -> None:
    """The fake writes T_PicInfo by offset; fail loudly if the layout differs."""
    pointer = ctypes.sizeof(ctypes.c_void_p)
    if pointer not in (4, 8):
        raise RuntimeError("unsupported pointer size")


def make_sdk_and_dll(sdk_class, vendor_dir, **knobs):
    _check_pic_layout()
    dll = FakeNetSDK(**knobs)
    sdk = sdk_class(vendor_dir, dll=dll)
    return sdk, dll


def make_sdk(sdk_class, vendor_dir):
    """Entry point for ``hvx_host.py --fake-sdk``: two connected cameras."""
    fps = float(os.environ.get("SMARTPARK_FAKE_SDK_FPS", "25"))
    sdk, dll = make_sdk_and_dll(sdk_class, vendor_dir, fps=fps)
    sdk.fake_dll = dll
    for ip in ("10.0.0.11", "10.0.0.12"):
        sdk.add_and_connect(ip, 30000, 3, "", "")
    return sdk
