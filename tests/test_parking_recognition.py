"""Phase 2: one approaching vehicle yields one normalized recognition event."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.plate import apply_site_plate
from app.db import Base
from app.domain.parking_engine import SESSION_CREATED
from app.domain.recognition import CONF_HIGH, CONF_LOW, NormalizedRecognitionEvent
from app.domain.recognition_engine import (
    FASTALPR_ONLY,
    HYBRID,
    NATIVE_ONLY,
    LaneRecognitionEngine,
    RecognitionPolicy,
    classify_confidence,
    policy_from_settings,
)
from app.models import Camera, Gate, Lane, ParkingSession, Site
from app.services import parking_sessions as sessions
from app.services.latest_frame import LatestFrameBuffer
from pydantic import ValidationError

from app.config import Settings


TEN_FRAMES = [
    ("T285DQP", 0.84),
    ("T285D0P", 0.72),
    ("T285DQP", 0.91),
    ("T285DQP", 0.90),
    ("T285DQP", 0.89),
    ("T285DQP", 0.88),
    ("T285DQP", 0.93),
    ("T285DQP", 0.90),
    ("T285DQP", 0.91),
    ("T285DQP", 0.92),
]


def _feed(engine: LaneRecognitionEngine, frames, *, provider="FASTALPR", t0=0.0, dt=0.15, **kwargs):
    events = []
    for index, (plate, confidence) in enumerate(frames):
        events.extend(engine.observe(
            plate_raw=plate, confidence=confidence, now=t0 + index * dt, provider=provider, **kwargs,
        ))
    return events


class RecognitionPolicyTests(unittest.TestCase):
    def test_confidence_classes(self):
        policy = RecognitionPolicy()
        self.assertEqual(classify_confidence(0.95, policy), CONF_HIGH)
        self.assertEqual(classify_confidence(0.80, policy), "MEDIUM")
        self.assertEqual(classify_confidence(0.40, policy), CONF_LOW)

    def test_settings_expose_consensus_window(self):
        policy = policy_from_settings()
        self.assertGreater(policy.consensus_window_seconds, 0)
        with self.assertRaises(ValidationError):
            Settings(recognition_consensus_window_seconds=0)

    def test_tanzania_corrections_are_opt_in(self):
        neutral = apply_site_plate("T285D0P", validation="NONE")
        self.assertEqual(neutral["normalized_plate"], "T285D0P")
        self.assertFalse(neutral["ocr_corrected"])


class TemporalConsensusTests(unittest.TestCase):
    def test_same_car_across_ten_frames_is_one_event(self):
        engine = LaneRecognitionEngine(1, site_id=1, lane_id=10, policy=RecognitionPolicy(mode=FASTALPR_ONLY))
        events = _feed(engine, TEN_FRAMES)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.plate_normalized, "T285DQP")
        self.assertTrue(event.accepted)
        self.assertEqual(event.provider, "FASTALPR")
        self.assertEqual(set(event.as_dict()) & {
            "event_id", "site_id", "camera_id", "lane_id", "occurred_at", "provider",
            "plate_raw", "plate_normalized", "confidence", "bbox", "vehicle_detected",
            "image_ref", "plate_crop_ref",
        }, {
            "event_id", "site_id", "camera_id", "lane_id", "occurred_at", "provider",
            "plate_raw", "plate_normalized", "confidence", "bbox", "vehicle_detected",
            "image_ref", "plate_crop_ref",
        })

    def test_one_character_disagreement_reaches_consensus(self):
        engine = LaneRecognitionEngine(1, policy=RecognitionPolicy(mode=FASTALPR_ONLY))
        events = _feed(engine, TEN_FRAMES[:4])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].plate_normalized, "T285DQP")
        self.assertGreaterEqual(events[0].consensus["agreeing"], 2)


class HybridProviderTests(unittest.TestCase):
    def test_native_and_fastalpr_agreement_is_one_event(self):
        engine = LaneRecognitionEngine(1, policy=RecognitionPolicy(mode=HYBRID))
        native = [("T285DQP", 0.94), ("T285DQP", 0.93)]
        local = [("T285DQP", 0.90), ("T285DQP", 0.91)]
        events = _feed(engine, native, provider="HVX_NATIVE")
        self.assertEqual(events, [])
        events = _feed(engine, local, provider="FASTALPR", t0=0.4)
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0].accepted)
        self.assertFalse(events[0].needs_review)
        self.assertEqual(events[0].plate_normalized, "T285DQP")
        self.assertEqual(events[0].fusion["method"], "AGREED")

    def test_native_and_fastalpr_disagreement_is_held(self):
        engine = LaneRecognitionEngine(2, policy=RecognitionPolicy(mode=HYBRID))
        events = _feed(engine, [("KAA123A", 0.95), ("KAA123A", 0.96)], provider="HVX_NATIVE")
        events += _feed(engine, [("KBB456B", 0.95), ("KBB456B", 0.94)], provider="FASTALPR", t0=0.4)
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0].needs_review)
        self.assertFalse(events[0].accepted)
        self.assertIsNone(events[0].as_entry_candidate())

    def test_native_only_ignores_fastalpr_frames(self):
        engine = LaneRecognitionEngine(3, policy=RecognitionPolicy(mode=NATIVE_ONLY))
        self.assertEqual(_feed(engine, [("ABC123", 0.95)] * 4, provider="FASTALPR"), [])
        events = _feed(engine, [("ABC123", 0.95)] * 4, provider="HVX_NATIVE", t0=1.0)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].provider, "HVX_NATIVE")


class PresenceAndStaleTests(unittest.TestCase):
    def test_presence_required_ignores_background_plates(self):
        engine = LaneRecognitionEngine(
            4, policy=RecognitionPolicy(mode=FASTALPR_ONLY), presence_capable=True,
        )
        self.assertEqual(_feed(engine, [("ABC123", 0.95)] * 4), [])
        self.assertGreater(engine.background_ignored, 0)
        engine.set_presence(True)
        events = _feed(engine, [("ABC123", 0.95)] * 4, t0=8.0)
        self.assertEqual(len(events), 1)

    def test_slow_fastalpr_drops_stale_frames_no_backlog(self):
        buf = LatestFrameBuffer("detect", maxsize=1)
        for number in range(20):
            buf.put(b"\xff\xd8" + bytes([number]))
        self.assertGreaterEqual(buf.dropped, 19)
        self.assertEqual(buf.depth(), 1)
        engine = LaneRecognitionEngine(5, policy=RecognitionPolicy(mode=FASTALPR_ONLY, stale_frame_ms=1000))
        self.assertEqual(
            engine.observe(plate_raw="ABC123", confidence=0.95, now=0.0, frame_age_ms=2500),
            [],
        )
        self.assertEqual(engine.stale_dropped, 1)
        events = _feed(engine, [("ABC123", 0.95), ("ABC123", 0.94)], frame_age_ms=40)
        self.assertEqual(len(events), 1)


class UiIndependenceTests(unittest.TestCase):
    def test_recognition_runs_without_ui_imports(self):
        worker = (ROOT / "app" / "recognition_worker.py").read_text(encoding="utf-8")
        engine_src = (ROOT / "app" / "domain" / "recognition_engine.py").read_text(encoding="utf-8")
        self.assertNotIn("app.desktop", worker)
        self.assertNotIn("app.web", worker)
        self.assertNotIn("import fastapi", engine_src)
        self.assertNotIn("from app.desktop", engine_src)
        self.assertNotIn("from app.web", engine_src)
        self.assertNotIn("from app.infrastructure.hardware.printers", engine_src)
        engine = LaneRecognitionEngine(6, policy=RecognitionPolicy(mode=FASTALPR_ONLY))
        events = _feed(engine, [("XYZ999", 0.93), ("XYZ999", 0.94)])
        self.assertEqual(len(events), 1)


class ParkingCandidateTests(unittest.TestCase):
    def _seed(self, db):
        db.add(Site(id=1, name="Site"))
        db.add(Gate(id=1, name="North", site_id=1))
        db.flush()
        db.add_all([
            Lane(id=10, gate_id=1, name="North Entry", direction="ENTRY"),
            Camera(id=100, name="N-In", ip_address="10.0.0.1", site_id=1, gate_id=1),
        ])
        db.commit()

    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        with self.Session() as db:
            self._seed(db)

    def tearDown(self):
        self.engine.dispose()

    def test_recognition_event_creates_one_parking_entry_candidate(self):
        rec = LaneRecognitionEngine(
            100, site_id=1, lane_id=10, policy=RecognitionPolicy(mode=FASTALPR_ONLY),
        )
        events = _feed(rec, TEN_FRAMES)
        self.assertEqual(len(events), 1)
        candidate = events[0].as_entry_candidate()
        self.assertIsNotNone(candidate)
        with self.Session() as db:
            row, created = sessions.start_entry_from_recognition(db, events[0], gate_id=1)
            again, created2 = sessions.start_entry_from_recognition(db, events[0], gate_id=1)
            self.assertTrue(created)
            self.assertFalse(created2)
            self.assertEqual(row.id, again.id)
            self.assertEqual(row.lifecycle, SESSION_CREATED)
            self.assertEqual(row.entry_event_id, events[0].event_id)
            self.assertEqual(row.plate, "T285DQP")
            self.assertEqual(db.scalar(select(ParkingSession).where(ParkingSession.plate == "T285DQP")).id, row.id)

    def test_low_confidence_does_not_create_duplicate_session(self):
        rec = LaneRecognitionEngine(
            100, site_id=1, lane_id=10, policy=RecognitionPolicy(mode=FASTALPR_ONLY),
        )
        events = _feed(rec, [("T285DQP", 0.40)] * 10)
        self.assertEqual(events, [])
        held = NormalizedRecognitionEvent(
            event_id="low-1", site_id=1, camera_id=100, lane_id=10, occurred_at="t",
            provider="FASTALPR", plate_raw="T285DQP", plate_normalized="T285DQP",
            confidence=0.4, bbox=None, vehicle_detected=True, image_ref=None, plate_crop_ref=None,
            confidence_class=CONF_LOW, needs_review=False, accepted=False,
        )
        with self.Session() as db:
            row, created = sessions.start_entry_from_recognition(db, held, gate_id=1)
            self.assertIsNone(row)
            self.assertFalse(created)
            self.assertIsNone(db.scalar(select(ParkingSession)))

    def test_hybrid_disagreement_does_not_open_a_session(self):
        rec = LaneRecognitionEngine(
            100, site_id=1, lane_id=10, policy=RecognitionPolicy(mode=HYBRID),
        )
        events = _feed(rec, [("KAA123A", 0.95), ("KAA123A", 0.96)], provider="HVX_NATIVE")
        events += _feed(rec, [("KBB456B", 0.95), ("KBB456B", 0.94)], provider="FASTALPR", t0=0.4)
        with self.Session() as db:
            row, created = sessions.start_entry_from_recognition(db, events[0], gate_id=1)
            self.assertIsNone(row)
            self.assertFalse(created)


if __name__ == "__main__":
    unittest.main()
