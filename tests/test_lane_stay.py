"""A car waiting at a lane is captured again and again: one stay, one visit, best read wins.

Bench (SERVER01, 102 min): 69% of vehicles were captured 2+ times, ~4 s apart,
up to 2.5 min. A far first read (T630OWQ, T125EOT) opened a session and the
correct later read (T630DWQ, T125EJT) opened a second one for the same car.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.application.entry_lane import EntryLaneController
from app.application.exit_lane import ExitLaneController
from app.domain.parking_engine import LanePolicy, PASSAGE_WAIT
from app.domain.recognition import CONF_HIGH, NormalizedRecognitionEvent
from app.models import AccessDecision, Camera, Gate, ParkingSession
from app.services import lane_stay
from tests.test_lane_flow import Opener, Session  # noqa: F401  (fixture)

POLICY = LanePolicy(receipt_required_before_open=False, passage_sensing=PASSAGE_WAIT)


def _read(plate, n, confidence=0.9):
    return NormalizedRecognitionEvent(
        event_id=f"s-{plate}-{n}", site_id=1, camera_id=100, lane_id=10, occurred_at="2026-11-18T08:00:00+00:00",
        provider="FASTALPR", plate_raw=plate, plate_normalized=plate, confidence=confidence, bbox=None,
        vehicle_detected=True, image_ref="", plate_crop_ref="", confidence_class=CONF_HIGH, accepted=True,
    )


def _entry(db, plate, n, confidence=0.9):
    lane = EntryLaneController(opener=Opener())
    return asyncio.run(lane.submit(db, _read(plate, n, confidence), gate=db.get(Gate, 1),
                                   camera=db.get(Camera, 100), policy=POLICY))


def test_stay_votes_for_the_best_supported_plate():
    stay = lane_stay.Stay(1, 0, 0, [("T125EOT", 0.9), ("T125EJT", 0.6), ("T125EJT", 0.6), ("T125EJT", 0.6)])
    assert stay.best_plate() == "T125EJT"
    # O is not an issued series letter, so the valid shape wins a close vote
    assert lane_stay.Stay(1, 0, 0, [("T630OWQ", 0.8), ("T630DWQ", 0.7)]).best_plate() == "T630DWQ"
    assert lane_stay.same_vehicle("T630OWQ", "T630DWQ") and not lane_stay.same_vehicle("T630DWQ", "T921EQS")


def test_stay_ends_after_a_gap_or_a_different_car():
    a = lane_stay.observe(5, "T125EJT", 0.9, now=100.0)
    b = lane_stay.observe(5, "T125EJT", 0.9, now=104.0)
    assert b is a and b.repeats == 1
    c = lane_stay.observe(5, "T921EQS", 0.9, now=106.0)           # the next car
    assert c is not a and c.repeats == 0
    d = lane_stay.observe(5, "T921EQS", 0.9, now=106.0 + lane_stay.STAY_GAP_SECONDS + 1)
    assert d is not c                                              # it left and came back


def test_misread_then_correct_reads_make_one_visit_with_the_right_plate(Session):  # noqa: F811
    with Session() as db:
        first = _entry(db, "T125EOT", 1, 0.9)
        assert first["created_session"] is True
        replies = [_entry(db, "T125EJT", n, 0.6) for n in (2, 3, 4)]
        assert [r["created_session"] for r in replies] == [False, False, False]
        assert all(r["barrier_opened"] is False for r in replies)
        assert replies[0]["reason"] == "same_stay"                 # 0.9 vs 0.6: keep the first plate
        assert replies[1]["reason"] == "plate_corrected" and replies[1]["plate_corrected_from"] == "T125EOT"
        assert replies[2]["reason"] == "same_stay"
        plates = db.scalars(select(ParkingSession.plate)).all()
        assert plates == ["T125EJT"]                               # one visit, corrected plate
        outcomes = db.scalars(select(AccessDecision.outcome)).all()
        assert outcomes.count("PLATE_CORRECTED") == 1


def test_waiting_car_captured_many_times_keeps_one_visit(Session):  # noqa: F811
    with Session() as db:
        results = [_entry(db, "T630DWQ", n) for n in range(10)]
        assert sum(r["created_session"] for r in results) == 1
        assert {r["reason"] for r in results[1:]} == {"same_stay"}
        assert db.scalars(select(ParkingSession.plate)).all() == ["T630DWQ"]


def test_correction_never_takes_a_plate_that_has_its_own_visit(Session):  # noqa: F811
    with Session() as db:
        from datetime import datetime, timedelta, timezone

        _entry(db, "T630DWQ", 1)
        parked = db.scalar(select(ParkingSession))
        parked.created_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        db.commit()
        lane_stay.reset()                                          # that car is parked inside
        _entry(db, "T630OWQ", 2, 0.5)                              # a different car, read wrongly
        out = [_entry(db, "T630DWQ", n, 0.9) for n in (3, 4)]
        assert all(r["created_session"] is False for r in out)
        assert sorted(db.scalars(select(ParkingSession.plate)).all()) == ["T630DWQ", "T630OWQ"]


def test_exit_ignores_repeats_once_the_barrier_opened_for_the_stay():
    stay = lane_stay.observe(200, "T125EJT", 0.9)
    lane_stay.mark_opened(200)

    class _Camera:
        id = 200

    out = asyncio.run(ExitLaneController().submit_plate(
        None, plate="T125EJT", event_id="x", site_id=1, camera=_Camera(), confidence=0.9))
    assert out["reason"] == "same_stay" and out["barrier_opened"] is False and stay.repeats == 1
