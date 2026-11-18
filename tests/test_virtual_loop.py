"""Zirp's own vehicle trigger: the virtual loop fires on distance, not stillness."""

from app.services.camera_framing import ArrivalGate


def box(x, width, y=300):
    return {"x1": x, "y1": y, "x2": x + width, "y2": y + width // 3, "image_width": 704, "image_height": 576}


def test_a_rolling_car_fires_once_when_its_plate_reaches_the_capture_width():
    gate = ArrivalGate(min_plate_width_px=64, fire_on_width=True)
    phases = [gate.observe(box(100 + 40 * i, 30 + 10 * i), 0.25 * i) for i in range(8)]   # moves every sample
    assert phases.count("ready") == 1
    assert phases[:4] == ["far"] * 4 and phases[4] == "ready"   # width 70 >= 64 at the 5th sample
    assert "moving" in phases[5:]                               # the same car does not fire again


def test_the_next_car_fires_after_the_lane_clears():
    gate = ArrivalGate(min_plate_width_px=64, fire_on_width=True, absence_seconds=0.5)
    assert gate.observe(box(200, 80), 0.0) == "ready"
    assert gate.observe(None, 0.3) == "missing"
    assert gate.observe(None, 0.9) == "absent"                  # fired car leaving is a normal absence
    assert gate.observe(box(220, 90), 1.2) == "ready"


def test_a_car_that_stays_far_is_handed_over_when_it_leaves():
    gate = ArrivalGate(min_plate_width_px=64, fire_on_width=True, absence_seconds=0.5)
    for i, width in enumerate((30, 44, 52, 48)):
        assert gate.observe(box(100, width), 0.25 * i) == "far"
    assert gate.best_width == 52
    gate.observe(None, 1.0)
    assert gate.observe(None, 1.6) == "departed"
    assert gate.best_width == 0


def test_the_still_plate_rule_is_unchanged_without_the_virtual_loop():
    gate = ArrivalGate(min_plate_width_px=64, stable_seconds=0.25)
    assert gate.observe(box(100, 80), 0.0) == "moving"
    assert gate.observe(box(300, 80), 0.25) == "moving"          # moved: no read


def test_zirp_trigger_commands_the_snapshot_once_per_car():
    """capture_trigger=zirp: the virtual loop commands the camera's snapshot
    (read through the event path) instead of reading the low-res live frame."""
    import asyncio
    from contextlib import contextmanager
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    from app import api_main as api
    from app.config import settings
    from app.models import Camera
    from app.services.camera_framing import gate_for
    from app.services.recognition_runtime import runtime

    camera = Camera(id=9903, name="Exit", ip_address="10.1.0.4", adapter_id="hvx",
                    recognition_mode="FASTALPR_ONLY", sdk_handle=5, stream_profiles={})
    jpeg = b"\xff\xd8" + b"0" * 64 + b"\xff\xd9"
    plate = {"x1": 200, "y1": 300, "x2": 290, "y2": 330, "image_width": 704, "image_height": 576, "confidence": 0.9}

    @contextmanager
    def session():
        yield SimpleNamespace(get=lambda model, key: camera if model is Camera else None)

    async def run():
        runtime.reset()
        gate = gate_for(camera.id)
        gate.reset()
        gate.fire_on_width, gate.min_plate_width_px = True, 64
        for cache in (api._detect_at, api._alpr_fp):
            cache.pop(camera.id, None)
        with patch.object(settings, "capture_trigger", "zirp"), \
             patch("app.recognition_worker.worker_owns_software_reads", return_value=False), \
             patch("app.api_main.short_session", session), \
             patch("app.services.media_gateway.gateway.peek_detect",
                   return_value=SimpleNamespace(jpeg=jpeg, seq=1, received_at=api.time.monotonic())), \
             patch("app.services.alpr.locate_plate_boxes", return_value=([plate], {"available": True, "image_width": 704})), \
             patch("app.api_main.effective_capture_plate_width", return_value=64, create=True), \
             patch("app.services.camera_framing.effective_capture_plate_width", return_value=64), \
             patch("app.api_main._read_presence_now", new=AsyncMock()) as snapshot, \
             patch("app.api_main._run_local_alpr", new=AsyncMock()) as live_read:
            for _ in range(3):
                api._detect_at.pop(camera.id, None)
                await api._maybe_watch_local_alpr(camera.id, 5)
                await asyncio.sleep(0)
            assert snapshot.await_count == 1            # one snapshot for this car
            assert snapshot.await_args.args[:2] == (camera.id, 5)
            live_read.assert_not_awaited()               # the low-res live frame is not the evidence

    try:
        asyncio.run(run())
    finally:
        gate_for(9903).reset()


def test_a_car_that_fired_gets_no_extra_departure_read():
    gate = ArrivalGate(min_plate_width_px=64, fire_on_width=True, absence_seconds=0.5)
    assert gate.observe(box(200, 80), 0.0) == "ready"
    gate.note_ocr(published=False)                        # unread: may retry while in view
    gate.observe(None, 0.3)
    assert gate.observe(None, 0.9) == "absent"            # not "departed": it already fired


def test_a_frame_wide_pattern_is_not_a_plate():
    """A bollard row detected as a 560 px "plate" (read as 11111) on a 704 px
    frame must not fire the trigger or hold the gate."""
    import asyncio
    from unittest.mock import patch

    from app import api_main as api
    from app.models import Camera
    from app.services.camera_framing import gate_for

    camera = Camera(id=9904, name="Exit", ip_address="10.1.0.5", stream_profiles={})
    bollards = {"x1": 80, "y1": 120, "x2": 640, "y2": 330, "image_width": 704, "image_height": 576, "confidence": 0.7}

    async def run():
        gate = gate_for(camera.id)
        gate.reset()
        gate.fire_on_width = True
        api._detect_at.pop(camera.id, None)
        with patch("app.services.alpr.locate_plate_boxes",
                   return_value=([bollards], {"available": True, "image_width": 704, "image_height": 576})), \
             patch("app.services.camera_framing.effective_capture_plate_width", return_value=64):
            return await api._video_arrival_ready(camera, b"\xff\xd8x\xff\xd9")

    try:
        assert asyncio.run(run()) is False
        assert gate_for(9904).best_width == 0
    finally:
        gate_for(9904).reset()


def test_a_car_waiting_short_of_the_capture_distance_fires_after_lingering():
    gate = ArrivalGate(min_plate_width_px=64, fire_on_width=True, far_fallback_seconds=1.5)
    phases = [gate.observe(box(150, 52), 0.25 * i) for i in range(8)]   # 52 px, stays put
    assert phases[:6] == ["far"] * 6
    assert phases[6] == "ready"                                         # at 1.5 s in view
    assert phases.count("ready") == 1


def test_a_queued_car_behind_the_fired_one_also_fires():
    gate = ArrivalGate(min_plate_width_px=64, fire_on_width=True)
    assert gate.observe(box(200, 120), 0.0) == "ready"          # first car close
    assert gate.observe(box(210, 130), 0.25) == "moving"
    assert gate.observe(box(300, 50), 0.5) == "new_vehicle"     # next car, farther, no gap
    phases = [gate.observe(box(300, w), 0.75 + 0.25 * i) for i, w in enumerate((60, 80, 95))]
    assert phases.count("ready") == 1
