"""ZIRP's own trigger with per-camera capture calibration.

The removed ArrivalGate tests lived here; the gate's own behaviour is now
covered by tests/test_capture_calibration.py. These keep the Site Service
integration: one camera snapshot per car, and scene patterns never fire.
"""
import asyncio
import io

from PIL import Image, ImageDraw


def _plate_jpeg(box):
    image = Image.new("RGB", (704, 576), (110, 110, 110))
    d = ImageDraw.Draw(image)
    d.rectangle([box["x1"], box["y1"], box["x2"], box["y2"]], fill=(235, 235, 235))
    for x in range(box["x1"] + 6, box["x2"] - 6, 12):
        d.rectangle([x, box["y1"] + 6, x + 5, box["y2"] - 6], fill=(10, 10, 10))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=92)
    return out.getvalue()


def test_zirp_trigger_commands_the_snapshot_once_per_car():
    """capture_trigger=zirp: the capture gate commands the camera's snapshot
    (read through the event path) instead of reading the low-res live frame."""
    from contextlib import contextmanager
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    from app import api_main as api
    from app.config import settings
    from app.models import Camera
    from app.services import capture_calibration as cc
    from app.services.recognition_runtime import runtime

    camera = Camera(id=9903, name="Exit", ip_address="10.1.0.4", adapter_id="hvx",
                    recognition_mode="FASTALPR_ONLY", sdk_handle=5, stream_profiles={})
    plate = {"x1": 200, "y1": 300, "x2": 300, "y2": 334, "image_width": 704, "image_height": 576, "confidence": 0.9}
    jpeg = _plate_jpeg(plate)

    @contextmanager
    def session():
        yield SimpleNamespace(get=lambda model, key: camera if model is Camera else None)

    async def run():
        runtime.reset()
        cc.override(camera.id, {"enabled": True, "min_plate_width_px": 64, "candidate_frames": 1})
        cc.gate_for(camera.id).reset()
        for cache in (api._detect_at, api._alpr_fp):
            cache.pop(camera.id, None)
        with patch.object(settings, "capture_trigger", "zirp"), \
             patch("app.services.capture_calibration.in_test_mode", return_value=False), \
             patch("app.recognition_worker.worker_owns_software_reads", return_value=False), \
             patch("app.api_main.short_session", session), \
             patch("app.services.media_gateway.gateway.peek_detect",
                   return_value=SimpleNamespace(jpeg=jpeg, seq=1, received_at=api.time.monotonic())), \
             patch("app.services.alpr.locate_plate_boxes", return_value=([plate], {"available": True, "image_width": 704})), \
             patch("app.api_main._read_presence_now", new=AsyncMock()) as snapshot, \
             patch("app.api_main._run_local_alpr", new=AsyncMock()) as live_read:
            for _ in range(3):
                api._detect_at.pop(camera.id, None)
                api._alpr_fp.pop(camera.id, None)
                await api._maybe_watch_local_alpr(camera.id, 5)
                await asyncio.sleep(0)
            assert snapshot.await_count == 1            # one snapshot for this car
            assert snapshot.await_args.args[:2] == (camera.id, 5)
            live_read.assert_not_awaited()               # the low-res live frame is not the evidence

    try:
        asyncio.run(run())
    finally:
        cc.override(9903, None)
        cc.gate_for(9903).reset()


def test_a_frame_wide_pattern_is_not_a_plate():
    """A bollard row detected as a 560 px "plate" (read as 11111) on a 704 px
    frame must not fire the trigger or hold the gate."""
    from unittest.mock import patch

    from app import api_main as api
    from app.models import Camera
    from app.services import capture_calibration as cc

    camera = Camera(id=9904, name="Exit", ip_address="10.1.0.5", stream_profiles={})
    bollards = {"x1": 80, "y1": 120, "x2": 640, "y2": 330, "image_width": 704, "image_height": 576, "confidence": 0.7}

    async def run():
        cc.override(camera.id, {})
        cc.gate_for(camera.id).reset()
        api._detect_at.pop(camera.id, None)
        with patch("app.services.alpr.locate_plate_boxes",
                   return_value=([bollards], {"available": True, "image_width": 704, "image_height": 576})):
            return await api._video_arrival_ready(camera, b"\xff\xd8x\xff\xd9")

    try:
        assert asyncio.run(run()) is False
        assert cc.gate_for(9904).best_width == 0
    finally:
        cc.override(9904, None)
        cc.gate_for(9904).reset()
