"""The visit gate still limits repeat reads. Live lanes crop the camera box or the first plate box."""

from __future__ import annotations

import unittest

from app.services.camera_framing import (
    ArrivalGate,
    apply_framing,
    best_arrival_box,
    box_in_detection_zone,
    framing_from_profiles,
    parse_detect_zoom,
)
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

    def test_materially_shifted_box_rearms_for_following_vehicle(self):
        gate = ArrivalGate(stable_seconds=0.2)
        first = _box(20, 90)
        following = _box(110, 180)
        self.assertEqual(gate.observe(first, 0.0), "moving")
        self.assertEqual(gate.observe(first, 0.3), "ready")
        gate.note_ocr(published=True)
        self.assertEqual(gate.observe(following, 0.4), "new_vehicle")
        self.assertEqual(gate.observe(following, 0.7), "ready")

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

    def test_far_plate_waits_for_readable_distance_without_timer_escape(self):
        gate = ArrivalGate(stable_seconds=0.2, min_plate_width_px=64, far_fallback_seconds=1.0)
        far = _box(20, 70)
        self.assertEqual(gate.observe(far, 0.0), "moving")
        self.assertEqual(gate.observe(far, 0.3), "far")
        self.assertEqual(gate.observe(far, 1.3), "far")

    def test_arrival_prefers_largest_plate_box(self):
        small = {**_box(10, 70), "confidence": 0.99}
        large = {**_box(20, 140), "confidence": 0.70}
        self.assertIs(best_arrival_box([small, large]), large)

    def test_near_plate_still_waits_for_a_stable_frame(self):
        gate = ArrivalGate(stable_seconds=0.8, min_plate_width_px=64)
        self.assertEqual(gate.observe(_box(10, 80), 0.0), "moving")
        shifted = _box(60, 140)
        self.assertEqual(gate.observe(shifted, 0.1), "moving")
        self.assertEqual(gate.observe(shifted, 0.95), "ready")

    def test_far_moving_plate_never_gets_fallback_ocr_opportunity(self):
        gate = ArrivalGate(stable_seconds=0.8, min_plate_width_px=64, far_fallback_seconds=0.5)
        self.assertEqual(gate.observe(_box(10, 50), 0.0), "moving")
        self.assertEqual(gate.observe(_box(24, 64), 0.2), "moving")
        # The box is still moving and remains below the preferred readable
        # width. Visibility time must not bypass the arrival gate.
        self.assertEqual(gate.observe(_box(38, 78), 0.6), "moving")

    def test_box_admission_uses_the_zone_center(self):
        outside = _box(0, 40, y1=20, y2=50)
        inside = _box(80, 150, y1=30, y2=70)
        zone = "0.25,0.20,0.80,0.80"
        self.assertFalse(box_in_detection_zone(outside, zone))
        self.assertTrue(box_in_detection_zone(inside, zone))

    def test_one_detector_miss_does_not_restart_stationary_capture(self):
        gate = ArrivalGate(stable_seconds=0.3, absence_seconds=0.6)
        box = _box(20, 90)
        self.assertEqual(gate.observe(box, 0.0), "moving")
        self.assertEqual(gate.observe(box, 0.3), "ready")
        gate.note_ocr(published=False)
        self.assertEqual(gate.observe(None, 0.35), "missing")
        # The original stable box is still valid after the brief detector
        # miss, so the next frame is eligible immediately.
        self.assertEqual(gate.observe(box, 0.4), "ready")

    def test_sustained_detector_miss_starts_a_new_arrival(self):
        gate = ArrivalGate(stable_seconds=0.3, absence_seconds=0.6)
        box = _box(20, 90)
        gate.observe(box, 0.0)
        gate.observe(box, 0.3)
        gate.note_ocr(published=False)
        self.assertEqual(gate.observe(None, 0.7), "missing")
        self.assertEqual(gate.observe(None, 1.4), "absent")
        self.assertEqual(gate.observe(box, 1.5), "moving")


class FramingTests(unittest.TestCase):
    def test_unconfigured_camera_exposes_the_site_default_zone(self):
        framing = framing_from_profiles({})
        self.assertEqual(framing["detect_roi"], "0.06,0.18,0.94,0.92")

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
    def test_detection_snapshot_is_cropped_to_zone_and_zoom(self):
        import cv2
        import numpy as np
        from PIL import Image
        from io import BytesIO
        from app.services.captures import detection_zone_jpeg

        image = np.zeros((100, 200, 3), dtype=np.uint8)
        ok, encoded = cv2.imencode('.jpg', image)
        self.assertTrue(ok)
        snapshot = detection_zone_jpeg(
            encoded.tobytes(), detect_roi="0.25,0.25,0.75,0.75", detect_zoom=2,
        )
        with Image.open(BytesIO(snapshot)) as cropped:
            self.assertEqual(cropped.size, (50, 32))

    def test_worker_evidence_snapshot_uses_the_same_zone(self):
        import cv2
        import numpy as np
        from PIL import Image
        from io import BytesIO
        from unittest.mock import patch
        from app.recognition_worker import _publish_frame

        image = np.zeros((100, 200, 3), dtype=np.uint8)
        ok, encoded = cv2.imencode('.jpg', image)
        self.assertTrue(ok)
        writes = []

        def write(kind, name, data):
            writes.append((kind, data))
            return f"{kind}/{name}"

        event = {
            "event_id": "zoneevent",
            "vehicle_detected": True,
            "normalized_plate": "T123ABC",
            "bbox": {"x1": 60, "y1": 40, "x2": 140, "y2": 60, "crop": {"x1": 0, "y1": 0, "x2": 80, "y2": 20}},
            "detect_roi": "0.25,0.25,0.75,0.75",
            "detect_zoom": 2,
        }
        with patch("app.services.captures._write_jpeg", side_effect=write), \
             patch("app.recognition_worker.publish_recognition", return_value={"queued": True}):
            _publish_frame(event, encoded.tobytes())
        snapshot = next(data for kind, data in writes if kind == "snapshots")
        with Image.open(BytesIO(snapshot)) as cropped:
            self.assertEqual(cropped.size, (50, 32))
        self.assertTrue(event["snapshot_zone"])

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
