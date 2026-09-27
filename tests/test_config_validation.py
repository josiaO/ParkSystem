from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.config import Settings
from app.core.consensus import detect_coverage, resolve_local_reads


class ConfigValidationTests(unittest.TestCase):
    def test_rejects_invalid_detect_fps(self):
        with self.assertRaises(ValidationError):
            Settings(detect_fps=0)

    def test_rejects_invalid_alpr_mode(self):
        with self.assertRaises(ValidationError):
            Settings(alpr_mode="NOT_A_MODE")

    def test_accepts_documented_defaults(self):
        cfg = Settings(alpr_mode="NATIVE_ONLY", detect_fps=5.0, rtsp_transport="TCP")
        self.assertEqual(cfg.alpr_mode, "NATIVE_ONLY")
        self.assertEqual(cfg.detect_fps, 5.0)


class ConsensusTests(unittest.TestCase):
    def test_two_agreeing_frames_accept(self):
        decision = resolve_local_reads([("T285DQP", 0.6), ("T285DQP", 0.7)])
        self.assertTrue(decision.accepted)
        self.assertEqual(decision.plate, "T285DQP")
        self.assertEqual(decision.reason, "multi-frame agreement")

    def test_single_weak_frame_rejected(self):
        decision = resolve_local_reads([("T285DQP", 0.4)])
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, "no consensus")

    def test_high_confidence_single_frame_accepts(self):
        decision = resolve_local_reads([("T285DQP", 0.95)])
        self.assertTrue(decision.accepted)

    def test_detect_fps_covers_typical_entry(self):
        cover = detect_coverage(fps=5.0, dwell_seconds=1.0, min_frames=2)
        self.assertEqual(cover["interval_ms"], 200.0)
        self.assertTrue(cover["enough_for_consensus"])
        slow = detect_coverage(fps=1.0, dwell_seconds=1.0, min_frames=2)
        self.assertFalse(slow["enough_for_consensus"])


if __name__ == "__main__":
    unittest.main()
