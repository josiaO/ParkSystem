"""Silent video must recover independently of recognition and GUI work."""
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import pytest

from app.services.media_gateway import LocalMediaGateway, CameraLiveSpec


def spec():
    return CameraLiveSpec(id=987, ip='127.0.0.1', username='', password='',
                          rtsp_url='rtsp://camera/configured-sub', sdk_handle=7)


@pytest.mark.asyncio
async def test_sdk_without_first_jpeg_returns_for_fallback():
    gateway = LocalMediaGateway()
    row = gateway._session_for(spec())
    row.viewers = 1
    times = iter([0., 0., 4.])
    with patch('app.services.media_gateway.HVXHostClient', return_value=SimpleNamespace(live_jpeg=AsyncMock(return_value=b''))), \
         patch('app.services.media_gateway.time.monotonic', side_effect=lambda: next(times)), \
         patch('app.services.media_gateway.settings.stream_read_timeout_seconds', 3.):
        assert await gateway._sdk_frames(row) is False
    assert 'RTSP fallback' in row.last_error


@pytest.mark.asyncio
async def test_sdk_video_failure_tries_rtsp_without_touching_recognition():
    gateway = LocalMediaGateway()
    row = gateway._session_for(spec())
    row.viewers = 1
    async def rtsp(_row):
        row.viewers = 0
        return True
    with patch.object(gateway, '_sdk_frames', AsyncMock(return_value=False)) as sdk, \
         patch.object(gateway, '_rtsp_frames', AsyncMock(side_effect=rtsp)) as stream, \
         patch.object(gateway, '_http_stills', AsyncMock()) as stills:
        await gateway._produce(row)
    sdk.assert_awaited_once()
    stream.assert_awaited_once()
    stills.assert_not_awaited()


@pytest.mark.asyncio
async def test_configured_rtsp_url_is_tried_before_guessed_vendor_paths():
    gateway = LocalMediaGateway()
    row = gateway._session_for(spec())
    row.viewers = 1
    urls = []
    async def frames(url, **kwargs):
        urls.append(url)
        yield b'\xff\xd8frame\xff\xd9'
        row.viewers = 0
    with patch.object(gateway, 'ffmpeg_jpeg_stream', frames):
        assert await gateway._rtsp_frames(row)
    assert urls == ['rtsp://camera/configured-sub']


def method(name, cls='CameraLivePane'):
    path = Path('app/desktop/main.py')
    tree = ast.parse(path.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
    fn = next(n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == name)
    env = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(path), 'exec'), env)
    return env[name], env


def test_switching_camera_does_not_wait_for_reader_or_call_api():
    stop, env = method('_stop_mjpeg')
    stream = SimpleNamespace(stop=Mock(), wait=Mock(side_effect=AssertionError('GUI waited')))
    pane = SimpleNamespace(_mjpeg=stream)
    stop(pane)
    stream.stop.assert_called_once()
    assert pane._mjpeg is None


def test_clean_stream_eof_requests_reconnect():
    from contextlib import nullcontext
    from app.desktop.frame_mailbox import DisplayMailbox
    from app.desktop.api import api
    import time
    run, env = method('run', cls='MjpegStream')
    response = SimpleNamespace(status_code=200, iter_bytes=lambda: iter([]))
    client = SimpleNamespace(stream=lambda *a, **k: nullcontext(response), close=Mock())
    env.update(httpx=SimpleNamespace(Client=lambda **kw: client, Timeout=lambda **kw: kw),
               BASE='http://local', api=SimpleNamespace(_headers=lambda: {}), time=time)
    thread = SimpleNamespace(_stop=False, camera_id=1, mailbox=DisplayMailbox(), failed=Mock(), frame=Mock())
    run(thread)
    thread.failed.emit.assert_called_once_with('Video stream ended; reconnecting')
    client.close.assert_called_once()


def test_sdk_does_not_serve_frozen_cache_as_live_video():
    import threading
    from tools.hvx_sdk_host.hvx_sdk import HVXSDK
    sdk = HVXSDK.__new__(HVXSDK)
    sdk._lock = threading.Lock()
    sdk._last_live_jpeg = {7: b'\xff\xd8live'}
    sdk._last_live_at = {7: 10.0}
    with patch('tools.hvx_sdk_host.hvx_sdk.time.monotonic', return_value=11.0):
        assert sdk.live_jpeg_for(7) == b'\xff\xd8live'
    with patch('tools.hvx_sdk_host.hvx_sdk.time.monotonic', return_value=14.0):
        assert sdk.live_jpeg_for(7) == b''
    assert sdk._last_live_jpeg[7] == b'\xff\xd8live'


@pytest.mark.asyncio
async def test_mediamtx_fallback_waits_for_old_decoder_cleanup():
    from app.services import mediamtx_live
    released = asyncio.Event()
    started = asyncio.Event()
    async def consume():
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            released.set()
    task = asyncio.create_task(consume())
    await started.wait()
    mediamtx_live._consumers[987] = task
    stopped = mediamtx_live.stop_live_consumer(987)
    assert stopped is task
    await asyncio.gather(stopped, return_exceptions=True)
    assert released.is_set()
    assert 987 not in mediamtx_live._consumers


def test_additional_viewer_reuses_active_direct_fallback():
    from dataclasses import replace
    from app.services import preview
    camera = replace(spec(), sdk_handle=None)
    row = SimpleNamespace(producer=SimpleNamespace(done=lambda: False), viewers=1, last_view_at=0.)
    with patch.object(preview.gateway, 'session', return_value=row), \
         patch('app.infrastructure.media.registry.mediamtx_live_active', side_effect=AssertionError('second producer')):
        preview.ensure_mjpeg_source(camera)
    preview._last_view.pop(camera.id, None)
