from __future__ import annotations

import unittest

from app.services.live_pair import camera_label, camera_side, lane_options, pair_lane_cameras, slot_cameras


class LivePairTests(unittest.TestCase):
    def test_pairs_entry_and_exit_of_one_gate(self):
        cams = [
            {"id": 1, "name": "1# Entry", "gate_id": 10, "lane_direction": "ENTRY"},
            {"id": 2, "name": "1# Exit", "gate_id": 10, "lane_direction": "EXIT"},
            {"id": 3, "name": "2# Entry", "gate_id": 20, "lane_direction": "ENTRY"},
            {"id": 4, "name": "2# Exit", "gate_id": 20, "lane_direction": "EXIT"},
        ]
        left, right = pair_lane_cameras(cams, 10)
        self.assertEqual(left["id"], 1)
        self.assertEqual(right["id"], 2)

    def test_all_cameras_uses_first_entry_exit(self):
        cams = [
            {"id": 1, "name": "1# Entry", "gate_id": 10, "side": "ENTRY"},
            {"id": 2, "name": "1# Exit", "gate_id": 10, "side": "EXIT"},
        ]
        left, right = pair_lane_cameras(cams, None)
        self.assertEqual(left["id"], 1)
        self.assertEqual(right["id"], 2)

    def test_single_camera_leaves_other_side_empty(self):
        cams = [{"id": 1, "name": "Only", "lane_direction": "ENTRY"}]
        left, right = pair_lane_cameras(cams, None)
        self.assertEqual(left["id"], 1)
        self.assertIsNone(right)

    def test_lane_options_include_all_and_named_gates(self):
        cams = [
            {"id": 1, "gate_id": 10, "lane_name": "1#"},
            {"id": 2, "gate_id": 10, "lane_name": "1#"},
            {"id": 3, "gate_id": 20, "gate_name": "2#"},
        ]
        opts = lane_options(cams)
        self.assertEqual(opts[0], (None, "All cameras"))
        self.assertEqual(opts[1], (10, "1#"))
        self.assertEqual(opts[2], (20, "2#"))

    def test_independent_slot_picks(self):
        cams = [
            {"id": 1, "name": "1# Entry"},
            {"id": 2, "name": "1# Exit"},
            {"id": 3, "name": "2# Entry"},
            {"id": 4, "name": "2# Exit"},
        ]
        left, right = slot_cameras(cams, 4, 1)
        self.assertEqual(left["id"], 4)
        self.assertEqual(right["id"], 1)

    def test_camera_label_includes_name_and_ip(self):
        label = camera_label({"name": "2# Exit", "ip_address": "192.168.1.50", "lane_direction": "EXIT"})
        self.assertIn("2# Exit", label)
        self.assertIn("192.168.1.50", label)
        self.assertEqual(camera_side({"lane_direction": "ENTRY"}), "ENTRY")
        self.assertEqual(camera_side({"side": "exit"}), "EXIT")
        self.assertEqual(camera_side(None), "")
