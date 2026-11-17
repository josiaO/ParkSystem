"""Manual barrier openings: car/visit/money capture, alert routing and delivery."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db import Base
from app.domain.parking_engine import LanePolicy
from app.infrastructure.payments.ledger import record_succeeded_payment
from app.models import (
    MANUAL_SOURCE_ADMIT,
    MANUAL_SOURCE_GATE,
    MANUAL_SOURCE_UNCOMMANDED,
    AccessPlan,
    AlertDelivery,
    Camera,
    Gate,
    GateCommandRecord,
    Lane,
    ManualOpenEvent,
    RegisteredVehicle,
    Site,
    Tariff,
    User,
    VehicleCapture,
)
from app.services import alerts, manual_open
from app.services.parking_sessions import complete_casual_entry, start_entry

RULES = {
    "currency": "TZS", "day_start": "00:00:00", "day_end": "23:59:59",
    "free_day_seconds": 2700, "free_night_seconds": 2700,
    "day_block_seconds": 2700, "night_block_seconds": 2700,
    "day_block_fee": 1000, "night_block_fee": 1000,
    "daily_wrap_fee": 34000, "over_1000_subtract": 1000,
}
NOW = datetime(2026, 11, 16, 15, 0, tzinfo=timezone.utc)


@pytest.fixture()
def Session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        db.add(Site(id=1, name="Rock City", currency="TZS"))
        db.add(Gate(id=2, name="2#", site_id=1))
        db.flush()
        db.add_all([
            Lane(id=20, gate_id=2, name="2# Entry", direction="ENTRY"),
            Lane(id=21, gate_id=2, name="2# Exit", direction="EXIT"),
            Camera(id=3, name="2# Entry", ip_address="10.0.0.49", site_id=1, gate_id=2, lane_id=20, lane_direction="ENTRY"),
            Camera(id=4, name="2# Exit", ip_address="10.0.0.50", site_id=1, gate_id=2, lane_id=21, lane_direction="EXIT"),
            User(id=7, username="cashier", full_name="Cashier A", password_hash="x"),
            User(id=8, username="supervisor", full_name="Supervisor", password_hash="x"),
        ])
        db.add(Tariff(site_id=1, name="Car1", car_type="Car1", currency="TZS", rules=RULES, active=True))
        db.commit()
    manual_open.boom_watch.reset()
    manual_open._boom_index_cache.clear()
    yield factory
    engine.dispose()


def _visit(db, plate, entered):
    row, _ = start_entry(db, plate=plate, event_id=f"e-{plate}", site_id=1, gate_id=2, lane_id=20,
                         camera_id=3, policy=LanePolicy())
    row.entry_time = entered
    db.commit()
    return complete_casual_entry(db, row, policy=LanePolicy())


def _capture(db, plate, camera_id, at, confidence=0.98):
    row = VehicleCapture(camera_id=camera_id, gate_id=2, lane_direction="EXIT" if camera_id == 4 else "ENTRY",
                         plate=plate, plate_raw=plate, confidence=confidence, created_at=at)
    db.add(row)
    db.commit()
    return row


def _recipients(db, **extra):
    alerts.save_alert_settings(db, {"recipients": [
        {"channel": "sms", "to": "0712345678", "name": "Manager"},
        {"channel": "email", "to": "ops@example.test"},
    ], **extra})


# ----------------------------------------------------------------- recording

def test_exit_manual_open_captures_car_visit_and_amount_owed(Session):
    with Session() as db:
        _recipients(db)
        visit = _visit(db, "T123ABC", NOW - timedelta(hours=3))
        _capture(db, "T123ABC", 4, NOW - timedelta(seconds=20))
        event = manual_open.record_manual_open(
            db, source=MANUAL_SOURCE_GATE, gate=db.get(Gate, 2), side="EXIT", user=db.get(User, 7),
            reason="barrier stuck, driver says paid", command_ok=True, command_message="open lane 2# EXIT", at=NOW,
        )
        assert event.plate == "T123ABC"
        assert event.session_id == visit.id
        assert event.lane_label == "2# Exit"
        assert event.operator_name == "Cashier A"
        assert float(event.amount_owed) > 0 and float(event.amount_due) == float(event.amount_owed)
        assert event.duration_seconds == 3 * 3600
        assert float(event.plate_seconds_before) == 20.0
        deliveries = db.scalars(select(AlertDelivery).where(AlertDelivery.event_id == event.id)).all()
        assert {(d.channel, d.recipient) for d in deliveries} == {("sms", "+255712345678"), ("email", "ops@example.test")}
        assert event.alert_status == "QUEUED"
        # The session itself is untouched: a manual open is not a payment or a closure.
        db.refresh(visit)
        assert visit.status != "CLOSED" and float(visit.amount_paid or 0) == 0


def test_paid_inside_grace_owes_nothing(Session):
    with Session() as db:
        visit = _visit(db, "T200PAY", NOW - timedelta(hours=2))
        from app.services.simulation import mark_paid
        with patch("app.services.simulation.quote_session") as quote:
            quote.side_effect = lambda d, r, **k: (setattr(r, "amount_due", 3000), {})[1]
            mark_paid(db, visit, method="KIOSK_CASH")
        db.refresh(visit)
        snap = manual_open.owed_snapshot(db, visit, at=datetime.now(timezone.utc))
        assert snap["basis"] == "payment_grace" and snap["owed"] == 0 and snap["paid"] == 3000


def test_subscriber_owes_nothing_and_zero_fee_alert_can_be_muted(Session):
    with Session() as db:
        _recipients(db, notify_zero_fee=False)
        plan = AccessPlan(site_id=1, name="Staff", kind="STAFF", enabled=True)
        db.add(plan)
        db.flush()
        db.add(RegisteredVehicle(site_id=1, plate="T300VIP", plan_id=plan.id, enabled=True))
        db.commit()
        _visit(db, "T300VIP", NOW - timedelta(hours=5))
        _capture(db, "T300VIP", 4, NOW - timedelta(seconds=5))
        event = manual_open.record_manual_open(db, source=MANUAL_SOURCE_GATE, gate=db.get(Gate, 2), side="EXIT",
                                               user=db.get(User, 7), reason="vip", command_ok=True, at=NOW)
        assert float(event.amount_owed) == 0 and event.parker_kind == "STAFF"
        assert event.alert_status == "NOT_SENT"
        assert db.scalar(select(AlertDelivery.id)) is None


def test_no_recent_plate_is_unidentified_and_always_alerted(Session):
    with Session() as db:
        _recipients(db, notify_zero_fee=False)
        _capture(db, "T999OLD", 4, NOW - timedelta(seconds=settings.manual_open_capture_window_seconds + 30))
        event = manual_open.record_manual_open(db, source=MANUAL_SOURCE_GATE, gate=db.get(Gate, 2), side="EXIT",
                                               user=db.get(User, 7), reason="no read", command_ok=True, at=NOW)
        assert event.plate == "" and event.session_id is None
        assert event.alert_status == "QUEUED"
        text = alerts.format_alert(event, db)
        assert "NOT identified" in text["short"]


def test_only_the_lane_side_that_opened_is_searched(Session):
    with Session() as db:
        _capture(db, "T111ENT", 3, NOW - timedelta(seconds=3))  # entry camera, other side
        event = manual_open.record_manual_open(db, source=MANUAL_SOURCE_GATE, gate=db.get(Gate, 2), side="EXIT",
                                               user=db.get(User, 7), reason="exit", command_ok=True, at=NOW)
        assert event.plate == ""


def test_admit_without_receipt_uses_the_session_plate(Session):
    with Session() as db:
        visit = _visit(db, "T444ADM", NOW - timedelta(minutes=1))
        event = manual_open.record_manual_open(db, source=MANUAL_SOURCE_ADMIT, gate=db.get(Gate, 2), camera=db.get(Camera, 3),
                                               side="ENTRY", user=db.get(User, 7), reason="printer jam",
                                               session=visit, command_ok=True, at=NOW)
        assert event.plate == "T444ADM" and event.session_id == visit.id and float(event.amount_owed) == 0


def test_evidence_photo_is_copied_into_the_never_pruned_folder(Session, tmp_path):
    with patch.object(type(settings), "media_dir", property(lambda self: tmp_path)):
        (tmp_path / "snapshots").mkdir()
        (tmp_path / "snapshots" / "cam4-car.jpg").write_bytes(b"\xff\xd8car")
        with Session() as db:
            capture = _capture(db, "T555PIC", 4, NOW - timedelta(seconds=2))
            capture.snapshot_path = "snapshots/cam4-car.jpg"
            db.commit()
            event = manual_open.record_manual_open(db, source=MANUAL_SOURCE_GATE, gate=db.get(Gate, 2), side="EXIT",
                                                   user=db.get(User, 7), reason="test", command_ok=True, at=NOW)
            assert event.photo_ref.startswith("manual/")
            assert (tmp_path / event.photo_ref).read_bytes() == b"\xff\xd8car"
            assert manual_open._read_media(event.photo_ref) == b"\xff\xd8car"


# -------------------------------------------------------------------- message

def test_alert_text_names_plate_money_operator_reason_and_photo(Session):
    with Session() as db:
        _recipients(db)
        _visit(db, "T123ABC", NOW - timedelta(hours=3))
        _capture(db, "T123ABC", 4, NOW - timedelta(seconds=20))
        event = manual_open.record_manual_open(db, source=MANUAL_SOURCE_GATE, gate=db.get(Gate, 2), side="EXIT",
                                               user=db.get(User, 7), reason="driver has no cash",
                                               command_ok=True, at=NOW)
        event.photo_ref = "manual/x.jpg"
        text = alerts.format_alert(event, db)
        assert "T123ABC" in text["short"] and "owed TZS" in text["short"]
        assert "Cashier A" in text["short"] and "driver has no cash" in text["short"]
        assert "/manual-opens/" in text["short"] and "sig=" in text["short"]
        assert len(text["short"]) <= 459
        assert "owed TZS" in text["subject"]


def test_uncommanded_and_failed_wording():
    event = ManualOpenEvent(id=1, source=MANUAL_SOURCE_UNCOMMANDED, lane_label="2# Exit", command_ok=True,
                            created_at=NOW, amount_owed=0, amount_due=0, amount_paid=0, currency="TZS",
                            command_message="", reason="")
    assert "WITHOUT a Zirp command" in alerts.format_alert(event)["short"]
    event.source, event.command_ok = MANUAL_SOURCE_GATE, False
    assert "FAILED" in alerts.format_alert(event)["short"]


def test_alert_rules():
    cfg = {"enabled": True, "recipients": [{"channel": "sms", "to": "+255712345678"}],
           "notify_zero_fee": False, "notify_failed_commands": False}
    base = dict(id=1, source=MANUAL_SOURCE_GATE, command_ok=True, plate="T1", amount_owed=0)
    assert not alerts.should_alert(ManualOpenEvent(**base), cfg)
    assert alerts.should_alert(ManualOpenEvent(**{**base, "amount_owed": 500}), cfg)
    assert alerts.should_alert(ManualOpenEvent(**{**base, "plate": ""}), cfg)
    assert alerts.should_alert(ManualOpenEvent(**{**base, "source": MANUAL_SOURCE_UNCOMMANDED}), cfg)
    assert not alerts.should_alert(ManualOpenEvent(**{**base, "command_ok": False, "amount_owed": 500}), cfg)
    assert not alerts.should_alert(ManualOpenEvent(**{**base, "amount_owed": 500}), {**cfg, "enabled": False})


# ------------------------------------------------------------------- delivery

def _queued_event(Session):
    with Session() as db:
        _recipients(db)
        event = manual_open.record_manual_open(db, source=MANUAL_SOURCE_GATE, gate=db.get(Gate, 2), side="EXIT",
                                               user=db.get(User, 7), reason="test", command_ok=True, at=NOW)
        return event.id


def test_delivery_success_marks_sent(Session):
    event_id = _queued_event(Session)
    sent = []
    counts = alerts.deliver_due_once(Session, sender=lambda db, d, e: sent.append((d.channel, e.id)) or "ok",
                                     now=datetime.now(timezone.utc))
    assert counts["sent"] == 2 and len(sent) == 2
    with Session() as db:
        assert db.get(ManualOpenEvent, event_id).alert_status == "SENT"
        assert all(d.status == "SENT" for d in db.scalars(select(AlertDelivery)).all())
    assert alerts.deliver_due_once(Session, sender=lambda *a: "ok")["sent"] == 0  # nothing re-sent


def test_delivery_failure_retries_with_backoff_then_dead_letters(Session):
    event_id = _queued_event(Session)

    def boom(db, delivery, event):
        raise alerts.AlertSendError("provider down")

    now = datetime.now(timezone.utc)
    counts = alerts.deliver_due_once(Session, sender=boom, now=now)
    assert counts["retry"] == 2
    with Session() as db:
        rows = db.scalars(select(AlertDelivery)).all()
        assert all(r.status == "RETRY" and r.attempts == 1 and "provider down" in r.last_error for r in rows)
        assert all(alerts._aware(r.next_attempt_at) >= now + timedelta(seconds=15) for r in rows)
        assert db.get(ManualOpenEvent, event_id).alert_status == "QUEUED"
    # Not due yet: nothing is attempted.
    assert alerts.deliver_due_once(Session, sender=boom, now=now)["retry"] == 0
    with patch.object(settings, "alerts_max_attempts", 2):
        counts = alerts.deliver_due_once(Session, sender=boom, now=now + timedelta(hours=2))
    assert counts["dead"] == 2
    with Session() as db:
        assert db.get(ManualOpenEvent, event_id).alert_status == "FAILED"


def test_claims_are_exclusive(Session):
    _queued_event(Session)
    now = datetime.now(timezone.utc)
    with Session() as db:
        first = alerts.claim_due(db, now=now)
        second = alerts.claim_due(db, now=now)
        assert len(first) == 2 and second == []
        # A claim abandoned by a crashed process is reclaimed after the timeout.
        assert len(alerts.claim_due(db, now=now + alerts.CLAIM_TIMEOUT + timedelta(seconds=1))) == 2


def test_sms_adapter_reads_africastalking_status():
    class Response:
        status_code = 201
        text = ""

        def __init__(self, code):
            self._code = code

        def json(self):
            return {"SMSMessageData": {"Recipients": [{"statusCode": self._code, "status": "x", "messageId": "m1"}]}}

    with patch.object(settings, "alerts_africastalking_username", "sandbox"), \
            patch.object(settings, "alerts_africastalking_api_key", "k" * 20), \
            patch("httpx.post", return_value=Response(101)) as post:
        assert alerts.send_sms("+255712345678", "hi") == "m1"
        assert post.call_args.kwargs["headers"]["apiKey"] == "k" * 20
    with patch.object(settings, "alerts_africastalking_username", "sandbox"), \
            patch.object(settings, "alerts_africastalking_api_key", "k" * 20), \
            patch("httpx.post", return_value=Response(403)):
        with pytest.raises(alerts.AlertSendError):
            alerts.send_sms("+255712345678", "hi")


def test_unconfigured_provider_fails_cleanly():
    with patch.object(settings, "alerts_africastalking_api_key", ""):
        with pytest.raises(alerts.AlertSendError):
            alerts.send_sms("+255712345678", "hi")


# ------------------------------------------------------------------- settings

def test_settings_validation(Session):
    with Session() as db:
        saved = alerts.save_alert_settings(db, {"recipients": [
            {"channel": "SMS", "to": "0712 345 678"}, {"channel": "sms", "to": "+255712345678"},
            {"channel": "webhook", "to": "https://hooks.example.test/zirp"},
        ], "boom_inputs": {"4": {"index": 5, "active": 1}}})
        assert [r["to"] for r in saved["recipients"]] == ["+255712345678", "https://hooks.example.test/zirp"]
        assert saved["boom_inputs"] == {"4": {"index": 5, "active": 1}}
        for bad in ({"channel": "email", "to": "not-an-email"}, {"channel": "fax", "to": "1"},
                    {"channel": "webhook", "to": "ftp://x"}):
            with pytest.raises(ValueError):
                alerts.save_alert_settings(db, {"recipients": [bad]})


# ---------------------------------------------------------------- uncommanded

def test_boom_rising_without_a_command_is_recorded_once(Session):
    with Session() as db:
        alerts.save_alert_settings(db, {"boom_inputs": {"4": {"index": 5, "active": 1}}})
        camera = db.get(Camera, 4)
        assert manual_open.observe_boom_input(db, camera, 0, at=NOW) is None      # primes
        event = manual_open.observe_boom_input(db, camera, 1, at=NOW)
        assert event is not None and event.source == MANUAL_SOURCE_UNCOMMANDED and event.lane_label == "2# Exit"
        assert manual_open.observe_boom_input(db, camera, 1, at=NOW) is None      # still up: no repeat
        assert manual_open.observe_boom_input(db, camera, 0, at=NOW) is None


def test_boom_rising_after_a_zirp_command_is_not_uncommanded(Session):
    with Session() as db:
        alerts.save_alert_settings(db, {"boom_inputs": {"4": {"index": 5, "active": 1}}})
        db.add(GateCommandRecord(command_uuid="c1", gate_id=2, ok=True, created_at=NOW - timedelta(seconds=2)))
        db.commit()
        camera = db.get(Camera, 4)
        manual_open.observe_boom_input(db, camera, 0, at=NOW)
        assert manual_open.observe_boom_input(db, camera, 1, at=NOW) is None
        # A recorded operator manual open on the same lane also explains it.
        manual_open.record_manual_open(db, source=MANUAL_SOURCE_GATE, gate=db.get(Gate, 2), side="EXIT",
                                       user=db.get(User, 7), reason="op", command_ok=True,
                                       at=NOW + timedelta(seconds=60), queue_alerts=False)
        manual_open.observe_boom_input(db, camera, 0, at=NOW + timedelta(seconds=61))
        assert manual_open.observe_boom_input(db, camera, 1, at=NOW + timedelta(seconds=62)) is None


def test_unconfigured_camera_is_ignored(Session):
    with Session() as db:
        camera = db.get(Camera, 3)
        manual_open.observe_boom_input(db, camera, 0, at=NOW)
        assert manual_open.observe_boom_input(db, camera, 1, at=NOW) is None


# --------------------------------------------------------------- photo links

def test_photo_link_signature():
    event = ManualOpenEvent(id=42)
    path = manual_open.signed_photo_path(event, hours=1)
    exp = int(path.split("exp=")[1].split("&")[0])
    sig = path.split("sig=")[1]
    assert manual_open.verify_photo_signature(42, exp, sig)
    assert not manual_open.verify_photo_signature(43, exp, sig)
    assert not manual_open.verify_photo_signature(42, exp + 1, sig)
    assert not manual_open.verify_photo_signature(42, int(time.time()) - 5, manual_open.photo_signature(42, int(time.time()) - 5))


def test_photo_link_is_the_only_public_manual_open_route():
    from app.services.public_ingress import public_route_category

    assert public_route_category("/manual-opens/5/photo.jpg", "GET") == "alert-photo"
    assert public_route_category("/manual-opens/5", "GET") is None
    assert public_route_category("/manual-opens", "GET") is None
    assert public_route_category("/manual-opens/5/acknowledge", "POST") is None


# --------------------------------------------------------------------- routes

def test_manual_open_routes_require_a_reason_and_skip_close_and_dry_run():
    from fastapi import HTTPException

    import app.api_main as runtime
    from app.schemas import ManualGateCommand

    with pytest.raises(HTTPException) as err:
        runtime._require_manual_reason(ManualGateCommand(reason=" ", side="EXIT"))
    assert err.value.status_code == 400
    runtime._require_manual_reason(ManualGateCommand(reason=" ", action="close"))
    runtime._require_manual_reason(ManualGateCommand(reason="", dry_run=True))
    with patch("app.services.manual_open.safe_record_manual_open") as record:
        result = SimpleNamespace(ok=True, simulated=False, message="m")
        runtime._record_manual_open_from_command(None, ManualGateCommand(reason="x", action="close"), result, user=None)
        runtime._record_manual_open_from_command(None, ManualGateCommand(reason="x", dry_run=True), result, user=None)
        assert record.call_count == 0
        runtime._record_manual_open_from_command("db", ManualGateCommand(reason="fault"), result, user="u",
                                                 gate=SimpleNamespace(id=2), side="EXIT")
        kwargs = record.call_args.kwargs
        assert kwargs["source"] == MANUAL_SOURCE_GATE and kwargs["command_ok"] is True and kwargs["side"] == "EXIT"


# --------------------------------------------------------------------- desktop

def test_desktop_banner_text():
    from app.desktop.desk import manual_open_banner

    assert manual_open_banner([]) == ""
    text = manual_open_banner([
        {"id": 2, "lane": "2# Exit", "plate": "T123ABC", "amount_owed": 5000, "currency": "TZS", "session_id": 9,
         "operator": "Cashier A", "reason": "no cash", "source": MANUAL_SOURCE_GATE, "command_ok": True},
        {"id": 1, "lane": "2# Entry", "plate": "", "source": MANUAL_SOURCE_UNCOMMANDED},
    ])
    assert "T123ABC" in text and "owed TZS 5,000" in text and "Cashier A" in text and "+1 more" in text
    assert "UNIDENTIFIED" in manual_open_banner([{"id": 3, "lane": "x", "plate": ""}])
