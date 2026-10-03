"""Temporal consensus, process-safe native/FastALPR fusion and durable idempotency."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.core.consensus import ConsensusTrack
from app.core.hybrid import SOURCE_LOCAL, SOURCE_NATIVE, Candidate, FusionCoordinator
from app.domain.events import from_recognition_dict
from app.services import hybrid_fusion
from app.services.events import recognition_from_outbox
from app.services.queues import SQLiteOutbox


class ConsensusTrackTests(unittest.TestCase):
    def test_similar_reads_support_majority_and_publish_once(self):
        track = ConsensusTrack()
        self.assertFalse(track.observe("T285DQP", 0.0, confidence=0.8).publish)
        second = track.observe("T285DOP", 0.2, confidence=0.6)  # one confused character
        self.assertFalse(second.publish, second.reason)
        third = track.observe("T285DQP", 0.4, confidence=0.9)
        self.assertTrue(third.publish)
        self.assertEqual(third.plate, "T285DQP")
        self.assertEqual(third.agreeing, 2)
        self.assertEqual(third.reads, 3)
        self.assertGreater(third.share, 0.9)
        # Consensus confidence is the mean of exact agreeing reads, not the max.
        self.assertAlmostEqual(third.confidence, 0.85, places=3)
        # Still visible: no second event for the same vehicle.
        for t in (0.6, 1.0, 1.9, 2.8, 4.0):
            self.assertFalse(track.observe("T285DQP", t, confidence=0.9).publish)

    def test_split_vote_between_unrelated_plates_is_held(self):
        track = ConsensusTrack()
        track.observe("KAA123A", 0.0, confidence=0.8)
        decision = track.observe("ZZZ999Z", 0.2, confidence=0.8)
        self.assertFalse(decision.publish)
        # A third read resolves it (two exact reads, ~67% of the weight).
        third = track.observe("KAA123A", 0.4, confidence=0.8)
        self.assertTrue(third.publish)
        self.assertEqual(third.plate, "KAA123A")
        # Two exact reads that hold too little weight are still held.
        held = ConsensusTrack()
        held.observe("KAA123A", 0.0, confidence=0.5)
        held.observe("ZZZ999Z", 0.1, confidence=0.9)
        held.observe("YYY888Y", 0.2, confidence=0.9)
        low = held.observe("KAA123A", 0.3, confidence=0.5)
        self.assertEqual(low.plate, "KAA123A")
        self.assertEqual(low.agreeing, 2)
        self.assertFalse(low.publish)
        self.assertIn("no consensus", low.reason)

    def test_gap_starts_new_visit_and_allows_republish(self):
        track = ConsensusTrack(window_seconds=2.0, hold_seconds=20.0)
        track.observe("ABC123", 0.0, confidence=0.8)
        self.assertTrue(track.observe("ABC123", 0.2, confidence=0.8).publish)
        track.observe("ABC123", 30.0, confidence=0.8)
        self.assertTrue(track.observe("ABC123", 30.2, confidence=0.8).publish)
        # Within the hold window a new visit of the same plate is suppressed.
        track.observe("ABC123", 35.0, confidence=0.8)
        self.assertFalse(track.observe("ABC123", 35.2, confidence=0.8).publish)

    def test_release_allows_retry_after_failed_publish(self):
        track = ConsensusTrack()
        track.observe("ABC123", 0.0, confidence=0.8)
        self.assertTrue(track.observe("ABC123", 0.2, confidence=0.8).publish)
        track.release()
        self.assertTrue(track.observe("ABC123", 0.4, confidence=0.8).publish)

    def test_empty_read_does_not_break_visit(self):
        track = ConsensusTrack()
        track.observe("ABC123", 0.0, confidence=0.8)
        self.assertFalse(track.observe("", 0.1).publish)
        self.assertTrue(track.observe("ABC123", 0.3, confidence=0.8).publish)

    def test_high_confidence_publishes_on_first_read(self):
        track = ConsensusTrack()
        first = track.observe("T277ECR", 0.0, confidence=0.95)
        self.assertTrue(first.publish)
        self.assertEqual(first.plate, "T277ECR")
        self.assertFalse(track.observe("T277ECR", 0.2, confidence=0.95).publish)


class FusionCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.coord = FusionCoordinator(pair_window_seconds=3.0, wait_seconds=1.5, hold_seconds=20.0)

    def test_agreement_is_accepted_immediately_and_once(self):
        out = self.coord.offer(1, Candidate(SOURCE_NATIVE, "T285DQP", 0.9, 10.0), now=10.0)
        self.assertEqual(out, [])
        out = self.coord.offer(1, Candidate(SOURCE_LOCAL, "T285DQP", 0.88, 10.4), now=10.4)
        self.assertEqual(len(out), 1)
        decision = out[0]
        self.assertTrue(decision.paired)
        self.assertEqual(decision.decision.method, "AGREED")
        self.assertFalse(decision.decision.needs_review)
        self.assertFalse(decision.suppressed)
        # The worker keeps reading the same car: duplicate suppressed.
        dup = self.coord.offer(1, Candidate(SOURCE_LOCAL, "T285DQP", 0.9, 12.0), now=12.0, counterpart_available=False)
        self.assertEqual(len(dup), 1)
        self.assertTrue(dup[0].suppressed)
        near = self.coord.offer(1, Candidate(SOURCE_NATIVE, "T285D0P", 0.7, 13.0), now=13.0, counterpart_available=False)
        self.assertTrue(near[0].suppressed, "near-identical plate is the same physical vehicle")
        self.assertEqual(self.coord.flush(30.0), [])

    def test_disagreement_is_held_for_review_not_two_sessions(self):
        self.coord.offer(2, Candidate(SOURCE_NATIVE, "KAA123A", 0.95, 0.0), now=0.0)
        out = self.coord.offer(2, Candidate(SOURCE_LOCAL, "KBB456B", 0.95, 0.5), now=0.5)
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0].decision.needs_review)
        self.assertTrue(out[0].decision.disagreed)
        self.assertEqual(out[0].decision.method, "REVIEW_REQUIRED")
        self.assertEqual(self.coord.pending(2), {SOURCE_NATIVE: None, SOURCE_LOCAL: None})

    def test_single_provider_decides_after_wait_when_counterpart_missing(self):
        self.assertEqual(self.coord.offer(3, Candidate(SOURCE_NATIVE, "ABC123", 0.9, 0.0), now=0.0), [])
        self.assertEqual(self.coord.flush(1.0), [])
        out = self.coord.flush(1.6)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].decision.method, "NATIVE_ONLY")
        self.assertFalse(out[0].paired)

    def test_single_provider_decides_immediately_when_counterpart_unavailable(self):
        out = self.coord.offer(4, Candidate(SOURCE_LOCAL, "ABC123", 0.95, 0.0), now=0.0, counterpart_available=False)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].decision.method, "LOCAL_ONLY")

    def test_stale_candidate_is_not_paired_with_next_vehicle(self):
        self.coord.offer(5, Candidate(SOURCE_NATIVE, "AAA111", 0.9, 0.0), now=0.0)
        out = self.coord.offer(5, Candidate(SOURCE_LOCAL, "BBB222", 0.9, 10.0), now=10.0)
        # Native decided alone first; the new local still waits for its own counterpart.
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].decision.resolved_plate, "AAA111")
        self.assertEqual(out[0].decision.method, "NATIVE_ONLY")
        self.assertIsNotNone(self.coord.pending(5)[SOURCE_LOCAL])
        later = self.coord.flush(12.0)
        self.assertEqual([o.decision.resolved_plate for o in later], ["BBB222"])

    def test_held_decision_does_not_own_duplicate_window(self):
        self.coord.offer(6, Candidate(SOURCE_NATIVE, "KAA123A", 0.95, 0.0), now=0.0)
        held = self.coord.offer(6, Candidate(SOURCE_LOCAL, "KBB456B", 0.95, 0.1), now=0.1)[0]
        self.assertTrue(held.decision.needs_review)
        agreed = self.coord.offer(6, Candidate(SOURCE_NATIVE, "KAA123A", 0.95, 5.0), now=5.0)
        agreed += self.coord.offer(6, Candidate(SOURCE_LOCAL, "KAA123A", 0.95, 5.1), now=5.1)
        self.assertEqual(len(agreed), 1)
        self.assertFalse(agreed[0].suppressed)
        self.assertEqual(agreed[0].decision.method, "AGREED")


class DurableIdempotencyTests(unittest.TestCase):
    def test_processed_mark_survives_restart_and_is_atomic_with_ack(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "q.sqlite3"
            box = SQLiteOutbox(path)
            item = box.enqueue("PlateRecognized", {"event_id": "evt-1"})
            self.assertFalse(box.was_processed("evt-1"))
            box.ack(item, processed_key="evt-1")
            self.assertEqual(box.depth(), 0)
            # Crash + redelivery from a producer retry: a new outbox handle still knows.
            again = SQLiteOutbox(path)
            self.assertTrue(again.was_processed("evt-1"))
            self.assertFalse(again.was_processed(""))
            self.assertFalse(again.was_processed(None))
            self.assertEqual(again.snapshot()["duplicates"], 1)

    def test_processed_retention_is_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            box = SQLiteOutbox(Path(folder) / "q.sqlite3")
            with box._connect() as db:
                db.execute("INSERT INTO processed (key, ts) VALUES ('old', 0)")
            box.ack(box.enqueue("x", {}), processed_key="new")
            self.assertFalse(box.was_processed("old"))
            self.assertTrue(box.was_processed("new"))


class _FakeCamera(SimpleNamespace):
    pass


class HybridFusionServiceTests(unittest.TestCase):
    def setUp(self):
        hybrid_fusion.reset()
        self.persisted: list[dict] = []

        async def persist(db, camera, capture, jpeg, crop):
            self.persisted.append({"camera": camera.id, "capture": capture, "jpeg": jpeg, "crop": crop})
            return {"plate": capture["plate"]}

        hybrid_fusion.set_persist(persist)
        self.camera = _FakeCamera(id=9, name="entry", recognition_mode="HYBRID", adapter_id="hvx", enabled=True)

    def tearDown(self):
        hybrid_fusion.set_persist(None)
        hybrid_fusion.reset()

    def test_native_and_worker_candidate_persist_one_fused_capture(self):
        native = {"plate": "T285DQP", "plate_raw": "T 285 DQP", "confidence": 0.9, "image_id": 77, "source": "qy_Net_RegImageRecvEx"}
        recognized = recognition_from_outbox({
            "kind": "PlateRecognized",
            "payload": from_recognition_dict({
                "event_id": "evt-9", "camera_id": 9, "normalized_plate": "T285DQP", "confidence": 0.86,
                "consensus": {"publish": True, "agreeing": 2, "reads": 3, "share": 0.95},
                "recognition_mode": "NATIVE_WITH_LOCAL_VERIFY", "fusion_role": "candidate",
            }),
        })
        with patch.object(hybrid_fusion, "local_counterpart_available", return_value=True), \
             patch.object(hybrid_fusion, "native_counterpart_available", return_value=True):
            first = asyncio.run(hybrid_fusion.offer_native(None, self.camera, native, jpeg=b"\xff\xd8car\xff\xd9", crop=b"\xff\xd8p\xff\xd9", capture={"image_id": 77}))
            self.assertEqual(first, [])
            second = asyncio.run(hybrid_fusion.offer_local(None, self.camera, recognized))
        self.assertEqual(len(second), 1)
        self.assertEqual(len(self.persisted), 1)
        capture = self.persisted[0]["capture"]
        self.assertEqual(capture["plate"], "T285DQP")
        self.assertEqual(capture["source"], "hybrid")
        self.assertEqual(capture["image_id"], 77)
        self.assertEqual(capture["event_id"], "evt-9")
        self.assertEqual(capture["fusion"]["method"], "AGREED")
        self.assertTrue(capture["fusion"]["paired"])
        self.assertFalse(capture["needs_review"])
        # Native evidence JPEG (from the SDK callback) is the archived frame.
        self.assertEqual(self.persisted[0]["jpeg"], b"\xff\xd8car\xff\xd9")
        self.assertEqual(hybrid_fusion.stats()["paired"], 1)

    def test_disagreement_persists_one_held_capture(self):
        native = {"plate": "KAA123A", "confidence": 0.95, "image_id": 1}
        recognized = {"event_id": "evt-2", "camera_id": 9, "plate": "KBB456B", "confidence": 0.95}
        with patch.object(hybrid_fusion, "local_counterpart_available", return_value=True), \
             patch.object(hybrid_fusion, "native_counterpart_available", return_value=True):
            asyncio.run(hybrid_fusion.offer_native(None, self.camera, native, jpeg=b"\xff\xd8x\xff\xd9"))
            asyncio.run(hybrid_fusion.offer_local(None, self.camera, recognized))
        self.assertEqual(len(self.persisted), 1)
        capture = self.persisted[0]["capture"]
        self.assertTrue(capture["needs_review"])
        self.assertTrue(capture["pending_confirmation"])
        self.assertTrue(capture["fusion"]["disagreed"])
        self.assertEqual(hybrid_fusion.stats()["held"], 1)

    def test_native_only_when_worker_unavailable(self):
        with patch.object(hybrid_fusion, "local_counterpart_available", return_value=False):
            out = asyncio.run(hybrid_fusion.offer_native(None, self.camera, {"plate": "ABC123", "confidence": 0.9}, jpeg=b"\xff\xd8x\xff\xd9"))
        self.assertEqual(len(out), 1)
        self.assertEqual(self.persisted[0]["capture"]["fusion"]["method"], "NATIVE_ONLY")

    def test_flush_decides_waiting_native_after_timeout(self):
        coordinator = hybrid_fusion.coordinator()
        coordinator.wait_seconds = 0.0
        with patch.object(hybrid_fusion, "local_counterpart_available", return_value=True):
            asyncio.run(hybrid_fusion.offer_native(None, self.camera, {"plate": "ABC123", "confidence": 0.9}, jpeg=b"\xff\xd8x\xff\xd9"))
        self.assertEqual(self.persisted, [])

        class _Session:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def get(self, model, ident):
                return _FakeCamera(id=ident, recognition_mode="HYBRID", adapter_id="hvx", enabled=True)

        applied = asyncio.run(hybrid_fusion.flush(_Session))
        self.assertEqual(applied, 1)
        self.assertEqual(self.persisted[0]["capture"]["plate"], "ABC123")
        coordinator.wait_seconds = 1.5

    def test_routes_camera_requires_hybrid_mode_and_worker_ownership(self):
        local_only = _FakeCamera(id=1, recognition_mode="FASTALPR_ONLY", adapter_id="rtsp")
        self.assertFalse(hybrid_fusion.routes_camera(local_only))
        with patch("app.recognition_worker.worker_owns_software_reads", return_value=False):
            self.assertFalse(hybrid_fusion.routes_camera(self.camera))
        with patch("app.recognition_worker.worker_owns_software_reads", return_value=True):
            self.assertTrue(hybrid_fusion.routes_camera(self.camera))

    def test_worker_event_contract_carries_consensus_and_role(self):
        event = from_recognition_dict({"normalized_plate": "ABC123", "consensus": {"share": 1.0}, "fusion_role": "candidate", "recognition_mode": "NATIVE_WITH_LOCAL_VERIFY"})
        self.assertEqual(event["payload"]["fusion_role"], "candidate")
        self.assertEqual(event["payload"]["consensus"], {"share": 1.0})
        unwrapped = recognition_from_outbox({"kind": "PlateRecognized", "payload": event})
        self.assertEqual(unwrapped["recognition_mode"], "NATIVE_WITH_LOCAL_VERIFY")


class SiteServiceWiringTests(unittest.TestCase):
    def test_outbox_loop_uses_processed_marks_and_hybrid_routing(self):
        text = (Path(__file__).resolve().parents[1] / "app" / "api_main.py").read_text(encoding="utf-8")
        loop = text.split("async def _outbox_loop")[1].split("async def _fusion_flush_loop")[0]
        self.assertIn("box.was_processed(event_key)", loop)
        self.assertIn("processed_key=event_key", loop)
        self.assertIn("VehicleCapture.event_id == event_key", loop)
        self.assertIn("hybrid_fusion.offer_local", loop)
        drain = text.split("async def _drain_camera_events")[1].split("async def _poll_coil_and_read")[0]
        self.assertIn("hybrid_fusion.offer_native", drain)
        self.assertIn("worker_owns_software_reads(camera_id)", drain)
        self.assertIn("hybrid_fusion.set_persist(_persist_capture_event)", text)
        self.assertIn('name="hybrid-fusion-flush"', text)


if __name__ == "__main__":
    unittest.main()
