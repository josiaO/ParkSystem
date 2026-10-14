"""Scoring for the Windows startup check. No live camera and no gate pulse."""

from __future__ import annotations

import unittest

from tools.startup_check import (
    FAIL,
    PASS,
    SKIP,
    WARN,
    evaluate_gates,
    evaluate_recognition,
    evaluate_video,
    gate_request,
    gate_sides,
)


def _row(**overrides):
    row = {
        "camera_id": 1,
        "camera_name": "1# Entry",
        "live_connected": True,
        "estimated_frame_age_ms": 120,
        "frame_seq": 10,
        "frames_changed": 4,
        "frozen": False,
    }
    row.update(overrides)
    return row


def _snap(*cameras, worker_ok=True):
    return {
        "cameras": list(cameras),
        "worker": {"ok": worker_ok, "state": "READY" if worker_ok else "OFFLINE", "heartbeat_age_seconds": 1.2},
    }


class StartupCheckTests(unittest.TestCase):
    def test_moving_fresh_video_passes(self):
        first = _snap(_row(frame_seq=10, frames_changed=1))
        last = _snap(_row(frame_seq=18, frames_changed=6, estimated_frame_age_ms=180))
        checks = {row["id"]: row for row in evaluate_video([first, last], {1})}
        self.assertEqual(checks["V1"]["status"], PASS)
        self.assertEqual(checks["V2"]["status"], PASS)

    def test_frozen_picture_fails(self):
        frozen = _snap(_row(frame_seq=10, frames_changed=1, frozen=True))
        checks = {row["id"]: row for row in evaluate_video([frozen, frozen], {1})}
        self.assertEqual(checks["V1"]["status"], FAIL)

    def test_stale_frames_fail(self):
        first = _snap(_row(frame_seq=1, estimated_frame_age_ms=3000))
        last = _snap(_row(frame_seq=8, estimated_frame_age_ms=4000))
        checks = {row["id"]: row for row in evaluate_video([first, last], {1})}
        self.assertEqual(checks["V1"]["status"], PASS)
        self.assertEqual(checks["V2"]["status"], FAIL)

    def test_recognition_without_a_plate_warns(self):
        checks = {row["id"]: row for row in evaluate_recognition(
            {"ok": True, "heartbeat_age_seconds": 1},
            [{"camera_id": 1, "camera_name": "1# Entry", "http_ok": True, "body": {"ok": True, "evidence_source": "live_frame", "best": {}}}],
        )}
        self.assertEqual(checks["R1"]["status"], PASS)
        self.assertEqual(checks["R2"]["status"], WARN)

    def test_recognition_failure_and_dead_worker(self):
        checks = {row["id"]: row for row in evaluate_recognition(
            {"ok": False, "state": "OFFLINE"},
            [{"camera_id": 1, "camera_name": "1# Entry", "http_ok": True, "body": {"ok": False, "detail": "no frame"}}],
        )}
        self.assertEqual(checks["R1"]["status"], FAIL)
        self.assertEqual(checks["R2"]["status"], FAIL)

    def test_gate_dry_run_passes_and_live_response_fails(self):
        request = gate_request({"id": 1, "name": "1#"}, "ENTRY")
        self.assertIs(request["dry_run"], True)
        self.assertEqual(gate_sides({"cameras": [{"lane_direction": "ENTRY"}, {"lane_direction": "EXIT"}]}), ["ENTRY", "EXIT"])
        dry = evaluate_gates([{
            "label": "1# ENTRY",
            "http_ok": True,
            "request_dry_run": True,
            "body": {"ok": True, "simulated": True, "message": "dry-run open lane 1#"},
        }])
        self.assertEqual(dry[0]["status"], PASS)
        live = evaluate_gates([{
            "label": "1# ENTRY",
            "http_ok": True,
            "request_dry_run": True,
            "body": {"ok": True, "simulated": False, "message": "open lane 1#"},
        }])
        self.assertEqual(live[0]["status"], FAIL)
        skipped = evaluate_gates([{"label": "2#", "skipped": True, "detail": "disabled", "request_dry_run": True}])
        self.assertEqual(skipped[0]["status"], SKIP)


if __name__ == "__main__":
    unittest.main()
