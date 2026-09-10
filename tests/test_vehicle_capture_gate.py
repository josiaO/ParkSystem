"""Vehicle snapshots must only persist when a car/plate is evidenced."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.captures import plausible_vehicle_plate, should_persist_vehicle_capture


class VehicleCaptureGateTests(unittest.TestCase):
    def test_rejects_sign_text_and_empty_scenes(self):
        self.assertFalse(plausible_vehicle_plate("STATION"))
        self.assertFalse(plausible_vehicle_plate("POLICE"))
        self.assertFalse(plausible_vehicle_plate("ABC"))
        ok, reason = should_persist_vehicle_capture({"plate": "", "source": "fastalpr"})
        self.assertFalse(ok)
        self.assertEqual(reason, "no-vehicle-no-plate")
        ok, reason = should_persist_vehicle_capture({
            "plate": "STATION", "score": 0.9, "source": "fastalpr",
            "bbox": {"x1": 10, "y1": 20, "x2": 120, "y2": 50},
        })
        self.assertFalse(ok)
        self.assertEqual(reason, "implausible-plate")

    def test_accepts_native_vehicle_even_without_plate_yet(self):
        ok, reason = should_persist_vehicle_capture({"plate": "", "have_vehicle": True, "score": 0})
        self.assertTrue(ok)
        self.assertEqual(reason, "native-vehicle")

    def test_accepts_tanzania_plate_with_bbox(self):
        ok, reason = should_persist_vehicle_capture({
            "plate": "T104EJW",
            "score": 0.4,
            "source": "fastalpr",
            "bbox": {"x1": 100, "y1": 200, "x2": 260, "y2": 245},
        })
        self.assertTrue(ok)
        self.assertEqual(reason, "plausible-plate")

    def test_rejects_fastalpr_without_detector_box(self):
        ok, reason = should_persist_vehicle_capture({
            "plate": "T104EJW",
            "score": 0.4,
            "source": "fastalpr",
        })
        self.assertFalse(ok)
        self.assertEqual(reason, "no-plate-bbox")

    def test_rejects_tall_non_plate_bbox(self):
        ok, reason = should_persist_vehicle_capture({
            "plate": "T104EJW",
            "score": 0.5,
            "source": "fastalpr",
            "bbox": {"x1": 10, "y1": 10, "x2": 40, "y2": 200},
        })
        self.assertFalse(ok)
        self.assertEqual(reason, "bbox-not-plate-shaped")


if __name__ == "__main__":
    unittest.main()
