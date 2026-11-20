"""One car, several reads: the best read of a lane visit wins.

Field data, SITE-PC01, 20 Nov 2026 (30 h): 79% of live sub-stream (704 px) reads
were held for review and usually arrived first. Because one capture is kept per
lane visit, the camera's better full-resolution read of the same car got the
held row back: exits were never decided and 27 entry sessions took the held
plate. See app/services/visit_reads.py.
"""
from __future__ import annotations

import asyncio
import io
import sys
from pathlib import Path
from unittest.mock import PropertyMock

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.plate import apply_site_plate, validate_plate  # noqa: E402
from app.db import Base  # noqa: E402
from app.models import Camera, VehicleCapture  # noqa: E402
from app.services import visit_reads  # noqa: E402


# ------------------------------------------------------------------- rules

def plan(**kw):
    base = dict(held=True, held_plate="T837EH8", held_confidence=0.70, incoming_plate="T837EHB",
                incoming_confidence=0.97, incoming_held=False)
    return visit_reads.plan_upgrade(**{**base, **kw})


def test_a_confident_read_replaces_a_held_one():
    assert plan() == visit_reads.BETTER


def test_two_frames_agreeing_release_the_hold_even_below_0_92():
    assert plan(held_plate="T676ATJ", held_confidence=0.91, incoming_plate="T676ATJ",
                incoming_confidence=0.88, incoming_held=True) == visit_reads.CONSENSUS


def test_agreement_of_two_weak_reads_is_not_enough():
    assert plan(held_plate="T676ATJ", held_confidence=0.70, incoming_plate="T676ATJ",
                incoming_confidence=0.72, incoming_held=True) is None


def test_a_held_but_clearly_better_read_becomes_the_operator_candidate():
    assert plan(incoming_confidence=0.80, incoming_held=True) == visit_reads.BETTER_CANDIDATE
    assert plan(incoming_confidence=0.72, incoming_held=True) is None


def test_a_capture_that_was_already_decided_never_changes():
    assert plan(held=False) is None


def test_a_weaker_read_never_replaces_the_held_one():
    assert plan(held_confidence=0.90, incoming_confidence=0.85) is None


# --------------------------------------------------------------- end to end

def _jpeg(shade):
    out = io.BytesIO()
    Image.new("RGB", (64, 48), (shade, shade, shade)).save(out, format="JPEG")
    return out.getvalue()


@pytest.fixture()
def lane(monkeypatch, tmp_path):
    from app import api_main as api
    from app.config import Settings
    from app.services.recognition_runtime import runtime

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(Settings, "media_dir", PropertyMock(return_value=tmp_path))
    monkeypatch.setattr("app.services.capture_calibration.in_test_mode", lambda camera_id: False)
    monkeypatch.setattr("app.services.capture_calibration.for_camera", lambda camera_id, camera=None: {"enabled": False})
    monkeypatch.setattr("app.services.node_scope.camera_active_on_this_installation", lambda *a, **k: True)
    monkeypatch.setattr("app.services.modules.is_enabled", lambda *a, **k: False)
    with Session() as db:
        camera = Camera(id=44, name="2# Exit", ip_address="10.9.9.4", lane_direction="EXIT")
        db.add(camera)
        db.commit()
        runtime.reset()
        state = runtime.lane(44)
        state.visit.observe(presence=True, native_event=True)

        async def read(plate, conf, image_id, *, held):
            capture = {"plate": plate, "score": conf, "image_id": image_id, "have_vehicle": True,
                       "visit_id": state.visit.visit_id, "needs_review": held, "pending_confirmation": held,
                       "bbox": {"x1": 10, "y1": 20, "x2": 40, "y2": 30, "image_width": 64, "image_height": 48}}
            return await api._persist_capture_event(db, camera, capture, _jpeg(80 + image_id), b"")

        yield db, read
    runtime.reset()


def _rows(db):
    return db.query(VehicleCapture).filter(VehicleCapture.camera_id == 44).order_by(VehicleCapture.id).all()


def test_good_full_res_read_replaces_held_substream_read_of_the_same_car(lane):
    db, read = lane
    asyncio.run(read("T837EH8", 0.67, 1, held=True))          # 704 px live frame, held
    asyncio.run(read("T837EHB", 0.99, 2, held=False))         # camera's 1920 px still
    [row] = _rows(db)
    assert row.plate == "T837EHB" and float(row.confidence) == pytest.approx(0.99)
    assert row.bbox["needs_review"] is False and row.bbox["pending_confirmation"] is False
    assert row.bbox["visit_upgrades"][-1]["from_plate"] == "T837EH8"


def test_released_read_reaches_the_exit_controller(lane, monkeypatch):
    """Before the fix the exit controller never ran for the better read."""
    db, read = lane
    monkeypatch.setattr("app.services.modules.is_enabled", lambda *a, **k: True)
    decided: list[str] = []

    async def fake_exit(db, *, camera, capture, gate, source):
        decided.append(capture.plate)
        return {"ok": True, "reason": "test"}

    monkeypatch.setattr("app.application.live_parking.handle_live_exit", fake_exit)
    asyncio.run(read("T837EH8", 0.67, 1, held=True))
    assert decided == []                                       # held: nothing decided
    asyncio.run(read("T837EHB", 0.99, 2, held=False))
    assert decided == ["T837EHB"], "the better read of the same car must be decided"


def test_two_agreeing_frames_release_a_held_read(lane):
    db, read = lane
    asyncio.run(read("T676ATJ", 0.91, 1, held=True))
    asyncio.run(read("T676ATJ", 0.89, 2, held=True))
    [row] = _rows(db)
    assert row.bbox["needs_review"] is False
    assert row.bbox["visit_upgrades"][-1]["kind"] == "consensus"


def test_a_decided_capture_is_not_overwritten(lane):
    db, read = lane
    asyncio.run(read("T390EAM", 0.99, 1, held=False))
    asyncio.run(read("T390EAN", 0.995, 2, held=False))
    [row] = _rows(db)
    assert row.plate == "T390EAM"
    assert "visit_upgrades" not in (row.bbox or {})


# ------------------------------------------------------ Tanzanian validation

@pytest.mark.parametrize("plate", ["T123ABC", "T843ADF", "MC123ABC", "STK1234", "STL7531", "PT1234",
                                   "SU1234", "JWTZ1234", "CD1234"])
def test_tz_validation_accepts_real_formats(plate):
    assert validate_plate(plate, "TZ")["ok"], plate


@pytest.mark.parametrize("plate", ["TQYOTA", "T70DMT", "TA93EPZ", "TT89DSD", "T825QDZR", "T933OS1",
                                   "T1621DPT", "THEYUNGES", "129EDM", "1581ZZR"])
def test_tz_validation_holds_badge_glare_and_truncated_reads(plate):
    assessed = apply_site_plate(plate, validation="TZ")
    assert assessed["hold_for_operator"], (plate, assessed)


def test_tz_correction_still_restores_a_lost_t_before_validation():
    assessed = apply_site_plate("7843ADF", validation="TZ")
    assert assessed["normalized_plate"] == "T843ADF" and not assessed["hold_for_operator"]
