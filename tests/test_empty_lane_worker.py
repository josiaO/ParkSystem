import asyncio
from unittest.mock import AsyncMock, patch
from app.recognition_worker import _infer_camera
from app.services.recognition_runtime import runtime


def test_empty_lane_updates_worker_heartbeat_without_ocr():
    async def run():
        runtime.reset()
        stop = asyncio.Event()
        stats = {}
        async def frames(*args, **kwargs):
            while not stop.is_set():
                yield b'\xff\xd8fake-jpeg'
                await asyncio.sleep(.02)
        provider = type('Provider', (), {'process': AsyncMock(side_effect=AssertionError('OCR on empty lane'))})()
        with patch('app.infrastructure.media.registry.get_detect_endpoint', AsyncMock(return_value={'provider':'MEDIAMTX','rtsp':'rtsp://127.0.0.1:8554/cam1_detect'})), \
             patch('app.services.recognition_decoder.iter_jpegs', frames), \
             patch('app.services.alpr.locate_plate_boxes', return_value=([], {'available':True})), \
             patch('app.infrastructure.recognition.recognition_provider_for', return_value=provider):
            task = asyncio.create_task(_infer_camera({'id':1}, stop, stats))
            try:
                for _ in range(100):
                    if stats.get('state') == 'READY':break
                    await asyncio.sleep(.01)
                assert stats.get('state') == 'READY'
                assert stats.get('last_inference_at',0) > 0
                provider.process.assert_not_called()
            finally:
                stop.set()
                await asyncio.wait_for(task,2)
                runtime.reset()
    asyncio.run(run())


def test_cancellation_drains_detector_before_lane_is_replaced():
    import threading
    async def run():
        runtime.reset()
        started, release, completed = threading.Event(), threading.Event(), threading.Event()
        stop = asyncio.Event()
        def locate(*args, **kwargs):
            started.set()
            release.wait(3)
            completed.set()
            return [], {'available':True}
        async def frames(*args, **kwargs):
            while True:
                yield b'\xff\xd8fake'
                await asyncio.sleep(.01)
        with patch('app.infrastructure.media.registry.get_detect_endpoint', AsyncMock(return_value={'provider':'MEDIAMTX','rtsp':'rtsp://127.0.0.1:8554/cam1_detect'})), \
             patch('app.services.recognition_decoder.iter_jpegs', frames), \
             patch('app.services.alpr.locate_plate_boxes', locate):
            task = asyncio.create_task(_infer_camera({'id':1},stop,{}))
            try:
                for _ in range(100):
                    if started.is_set():break
                    await asyncio.sleep(.01)
                assert started.is_set()
                task.cancel()
                await asyncio.sleep(.02)
                assert not task.done()
                release.set()
                await asyncio.gather(task,return_exceptions=True)
                assert completed.is_set()
            finally:
                release.set()
                stop.set()
                await asyncio.gather(task,return_exceptions=True)
                runtime.reset()
    asyncio.run(run())
