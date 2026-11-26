"""Calibration rules decide what is read, and every switch changes the outcome.

Guards SITE-PC01, 23 Nov 2026:
- 893 reads were refused as "outside capture zone" in one day. Zirp read the
  most confident plate anywhere on the picture (a parked car, the next lane)
  and only then checked the zone, so the car inside the zone was never read.
- "Store reads before the start line" (start line not enforced) did nothing:
  each zone's top edge sits just above its start line, so an early read was
  refused as outside the zone instead.
- Camera 4 stayed disconnected for 20 minutes: the SDK host answered "already
  connected" with a session number it had since given to camera 1.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.services import capture_calibration as cc

# Camera 1's saved calibration on SITE-PC01 (live picture 704 x 576).
ZONE = [[0.0952, 0.4036], [0.2262, 0.9709], [0.9747, 0.9782], [0.6935, 0.4073]]


def _config(**enforce):
    rules = {**cc.DEFAULT_ENFORCE, **enforce}
    return {**cc.DEFAULTS, "enabled": True, "zone": ZONE,
            "trigger_line": {"y": 0.4582, "side": "below"}, "end_line": {"y": 0.6582},
            "reference_width": 704, "enforce": rules}


def _box(cx, cy, confidence=0.9, w=704, h=576):
    x, y = cx * w, cy * h
    return {"x1": x - 40, "y1": y - 12, "x2": x + 40, "y2": y + 12,
            "image_width": w, "image_height": h, "confidence": confidence}


def _judge(box, **enforce):
    return cc.evaluate_frame(b"", [box], _config(**enforce))[0]


def test_plate_still_approaching_follows_the_start_line_switch():
    approaching = _box(0.45, 0.35)                     # above the zone, in the lane
    assert _judge(approaching, start_line=False).eligible
    refused = _judge(approaching, start_line=True)
    assert not refused.eligible
    assert all("capture zone" not in reason or "before" in reason for reason in refused.reasons)


def test_plate_off_to_the_side_is_always_a_zone_refusal():
    beside = _box(0.03, 0.80)                          # left of the zone: another lane
    verdict = _judge(beside, start_line=False, end_line=False)
    assert not verdict.eligible
    assert verdict.reasons == ["outside capture zone"]
    assert _judge(beside, zone=False, start_line=False, end_line=False).eligible


def test_plate_inside_between_the_lines_is_stored():
    assert _judge(_box(0.5, 0.55), start_line=True, end_line=True).eligible


def test_end_line_switch_decides_a_plate_that_has_driven_through():
    gone = _box(0.6, 0.75)                             # inside the zone, past the end line
    assert _judge(gone, end_line=False).eligible
    assert not _judge(gone, end_line=True).eligible


def test_zone_without_lines_keeps_refusing_everything_outside():
    config = {**_config(), "trigger_line": None, "end_line": None}
    assert not cc.evaluate_frame(b"", [_box(0.45, 0.30)], config)[0].eligible


def test_only_plates_inside_the_calibration_are_offered_for_reading(monkeypatch):
    monkeypatch.setattr(cc, "for_camera", lambda camera_id, camera=None: _config())
    parked = _box(0.03, 0.80, confidence=0.99)         # most confident, but outside
    arriving = _box(0.5, 0.55, confidence=0.70)
    kept, refused = cc.plates_to_read(1, b"", [parked, arriving])
    assert kept == [arriving]
    assert refused and refused[0].box is parked


def test_uncalibrated_camera_reads_every_plate(monkeypatch):
    monkeypatch.setattr(cc, "for_camera", lambda camera_id, camera=None: {**cc.DEFAULTS, "enabled": False})
    boxes = [_box(0.03, 0.80), _box(0.5, 0.55)]
    assert cc.plates_to_read(1, b"", boxes)[0] == boxes


# ------------------------------------------------------- Site Service read path

JPEG = b"\xff\xd8frame\xff\xd9"


def _read(api, camera, boxes, recognize):
    async def run():
        return await api._run_local_alpr_locked(None, camera, JPEG, ticket=None)

    with patch("app.services.media_gateway.gateway.peek_detect", return_value=None), \
         patch("app.services.alpr.locate_plate_boxes", return_value=(boxes, {"available": True})), \
         patch("app.services.alpr.recognize_arrival_bytes", side_effect=recognize), \
         patch.object(cc, "for_camera", lambda camera_id, camera=None: _config()), \
         patch.object(api, "_persist_capture_event", AsyncMock()), \
         patch.object(api, "_crop_from_alpr", return_value=b""):
        return asyncio.run(run())


def test_camera_picture_reads_the_car_in_the_zone_not_the_parked_one():
    from app import api_main as api
    from app.models import Camera

    camera = Camera(id=901, name="Entry", ip_address="10.0.0.9", stream_profiles={})
    parked, arriving = _box(0.03, 0.80, 0.99), _box(0.5, 0.55, 0.70)
    offered = []

    def recognize(jpeg, **kwargs):
        offered.append(kwargs.get("detected_boxes"))
        return {"ok": True, "plates": [], "best": None}

    _read(api, camera, [parked, arriving], recognize)
    assert offered == [[arriving]]


def test_nothing_is_read_when_every_plate_is_outside_the_calibration():
    from app import api_main as api
    from app.models import Camera

    camera = Camera(id=902, name="Entry", ip_address="10.0.0.9", stream_profiles={})
    calls = []
    result = _read(api, camera, [_box(0.03, 0.80, 0.99)], lambda *a, **k: calls.append(1))
    assert calls == []
    assert result.get("calibration_refused")
    assert cc.live_state(902)["last_rejected"]["reasons"] == ["outside capture zone"]


# ------------------------------------------------------------ camera SDK host


def _host():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/hvx_sdk_host"))
    from hvx_sdk import HVXSDK
    import threading

    sdk = HVXSDK.__new__(HVXSDK)
    sdk._lock = threading.RLock()
    sdk._connection_locks = {}
    sdk._connection_results = {}
    sdk._recognition_sessions = {}
    sdk.dll = type("Dll", (), {"Net_QueryConnState": staticmethod(lambda handle: 0)})()
    return sdk


def test_host_does_not_reuse_a_session_number_now_owned_by_another_camera():
    sdk = _host()
    signature_args = ("192.168.10.50", 30000, 3, "admin", "pw")
    logins = []

    def connect(ip, port, timeout, user, password):
        logins.append(ip)
        handle = {"192.168.10.50": 1, "192.168.10.144": 1}[ip] if len(logins) < 3 else 4
        sdk._recognition_sessions[handle] = {"ip": ip}
        return {"connected": True, "handle": handle, "steps": []}

    sdk._add_and_connect = connect
    disconnected = []
    sdk.disconnect = lambda handle, force=False: disconnected.append(handle)

    assert sdk.add_and_connect(*signature_args)["handle"] == 1          # .50 gets 1
    assert sdk.add_and_connect("192.168.10.144", 30000, 3, "admin", "pw")["handle"] == 1   # SDK reuses 1 for .144
    again = sdk.add_and_connect(*signature_args)
    assert logins == ["192.168.10.50", "192.168.10.144", "192.168.10.50"]   # a real login, not "reused"
    assert not again.get("reused")
    assert again["handle"] == 4
    assert disconnected == []                                           # camera 1's session left alone


def test_host_still_reuses_its_own_live_session():
    sdk = _host()
    calls = []

    def connect(ip, *args):
        calls.append(ip)
        sdk._recognition_sessions[2] = {"ip": ip}
        return {"connected": True, "handle": 2, "steps": []}

    sdk._add_and_connect = connect
    sdk.disconnect = lambda *a, **k: pytest.fail("must not disconnect a healthy session")
    sdk.add_and_connect("192.168.10.49", 30000, 3, "admin", "pw")
    assert sdk.add_and_connect("192.168.10.49", 30000, 3, "admin", "pw")["reused"]
    assert calls == ["192.168.10.49"]


def test_detector_minimum_above_080_is_not_applied():
    """Gate 2 had 0.90 saved; good plates score 0.85-0.89, so it refused most cars."""
    from types import SimpleNamespace

    with pytest.raises(ValueError, match="0.80 or less"):
        cc.validate({**_config(), "min_detection_confidence": 0.9})

    class _Db:
        def get(self, model, key):
            return SimpleNamespace(value={**_config(), "min_detection_confidence": 0.9})

    camera = SimpleNamespace(id=3, name="2# Entry", site_id=1, gate_id=2, lane_id=None, lane_direction="ENTRY")
    loaded = cc.load(_Db(), camera)
    assert loaded["min_detection_confidence"] == 0.0
    assert any("0.80 or less" in message for message in loaded["ignored"])
    assert cc.evaluate_frame(b"", [_box(0.5, 0.55, confidence=0.87)], loaded)[0].eligible


# ------------------------------------------------- camera's own plate rectangle


def _real_jpeg(w=704, h=576):
    import io
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (w, h), (90, 90, 90)).save(out, "JPEG")
    return out.getvalue()


def _read_native(api, camera, jpeg, native, recognize, found=()):
    async def run():
        return await api._run_local_alpr_locked(None, camera, jpeg, native=native, ticket=None)

    with patch("app.services.media_gateway.gateway.peek_detect", return_value=None), \
         patch("app.services.alpr.locate_plate_boxes", return_value=(list(found), {"available": True})), \
         patch("app.services.alpr.recognize_arrival_bytes", side_effect=recognize), \
         patch.object(cc, "for_camera", lambda camera_id, camera=None: _config(picture_quality=False)), \
         patch.object(api, "_persist_capture_event", AsyncMock()), \
         patch.object(api, "_crop_from_alpr", return_value=b""):
        return asyncio.run(run())


def test_camera_plate_box_is_read_when_the_detector_finds_none():
    """The camera's rectangle has no detector score and no picture size.

    It was scored 0 (refused by the detector rule, skipped by the crop
    reader's floor) and could not be placed on the picture, so this fallback
    never read a plate.
    """
    from app import api_main as api
    from app.models import Camera

    camera = Camera(id=903, name="Entry", ip_address="10.0.0.9", stream_profiles={})
    box = _box(0.5, 0.55)
    native = {"bbox": {k: int(box[k]) for k in ("x1", "y1", "x2", "y2")},
              "image_width": 704, "image_height": 576}
    offered = []

    def recognize(jpeg, **kwargs):
        offered.append(kwargs.get("detected_boxes"))
        return {"ok": True, "plates": [], "best": None}

    result = _read_native(api, camera, _real_jpeg(), native, recognize)
    assert not result.get("calibration_refused"), result
    assert len(offered) == 1 and len(offered[0]) == 1
    read = offered[0][0]
    assert read["confidence"] == 1.0 and read["source"] == "camera"
    assert (read["image_width"], read["image_height"]) == (704, 576)


def test_an_empty_still_is_not_searched_twice():
    from app import api_main as api
    from app.models import Camera

    camera = Camera(id=904, name="Entry", ip_address="10.0.0.9", stream_profiles={})
    calls = []
    result = _read_native(api, camera, _real_jpeg(), {}, lambda *a, **k: calls.append(1))
    assert calls == []
    assert result["best"] is None


def test_retired_site_wide_detect_roi_no_longer_crops(monkeypatch):
    from app.config import settings
    from app.services.alpr import parse_detect_roi

    monkeypatch.setattr(settings, "alpr_detect_roi", "0.2,0.2,0.8,0.8", raising=False)
    assert parse_detect_roi(None) is None
    assert parse_detect_roi("off") is None
    assert parse_detect_roi("0.1,0.1,0.9,0.9") == (0.1, 0.1, 0.9, 0.9)


# ------------------------------------------------- camera's own plate region

REGION = [{"x": 140, "y": 230}, {"x": 560, "y": 230}, {"x": 560, "y": 560}, {"x": 140, "y": 560}]


def _searched_roi(native):
    from app import api_main as api
    from app.models import Camera

    camera = Camera(id=905, name="Entry", ip_address="10.0.0.9", stream_profiles={})
    searched = []

    def locate(jpeg, **kwargs):
        searched.append(kwargs.get("detect_roi"))
        return [], {"available": True}

    async def run():
        return await api._run_local_alpr_locked(None, camera, _real_jpeg(), native=native, ticket=None)

    with patch("app.services.media_gateway.gateway.peek_detect", return_value=None), \
         patch("app.services.alpr.locate_plate_boxes", side_effect=locate), \
         patch.object(cc, "for_camera", lambda camera_id, camera=None: _config(picture_quality=False)), \
         patch.object(api, "_persist_capture_event", AsyncMock()), \
         patch.object(api, "_crop_from_alpr", return_value=b""):
        asyncio.run(run())
    return searched


def test_camera_event_is_searched_inside_the_cameras_own_plate_region():
    searched = _searched_roi({"plate_region": REGION, "image_width": 704, "image_height": 576})
    assert len(searched) == 1 and searched[0]
    x1, y1, x2, y2 = (float(v) for v in searched[0].split(","))
    assert x1 < 140 / 704 and x2 > 560 / 704 and y1 < 230 / 576 and y2 > 560 / 576 - 0.0001
    assert x1 > 0.05 and y1 > 0.2        # the region, padded, not the whole picture


def test_no_camera_region_searches_the_whole_picture():
    assert _searched_roi({}) == [None]


def test_region_outside_the_picture_is_not_used():
    from app.services.camera_framing import native_plate_region_to_roi

    off = [{"x": 100, "y": 100}, {"x": 3000, "y": 100}, {"x": 3000, "y": 900}, {"x": 100, "y": 900}]
    assert native_plate_region_to_roi(off, image_width=1920, image_height=1080) == ""
    zeros = [{"x": 0, "y": 0}] * 4
    assert native_plate_region_to_roi(zeros, image_width=1920, image_height=1080) == ""
