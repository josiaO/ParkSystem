"""Behavior checks for bounded evidence, current-frame crops and live UI work."""
import asyncio
import threading
from collections import OrderedDict
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.desktop.frame_mailbox import ImageRequestState
from tools.hvx_sdk_host.hvx_sdk import HVXSDK


def test_callback_tokens_keep_reused_vendor_ids_and_cameras_separate():
    sdk = HVXSDK.__new__(HVXSDK)
    sdk._lock = threading.Lock()
    sdk._last_capture = {}
    sdk._last_event_jpeg = {}
    sdk._last_event_crop = {}
    sdk._pending_events = {}
    sdk._event_media = OrderedDict()
    def emit(handle, jpeg, crop):
        pic = SimpleNamespace(contents=SimpleNamespace(ptPanoramaPicBuff=jpeg,
            uiPanoramaPicLen=len(jpeg), ptVehiclePicBuff=crop, uiVehiclePicLen=len(crop)))
        sdk._copy_buffer = lambda ptr, length: ptr
        sdk._on_image(handle, 0, None, pic, None)
        return sdk._last_capture[handle]['capture_token']
    first = emit(1, b'\xff\xd8first', b'\xff\xd8crop1')
    second = emit(1, b'\xff\xd8second', b'\xff\xd8crop2')
    emit(2, b'\xff\xd8other', b'\xff\xd8othercrop')
    assert first != second
    assert sdk.event_jpeg_for(1, capture_token=first) == b'\xff\xd8first'
    assert sdk.event_crop_for(1, capture_token=second) == b'\xff\xd8crop2'
    assert sdk.event_crop_for(2, capture_token=second) == b''
    assert sdk.event_jpeg_for(1, 0) == b''
    assert sdk.event_jpeg_for(1, 123) == b''
    assert sdk.event_jpeg_for(1, capture_token='missing') == b''
    for i in range(1000):
        emit(1, b'\xff\xd8frame', b'\xff\xd8crop')
    assert len(sdk._event_media) == 128
    assert len(sdk._pending_events[1]) == 64
    assert sdk.event_jpeg_for(1, capture_token=first) == b''
    with patch("tools.hvx_sdk_host.hvx_sdk.EVENT_MEDIA_MAX_BYTES", 100):
        for _ in range(30):
            emit(1, b"\xff\xd8" + b"x" * 20, b"\xff\xd8" + b"y" * 20)
    assert sum(len(v[1]) + len(v[2]) for v in sdk._event_media.values()) <= 100


def test_desktop_evidence_fetches_are_bounded_and_reject_obsolete_replies():
    state = ImageRequestState()
    assert state.request((1, 'first'))
    for _ in range(10000):
        assert not state.request((1, 'first'))
    assert not state.request((2, 'next-camera'))
    assert not state.complete((1, 'first'), True)
    assert state.request((2, 'next-camera'))
    assert not state.complete((2, 'next-camera'), False)
    assert state.request((2, 'next-camera'))
    assert state.complete((2, 'next-camera'), True)
    assert not state.request((2, 'next-camera'))
    assert not state.request(None)
    assert state.shown is None


def test_desktop_live_pane_has_vehicle_snapshot_and_plate_crop_panels():
    from pathlib import Path

    source = Path("app/desktop/main.py").read_text(encoding="utf-8")
    pane = source.split("class CameraLivePane", 1)[1].split("class Cameras", 1)[0]
    assert 'self.snapshot=QLabel("Vehicle snapshot")' in pane
    assert 'self.crop=QLabel("Plate crop")' in pane
    assert '_request_evidence("snapshot", snapshot, self.snapshot)' in pane
    assert '_request_evidence("crop", crop, self.crop)' in pane


def test_video_presence_uses_current_detection_even_with_old_display_box():
    from app.api_main import _video_arrival_ready
    from app.services.camera_framing import gate_for
    from app.services import preview
    camera = SimpleNamespace(id=98765)
    preview.remember_plate_box(camera.id, dict(x1=10,y1=10,x2=80,y2=30,image_width=200,image_height=100))
    visit = SimpleNamespace(observe=Mock(), state='IDLE')
    with patch('app.api_main._detect_due', return_value=True), \
         patch('app.api_main._mark_detect'), \
         patch('app.services.alpr.locate_plate_boxes', return_value=([], {'available':True})) as locate, \
         patch('app.services.recognition_runtime.runtime.lane', return_value=SimpleNamespace(visit=visit)):
        assert not asyncio.run(_video_arrival_ready(camera, b'current-frame'))
    locate.assert_called_once_with(b'current-frame')
    assert visit.observe.call_args.kwargs['presence'] is False
    assert preview.held_plate_box(camera.id) is None
    gate_for(camera.id).reset()
    preview._state.pop(camera.id, None)


def test_arrival_ocr_receives_plate_pixels_not_car_pixels():
    import cv2
    import numpy as np
    from app.services.alpr import recognize_arrival_bytes
    car = np.zeros((600, 1000, 3), dtype=np.uint8)
    car[250:350, 350:650] = 220
    ok, encoded = cv2.imencode('.jpg', car)
    assert ok
    ocr = Mock(return_value=SimpleNamespace(text='T285DQP', confidence=0.99))
    engine = SimpleNamespace(ocr=SimpleNamespace(predict=ocr))
    box = dict(x1=350,y1=250,x2=650,y2=350,confidence=0.99)
    with patch('app.services.alpr._load_engine', return_value=engine), \
         patch('app.services.alpr.locate_plate_boxes', side_effect=AssertionError('duplicate detection')):
        result = recognize_arrival_bytes(encoded.tobytes(), detected_boxes=[box], save_evidence=False)
    assert ocr.call_count == 1
    crop = ocr.call_args.args[0]
    assert crop.shape[0] < 600 and crop.shape[1] < 1000
    assert crop.mean() > car.mean()
    assert result['best']['plate_normalized'] == 'T285DQP'


def test_cancelled_inference_keeps_ownership_until_native_thread_finishes():
    from app.services.inference_thread import run_inference
    started, release = threading.Event(), threading.Event()
    def native():
        started.set()
        assert release.wait(3)
    async def scenario():
        task = asyncio.create_task(run_inference(native))
        try:
            for _ in range(200):
                if started.is_set():
                    break
                await asyncio.sleep(0.005)
            assert started.is_set()
            task.cancel()
            await asyncio.sleep(0.02)
            assert not task.done()
        finally:
            release.set()
        try:
            await task
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError('cancellation was swallowed')
    asyncio.run(scenario())


def test_rolling_evidence_changes_url_and_versioned_url_loads(tmp_path):
    from unittest.mock import PropertyMock
    from app.api_main import _publish_live_still
    from app.config import Settings
    from app.services.captures import _jpeg_from_ref
    with patch.object(Settings, 'media_dir', new_callable=PropertyMock, return_value=tmp_path):
        first = _publish_live_still(77, 'crops', b'\xff\xd8first')
        second = _publish_live_still(77, 'crops', b'\xff\xd8second')
        assert first != second
        assert first.split('?')[0] == second.split('?')[0]
        assert _jpeg_from_ref(second) == b'\xff\xd8second'
        assert len(list((tmp_path/'crops').iterdir())) == 1
