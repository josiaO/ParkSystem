import asyncio
import ctypes
import struct
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Camera
from app import recognition_worker
from app import api_main
from app.services import mediamtx_detect
from app.infrastructure.media import registry
from tools.hvx_sdk_host.hvx_sdk import HVXSDK, HVXSDKError


@pytest.mark.parametrize("state", ["STARTING", "RECONNECTING", "DEGRADED", "STALLED"])
def test_worker_claim_without_healthy_frames_does_not_disable_site_ocr(tmp_path, state):
    engine = create_engine(f"sqlite:///{tmp_path / 'site.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    try:
        with factory() as database:
            database.add(Camera(id=83, name="Dahua", ip_address="10.8.0.83", adapter_id="dahua"))
            database.commit()
        health = {
            "ok": True,
            "claimed_camera_ids": [83],
            "cameras": [{"camera_id": 83, "state": state}],
        }
        with patch("app.db.SessionLocal", factory), \
             patch("app.services.flags.flags", return_value={"fastalpr_new_pipeline_enabled": True}), \
             patch("app.infrastructure.media.registry.mediamtx_detect_active", return_value=True), \
             patch.object(recognition_worker, "_software_camera", return_value=True), \
             patch.object(recognition_worker, "worker_health", return_value=health), \
             patch.object(recognition_worker, "_owns_cache", {}):
            assert not recognition_worker.worker_owns_software_reads(83)
            ready = AsyncMock(return_value=True)
            read = AsyncMock(return_value={"ok": True, "best": {"plate": "T123ABC"}})
            with patch.object(api_main, "short_session", factory), \
                 patch.object(api_main, "_current_recognition_jpeg", return_value=b"\xff\xd8frame"), \
                 patch.object(api_main, "_video_arrival_ready", ready), \
                 patch.object(api_main, "_run_local_alpr", read), \
                 patch.object(api_main, "_note_arrival_result", return_value=True), \
                 patch.object(api_main, "_alpr_fp", {}):
                asyncio.run(api_main._maybe_local_ipcam_alpr(83))
            ready.assert_awaited_once()
            read.assert_awaited_once()
            health["cameras"][0].update(state="READY", last_frame_at=time.time(), last_inference_at=time.time())
            recognition_worker._owns_cache.clear()
            assert recognition_worker.worker_owns_software_reads(83)
            health["cameras"][0].update(state="STALLED", last_frame_at=time.time())
            recognition_worker._owns_cache.clear()
            # A slow native inference call still owns its decoder lane; Site
            # Service must not start a second FastALPR instance beside it.
            assert recognition_worker.worker_owns_software_reads(83)
            health["cameras"][0]["last_frame_at"] -= 60
            recognition_worker._owns_cache.clear()
            assert not recognition_worker.worker_owns_software_reads(83)
    finally:
        engine.dispose()


def test_site_detect_consumer_uses_path_from_media_owner_not_local_globals():
    with patch("app.infrastructure.media.registry.media_telemetry", return_value={
        "roles": {"DETECT": {"mediamtx_path": "cam83_detect", "registered": True}},
    }), patch("app.services.mediamtx.detect_endpoint", return_value={"rtsp": "rtsp://127.0.0.1:8554/cam83"}):
        assert mediamtx_detect._detect_url(83) == "rtsp://127.0.0.1:8554/cam83_detect"


@pytest.mark.parametrize("registered", [False, True])
def test_running_mediamtx_without_camera_path_is_not_a_detect_source(registered):
    with patch.object(registry, "_camera_enabled", return_value=True), \
         patch.object(registry, "_sdk_camera", return_value=False), \
         patch.object(registry.mediamtx, "running", return_value=True), \
         patch.object(registry, "media_telemetry", return_value={
             "roles": {"DETECT": {"registered": registered}},
         }):
        assert registry.mediamtx_detect_active(83) is registered


def sdk_reader(native):
    sdk = HVXSDK.__new__(HVXSDK)
    sdk._lock = threading.Lock()
    sdk._video_locks = {}
    sdk._last_live_jpeg = {}
    sdk._live_received_at = {}
    sdk._video_streams = {}
    sdk._hwnds = {}
    sdk._recognition_sessions = {}
    sdk._report_cbs = {}
    sdk._image_cbs = {}
    sdk._last_capture = {}
    sdk._video_handles = {0}
    sdk._live_requested_at = {}
    sdk._function_lists = {}
    sdk._video_diagnostics = {}
    sdk._last_event_jpeg = {}
    sdk._last_event_crop = {}
    sdk._pending_events = {}
    sdk._pending_reports = {}
    sdk._gpio_state = {}
    sdk._event_media = {}
    sdk.dll = SimpleNamespace(Net_GetJpgBuffer=native, Net_FreeBuffer=Mock(return_value=0))
    return sdk


def test_sdk_failure_is_not_an_undifferentiated_empty_frame():
    sdk = sdk_reader(Mock(return_value=7))
    assert sdk._get_jpg_buffer(0) == b""
    video = sdk.video_status(0)
    assert video["jpeg_rc"] == 7
    assert video["jpeg_error"] == "SDK_ERROR"
    assert video["state"] == "NO_FRAMES"
    assert video["frames_received"] == 0


def test_windows_native_reader_uses_the_play_sdk_window_instead_of_jpg_polling():
    native = Mock(side_effect=OSError("the vendor JPEG poll must not run"))
    sdk = sdk_reader(native)
    sdk._hwnds[0] = 123
    with patch.object(__import__("tools.hvx_sdk_host.hvx_sdk", fromlist=["os"]).os, "name", "nt"), \
         patch.object(sdk, "_capture_window_jpeg", return_value=b"\xff\xd8window\xff\xd9") as capture:
        assert sdk._get_jpg_buffer(0) == b"\xff\xd8window\xff\xd9"
    capture.assert_called_once_with(0)
    native.assert_not_called()


@pytest.mark.parametrize("blob,reason", [(b"", "EMPTY_BUFFER"), (b"not-jpeg", "INVALID_JPEG"), (b"\xff\xd8frame", "")])
def test_sdk_buffer_result_is_observable_and_freed(blob, reason):
    buffer = ctypes.create_string_buffer(blob)
    def native(handle, output, size):
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.addressof(buffer)
        ctypes.cast(size, ctypes.POINTER(ctypes.c_ulong))[0] = len(blob)
        return 0
    sdk = sdk_reader(native)
    assert sdk._get_jpg_buffer(0) == (blob if not reason else b"")
    video = sdk.video_status(0)
    assert video["jpeg_error"] == reason
    assert video["jpeg_bytes"] == len(blob)
    assert video["frames_received"] == (0 if reason else 1)
    sdk.dll.Net_FreeBuffer.assert_called_once()


def test_sdk_read_cannot_overlap_decoder_restart():
    native = Mock(return_value=7)
    sdk = sdk_reader(native)
    lock = sdk._video_lock(0)
    entered = threading.Event()
    finished = threading.Event()
    def read():
        entered.set()
        sdk._get_jpg_buffer(0)
        finished.set()
    with lock:
        reader = threading.Thread(target=read)
        reader.start()
        assert entered.wait(1)
        assert not finished.wait(.05)
        native.assert_not_called()
    reader.join(1)
    assert not reader.is_alive()
    native.assert_called_once()


def test_sdk_diagnostic_records_native_exceptions_without_crashing():
    sdk = sdk_reader(Mock(side_effect=OSError("decoder failed")))
    assert sdk._get_jpg_buffer(0) == b""
    assert sdk.video_status(0)["jpeg_error"] == "OSError"


def test_play_sdk_draw_data_callback_produces_jpeg_without_window_capture():
    sdk = HVXSDK.__new__(HVXSDK)
    sdk._lock = threading.Lock()
    sdk._draw_frames = {}
    sdk._draw_frame_seq = {}
    sdk._draw_encoded_seq = {}
    sdk._last_live_jpeg = {}
    sdk._live_received_at = {}
    sdk._video_handles = {0}
    sdk._video_diagnostics = {}

    # Two rows of a bottom-up 24-bit BGR DIB. Each row is padded to 8 bytes.
    dib = ctypes.create_string_buffer(
        struct.pack("<IiiHHIIiiII", 40, 2, 2, 1, 24, 0, 16, 0, 0, 0, 0)
    )
    pixels = ctypes.create_string_buffer(
        bytes((0, 0, 255, 0, 255, 0, 0, 0, 255, 0, 0, 255, 255, 255, 255, 0))
    )
    sdk._on_draw_data(
        0,
        None,
        ctypes.cast(dib, ctypes.c_void_p),
        ctypes.cast(pixels, ctypes.POINTER(ctypes.c_ubyte)),
        2,
        2,
        None,
    )

    jpeg = sdk._draw_data_jpeg(0)
    assert jpeg.startswith(b"\xff\xd8")
    assert jpeg.endswith(b"\xff\xd9")
    assert sdk.video_status(0)["capture_mode"] == "sdk_draw_data"


def test_native_decoder_fault_reopens_only_that_camera():
    sdk = HVXSDK.__new__(HVXSDK)
    sdk._lock = threading.Lock()
    sdk._video_locks = {}
    sdk._video_streams = {7: 1}
    sdk._video_handles = {7, 8}
    sdk._video_threads = {}
    sdk._last_live_jpeg = {}
    sdk._live_received_at = {}
    sdk._live_requested_at = {7: 10.0, 8: 10.0}
    sdk._video_diagnostics = {7: {"native_decoder_fault": True}}
    sdk._hwnds = {}
    sdk._call_video_ui = lambda operation: operation()
    sdk._start_video = Mock(return_value={"ok": True, "stream_type": 1})
    sdk.dll = SimpleNamespace(Net_StopVideo=Mock(return_value=0))
    assert sdk._recover_video_decoder(7)
    sdk.dll.Net_StopVideo.assert_called_once_with(7)
    sdk._start_video.assert_called_once_with(7, 1)
    assert 8 in sdk._video_handles
    assert not sdk._video_diagnostics[7]["native_decoder_fault"]


def test_video_control_times_out_instead_of_waiting_forever_for_native_read():
    sdk = sdk_reader(Mock())
    sdk._call_video_ui = lambda operation: operation()
    lock = Mock()
    lock.acquire.return_value = False
    sdk._video_locks[0] = lock
    with pytest.raises(HVXSDKError, match="decoder is busy"):
        sdk.start_video(0)
    lock.acquire.assert_called_once_with(timeout=1.0)
    assert "decoder is busy" in sdk.video_status(0)["control_error"]


def test_sdk_error_buffer_is_freed_even_when_native_call_fails():
    buffer = ctypes.create_string_buffer(b"failed")
    def native(handle, output, size):
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.addressof(buffer)
        return 7
    sdk = sdk_reader(native)
    assert sdk._get_jpg_buffer(0) == b""
    sdk.dll.Net_FreeBuffer.assert_called_once()


def test_blocked_camera_does_not_prevent_other_decoders_shutting_down():
    sdk = sdk_reader(Mock())
    sdk._video_handles = {0, 1}
    sdk.initialized = True
    sdk.dll.Net_UNinit = Mock()
    sdk.stop_video = Mock(side_effect=[HVXSDKError("busy"), 0])
    sdk.close()
    assert sdk.stop_video.call_count == 2
    sdk.dll.Net_UNinit.assert_not_called()


def test_timed_out_start_keeps_native_operation_serialized_until_it_finishes():
    sdk = sdk_reader(Mock(return_value=7))
    sdk._video_handles = set()
    sdk._live_requested_at = {}
    sdk._hidden_hwnd = Mock(return_value=123)
    sdk._ensure_camera_pump = Mock()
    entered = threading.Event()
    release = threading.Event()
    completed = threading.Event()
    operations = []
    def start(*args):
        entered.set()
        release.wait(2)
        return 0
    sdk.dll.Net_StartVideo = Mock(side_effect=start)
    def timed_out(operation):
        worker = threading.Thread(target=operation)
        operations.append(worker)
        worker.start()
        assert entered.wait(1)
        raise HVXSDKError("Video control timed out")
    sdk._call_video_ui = timed_out
    def read():
        sdk._get_jpg_buffer(0)
        completed.set()
    reader = None
    try:
        with pytest.raises(HVXSDKError, match="timed out"):
            sdk.start_video(0)
        reader = threading.Thread(target=read)
        reader.start()
        assert not completed.wait(.05)
        sdk.dll.Net_GetJpgBuffer.assert_not_called()
    finally:
        release.set()
        for worker in operations:
            worker.join(1)
            assert not worker.is_alive()
        if reader is not None:
            reader.join(1)
            assert not reader.is_alive()


def test_shutdown_keeps_window_owner_alive_until_video_stops():
    sdk = sdk_reader(Mock())
    sdk._video_handles = {0}
    sdk._video_running = True
    sdk.initialized = True
    sdk.dll.Net_UNinit = Mock()
    def stop(handle):
        assert sdk._video_running
        return 0
    sdk.stop_video = stop
    sdk.close()
    assert not sdk._video_running
    sdk.dll.Net_UNinit.assert_called_once()


def test_camera_session_is_not_deleted_when_decoder_cannot_stop():
    sdk = sdk_reader(Mock())
    sdk.stop_video = Mock(return_value=-1)
    sdk._connection_results = {"camera": {"result": {"handle": 0}}}
    sdk.dll.Net_DisConnCamera = Mock()
    with pytest.raises(HVXSDKError, match="session was retained"):
        sdk.disconnect(0)
    assert "camera" in sdk._connection_results
    sdk.dll.Net_DisConnCamera.assert_not_called()


def test_forced_disconnect_releases_session_when_decoder_cannot_stop():
    sdk = sdk_reader(Mock())
    sdk.stop_video = Mock(return_value=-1)
    sdk._connection_results = {"camera": {"result": {"handle": 0}}}
    sdk._video_handles = {0}
    sdk.dll.Net_DisConnCamera = Mock(return_value=0)
    assert sdk.disconnect(0, force=True) == 0
    assert "camera" not in sdk._connection_results
    sdk.dll.Net_DisConnCamera.assert_called_once_with(0)


def test_waiting_jpeg_read_does_not_use_a_stopped_decoder():
    sdk = sdk_reader(Mock(return_value=7))
    sdk._video_handles = {0}
    entered = threading.Event()
    def read():
        entered.set()
        sdk._get_jpg_buffer(0)
    with sdk._video_lock(0):
        reader = threading.Thread(target=read)
        reader.start()
        assert entered.wait(1)
        sdk._video_handles.clear()
    reader.join(1)
    assert not reader.is_alive()
    sdk.dll.Net_GetJpgBuffer.assert_not_called()
