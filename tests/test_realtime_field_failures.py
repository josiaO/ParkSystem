"""Field-failure regressions: latest-frame-wins, isolation, stale plates, exactly-once."""

from __future__ import annotations

import asyncio
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import Base
from app.domain.parking_engine import LanePolicy
from app.domain.recognition import CONF_HIGH, NormalizedRecognitionEvent
from app.models import Camera, Gate, Lane, ParkingSession, Site
from app.services import parking_sessions as sessions
from app.services.preview import fresh_last_car, remember_last_car
from app.services.recognition_runtime import (
    EVENT_PUBLISHED,
    IDLE,
    FairInferenceScheduler,
    RecognitionRuntime,
    RecognitionTicket,
    runtime,
)


JPEG = b"\xff\xd8" + b"FRAME" + b"\xff\xd9"


def _event(plate: str, event_id: str, *, camera_id=100, visit_id="", confidence=0.95):
    return NormalizedRecognitionEvent(
        event_id=event_id,
        site_id=1,
        camera_id=camera_id,
        lane_id=10,
        occurred_at="2026-10-02T12:00:00+00:00",
        provider="FASTALPR",
        plate_raw=plate,
        plate_normalized=plate,
        confidence=confidence,
        bbox=None,
        vehicle_detected=True,
        image_ref="",
        plate_crop_ref="",
        confidence_class=CONF_HIGH,
        accepted=True,
        visit_id=visit_id,
    )


class LatestFrameWinsTests(unittest.TestCase):
    def setUp(self):
        self.rt = RecognitionRuntime(max_concurrency=2)
        self.rt.reset()
        self.rt.scheduler = FairInferenceScheduler(2)

    def test_a_slow_inference_keeps_only_newest_pending_frame(self):
        lane = self.rt.lane(1)
        for number in range(1, 6):
            lane.offer_frame(JPEG + bytes([number]), source="detect")
        self.assertEqual(lane.mailbox.depth(), 1)
        self.assertGreaterEqual(lane.mailbox.dropped, 4)
        ticket = self.rt.begin_if_idle(1)
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket.frame_seq, 5)
        self.assertEqual(lane.mailbox.depth(), 0)
        self.assertLessEqual(lane.mailbox.depth(), 1)

    def test_b_older_ocr_cannot_replace_newer_plate(self):
        lane = self.rt.lane(2)
        first = lane.offer_frame(JPEG + b"1")
        old = lane.begin(first)
        newer = lane.offer_frame(JPEG + b"2")
        new = lane.begin(newer)
        self.assertTrue(lane.accept(new, plate="T999NEW"))
        self.assertFalse(lane.accept(old, plate="T000OLD"))
        self.assertEqual(lane.last_plate, "T999NEW")
        self.assertGreater(lane.stale_results_rejected, 0)


class IsolationAndWatchdogTests(unittest.TestCase):
    def test_c_blocked_camera_does_not_starve_others(self):
        sched = FairInferenceScheduler(2)
        self.assertTrue(sched.try_acquire(1))
        self.assertTrue(sched.try_acquire(2))
        self.assertFalse(sched.try_acquire(3))
        self.assertFalse(sched.try_acquire(1))
        sched.force_release(1)
        self.assertTrue(sched.try_acquire(3))
        self.assertTrue(sched.try_acquire(4) or sched.try_acquire(2) is False)
        sched.release(2)
        self.assertTrue(sched.try_acquire(4))
        self.assertEqual(sorted(sched.held()), [3, 4])

    def test_d_watchdog_recovers_stalled_inference(self):
        rt = RecognitionRuntime(max_concurrency=2)
        rt.reset()
        rt.scheduler = FairInferenceScheduler(2)
        lane = rt.lane(7)
        lane.offer_frame(JPEG)
        ticket = rt.begin_if_idle(7)
        self.assertIsNotNone(ticket)
        ticket = RecognitionTicket(
            camera_id=7,
            frame_seq=ticket.frame_seq,
            generation=ticket.generation,
            captured_at=time.monotonic() - 8.0,
            recognition_started_at=time.monotonic() - 8.0,
            jpeg=JPEG,
        )
        lane.inflight = ticket
        lane.last_frame_at = time.monotonic()
        lane.last_recognition_started_at = ticket.recognition_started_at
        self.assertTrue(lane.is_stalled(5.0))
        recovered = rt.watchdog_once(5.0)
        self.assertIn(7, recovered)
        self.assertIsNone(lane.inflight)
        self.assertGreater(lane.generation, ticket.generation)
        lane.offer_frame(JPEG + b"n")
        fresh = rt.begin_if_idle(7)
        self.assertIsNotNone(fresh)
        self.assertFalse(lane.accept(ticket, plate="STALE"))
        self.assertTrue(rt.finish(fresh, plate="T111NEW"))
        self.assertEqual(lane.last_plate, "T111NEW")


class StaleAndPhantomPlateTests(unittest.TestCase):
    def tearDown(self):
        from app.services import preview
        preview._state.clear()
        runtime.reset()

    def test_e_empty_lane_clears_current_plate(self):
        lane = runtime.lane(3)
        lane.visit.observe(presence=True, plate="T123ABC", now=100.0)
        lane.last_plate = "T123ABC"
        lane.last_plate_at = time.monotonic()
        remember_last_car(3, {"plate": "T123ABC"})
        self.assertEqual(fresh_last_car(3, max_age_seconds=4)["plate"], "T123ABC")
        lane.visit.observe(presence=False, plate="", now=100.1, absence_seconds=0.5)
        lane.visit.observe(presence=False, plate="", now=100.7, absence_seconds=0.5)
        self.assertEqual(lane.visit.state, IDLE)
        self.assertFalse(lane.visit.vehicle_present)
        lane.clear_current_plate()
        remember_last_car(3, None)
        self.assertIsNone(fresh_last_car(3, max_age_seconds=4))
        snap = lane.snapshot(now=time.monotonic(), plate_fresh_seconds=4)
        self.assertEqual(snap["last_plate"], "")
        self.assertFalse(snap["vehicle_present"])

    def test_f_no_fabricated_plate_without_ocr(self):
        from app.domain.recognition import empty_vehicle_event
        from app.services.alpr import recognize_bytes

        body = empty_vehicle_event()
        self.assertFalse(body["normalized_plate"])
        self.assertFalse(body["plate_text"])
        empty = recognize_bytes(b"")
        self.assertFalse(empty.get("best"))
        self.assertEqual(empty.get("plates"), [])


class VisitAndSessionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        with self.Session() as db:
            db.add(Site(id=1, name="Site"))
            db.add(Gate(id=1, name="North", site_id=1))
            db.flush()
            db.add_all([
                Lane(id=10, gate_id=1, name="North Entry", direction="ENTRY"),
                Camera(id=100, name="N-In", ip_address="10.0.0.1", site_id=1, gate_id=1, lane_direction="ENTRY"),
            ])
            db.commit()
        self.policy = LanePolicy(receipt_required_before_open=False)

    def tearDown(self):
        self.engine.dispose()

    def test_g_repeated_recognition_one_session(self):
        visit = "visit-same-car"
        with self.Session() as db:
            first, created = sessions.start_entry_from_recognition(
                db, _event("T285DQP", "e1", visit_id=visit), gate_id=1, policy=self.policy,
            )
            self.assertTrue(created)
            for index, plate in enumerate(("T285DQP", "T285DQP", "T285DQP"), start=2):
                row, created = sessions.start_entry_from_recognition(
                    db, _event(plate, f"e{index}", visit_id=visit), gate_id=1, policy=self.policy,
                )
                self.assertFalse(created)
                self.assertEqual(row.id, first.id)
            self.assertEqual(db.scalar(select(func.count()).select_from(ParkingSession)), 1)

    def test_h_concurrent_duplicate_visit_one_session(self):
        import tempfile
        from pathlib import Path

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "entry.sqlite3"
        engine = create_engine(
            f"sqlite:///{path}",
            connect_args={"check_same_thread": False, "timeout": 15},
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        with factory() as db:
            if db.get(Site, 1) is None:
                db.add(Site(id=1, name="Site"))
                db.add(Gate(id=1, name="North", site_id=1))
                db.flush()
                db.add_all([
                    Lane(id=10, gate_id=1, name="North Entry", direction="ENTRY"),
                    Camera(id=100, name="N-In", ip_address="10.0.0.1", site_id=1, gate_id=1, lane_direction="ENTRY"),
                ])
                db.commit()
        visit = "visit-concurrent"

        def _submit(event_id: str):
            with factory() as db:
                return sessions.start_entry(
                    db,
                    plate="T285DQP",
                    event_id=event_id,
                    site_id=1,
                    camera_id=100,
                    lane_id=10,
                    visit_id=visit,
                    policy=self.policy,
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(_submit, "c-a"), pool.submit(_submit, "c-b")]
            results = [item.result() for item in futures]
        ids = {row.id for row, _created in results}
        self.assertEqual(len(ids), 1)
        with factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(ParkingSession)), 1)
        engine.dispose()

    def test_i_ocr_variants_same_visit_one_session(self):
        visit = "visit-ocr"
        with self.Session() as db:
            a, _ = sessions.start_entry_from_recognition(
                db, _event("T285DQP", "v1", visit_id=visit), gate_id=1, policy=self.policy,
            )
            b, created_b = sessions.start_entry_from_recognition(
                db, _event("T285DOP", "v2", visit_id=visit), gate_id=1, policy=self.policy,
            )
            c, created_c = sessions.start_entry_from_recognition(
                db, _event("T285DQP", "v3", visit_id=visit), gate_id=1, policy=self.policy,
            )
            self.assertEqual(a.id, b.id)
            self.assertEqual(a.id, c.id)
            self.assertFalse(created_b)
            self.assertFalse(created_c)
            self.assertEqual(db.scalar(select(func.count()).select_from(ParkingSession)), 1)

    def test_j_same_plate_after_idle_is_new_visit(self):
        with self.Session() as db:
            first, created = sessions.start_entry_from_recognition(
                db, _event("T285DQP", "old", visit_id="visit-1"), gate_id=1, policy=self.policy,
            )
            self.assertTrue(created)
            first.status = "CLOSED"
            first.lifecycle = "CLOSED"
            db.commit()
            second, created2 = sessions.start_entry_from_recognition(
                db, _event("T285DQP", "new", visit_id="visit-2"), gate_id=1, policy=self.policy,
            )
            self.assertTrue(created2)
            self.assertNotEqual(first.id, second.id)
            self.assertEqual(db.scalar(select(func.count()).select_from(ParkingSession)), 2)

    def test_visit_state_machine_does_not_republish(self):
        lane = runtime.lane(100)
        lane.visit.reset()
        self.assertEqual(lane.visit.observe(presence=True, plate="", now=1.0), "RECOGNIZING")
        self.assertEqual(lane.visit.observe(presence=True, plate="T285DQP", now=1.1), "PLATE_CONFIRMED")
        self.assertTrue(lane.visit.mark_published("T285DQP"))
        self.assertEqual(lane.visit.state, EVENT_PUBLISHED)
        self.assertFalse(lane.visit.mark_published("T285DQP"))
        self.assertGreater(lane.visit.duplicate_events_suppressed, 0)


class FourCameraStressTests(unittest.TestCase):
    def test_k_four_cameras_bounded_and_fair(self):
        rt = RecognitionRuntime(max_concurrency=2)
        rt.reset()
        rt.scheduler = FairInferenceScheduler(2)
        held = []
        for camera_id in (1, 2, 3, 4):
            for n in range(8):
                rt.offer_frame(camera_id, JPEG + bytes([camera_id, n]))
            self.assertLessEqual(rt.lane(camera_id).mailbox.depth(), 1)
        t1 = rt.begin_if_idle(1)
        t2 = rt.begin_if_idle(2)
        self.assertIsNotNone(t1)
        self.assertIsNotNone(t2)
        self.assertIsNone(rt.begin_if_idle(3))
        self.assertIsNone(rt.begin_if_idle(4))
        self.assertTrue(rt.finish(t1, plate="A1"))
        t3 = rt.begin_if_idle(3)
        self.assertIsNotNone(t3)
        self.assertEqual(t3.camera_id, 3)
        for camera_id in (1, 2, 3, 4):
            self.assertLessEqual(rt.lane(camera_id).mailbox.depth(), 1)
        held.extend(rt.scheduler.held())
        self.assertLessEqual(len(set(held)), 2)


class LiveProviderLabelTests(unittest.TestCase):
    def test_labels_describe_negotiated_transport(self):
        from app.infrastructure.media.registry import (
            LIVE_PROVIDER_DIRECT_MJPEG,
            LIVE_PROVIDER_OFFLINE,
            LIVE_PROVIDER_WEBRTC,
            live_provider_label,
        )
        self.assertEqual(live_provider_label({"provider": "MEDIAMTX", "transport": "WEBRTC"}), LIVE_PROVIDER_WEBRTC)
        self.assertEqual(
            live_provider_label({"provider": "MEDIAMTX", "transport": "WEBRTC", "viewer_transport": "MJPEG"}),
            LIVE_PROVIDER_DIRECT_MJPEG,
        )
        self.assertEqual(live_provider_label({}), LIVE_PROVIDER_OFFLINE)


if __name__ == "__main__":
    unittest.main()
