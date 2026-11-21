"""Entry fallback: the camera missed a car, the operator presses "Ticket (F6)".

Zirp takes a picture now, forces a plate read and runs the normal entry path
(session, ticket printing, barrier policy). The plate is what the operator
typed, else what the read found, else an UNREAD placeholder whose ticket QR is
the car's identity at the exit.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app import api_main as api

JPEG = b"\xff\xd8fake-picture\xff\xd9"


class _Db:
    def __init__(self):
        self.committed = 0

    def get(self, model, key):
        return SimpleNamespace(id=key, name="2#")

    def commit(self):
        self.committed += 1


def _run(*, direction="ENTRY", typed="", read=None, picture=JPEG):
    camera = SimpleNamespace(id=3, name="2# Entry", lane_direction=direction, gate_id=2, site_id=1, lane_id=None)
    spec = SimpleNamespace(id=3, ip="192.168.1.49", username="", password="", rtsp_url="", sdk_handle=0, adapter_id="hvx")
    entries: list[dict] = []
    audits: list[str] = []

    async def fake_entry(db, *, camera, gate, plate, confidence, image_ref, source):
        entries.append({"plate": plate, "confidence": confidence, "image_ref": image_ref, "source": source})
        return {"ok": True, "action": "ENTRY", "reason": "created", "message": "Ticket printed."}

    alpr = {"best": {"plate_normalized": read[0], "confidence": read[1]}} if read else {}
    with patch.object(api, "_camera_for_node", lambda db, cid, action="": camera), \
         patch.object(api, "_live_spec", lambda c: spec), \
         patch.object(api, "touch_live", lambda spec: None), \
         patch.object(api, "release_connection", lambda db: None), \
         patch.object(api, "snapshot_for_camera", AsyncMock(return_value={"ok": bool(picture), "jpeg": picture})), \
         patch.object(api, "_manual_alpr_read", AsyncMock(return_value=alpr)), \
         patch("app.application.live_parking.handle_operator_entry", fake_entry), \
         patch("app.services.captures._write_jpeg", lambda kind, name, data: f"{kind}/{name}"), \
         patch("app.services.site_policy.site_policy", lambda db: {"plate_validation": "TZ"}), \
         patch.object(api, "write_audit", lambda db, user, action, kind, key, detail: audits.append(detail)):
        result = asyncio.run(api.entry_fallback(3, {"plate": typed}, db=_Db(), user=SimpleNamespace(username="cashier")))
    return result, entries, audits


def test_the_camera_read_is_used_when_the_operator_types_nothing():
    result, entries, audits = _run(read=("T404EDK", 0.93))
    assert result["plate"] == "T404EDK" and result["read_plate"] == "T404EDK" and not result["placeholder"]
    assert entries[0]["source"] == "operator-fallback" and entries[0]["image_ref"].startswith("snapshots/cam3-fallback-")
    assert "read=T404EDK" in audits[0]


def test_tanzanian_correction_applies_to_the_forced_read():
    result, _entries, _audits = _run(read=("7832ADF", 0.80))
    assert result["plate"] == "T832ADF"


def test_a_typed_plate_wins_over_the_camera():
    result, entries, audits = _run(typed="t123 abc", read=("T128ABC", 0.6))
    assert result["plate"] == "T123ABC" and result["typed_plate"] == "T123ABC"
    assert entries[0]["confidence"] == 1.0 and "typed=T123ABC" in audits[0]


def test_no_plate_at_all_still_prints_a_ticket_with_a_placeholder():
    result, entries, _audits = _run(read=None)
    assert result["placeholder"] is True and result["plate"].startswith("UNREAD")
    assert entries and entries[0]["plate"] == result["plate"]


def test_no_picture_still_lets_the_operator_admit_the_car():
    result, entries, _audits = _run(typed="T555XYZ", picture=b"")
    assert result["plate"] == "T555XYZ" and result["snapshot"] == "" and entries


def test_the_fallback_is_refused_on_an_exit_camera():
    with pytest.raises(HTTPException) as exc:
        _run(direction="EXIT")
    assert exc.value.status_code == 409


def test_operator_entry_goes_through_the_real_entry_controller():
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.application.live_parking import handle_operator_entry
    from app.db import Base
    from app.models import Camera, Gate, Lane, ParkingSession, Site, Tariff

    rules = {"currency": "TZS", "day_start": "00:00:00", "day_end": "23:59:59", "free_day_seconds": 2700,
             "free_night_seconds": 2700, "day_block_seconds": 2700, "night_block_seconds": 2700,
             "day_block_fee": 1000, "night_block_fee": 1000, "daily_wrap_fee": 34000, "over_1000_subtract": 1000}
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        db.add(Site(id=1, name="Site", currency="TZS"))
        db.flush()
        db.add(Gate(id=2, name="2#", site_id=1))
        db.flush()
        db.add(Lane(id=20, gate_id=2, name="2# Entry", direction="ENTRY"))
        db.flush()
        db.add(Camera(id=3, name="2# Entry", ip_address="10.0.0.3", site_id=1, gate_id=2, lane_id=20,
                      lane_direction="ENTRY"))
        db.add(Tariff(site_id=1, name="Car1", car_type="Car1", currency="TZS", rules=rules, active=True))
        db.commit()
        camera = db.get(Camera, 3)
        result = asyncio.run(handle_operator_entry(db, camera=camera, gate=None, plate="UNREAD7F3A",
                                                   image_ref="snapshots/x.jpg"))
        visit = db.scalar(select(ParkingSession).where(ParkingSession.plate == "UNREAD7F3A"))
        assert visit is not None, result
        assert visit.entry_image_ref == "snapshots/x.jpg"
    engine.dispose()


def test_live_gates_shows_ticket_on_entry_and_scan_on_exit(monkeypatch):
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from app.desktop import live_pane
    from app.desktop.main import CameraLivePane

    monkeypatch.setattr(live_pane.api, "can", lambda perm: True, raising=False)
    pane = CameraLivePane("Left")
    pane.set_camera({"id": 3, "name": "2# Entry", "lane_direction": "ENTRY", "gate_id": 2})
    assert not pane.ticket_btn.isHidden() and pane.scan_btn.isHidden()
    pane.set_camera({"id": 4, "name": "2# Exit", "lane_direction": "EXIT", "gate_id": 2})
    assert pane.ticket_btn.isHidden() and not pane.scan_btn.isHidden()
    pane.set_camera(None)
    assert pane.ticket_btn.isHidden() and pane.scan_btn.isHidden()
    pane.deleteLater()
    app.processEvents()
