import asyncio
import queue
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import api_main
from app.db import Base
from app.infrastructure.media import registry
from app.models import Camera
from app.recognition_worker import _camera_rows
from app.services import mediamtx
from app.services.stream_roles import hvx_profiles
from tools.hvx_sdk_host.hvx_sdk import HVXSDK


JPEG = b"\xff\xd8current\xff\xd9"


def make_sdk():
    sdk = HVXSDK.__new__(HVXSDK)
    sdk._lock = threading.Lock()
    sdk._video_locks = {}
    sdk._video_streams = {}
    sdk._video_handles = {7}
    sdk._video_threads = {}
    sdk._last_live_jpeg = {}
    sdk._live_received_at = {}
    sdk._live_requested_at = {7: 10.0}
    sdk._video_running = True
    sdk._ui_thread = None
    sdk._ui_commands = queue.Queue(maxsize=8)
    sdk._hwnd_queue = queue.Queue()
    sdk._hwnd_ready = {}
    sdk._hwnds = {}
    sdk._pump_messages = Mock()
    sdk._hidden_hwnd = Mock(return_value=123)
    sdk._ensure_camera_pump = Mock()
    sdk.dll = SimpleNamespace(Net_StartVideo=Mock(return_value=0), Net_StopVideo=Mock(return_value=0))
    return sdk


def test_video_start_and_stop_run_on_the_window_owner_thread():
    sdk = make_sdk()
    owners = []
    def native(*args):
        owners.append(threading.current_thread())
        return 0
    sdk.dll.Net_StartVideo.side_effect = native
    sdk.dll.Net_StopVideo.side_effect = native
    try:
        assert sdk.start_video(7)["ok"]
        sdk.stop_video(7)
        assert owners == [sdk._ui_thread, sdk._ui_thread]
        sdk.dll.Net_StartVideo.assert_called_once_with(7, 0, 123)
    finally:
        sdk._video_running = False
        if sdk._ui_thread:
            sdk._ui_thread.join(2)
            assert not sdk._ui_thread.is_alive()


def test_current_frame_is_sampled_once_per_tick_not_drained_in_a_hot_loop(monkeypatch):
    sdk = make_sdk()
    monkeypatch.setenv("SMARTPARK_HVX_JPEG_FPS", "10")
    clock = [10.0]
    arrivals = []
    def frame(handle):
        arrivals.append(clock[0])
        if len(arrivals) == 21:
            sdk._video_running = False
        clock[0] += .005
        return JPEG
    sdk._get_jpg_buffer = frame
    sdk._latest_jpg_buffer = Mock(side_effect=AssertionError("Current-frame API is not a queued stream"))
    with patch("tools.hvx_sdk_host.hvx_sdk.time.monotonic", side_effect=lambda: clock[0]), \
         patch("tools.hvx_sdk_host.hvx_sdk.time.sleep", side_effect=lambda duration: clock.__setitem__(0, clock[0] + duration)):
        sdk._camera_video_loop(7)
    assert len(arrivals) == 21
    assert arrivals[-1] - arrivals[0] >= 1.99
    assert sdk._last_live_jpeg[7] == JPEG
    sdk._latest_jpg_buffer.assert_not_called()
    sdk.dll.Net_StopVideo.assert_not_called()


def test_slow_native_video_control_does_not_hold_the_host_metadata_lock():
    sdk = make_sdk()
    entered = threading.Event()
    release = threading.Event()
    def slow_start(*args):
        entered.set()
        release.wait(2)
        return 0
    sdk.dll.Net_StartVideo.side_effect = slow_start
    caller = threading.Thread(target=lambda: sdk.start_video(7))
    try:
        caller.start()
        assert entered.wait(1)
        assert sdk._lock.acquire(timeout=.1)
        sdk._lock.release()
    finally:
        release.set()
        caller.join(2)
        sdk._video_running = False
        if sdk._ui_thread:
            sdk._ui_thread.join(2)
        assert not caller.is_alive()


def test_unused_camera_does_not_encode_jpegs_or_restart_its_decoder():
    sdk = make_sdk()
    sdk._get_jpg_buffer = Mock()
    with patch("tools.hvx_sdk_host.hvx_sdk.time.monotonic", return_value=20.0), \
         patch("tools.hvx_sdk_host.hvx_sdk.time.sleep", side_effect=lambda duration: setattr(sdk, "_video_running", False)):
        sdk._camera_video_loop(7)
    sdk._get_jpg_buffer.assert_not_called()
    sdk.dll.Net_StopVideo.assert_not_called()


def test_sdk_endpoint_and_telemetry_never_probe_mediamtx():
    with patch.object(registry, "_sdk_camera", return_value=True), \
         patch.object(mediamtx, "running", side_effect=AssertionError("SDK display must not wait for MediaMTX")):
        endpoint = asyncio.run(registry.get_live_endpoint(7))
        telemetry = registry.media_telemetry(7)
    assert endpoint["transport"] == "MJPEG"
    assert telemetry["state"] == "DIRECT"


def test_sdk_unregistration_does_not_repeat_twelve_missing_path_deletions_every_cycle():
    with patch.object(mediamtx, "_sources", {}), patch.object(mediamtx, "_removed_sources", set()), \
         patch.object(mediamtx, "write_config") as write, \
         patch.object(mediamtx, "running", return_value=True), \
         patch.object(mediamtx, "_control_api", return_value=404) as request:
        for _ in range(10):
            mediamtx.unregister_source(7)
        assert request.call_count == 3
        assert write.call_count <= 1


def test_worker_does_not_claim_sdk_cameras_without_mediamtx_paths(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'site.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    try:
        with factory() as database:
            database.add_all([
                Camera(id=1, name="SDK entry", ip_address="10.5.0.1", sdk_handle=0),
                Camera(id=2, name="SDK exit", ip_address="10.5.0.2", stream_profiles=hvx_profiles(1)),
                Camera(id=3, name="RTSP camera", ip_address="10.5.0.3", adapter_id="rtsp"),
            ])
            database.commit()
        with patch("app.db.SessionLocal", factory), \
             patch("app.services.flags.media_mtx_for_camera", return_value=True), \
             patch("app.services.node_scope.camera_in_recognition_scope", return_value=True), \
             patch("app.services.site_policy.site_policy", return_value={}), \
             patch("app.recognition_worker._software_camera", return_value=True):
            assert [row["id"] for row in _camera_rows()] == [3]
    finally:
        engine.dispose()


def test_native_transient_disconnect_does_not_cause_session_teardown(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'site.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with factory() as database:
            database.add(Camera(id=1, name="Entry", ip_address="10.5.0.1", sdk_handle=0))
            database.commit()
        with patch.object(api_main, "short_session", factory), \
             patch.object(api_main, "_hvx_restore_attempts", {}), \
             patch.object(api_main, "apply_sdk_connect", AsyncMock()) as reconnect:
            asyncio.run(api_main._restore_hvx_sessions({"available": True, "connections": [{"handle": 0, "ip": "10.5.0.1", "state": 3}]}))
            reconnect.assert_not_awaited()
    finally:
        engine.dispose()


def test_automatic_recognition_never_reads_minutes_old_evidence_as_a_live_car():
    from app.services.preview import PreviewState

    sample = SimpleNamespace(jpeg=JPEG, received_at=10.0)
    cached = PreviewState(jpeg=JPEG, captured_at=10.0)
    with patch("app.services.media_gateway.gateway.peek_detect", return_value=sample), \
         patch("app.services.media_gateway.gateway.peek_live", return_value=sample), \
         patch.object(api_main, "get_state", return_value=cached), \
         patch.object(api_main.time, "monotonic", return_value=500.0):
        assert api_main._current_recognition_jpeg(7) == b""
        sample.received_at = 499.9
        assert api_main._current_recognition_jpeg(7) == JPEG
