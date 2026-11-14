"""Regression tests for the 2026-11 field hardening pass.

Covers: audited admit-without-receipt, outbox poison handling, first-run
password disclosure, operator payment methods, camera adapter validation,
stale first frames on the live MJPEG endpoint and the SDK host live window.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import PropertyMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.application.entry_lane import EntryLaneController
from app.config import Settings
from app.db import Base
from app.domain.parking_engine import ACTIVE, LanePolicy
from app.domain.recognition import CONF_HIGH, NormalizedRecognitionEvent
from app.infrastructure.hardware.receipt_printers import HardwareReceiptPrinter
from app.models import AuditLog, Camera, Gate, ParkingSession, Site
from app.services.gates import GateCommandResult


def _event(plate: str, event_id: str) -> NormalizedRecognitionEvent:
    return NormalizedRecognitionEvent(
        event_id=event_id, site_id=1, camera_id=100, lane_id=None,
        occurred_at="2026-11-14T12:00:00+00:00", provider="HVX_NATIVE",
        plate_raw=plate, plate_normalized=plate, confidence=0.95, bbox=None,
        vehicle_detected=True, image_ref="", plate_crop_ref="",
        confidence_class=CONF_HIGH, accepted=True,
    )


class _Opener:
    def __init__(self):
        self.calls = []

    async def __call__(self, db, gate, cameras, reason, session, side, command_uuid=""):
        self.calls.append(command_uuid)
        return GateCommandResult(ok=True, simulated=False, message="OPEN", timestamp="t")


class _NoSensorPrinter:
    """A real printer without a taken sensor (generic thermal printer)."""

    id = "escpos"
    capabilities = HardwareReceiptPrinter.capabilities

    async def print_entry_receipt(self, document, *, job_id):
        from app.domain.receipt_engine import PrintOutcome

        return PrintOutcome(ok=True, status="PRESENTED", adapter_id="escpos", simulated=False)


@pytest.fixture()
def site_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session() as db:
        db.add(Site(id=1, name="Site"))
        db.add(Gate(id=1, name="North", site_id=1))
        db.flush()
        db.add(Camera(id=100, name="N-In", ip_address="10.0.0.1", site_id=1, gate_id=1, lane_direction="ENTRY"))
        db.commit()
    media = Path(tempfile.mkdtemp(prefix="zirp-hardening-"))
    with patch.object(Settings, "media_dir", new_callable=PropertyMock, return_value=media):
        yield Session
    shutil.rmtree(media, ignore_errors=True)
    engine.dispose()


def test_casual_entry_without_taken_sensor_waits_then_operator_admits_with_audit(site_db):
    policy = LanePolicy(receipt_required_before_open=True, passage_sensing="OPEN_COMMAND_COUNTS_AS_PASSED")

    async def run():
        opener = _Opener()
        ctrl = EntryLaneController(printer=_NoSensorPrinter(), opener=opener)
        with site_db() as db:
            gate, camera = db.get(Gate, 1), db.get(Camera, 100)
            first = await ctrl.submit(db, _event("T123ABC", "evt-1"), gate=gate, camera=camera, policy=policy)
            assert first["reason"] == "waiting_receipt"
            assert first["barrier_opened"] is False
            assert opener.calls == []
            row = db.get(ParkingSession, first["session"]["id"])
            done = await ctrl.operator_admit_without_receipt(
                db, row, reason="printer not installed", user_id=None, policy=policy, gate=gate, camera=camera,
            )
            assert done["ok"] is True
            assert len(opener.calls) == 1
            db.refresh(row)
            assert row.lifecycle == ACTIVE
            assert row.receipt_status == "OVERRIDE"
            audit = db.scalars(select(AuditLog).where(AuditLog.action == "RECEIPT_OPERATOR_OVERRIDE")).all()
            assert len(audit) == 1 and "printer not installed" in audit[0].detail
            # A second override is idempotent: no second barrier command.
            again = await ctrl.operator_admit_without_receipt(
                db, row, reason="double click", user_id=None, policy=policy, gate=gate, camera=camera,
            )
            assert again["reason"] == "already_open"
            assert len(opener.calls) == 1

    asyncio.run(run())


def test_outbox_dead_letters_a_poison_event_and_keeps_later_events(tmp_path):
    from app.services.queues import SQLiteOutbox

    box = SQLiteOutbox(tmp_path / "outbox.sqlite3")
    bad = box.enqueue("PlateRecognized", {"event_id": "bad"})
    good = box.enqueue("PlateRecognized", {"event_id": "good"})
    for attempt in range(SQLiteOutbox.MAX_ATTEMPTS - 1):
        assert box.record_failure(bad, "boom") is False
    assert box.record_failure(bad, "boom") is True
    assert [item["id"] for item in box.pending()] == [good]
    assert box.dead_letter_depth() == 1
    box.ack(good)
    assert box.depth() == 0


def test_setup_status_hides_password_and_accounts_from_lan_requests(tmp_path):
    from app.services import bootstrap

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with patch.object(Settings, "data_dir", new_callable=PropertyMock, return_value=tmp_path), \
         patch.object(bootstrap.settings, "bootstrap_password", ""):
        with Session() as db:
            from app.api_main import ensure_roles

            ensure_roles(db)
            remote = bootstrap.setup_status(db, local_request=False)
            assert remote["password"] == ""
            assert remote["usernames"] == []
            local = bootstrap.setup_status(db, local_request=True)
            assert local["password"]
            assert local["usernames"]
    engine.dispose()


def test_operator_can_record_cash_only():
    from app import api_main

    assert api_main._operator_payment_method(None) == "KIOSK_CASH"
    assert api_main._operator_payment_method("cash") == "KIOSK_CASH"
    for method in ("MOBILE_MONEY", "MOBILE_SIMULATED", "CARD"):
        with pytest.raises(HTTPException):
            api_main._operator_payment_method(method)


def test_unknown_camera_adapter_is_rejected_instead_of_becoming_qy():
    from app.schemas import CameraCreate, CameraUpdate

    assert CameraCreate(name="c", ip_address="10.0.0.9", adapter_id="QY").adapter_id == "qy"
    with pytest.raises(ValidationError):
        CameraCreate(name="c", ip_address="10.0.0.9", adapter_id="hikvison")
    with pytest.raises(ValidationError):
        CameraUpdate(adapter_id="rtps")


def test_live_mjpeg_never_sends_an_old_cached_frame_to_a_new_viewer():
    from app.services import preview

    camera_id = 9871
    row = preview.get_state(camera_id)
    row.jpeg = b"\xff\xd8old\xff\xd9"
    row.seq = 5
    row.captured_at = time.monotonic() - 600  # cached ten minutes ago

    async def run():
        gen = preview.mjpeg_from_cache(camera_id)
        first = asyncio.ensure_future(gen.__anext__())
        await asyncio.sleep(0.2)
        assert not first.done(), "stale cached frame was sent to a new viewer"
        row.jpeg = b"\xff\xd8new\xff\xd9"
        row.captured_at = time.monotonic()
        row.seq += 1
        preview._notify(row)
        part = await asyncio.wait_for(first, timeout=1.0)
        assert b"new" in part
        await gen.aclose()

    with patch.object(preview.gateway, "session", return_value=None):
        asyncio.run(run())


def test_sdk_host_first_request_does_not_return_an_old_frame():
    from tools.hvx_sdk_host.hvx_sdk import HVXSDK

    sdk = HVXSDK.__new__(HVXSDK)
    sdk._lock = threading.Lock()
    sdk._live_condition = threading.Condition(sdk._lock)
    sdk._live_requested_at = {}
    sdk._video_diagnostics = {}
    sdk._live_frame_seq = {7: 3}
    sdk._last_live_jpeg = {7: b"\xff\xd8old"}
    sdk._live_received_at = {7: time.monotonic() - 4.0}  # older than the live window
    jpeg, _ = sdk.live_frame_for(7, after_seq=0, wait_ms=50)
    assert jpeg == b""
    sdk._live_received_at[7] = time.monotonic()
    jpeg, _ = sdk.live_frame_for(7, after_seq=0, wait_ms=50)
    assert jpeg == b"\xff\xd8old"


def test_native_plate_is_kept_when_software_verification_produced_nothing():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app import api_main

    camera = SimpleNamespace(id=55, recognition_mode="HYBRID", adapter_id="qy")
    persist = AsyncMock(return_value={"plate": "T999XYZ"})
    native = {"plate": "T999XYZ", "confidence": 0.93}
    with patch.object(api_main, "_persist_capture_event", persist):
        for failed in (None, {"ok": False, "error": "timeout"}, {"persist_skipped": "stale recognition result"}):
            persist.reset_mock()
            used = asyncio.run(api_main._native_fallback_if_unread(None, camera, {"image_id": 1}, b"", b"", native, failed))
            assert used is True
            assert persist.await_args.args[2]["source"] == "native-fallback"
        persist.reset_mock()
        # Software ran and decided: do not override it with the native text.
        assert asyncio.run(api_main._native_fallback_if_unread(None, camera, {}, b"", b"", native, {"ok": True, "best": None})) is False
        # Software-only lanes never fall back to the camera text.
        local = SimpleNamespace(id=56, recognition_mode="FASTALPR_ONLY", adapter_id="qy")
        assert asyncio.run(api_main._native_fallback_if_unread(None, local, {}, b"", b"", native, None)) is False
        persist.assert_not_awaited()


def test_second_event_waits_for_running_read_instead_of_being_dropped():
    from types import SimpleNamespace
    from app import api_main

    camera = SimpleNamespace(id=57)
    calls = []

    async def fake_run(db, cam, jpeg, **kwargs):
        calls.append(kwargs.get("event_still"))
        if len(calls) == 1:
            return {"ok": False, "error": "busy"}
        return {"ok": True, "best": {"plate": "T1"}}

    async def run():
        blocker = asyncio.get_running_loop().create_future()
        api_main._local_alpr_pending[57] = asyncio.ensure_future(blocker)
        asyncio.get_running_loop().call_later(0.05, blocker.set_result, None)
        with patch.object(api_main, "_run_local_alpr", fake_run):
            result = await api_main._run_event_alpr(None, camera, b"\xff\xd8", native={})
        api_main._local_alpr_pending.pop(57, None)
        return result

    result = asyncio.run(run())
    assert result["ok"] is True
    assert calls == [True, True]
