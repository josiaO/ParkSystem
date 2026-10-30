"""The visit gate still limits repeat reads. Live lanes crop the camera box or the first plate box."""

from __future__ import annotations

import unittest

from app.services.camera_framing import ArrivalGate, apply_framing, best_arrival_box, framing_from_profiles, parse_detect_zoom
from app.services.stream_roles import merge_profiles, public_profiles


def _box(x1, x2, *, y1=40, y2=70, width=200, height=100):
    return {
        "x1": x1, "y1": y1, "x2": x2, "y2": y2,
        "image_width": width, "image_height": height,
    }


class ArrivalGateTests(unittest.TestCase):
    def test_ocr_waits_until_the_plate_holds_still(self):
        gate = ArrivalGate(stable_seconds=0.3, move_ratio=0.05)
        moving = _box(10, 80)
        self.assertEqual(gate.observe(moving, 0.0), "moving")
        shifted = _box(50, 120)
        self.assertEqual(gate.observe(shifted, 0.1), "moving")
        self.assertEqual(gate.observe(shifted, 0.2), "moving")
        self.assertEqual(gate.observe(shifted, 0.55), "ready")
        self.assertEqual(gate.observe(shifted, 0.7), "moving")
        gate.note_ocr(published=True)
        self.assertEqual(gate.observe(shifted, 0.8), "held")
        self.assertEqual(gate.observe(None, 0.9), "held")
        self.assertEqual(gate.observe(None, 1.6), "absent")
        self.assertEqual(gate.observe(moving, 1.7), "moving")

    def test_settled_plate_retries_fresh_frame_without_another_settle_delay(self):
        gate = ArrivalGate(stable_seconds=0.2, max_ocr=2)
        box = _box(20, 90)
        self.assertEqual(gate.observe(box, 0.0), "moving")
        self.assertEqual(gate.observe(box, 0.3), "ready")
        gate.note_ocr(published=False)
        self.assertEqual(gate.observe(box, 0.35), "ready")
        gate.note_ocr(published=False)
        self.assertEqual(gate.observe(box, 1.2), "cooldown")
        self.assertEqual(gate.observe(box, 1.7), "moving")
        self.assertEqual(gate.observe(box, 2.0), "ready")

    def test_rearm_allows_the_read_when_ocr_did_not_run(self):
        gate = ArrivalGate(stable_seconds=0.2)
        box = _box(20, 90)
        gate.observe(box, 0.0)
        self.assertEqual(gate.observe(box, 0.3), "ready")
        gate.rearm()
        self.assertEqual(gate.observe(box, 0.4), "ready")

    def test_far_plate_waits_for_readable_distance_then_has_bounded_fallback(self):
        gate = ArrivalGate(stable_seconds=0.2, min_plate_width_px=64, far_fallback_seconds=1.0)
        far = _box(20, 70)
        self.assertEqual(gate.observe(far, 0.0), "moving")
        self.assertEqual(gate.observe(far, 0.3), "far")
        self.assertEqual(gate.observe(far, 1.3), "ready")

    def test_arrival_prefers_largest_plate_box(self):
        small = {**_box(10, 70), "confidence": 0.99}
        large = {**_box(20, 140), "confidence": 0.70}
        self.assertIs(best_arrival_box([small, large]), large)

    def test_near_plate_gets_fast_read_opportunity_while_moving(self):
        gate = ArrivalGate(stable_seconds=0.8, min_plate_width_px=64)
        self.assertEqual(gate.observe(_box(10, 80), 0.0), "moving")
        self.assertEqual(gate.observe(_box(60, 140), 0.1), "ready")


class FramingTests(unittest.TestCase):
    def test_a_tight_lane_box_is_accepted(self):
        profiles = apply_framing({}, detect_roi="0.30,0.45,0.70,0.80", detect_zoom=2.5)
        framing = framing_from_profiles(profiles)
        self.assertEqual(framing["detect_zoom"], 2.5)
        self.assertTrue(framing["detect_roi"].startswith("0.3000,0.4500"))

    def test_tiny_box_is_rejected(self):
        with self.assertRaises(ValueError):
            apply_framing({}, detect_roi="0.10,0.10,0.12,0.12", detect_zoom=1)

    def test_zoom_is_clamped_and_stream_merge_keeps_the_zone(self):
        self.assertEqual(parse_detect_zoom(9), 4.0)
        self.assertEqual(parse_detect_zoom("nope"), 1.0)
        profiles = apply_framing({"MAIN": {"codec": "h264"}}, detect_roi="off", detect_zoom=1.5)
        merged = merge_profiles(profiles, {"SUB": {"codec": "h264"}})
        self.assertEqual(merged["FRAMING"]["detect_zoom"], 1.5)
        public = public_profiles(merged)
        self.assertEqual(public["FRAMING"]["detect_zoom"], 1.5)
        self.assertIn("MAIN", public)


class ZoomCropTests(unittest.TestCase):
    def test_zoom_keeps_the_center_of_the_zone(self):
        numpy = __import__("numpy")
        from app.services.alpr import _roi_crop

        image = numpy.zeros((100, 200, 3), dtype=numpy.uint8)
        view, dx, dy = _roi_crop(image, "0.10,0.20,0.90,0.80", 2)
        self.assertEqual((dx, dy), (60, 34))
        self.assertEqual(view.shape[:2], (32, 80))

class ArrivalCropReuseTests(unittest.TestCase):
    def test_reuses_detector_box_without_running_detection_again(self):
        from unittest.mock import patch
        import numpy as np
        from app.services.alpr import recognize_arrival_bytes
        box = {**_box(20, 90), "confidence": 0.9}
        with patch('app.services.alpr.locate_plate_boxes', side_effect=AssertionError('second detection')), \
             patch('app.services.alpr.decode_alpr_image', return_value=np.zeros((100,200,3), dtype=np.uint8)), \
             patch('app.services.alpr._load_engine', return_value=object()), \
             patch('app.services.alpr._hits_from_detections', return_value=[]) as ocr:
            result = recognize_arrival_bytes(b'frame', detected_boxes=[box])
        self.assertTrue(result['ok'])
        self.assertEqual(ocr.call_count, 1)

    def test_unavailable_detector_does_not_read_the_live_frame(self):
        from unittest.mock import patch
        from app.services.alpr import recognize_arrival_bytes
        with patch('app.services.alpr.locate_plate_boxes', return_value=([], {'available': False})), \
             patch('app.services.alpr.recognize_bytes', side_effect=AssertionError('full frame')):
            result = recognize_arrival_bytes(b'frame')
        self.assertFalse(result['ok'])
        self.assertEqual(result['plates'], [])
        self.assertEqual(result['pipeline'], 'arrival_crop_ocr')

    def test_full_frame_is_not_replaced_by_site_default(self):
        profiles = apply_framing({}, detect_roi='off', detect_zoom=1)
        self.assertEqual(framing_from_profiles(profiles)['detect_roi'], 'off')

    def test_nonfinite_zoom_is_safe(self):
        self.assertEqual(parse_detect_zoom(float('nan')), 1.0)
        self.assertEqual(parse_detect_zoom(float('inf')), 1.0)
