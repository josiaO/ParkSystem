import unittest
from pathlib import Path

from tools.evaluate_alpr import evaluate, read_rows


class EvaluationTests(unittest.TestCase):
    def test_fixed_fixture_metrics_and_breakdowns(self):
        folder = Path(__file__).parent / "fixtures" / "alpr"
        result = evaluate(read_rows(folder / "smoke.jsonl"), read_rows(folder / "smoke-predictions.jsonl"))
        metrics = result["overall"]
        self.assertEqual(metrics["plate_exact_match_accuracy"], .5)
        self.assertAlmostEqual(metrics["character_accuracy"], 12 / 13)
        self.assertEqual(metrics["detection_recall"], .5)
        self.assertEqual(metrics["false_positive_rate"], 1)
        self.assertEqual(metrics["false_acceptance_rate"], .5)
        self.assertEqual(metrics["latency_ms"], {"count": 3, "mean": 200, "p50": 200, "p95": 290})
        self.assertEqual(result["by"]["condition"]["night"]["plate_exact_match_accuracy"], 0)
        self.assertEqual(set(result["by"]["camera_id"]), {"cam-a", "cam-b"})

    def test_missing_predictions_are_rejected_instead_of_inflating_accuracy(self):
        with self.assertRaises(ValueError):
            evaluate([{"id": "one", "plate": "ABC"}], [])

    def test_unlabelled_metrics_are_unknown(self):
        report = evaluate([{"id": "one", "plate": "ABC"}], [{"id": "one", "plate": ""}])["overall"]
        self.assertEqual(report["character_accuracy"], 0)
        self.assertIsNone(report["detection_recall"])
        self.assertIsNone(report["false_acceptance_rate"])
        self.assertIsNone(report["latency_ms"]["mean"])
        self.assertIsNone(report["duplicate_event_rate"])
        self.assertIsNone(report["false_session_creation"])

    def test_visit_duplicate_and_false_session_metrics(self):
        labels = [
            {"id": "a", "plate": "ABC", "visit_id": "v1", "session_expected": True},
            {"id": "b", "plate": "ABC", "visit_id": "v1", "session_expected": True},
            {"id": "c", "plate": "", "visit_id": "v2", "session_expected": False},
        ]
        predictions = [
            {"id": "a", "plate": "ABC", "event_id": "e1", "session_created": True},
            {"id": "b", "plate": "ABC", "event_id": "e2", "session_created": True},
            {"id": "c", "plate": "XYZ", "event_id": "e3", "session_created": True},
        ]
        overall = evaluate(labels, predictions)["overall"]
        self.assertEqual(overall["duplicate_event_rate"], 0.5)
        self.assertEqual(overall["false_session_creation"], 1.0)

    def test_invalid_latency_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate([{"id": "one"}], [{"id": "one", "latency_ms": float("nan")}])
