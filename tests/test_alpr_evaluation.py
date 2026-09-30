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

    def test_invalid_latency_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate([{"id": "one"}], [{"id": "one", "latency_ms": float("nan")}])
