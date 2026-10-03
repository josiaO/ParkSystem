"""PASS/FAIL scoring for the USB field acceptance soak (no live cameras)."""

from __future__ import annotations

import unittest
from pathlib import Path

from tools.field_acceptance_test import (
    FAIL,
    PASS,
    SKIP,
    WARN,
    collect_cameras,
    evaluate_preflight,
    evaluate_soak,
    overall_status,
)


def _cam(**overrides):
    row = {
        "camera_id": 1,
        "camera_name": "1# Entry",
        "live_provider": "MEDIAMTX_WEBRTC",
        "live_connected": True,
        "estimated_frame_age_ms": 120,
        "ai_frame_age_ms": 400,
        "pending_queue_depth": 0,
        "recognition_inflight": False,
        "vehicle_present": False,
        "last_plate": "",
        "dropped_ai_frames": 0,
        "recognition_stalls": 0,
        "recognition_restarts": 0,
        "native_events_received": 0,
        "software_reads": 10,
        "published_events": 2,
        "duplicate_events_suppressed": 0,
        "sessions_created": 2,
        "reconnects": 0,
    }
    row.update(overrides)
    return row


def _snap(*cameras, inflight=0, cap=4):
    return {"cameras": list(cameras), "scheduler": {"inflight": inflight, "max_concurrency": cap}}


class FieldAcceptanceScoringTests(unittest.TestCase):
    def test_healthy_four_camera_soak_passes(self):
        first = _snap(
            _cam(camera_id=1, software_reads=1, published_events=0, sessions_created=0),
            _cam(camera_id=2, camera_name="1# Exit", software_reads=1, published_events=0, sessions_created=0),
            _cam(camera_id=3, camera_name="2# Entry", software_reads=1, published_events=0, sessions_created=0),
            _cam(camera_id=4, camera_name="2# Exit", software_reads=1, published_events=0, sessions_created=0),
        )
        last = _snap(
            _cam(camera_id=1, software_reads=8, published_events=3, sessions_created=3, vehicle_present=False),
            _cam(camera_id=2, camera_name="1# Exit", software_reads=7, published_events=2, sessions_created=2),
            _cam(camera_id=3, camera_name="2# Entry", software_reads=9, published_events=3, sessions_created=3),
            _cam(camera_id=4, camera_name="2# Exit", software_reads=6, published_events=2, sessions_created=2),
        )
        checks = evaluate_soak(
            [first, last],
            sessions=[{"id": 1, "camera_id": 1, "visit_id": "aaa"}, {"id": 2, "camera_id": 1, "visit_id": "bbb"}],
            expected_cars=6,
            connected_ids={1, 2, 3, 4},
        )
        by_id = {row["id"]: row for row in checks}
        self.assertEqual(by_id["S1"]["status"], PASS)
        self.assertEqual(by_id["S2"]["status"], PASS)
        self.assertEqual(by_id["S3"]["status"], PASS)
        self.assertEqual(by_id["S5"]["status"], PASS)
        self.assertEqual(by_id["S6"]["status"], PASS)
        self.assertEqual(by_id["S7"]["status"], PASS)
        self.assertEqual(by_id["S8"]["status"], PASS)
        self.assertEqual(by_id["S8b"]["status"], PASS)
        self.assertEqual(by_id["S9"]["status"], PASS)
        self.assertEqual(by_id["S10"]["status"], PASS)
        self.assertEqual(overall_status(checks), PASS)

    def test_backlog_stale_plate_starvation_and_duplicate_sessions_fail(self):
        first = _snap(
            _cam(software_reads=1, published_events=1, sessions_created=1, recognition_stalls=0),
            _cam(camera_id=2, camera_name="1# Exit", software_reads=1, published_events=1, sessions_created=1, live_provider="OFFLINE", live_connected=False),
        )
        last = _snap(
            _cam(pending_queue_depth=4, estimated_frame_age_ms=4000, software_reads=20, published_events=2, sessions_created=9, recognition_stalls=3, vehicle_present=False, last_plate="T285DQP"),
            _cam(camera_id=2, camera_name="1# Exit", software_reads=1, published_events=1, sessions_created=1, live_provider="OFFLINE", live_connected=False),
        )
        checks = evaluate_soak(
            [first, last],
            sessions=[
                {"camera_id": 1, "visit_id": "same"},
                {"camera_id": 1, "visit_id": "same"},
            ],
            expected_cars=4,
            connected_ids={1, 2},
        )
        by_id = {row["id"]: row for row in checks}
        self.assertEqual(by_id["S1"]["status"], FAIL)
        self.assertEqual(by_id["S2"]["status"], FAIL)
        self.assertEqual(by_id["S3"]["status"], FAIL)
        self.assertEqual(by_id["S6"]["status"], FAIL)
        self.assertEqual(by_id["S7"]["status"], FAIL)
        self.assertEqual(by_id["S8"]["status"], FAIL)
        self.assertEqual(by_id["S8b"]["status"], FAIL)
        self.assertEqual(by_id["S10"]["status"], FAIL)
        self.assertEqual(overall_status(checks), FAIL)

    def test_preflight_requires_live_ready_login_and_cameras(self):
        checks = evaluate_preflight(
            live={"ok": True, "status": "live"},
            ready={"ok": True, "db": {"ok": True}, "hvx_host": {"ok": True, "required": True}},
            cameras=[{"id": 1, "status": "SDK_CONNECTED"}, {"id": 2, "status": "SDK_CONNECTED"}],
            realtime={"cameras": [{"camera_id": 1}]},
            login_ok=True,
            windows=True,
        )
        by_id = {row["id"]: row for row in checks}
        self.assertEqual(by_id["P1"]["status"], PASS)
        self.assertEqual(by_id["P3"]["status"], PASS)
        self.assertEqual(by_id["P5"]["status"], PASS)
        self.assertEqual(by_id["P4b"]["status"], WARN)
        self.assertEqual(overall_status(checks), WARN)

        failed = evaluate_preflight(
            live=None, ready=None, cameras=None, realtime=None, login_ok=False, login_error="refused", windows=True,
        )
        self.assertEqual(overall_status(failed), FAIL)
        failed_by_id = {row["id"]: row for row in failed}
        self.assertIn("sign-in failed", failed_by_id["P4"]["detail"])
        self.assertIn("sign-in failed", failed_by_id["P6"]["detail"])

    def test_expected_cars_skipped_without_count(self):
        checks = evaluate_soak([_snap(_cam())])
        by_id = {row["id"]: row for row in checks}
        self.assertEqual(by_id["S10"]["status"], SKIP)

    def test_collect_tracks_empty_lane_plate(self):
        buckets = collect_cameras([_snap(_cam(vehicle_present=False, last_plate="ABC123"))])
        self.assertEqual(buckets[1]["empty_with_plate"], 1)

    def test_windows_field_script_is_ascii(self):
        path = Path(__file__).resolve().parents[1] / "packaging" / "windows" / "Run-FieldAcceptanceTest.ps1"
        data = path.read_bytes()
        data.decode("ascii")
        self.assertNotIn("\u2014".encode("utf-8"), data)
        self.assertIn(b"--password", data)
        self.assertIn(b"keep cars moving", data)
        lab = (Path(__file__).resolve().parents[1] / "packaging" / "windows" / "Run-CameraLab.bat").read_bytes()
        lab.decode("ascii")
        self.assertNotIn("\u2014".encode("utf-8"), lab)

    def test_windows_wipe_script_deletes_data_and_cache(self):
        path = Path(__file__).resolve().parents[1] / "packaging" / "windows" / "Wipe-SmartPark.ps1"
        data = path.read_bytes()
        data.decode("ascii")
        self.assertNotIn("\u2014".encode("utf-8"), data)
        text = data.decode("ascii")
        self.assertIn(r"ProgramData", text)
        self.assertIn("SmartParkEdge", text)
        self.assertIn("fast-plate-ocr", text)
        self.assertIn("open-image-models", text)
        self.assertIn("Unregister-ScheduledTask", text)
        self.assertIn("Stop-SmartParkProcesses", text)
        self.assertIn("SMARTPARK_*", text)
        bat = (Path(__file__).resolve().parents[1] / "packaging" / "windows" / "Wipe-SmartPark.bat").read_text(encoding="ascii")
        self.assertIn("Wipe-SmartPark.ps1", bat)
