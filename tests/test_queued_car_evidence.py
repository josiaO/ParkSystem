"""A second car read while the first car's visit is still open gets its own capture.

Field report: on 2# Exit a car's snapshot and crop stayed on screen (and in
the kiosk) while other cars passed and were recognised. One cause: the lane
visit stays open while the lane looks occupied, there is one capture per
visit, so the next car's read was folded into the first car's capture.
"""
from __future__ import annotations

import asyncio
import io
import sys
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import Base  # noqa: E402
from app.models import Camera, VehicleCapture  # noqa: E402
from app.services.lane_stay import different_vehicle  # noqa: E402


def test_different_vehicle_ignores_ocr_slips_and_truncation():
    assert different_vehicle("T461DMR", "T927ETV")
    assert not different_vehicle("T940OWQ", "T940DWQ")       # one slip
    assert not different_vehicle("SM15174", "15174")         # truncated read
    assert not different_vehicle("T461DMR", "")               # no plate yet
    assert not different_vehicle("T461DMR", "T461DMR")


def _jpeg(shade):
    out = io.BytesIO()
    Image.new("RGB", (64, 48), (shade, shade, shade)).save(out, format="JPEG")
    return out.getvalue()


def test_next_car_in_an_open_visit_gets_its_own_capture(monkeypatch, tmp_path):
    from app import api_main as api
    from app.services.recognition_runtime import runtime

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    from unittest.mock import PropertyMock

    from app.config import Settings
    monkeypatch.setattr(Settings, "media_dir", PropertyMock(return_value=tmp_path))
    monkeypatch.setattr("app.services.capture_calibration.in_test_mode", lambda camera_id: False)
    monkeypatch.setattr("app.services.capture_calibration.for_camera", lambda camera_id, camera=None: {"enabled": False})
    monkeypatch.setattr("app.services.node_scope.camera_active_on_this_installation", lambda *a, **k: True)
    monkeypatch.setattr("app.services.modules.is_enabled", lambda *a, **k: False)   # no session/barrier logic here

    with Session() as db:
        camera = Camera(id=41, name="Exit", ip_address="10.9.9.4", lane_direction="EXIT")
        db.add(camera)
        db.commit()
        runtime.reset()
        lane = runtime.lane(41)
        lane.visit.observe(presence=True, native_event=True)
        visit = lane.visit.visit_id

        async def store(plate, image_id, shade, y1=20):
            capture = {"plate": plate, "confidence": 0.99, "image_id": image_id, "have_vehicle": True,
                       "visit_id": lane.visit.visit_id,
                       "bbox": {"x1": 10, "y1": y1, "x2": 40, "y2": y1 + 10, "image_width": 64, "image_height": 48}}
            return await api._persist_capture_event(db, camera, capture, _jpeg(shade), b"")

        asyncio.run(store("T461DMR", 101, 40))
        # The lane never saw an empty frame: the next car arrives in the same visit.
        assert lane.visit.visit_id == visit
        # The next car queues behind the first one (earlier on the path).
        asyncio.run(store("T927ETV", 102, 200, y1=8))
        rows = db.query(VehicleCapture).filter(VehicleCapture.camera_id == 41).order_by(VehicleCapture.id).all()
        assert [r.plate for r in rows] == ["T461DMR", "T927ETV"]
        assert rows[0].visit_id != rows[1].visit_id
        assert rows[0].snapshot_path != rows[1].snapshot_path
        # A slip of the first plate in its own visit still folds into one capture.
        asyncio.run(store("T927ETW", 103, 120, y1=8))
        assert db.query(VehicleCapture).filter(VehicleCapture.camera_id == 41).count() == 2
    engine.dispose()
