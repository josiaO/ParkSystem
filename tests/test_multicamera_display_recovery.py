import asyncio
from dataclasses import replace
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.infrastructure.media import registry
from app.models import Camera
from app.services.media_gateway import CameraLiveSpec, LocalMediaGateway
from app.services.stream_roles import hvx_profiles
from tools.hvx_sdk_host.hvx_sdk import HVXSDK


JPEG = b"\xff\xd8live\xff\xd9"


@pytest.mark.parametrize("handle,profiles", [(7, {}), (None, hvx_profiles(7))])
def test_sdk_cameras_never_advertise_nonexistent_whep_paths(handle, profiles):
    camera = Camera(id=2, sdk_handle=handle, stream_profiles=profiles)
    database = SimpleNamespace(get=lambda model, key: camera)
    config = {"media_gateway_enabled": True, "live_view_provider": "MEDIAMTX", "webrtc_live_enabled": True}
    with patch.object(registry, "_migration_flags", return_value=config), \
         patch.object(registry, "media_mtx_for_camera", return_value=True), \
         patch.object(registry.mediamtx, "running", return_value=True), \
         patch.object(registry.mediamtx, "live_endpoint") as whep, \
         patch.object(registry.gateway, "get_live_endpoint", AsyncMock(return_value={"transport": "MJPEG", "path": "/cameras/2/live.mjpeg"})):
        assert not registry.mediamtx_live_active(2, database)
        assert not registry.mediamtx_detect_active(2, database)
        endpoint = asyncio.run(registry.get_live_endpoint(2, database))
    assert endpoint["transport"] == "MJPEG"
    assert endpoint["path"] == "/cameras/2/live.mjpeg"
    assert endpoint["state"] == "DIRECT"
    assert not endpoint["mediamtx_selected"]
    whep.assert_not_called()


def test_reconnected_handle_replaces_only_its_existing_producer():
    async def run():
        gateway = LocalMediaGateway()
        calls = []
        async def read(handle):
            calls.append(handle)
            return JPEG + bytes([handle])
        entry = CameraLiveSpec(1, "entry", "", "", "", 7, need_detect=True)
        exit_camera = replace(entry, id=2, ip="exit", sdk_handle=8)
        with patch("app.services.media_gateway.HVXHostClient") as host:
            host.return_value.live_jpeg = AsyncMock(side_effect=read)
            try:
                gateway.ensure_producer(entry)
                gateway.ensure_producer(exit_camera)
                await asyncio.sleep(.02)
                old = gateway.session(1).producer
                neighbor = gateway.session(2).producer
                updated = replace(entry, sdk_handle=9)
                gateway._session_for(updated)
                gateway.ensure_producer(updated)
                await asyncio.sleep(.06)
                assert old.cancelled()
                assert gateway.session(1).producer is not old
                assert gateway.session(2).producer is neighbor
                assert not neighbor.done()
                assert 9 in calls and 8 in calls
                assert gateway.session(1).live.latest().jpeg == JPEG + b"\x09"
                current = gateway.session(1).producer
                gateway.ensure_producer(replace(updated, need_detect=False))
                assert gateway.session(1).producer is current
            finally:
                gateway.stop_all()
                await asyncio.sleep(0)
    asyncio.run(run())


def make_sdk():
    sdk = HVXSDK.__new__(HVXSDK)
    sdk._lock = threading.Lock()
    sdk._last_live_jpeg = {8: JPEG + b"neighbor"}
    sdk._live_received_at = {8: 100.0}
    sdk._live_requested_at = {}
    sdk._video_streams = {7: 1, 8: 1}
    sdk._video_locks = {}
    sdk._video_diagnostics = {}
    sdk._video_handles = {8}
    sdk._video_retry_handles = set()
    sdk._video_retry_at = {}
    sdk._video_threads = {}
    sdk._video_running = True
    sdk._hidden_hwnd = Mock(return_value=123)
    sdk._call_video_ui = lambda operation: operation()
    sdk._ensure_camera_pump = Mock()
    sdk.dll = SimpleNamespace(Net_StartVideo=Mock(return_value=0), Net_StopVideo=Mock(),
                              Net_ShowPlateRegion=Mock(return_value=0), Net_ImageSnap=Mock(),
                              Net_DisConnCamera=Mock(), Net_GateSetup=Mock())
    return sdk


def test_failed_video_start_is_not_advertised_as_live_and_keeps_a_retry_lane():
    sdk = make_sdk()
    sdk.dll.Net_StartVideo.side_effect = [7, 7, 7, 0]
    assert not sdk.start_video(7)["ok"]
    assert 7 not in sdk._video_handles
    assert 7 in sdk._video_retry_handles
    sdk._ensure_camera_pump.assert_called_once_with(7)
    assert sdk.dll.Net_StartVideo.call_count == 3
    assert sdk.dll.Net_StopVideo.call_count == 2
    assert sdk.live_jpeg_for(7) == b""
    assert sdk._last_live_jpeg[8] == JPEG + b"neighbor"
    sdk.dll.Net_ImageSnap.assert_not_called()
    sdk.dll.Net_DisConnCamera.assert_not_called()
    sdk.dll.Net_GateSetup.assert_not_called()


def test_host_does_not_serve_a_stale_live_cache_or_a_vehicle_snapshot():
    sdk = make_sdk()
    sdk._last_event_jpeg = {8: JPEG + b"snapshot"}
    with patch("tools.hvx_sdk_host.hvx_sdk.time.monotonic", return_value=101.0):
        assert sdk.live_jpeg_for(8) == JPEG + b"neighbor"
    with patch("tools.hvx_sdk_host.hvx_sdk.time.monotonic", return_value=106.0):
        assert sdk.live_jpeg_for(8) == b""
    sdk.stop_video(8)
    assert 8 not in sdk._video_handles
    assert 8 not in sdk._last_live_jpeg


def test_simultaneous_connections_create_one_message_pump():
    sdk = make_sdk()
    sdk._ui_thread = None
    sdk._ui_loop = lambda: None
    thread = Mock()
    thread.is_alive.return_value = True
    with patch("tools.hvx_sdk_host.hvx_sdk.threading.Thread", return_value=thread) as create:
        sdk._ensure_ui_thread()
        sdk._ensure_ui_thread()
    create.assert_called_once()
    thread.start.assert_called_once()


def test_live_status_requires_recent_arrivals_not_a_historical_cache():
    from app.services import preview

    row = preview.PreviewState(jpeg=JPEG, captured_at=10.0)
    with patch.object(preview, "get_state", return_value=row), \
         patch.object(preview.gateway, "session", return_value=None), \
         patch.object(preview.time, "monotonic", return_value=100.0):
        assert not preview.live_is_current(2)
    session = SimpleNamespace(last_received_at=99.0)
    with patch.object(preview, "get_state", return_value=row), \
         patch.object(preview.gateway, "session", return_value=session), \
         patch.object(preview.time, "monotonic", return_value=100.0):
        assert preview.live_is_current(2)
