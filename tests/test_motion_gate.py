"""The plate detector runs only when the live picture moves."""

from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw

from app.config import settings
from app.services import motion_gate


def _jpeg(car_x: int | None = None) -> bytes:
    image = Image.new("RGB", (704, 576), (110, 110, 110))
    if car_x is not None:
        ImageDraw.Draw(image).rectangle([car_x, 250, car_x + 160, 400], fill=(230, 230, 230))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=85)
    return out.getvalue()


@pytest.fixture(autouse=True)
def fresh():
    motion_gate.reset()
    yield
    motion_gate.reset()


def test_a_still_empty_lane_is_searched_only_every_two_seconds():
    lane = _jpeg()
    assert motion_gate.should_detect(1, lane, now=0.0)          # first frame: nothing to compare
    assert not motion_gate.should_detect(1, lane, now=0.25)
    assert not motion_gate.should_detect(1, lane, now=1.75)
    assert motion_gate.should_detect(1, lane, now=2.1)          # idle check
    assert motion_gate.stats()["1"] == {"detected": 2, "skipped": 2}


def test_a_moving_car_is_searched_every_sample():
    assert motion_gate.should_detect(2, _jpeg(), now=0.0)
    assert motion_gate.should_detect(2, _jpeg(100), now=0.25)   # car arrives
    assert motion_gate.should_detect(2, _jpeg(140), now=0.50)   # car moves


def test_a_standing_car_with_a_plate_is_still_watched():
    still = _jpeg(300)
    motion_gate.should_detect(3, still, now=0.0)
    motion_gate.note_result(3, plate_seen=True, now=0.0)
    for t in (0.25, 0.5, 1.0, 2.9):
        assert motion_gate.should_detect(3, still, now=t)       # plate seen in the last 3 s
    assert not motion_gate.should_detect(3, still, now=3.2)


def test_switched_off_every_frame_is_searched(monkeypatch):
    monkeypatch.setattr(settings, "virtual_loop_motion_gate", False)
    lane = _jpeg()
    assert all(motion_gate.should_detect(4, lane, now=t / 4) for t in range(6))


def test_jpeg_noise_alone_is_not_motion():
    a = _jpeg()
    image = Image.open(io.BytesIO(a))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=60)              # re-encoded: compression noise only
    assert not motion_gate.moved(motion_gate.thumbnail(a), motion_gate.thumbnail(out.getvalue()))


def test_the_setting_is_on_screen_and_on_by_default():
    from app.services import runtime_settings

    assert "motion_gate" in runtime_settings.FIELDS
    assert runtime_settings.get("motion_gate") is True


def test_movement_outside_the_lane_is_ignored():
    """People on the pavement or traffic behind don't wake the detector."""
    config = {"enabled": True, "zone": [[0.2, 0.5], [0.8, 0.5], [0.8, 0.95], [0.2, 0.95]],
              "trigger_line": {"y": 0.6, "side": "below"}}
    region = motion_gate.watch_region(config)
    assert region == pytest.approx((0.12, 0.2, 0.88, 1.0))        # 0.30 above the zone: cars come from there
    still = _jpeg()
    image = Image.new("RGB", (704, 576), (110, 110, 110))
    ImageDraw.Draw(image).rectangle([0, 0, 60, 80], fill=(240, 240, 240))   # top-left corner only
    out = io.BytesIO(); image.save(out, format="JPEG", quality=85)
    assert motion_gate.should_detect(5, still, now=0.0, region=region)
    assert not motion_gate.should_detect(5, out.getvalue(), now=0.25, region=region)
    assert motion_gate.should_detect(5, _jpeg(300), now=0.5, region=region)   # a car in the lane


def test_uncalibrated_cameras_watch_the_whole_picture():
    assert motion_gate.watch_region({"enabled": False, "zone": [[0, 0], [1, 0], [1, 1]]}) is None
    assert motion_gate.watch_region({"enabled": True, "zone": []}) is None
