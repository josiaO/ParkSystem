"""Per-camera capture calibration: early detection never triggers premature OCR.

Synthetic frames: a 704x576 picture with a high-contrast "plate" drawn at a
chosen place and size; blur and darkness are applied with Pillow. The gate is
driven with the detector boxes those frames would produce.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Camera
from app.services import capture_calibration as cc

W, H = 704, 576

CALIBRATED = cc.validate({
    "enabled": True,
    "zone": [[0.2, 0.45], [0.8, 0.45], [0.8, 0.98], [0.2, 0.98]],
    "trigger_line": {"y": 0.5, "side": "below"},
    "min_plate_width_px": 90,
    "min_plate_height_px": 20,
    "min_detection_confidence": 0.5,
    "min_sharpness": 150,
    "min_brightness": 40,
    "max_brightness": 230,
    "candidate_frames": 3,
    "candidate_seconds": 0.8,
})


def frame(cx: float, cy: float, width: int, *, blur: float = 0, dark: bool = False) -> tuple[bytes, dict]:
    """A picture with one plate centred at (cx, cy) (normalised), ``width`` px wide."""
    image = Image.new("RGB", (W, H), (110, 110, 110))
    d = ImageDraw.Draw(image)
    height = max(6, int(width * 0.28))
    x1, y1 = int(cx * W - width / 2), int(cy * H - height / 2)
    d.rectangle([x1, y1, x1 + width, y1 + height], fill=(235, 235, 235))
    step = max(3, width // 14)
    for i in range(x1 + step, x1 + width - step, step * 2):
        d.rectangle([i, y1 + height // 5, i + step - 1, y1 + height - height // 5], fill=(10, 10, 10))
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(blur))
    if dark:
        image = image.point(lambda v: v // 8)
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=92)
    box = {"x1": x1, "y1": y1, "x2": x1 + width, "y2": y1 + height,
           "image_width": W, "image_height": H, "confidence": 0.9}
    return out.getvalue(), box


def step(gate, config, jpeg, boxes, t):
    candidates = cc.evaluate_frame(jpeg, boxes, config)
    return gate.observe(candidates, boxes, jpeg, t), candidates


def new_gate(config=CALIBRATED):
    gate = cc.CaptureGate()
    gate.configure(config)
    return gate


def test_far_plate_is_detected_but_not_read():
    gate = new_gate()
    phases = []
    for i, (cy, width) in enumerate([(0.15, 40), (0.25, 50), (0.35, 60)]):   # approaching, still far
        jpeg, box = frame(0.5, cy, width)
        phase, candidates = step(gate, CALIBRATED, jpeg, [box], i * 0.3)
        phases.append(phase)
        assert candidates and not candidates[0].eligible
    assert phases == ["far", "far", "far"]
    assert gate.selected is None


def test_entering_the_zone_reads_the_best_frame_not_the_first():
    gate = new_gate()
    shots = [(0.55, 100, 0), (0.62, 140, 0), (0.70, 120, 2.5)]  # 2nd is biggest & sharp, 3rd blurred
    phase = None
    for i, (cy, width, blur) in enumerate(shots):
        jpeg, box = frame(0.5, cy, width, blur=blur)
        phase, _ = step(gate, CALIBRATED, jpeg, [box], i * 0.2)
    assert phase == "ready"
    assert gate.selected.candidate.width_px == 140
    assert gate.selected.frames_considered >= 2


def test_fast_vehicle_leaving_the_zone_is_read_from_what_was_seen():
    gate = new_gate()
    jpeg, box = frame(0.5, 0.6, 120)
    assert step(gate, CALIBRATED, jpeg, [box], 0.0)[0] == "collecting"
    phase, _ = step(gate, CALIBRATED, b"", [], 0.1)                  # gone next frame
    assert phase == "ready" and gate.selected.candidate.width_px == 120


def test_slow_vehicle_window_closes_by_frame_count():
    gate = new_gate()
    phases = []
    for i in range(3):
        jpeg, box = frame(0.5, 0.6 + i * 0.01, 110 + i)
        phases.append(step(gate, CALIBRATED, jpeg, [box], i * 0.05)[0])
    assert phases == ["collecting", "collecting", "ready"]


def test_vehicle_stopping_in_the_zone_is_read_once():
    gate = new_gate()
    t = 0.0
    phases = []
    for _ in range(12):
        jpeg, box = frame(0.5, 0.7, 150)
        phase, _ = step(gate, CALIBRATED, jpeg, [box], t)
        phases.append(phase)
        if phase == "ready":
            gate.note_ocr(published=True)
        t += 0.2
    assert phases.count("ready") == 1
    assert phases[-1] == "held"


def test_repeated_detections_of_the_same_vehicle_do_not_read_again():
    gate = new_gate()
    for i in range(3):
        jpeg, box = frame(0.5, 0.7, 150)
        phase, _ = step(gate, CALIBRATED, jpeg, [box], i * 0.1)
    assert phase == "ready"
    gate.note_ocr(published=True)
    for i in range(5):
        jpeg, box = frame(0.5, 0.7 + 0.005 * i, 150)
        assert step(gate, CALIBRATED, jpeg, [box], 1 + i * 0.1)[0] == "held"


def test_multiple_vehicles_choose_the_eligible_nearest_plate():
    near_jpeg, near = frame(0.5, 0.75, 160)
    _, far = frame(0.3, 0.2, 50)          # second car far away, outside the zone
    candidates = cc.evaluate_frame(near_jpeg, [far, near], CALIBRATED)
    eligible = [c for c in candidates if c.eligible]
    assert len(eligible) == 1 and eligible[0].width_px == 160


@pytest.mark.parametrize("kwargs,reason", [
    ({"width": 60}, "wide"),                     # small plate
    ({"width": 120, "blur": 4}, "blurred"),      # motion blur
    ({"width": 120, "dark": True}, "too dark"),  # poor lighting
])
def test_poor_frames_are_not_eligible(kwargs, reason):
    jpeg, box = frame(0.5, 0.7, kwargs["width"], blur=kwargs.get("blur", 0), dark=kwargs.get("dark", False))
    candidate = cc.evaluate_frame(jpeg, [box], CALIBRATED)[0]
    assert not candidate.eligible
    assert any(reason in r for r in candidate.reasons), candidate.reasons


def test_partially_obscured_plate_below_minimum_height():
    jpeg, box = frame(0.5, 0.7, 120)
    box = dict(box, y2=box["y1"] + 12)          # lower half hidden
    candidate = cc.evaluate_frame(jpeg, [box], CALIBRATED)[0]
    assert not candidate.eligible and any("tall" in r for r in candidate.reasons)


def test_trigger_line_side_matters():
    jpeg, box = frame(0.5, 0.48, 120)            # inside the zone but above the line
    candidate = cc.evaluate_frame(jpeg, [box], CALIBRATED)[0]
    assert "not past trigger line" in candidate.reasons
    above = dict(CALIBRATED, trigger_line={"y": 0.5, "side": "above"})
    assert "not past trigger line" not in cc.evaluate_frame(jpeg, [box], above)[0].reasons


def test_uncalibrated_camera_reads_whole_picture_with_best_frame_selection():
    config = cc.validate({})
    jpeg, box = frame(0.5, 0.1, 40)              # far plate, top of picture
    candidate = cc.evaluate_frame(jpeg, [box], config)[0]
    assert candidate.eligible
    gate = new_gate(config)
    assert gate.observe([candidate], [box], jpeg, 0.0) == "collecting"


def test_polygon_zone():
    zone = [[0.1, 0.9], [0.5, 0.4], [0.9, 0.9]]   # triangle
    assert cc.point_in_polygon(0.5, 0.8, zone)
    assert not cc.point_in_polygon(0.15, 0.5, zone)


def test_validation_rejects_bad_input():
    with pytest.raises(ValueError):
        cc.validate({"zone": [[0.1, 0.1], [0.2, 0.2]]})
    with pytest.raises(ValueError):
        cc.validate({"zone": [[0.1, 0.1], [1.5, 0.2], [0.3, 0.9]]})
    with pytest.raises(ValueError):
        cc.validate({"min_plate_width_px": -1})
    with pytest.raises(ValueError):
        cc.validate({"min_brightness": 200, "max_brightness": 100})


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session() as session:
        yield session
    engine.dispose()


def _camera(db, cid, direction="ENTRY"):
    camera = Camera(id=cid, name=f"cam{cid}", ip_address=f"10.0.0.{cid}", lane_direction=direction)
    db.add(camera)
    db.commit()
    return camera


def test_each_camera_keeps_its_own_versioned_calibration(db):
    a, b = _camera(db, 1, "ENTRY"), _camera(db, 2, "EXIT")
    saved_a = cc.save(db, a, {"enabled": True, "min_plate_width_px": 90}, user="tech")
    saved_b = cc.save(db, b, {"enabled": True, "min_plate_width_px": 150, "min_plate_height_px": 40}, user="tech")
    assert (saved_a["min_plate_width_px"], saved_b["min_plate_width_px"]) == (90, 150)
    assert saved_a["camera_id"] == 1 and saved_b["direction"] == "EXIT"
    assert saved_a["version"] == 1
    again = cc.save(db, a, {"enabled": True, "min_plate_width_px": 95, "version": 1}, user="tech")
    assert again["version"] == 2 and cc.load(db, b)["min_plate_width_px"] == 150
    with pytest.raises(cc.ConflictError):
        cc.save(db, a, {"enabled": True, "version": 1})
    cc.remove(db, 1)
    assert cc.load(db, a)["calibrated"] is False


def test_uncalibrated_by_default(db):
    camera = _camera(db, 3)
    config = cc.load(db, camera)
    assert config["calibrated"] is False and config["zone"] == [] and config["min_plate_width_px"] == 0


def test_test_mode_expires_and_blocks_storing(db, monkeypatch):
    camera = _camera(db, 4)
    status = cc.set_test_mode(db, camera.id, enabled=True, minutes=5)
    assert status["enabled"] and status["until"]
    monkeypatch.setattr(cc, "in_test_mode", lambda camera_id: True)
    from app.services.captures import persist_event

    jpeg, _ = frame(0.5, 0.7, 150)
    row = persist_event(db, camera, jpeg=jpeg, crop=b"", force=True,
                        capture={"plate": "T123ABC", "confidence": 0.9, "image_id": 7, "have_vehicle": True})
    assert row is None                                       # no capture row -> no session, no barrier
    assert cc.live_state(4)["last_read"]["test_mode"] is True
    assert cc.set_test_mode(db, camera.id, enabled=False)["enabled"] is False


def test_legacy_zone_values_are_cleared_by_migration():
    import importlib.util

    path = ROOT / "app" / "migrations" / "alembic" / "versions" / "0020_clear_legacy_capture_zones.py"
    spec = importlib.util.spec_from_file_location("m0020", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    profiles = {"FRAMING": {"detect_roi": "0.1,0.2,0.9,0.9", "detect_zoom": 2.0, "capture_plate_width": 80,
                            "detect_width": 1280}, "detect_roi": "x", "LIVE": {"uri": "rtsp://cam"}}
    assert module.cleaned(profiles) == {"FRAMING": {"detect_width": 1280}, "LIVE": {"uri": "rtsp://cam"}}
    assert module.cleaned({"LIVE": {}}) is None


def test_old_framing_reports_whole_picture():
    from app.services.camera_framing import framing_from_profiles

    old = {"FRAMING": {"detect_roi": "0.1,0.2,0.9,0.9", "detect_zoom": 3, "capture_plate_width": 120}}
    framing = framing_from_profiles(old)
    assert framing["detect_roi"] == "off" and framing["detect_zoom"] == 1.0 and "capture_plate_width" not in framing


def test_calibration_api_requires_sign_in_and_is_registered():
    from fastapi.testclient import TestClient

    from app.api_main import app

    client = TestClient(app)
    # 401 (not 404): the routes exist and refuse an anonymous caller.
    for path in ("/cameras/1/calibration/live", "/cameras/1/calibration/snapshot.jpg"):
        assert client.get(path).status_code == 401
    assert client.put("/cameras/1/calibration/test-mode", json={"enabled": True}).status_code == 401
    assert client.get("/cameras/1/calibration").status_code == 401
    assert client.put("/cameras/1/calibration", json={"enabled": True}).status_code == 401


def _big_snapshot(box):
    image = Image.new("RGB", (1920, 1080), (110, 110, 110))
    ImageDraw.Draw(image).rectangle([box["x1"], box["y1"], box["x2"], box["y2"]], fill=(235, 235, 235))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=85)
    return out.getvalue()


def test_no_read_is_stored_outside_the_camera_calibration(db, monkeypatch):
    """Camera-triggered 1920x1080 snapshots are judged in the 704 px live picture's terms."""
    from app.services.captures import persist_event

    camera = _camera(db, 11)
    cc.save(db, camera, {"enabled": True, "zone": [[0.4, 0.5], [1.0, 0.5], [1.0, 1.0], [0.4, 1.0]],
                         "min_plate_width_px": 50, "reference_width": 704})
    cc.invalidate(11)
    monkeypatch.setattr(cc, "in_test_mode", lambda camera_id: False)
    monkeypatch.setattr(cc, "for_camera", lambda camera_id, camera=None: cc.load(db, camera or db.get(Camera, camera_id)))

    def capture(image_id, box):
        return {"plate": "T123ABC", "confidence": 0.95, "image_id": image_id, "have_vehicle": True,
                "bbox": {**box, "image_width": 1920, "image_height": 1080}}

    outside = {"x1": 100, "y1": 700, "x2": 300, "y2": 760}       # left of the zone
    too_small = {"x1": 1200, "y1": 800, "x2": 1300, "y2": 830}   # 100 px at 1920 = 37 px at 704 < 50
    good = {"x1": 1100, "y1": 800, "x2": 1300, "y2": 860}        # 200 px at 1920 = 73 px at 704
    for image_id, box in ((1, outside), (2, too_small)):
        row = persist_event(db, camera, jpeg=_big_snapshot(box), crop=b"", capture=capture(image_id, box))
        assert row is None
    rejected = cc.live_state(11)["last_rejected"]
    assert any("wide" in r for r in rejected["reasons"])
    row = persist_event(db, camera, jpeg=_big_snapshot(good), crop=b"", capture=capture(3, good))
    assert row is not None and row.plate == "T123ABC"


def test_a_read_without_a_plate_box_is_not_stored_on_a_calibrated_camera(db, monkeypatch):
    camera = _camera(db, 12)
    cc.save(db, camera, {"enabled": True, "min_plate_width_px": 40})
    monkeypatch.setattr(cc, "for_camera", lambda camera_id, camera=None: cc.load(db, db.get(Camera, camera_id)))
    verdict = cc.check_capture(12, None, b"")
    assert verdict is not None and not verdict.eligible


def test_uncalibrated_camera_is_not_blocked(db, monkeypatch):
    _camera(db, 13)
    monkeypatch.setattr(cc, "for_camera", lambda camera_id, camera=None: cc.load(db, db.get(Camera, camera_id)))
    assert cc.check_capture(13, {"x1": 1, "y1": 1, "x2": 5, "y2": 3}, b"") is None
