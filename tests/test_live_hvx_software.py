import asyncio
from contextlib import contextmanager
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from app import api_main as api
from app.models import Camera
from app.recognition_worker import _software_camera


def camera(mode='FASTALPR_ONLY'):
    return Camera(id=901,name='HVX test',ip_address='127.0.0.1',enabled=True,
                  adapter_id='hvx',sdk_handle=7,recognition_mode=mode,stream_profiles={})


def test_hvx_software_mode_owns_detect_stream_without_callbacks():
    with patch('app.services.modules.is_enabled',return_value=True), patch('app.services.modules.load_config',return_value={}):
        assert _software_camera(camera(), None)
        assert not _software_camera(camera('NATIVE_ONLY'), None)
    assert api._live_spec(camera()).need_detect
    assert not api._live_spec(camera('NATIVE_ONLY')).need_detect


def test_webrtc_viewer_does_not_prevent_starting_recognition_consumer():
    row=camera()
    @contextmanager
    def db():
        yield SimpleNamespace(get=lambda *args: row)
    with patch('app.recognition_worker.worker_owns_software_reads',return_value=False), \
         patch('app.api_main.short_session',db), \
         patch('app.services.node_scope.camera_in_recognition_scope',return_value=True), \
         patch('app.services.media_gateway.gateway.peek_detect',return_value=None), \
         patch('app.services.media_gateway.gateway.peek_live',return_value=None), \
         patch('app.api_main.get_state',return_value=SimpleNamespace(jpeg=b'')), \
         patch('app.api_main.viewers_for',return_value=1), \
         patch('app.infrastructure.media.registry.mediamtx_detect_active',return_value=True), \
         patch('app.services.mediamtx_detect.ensure_detect_consumer') as ensure:
        asyncio.run(api._maybe_watch_local_alpr(901,7))
        ensure.assert_called_once()
        assert ensure.call_args.args[0].need_detect


def test_accepted_live_plate_has_crop_without_debug_frame_files():
    buf=BytesIO()
    Image.new('RGB',(300,150),'white').save(buf,format='JPEG')
    result={'best': {'bbox': {'x1':100,'y1':50,'x2':220,'y2':90,'image_width':300,'image_height':150}}}
    crop=api._crop_from_alpr(result,buf.getvalue())
    assert crop.startswith(b'\xff\xd8')
    image=Image.open(BytesIO(crop))
    assert image.width < 300 and image.height < 150
