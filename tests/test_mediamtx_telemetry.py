"""MediaMTX stream-role dedup, Control API telemetry and codec reporting."""

from __future__ import annotations

import asyncio
import re
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.infrastructure.media import registry
from app.services import mediamtx, mediamtx_telemetry
from app.services.mediamtx_sources import upstream_role_uris

ROOT = Path(__file__).resolve().parents[1]


class PathPlanTests(unittest.TestCase):
    def tearDown(self):
        for cid in (30, 31, 32):
            mediamtx._sources.pop(cid, None)

    def test_shared_upstream_uses_one_path_for_live_and_detect(self):
        plan = mediamtx.path_plan(30, {"uri": "rtsp://cam/only", "detect_uri": "rtsp://cam/only"})
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["name"], "cam30")
        self.assertEqual(sorted(plan[0]["roles"]), ["DETECT", "EVIDENCE", "LIVE"] if "EVIDENCE" in plan[0]["roles"] else ["DETECT", "LIVE"])
        self.assertFalse(plan[0]["on_demand"])
        mediamtx._sources[30] = {"uri": "rtsp://cam/only", "detect_uri": "rtsp://cam/only"}
        self.assertEqual(mediamtx.detect_endpoint(30)["rtsp"], "rtsp://127.0.0.1:8554/cam30")
        self.assertTrue(mediamtx.detect_endpoint(30)["shared_upstream"])
        # Evidence with no distinct MAIN stream reuses the live path too.
        self.assertEqual(mediamtx.evidence_endpoint(30)["rtsp"], "rtsp://127.0.0.1:8554/cam30")

    def test_distinct_streams_get_distinct_paths_and_evidence_is_on_demand(self):
        plan = mediamtx.path_plan(31, {
            "uri": "rtsp://cam/sub",
            "detect_uri": "rtsp://cam/third",
            "evidence_uri": "rtsp://cam/main",
        })
        names = {p["name"]: p for p in plan}
        self.assertEqual(set(names), {"cam31", "cam31_detect", "cam31_evidence"})
        self.assertFalse(names["cam31"]["on_demand"])
        self.assertFalse(names["cam31_detect"]["on_demand"], "detect must never stop when nobody views")
        self.assertTrue(names["cam31_evidence"]["on_demand"])

    def test_evidence_matching_live_shares_that_path(self):
        plan = mediamtx.path_plan(32, {"uri": "rtsp://cam/main", "detect_uri": "rtsp://cam/sub", "evidence_uri": "rtsp://cam/main"})
        live = next(p for p in plan if p["name"] == "cam32")
        self.assertIn("EVIDENCE", live["roles"])
        self.assertEqual(len(plan), 2)

    def test_generated_config_honors_camera_transport(self):
        dest = ROOT / "data" / "test-mediamtx-transport.yml"
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with patch.object(mediamtx, "config_path", return_value=dest):
                mediamtx._sources[30] = {
                    "uri": "rtsp://cam/only",
                    "detect_uri": "rtsp://cam/only",
                    "transport": "UDP",
                }
                mediamtx.write_config()
            body = dest.read_text(encoding="utf-8")
        finally:
            dest.unlink(missing_ok=True)
        self.assertIn("rtspTransport: udp", body)

    def test_generated_config_writes_one_path_per_distinct_upstream(self):
        dest = ROOT / "data" / "test-mediamtx-dedup.yml"
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with patch.object(mediamtx, "config_path", return_value=dest):
                mediamtx._sources[30] = {"uri": "rtsp://cam/only", "detect_uri": "rtsp://cam/only", "evidence_uri": "rtsp://cam/main"}
                mediamtx.write_config()
            body = dest.read_text(encoding="utf-8")
        finally:
            dest.unlink(missing_ok=True)
        self.assertIn("  cam30:\n", body)
        self.assertNotIn("cam30_detect:", body)
        self.assertIn("cam30_evidence:", body)
        self.assertEqual(body.count("source: rtsp://cam/only"), 1)
        evidence_block = body.split("cam30_evidence:")[1]
        self.assertIn("sourceOnDemand: yes", evidence_block)
        live_block = body.split("  cam30:")[1].split("cam30_evidence:")[0]
        self.assertIn("sourceOnDemand: no", live_block)

    def test_sync_paths_removes_stale_split_detect_path(self):
        calls: list[tuple[str, str]] = []

        def fake_control(method, path, body=None):
            calls.append((method, path))
            return 200

        mediamtx._sources[30] = {"uri": "rtsp://cam/only", "detect_uri": "rtsp://cam/only"}
        with patch.object(mediamtx, "running", return_value=True), patch.object(mediamtx, "_control_api", fake_control):
            self.assertTrue(mediamtx.sync_paths())
        added = [p for m, p in calls if m == "POST"]
        deleted = [p for m, p in calls if m == "DELETE"]
        self.assertEqual(added, ["/v3/config/paths/add/cam30"])
        self.assertIn("/v3/config/paths/delete/cam30_detect", deleted)
        self.assertIn("/v3/config/paths/delete/cam30_evidence", deleted)

    def test_upstream_role_uris_resolve_evidence_from_main(self):
        profiles = {
            "MAIN": {"uri": "rtsp://cam/main"},
            "SUB": {"uri": "rtsp://cam/sub"},
            "LIVE": {"source": "SUB"},
            "DETECT": {"source": "SUB"},
            "EVIDENCE": {"source": "MAIN"},
        }
        live, detect, evidence = upstream_role_uris(ip="1.2.3.4", username="u", password="p", rtsp_url="rtsp://cam/sub", stream_profiles=profiles)
        self.assertEqual((live, detect, evidence), ("rtsp://cam/sub", "rtsp://cam/sub", "rtsp://cam/main"))
        live, detect, evidence = upstream_role_uris(ip="1.2.3.4", username="u", password="p", rtsp_url="rtsp://cam/x", stream_profiles=None)
        self.assertEqual((live, detect, evidence), ("rtsp://cam/x", "rtsp://cam/x", ""))


def _fake_api(paths, rtsp=None, webrtc=None):
    def _get(path):
        if path.startswith("/v3/paths/list"):
            return {"items": paths}
        if path.startswith("/v3/rtspsessions/list"):
            return {"items": rtsp or []}
        if path.startswith("/v3/webrtcsessions/list"):
            return {"items": webrtc or []}
        return None
    return _get


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        mediamtx_telemetry.reset()
        mediamtx._sources[40] = {"uri": "rtsp://cam/sub", "detect_uri": "rtsp://cam/sub", "evidence_uri": "rtsp://cam/main"}

    def tearDown(self):
        mediamtx_telemetry.reset()
        mediamtx._sources.pop(40, None)

    def test_control_api_unreachable_is_reported_not_raised(self):
        with patch.object(mediamtx_telemetry, "_get_json", return_value=None):
            snap = mediamtx_telemetry.refresh(force=True)
            summary = mediamtx_telemetry.summary()
        self.assertFalse(snap["ok"])
        self.assertIn("unreachable", snap["error"])
        self.assertEqual(summary["paths_total"], 0)
        self.assertFalse(summary["ok"])

    def test_paths_and_sessions_fold_into_roles(self):
        paths = [
            {"name": "cam40", "source": {"type": "rtspSource", "id": ""}, "ready": True, "readyTime": "t1",
             "tracks": ["H264", "MPEG-4 Audio"], "bytesReceived": 2048, "bytesSent": 4096,
             "readers": [{"type": "webRTCSession", "id": "a"}, {"type": "rtspSession", "id": "b"}]},
            {"name": "cam40_evidence", "source": None, "ready": False, "readyTime": "", "tracks": [], "readers": []},
        ]
        rtsp = [{"path": "cam40", "state": "read", "rtpPacketsSent": 500, "rtpPacketsLost": 3, "rtpPacketsInError": 1, "rtpPacketsJitter": 0.4}]
        webrtc = [{"path": "cam40", "state": "read", "rtpPacketsSent": 700, "rtpPacketsLost": 0, "rtpPacketsJitter": 0.1}]
        with patch.object(mediamtx_telemetry, "_get_json", _fake_api(paths, rtsp, webrtc)):
            tele = mediamtx_telemetry.camera_telemetry(40)
        self.assertTrue(tele["control_api_ok"])
        self.assertEqual(tele["codec"], "H264")
        self.assertTrue(tele["webrtc"]["compatible"])
        live = tele["roles"]["LIVE"]
        detect = tele["roles"]["DETECT"]
        evidence = tele["roles"]["EVIDENCE"]
        self.assertEqual(live["mediamtx_path"], detect["mediamtx_path"])
        self.assertTrue(live["shared_upstream"])
        self.assertEqual(live["readers"], 2)
        self.assertEqual(live["rtsp_readers"], 1)
        self.assertEqual(live["webrtc_readers"], 1)
        self.assertEqual(live["rtp"]["packets_lost"], 3)
        self.assertEqual(live["rtp"]["packets_in_error"], 1)
        self.assertAlmostEqual(live["rtp"]["jitter_max"], 0.4)
        self.assertEqual(live["bytes_received"], 2048)
        self.assertTrue(live["connected"])
        self.assertTrue(evidence["on_demand"])
        self.assertFalse(evidence["ready"])
        # Loss on the live path is surfaced as DEGRADED, not hidden.
        self.assertEqual(tele["state"], "DEGRADED")

    def test_ready_time_change_counts_as_reconnect(self):
        def snapshot(ready_time):
            return [{"name": "cam40", "source": {"type": "rtspSource"}, "ready": True, "readyTime": ready_time, "tracks": ["H264"], "readers": []}]
        with patch.object(mediamtx_telemetry, "_get_json", _fake_api(snapshot("t1"))):
            mediamtx_telemetry.refresh(force=True)
        with patch.object(mediamtx_telemetry, "_get_json", _fake_api(snapshot("t1"))):
            self.assertEqual(mediamtx_telemetry.refresh(force=True)["paths"]["cam40"]["reconnects"], 0)
        with patch.object(mediamtx_telemetry, "_get_json", _fake_api(snapshot("t2"))):
            tele = mediamtx_telemetry.refresh(force=True)
        self.assertEqual(tele["paths"]["cam40"]["reconnects"], 1)
        self.assertEqual(mediamtx_telemetry.camera_telemetry(40)["state"], "LIVE")

    def test_codec_compatibility_classification(self):
        self.assertTrue(mediamtx_telemetry.webrtc_compatibility("H264")["compatible"])
        self.assertIsNone(mediamtx_telemetry.webrtc_compatibility("H265")["compatible"])
        bad = mediamtx_telemetry.webrtc_compatibility("MPEG-4-VIDEO")
        self.assertFalse(bad["compatible"])
        self.assertIn("No transcoding", bad["reason"])
        self.assertIsNone(mediamtx_telemetry.webrtc_compatibility("")["compatible"])

    def test_snapshot_is_cached_between_calls(self):
        calls = {"n": 0}
        inner = _fake_api([{"name": "cam40", "ready": True, "readyTime": "t", "tracks": ["H264"], "readers": []}])

        def counting(path):
            calls["n"] += 1
            return inner(path)

        with patch.object(mediamtx_telemetry, "_get_json", counting):
            mediamtx_telemetry.refresh(force=True)
            first = calls["n"]
            mediamtx_telemetry.refresh()
            mediamtx_telemetry.summary()
        self.assertEqual(calls["n"], first, "second call within the cache window must not hit the Control API")

    def test_health_includes_telemetry_summary_when_running(self):
        paths = [{"name": "cam40", "ready": True, "readyTime": "t", "tracks": ["H264"], "readers": [{"type": "x", "id": "1"}]}]
        with patch.object(mediamtx, "running", return_value=True), \
             patch.object(mediamtx_telemetry, "_get_json", _fake_api(paths)):
            health = mediamtx.health()
        self.assertEqual(health["telemetry"]["paths_ready"], 1)
        self.assertEqual(health["telemetry"]["readers"], 1)
        self.assertIn("cam40", health["paths"])
        self.assertIn("cam40_evidence", health["paths"])


class RegistryCodecTests(unittest.TestCase):
    FLAGS = {"media_gateway_enabled": True, "live_view_provider": "MEDIAMTX", "webrtc_live_enabled": True}

    def _run(self, telemetry):
        with patch.object(registry, "_migration_flags", return_value=self.FLAGS), \
             patch.object(registry, "_camera_enabled", return_value=True), \
             patch.object(registry.mediamtx, "running", return_value=True), \
             patch.object(registry, "media_telemetry", return_value=telemetry), \
             patch.object(registry.gateway, "get_live_endpoint", AsyncMock(return_value={"kind": "mjpeg", "path": "/cameras/7/live.mjpeg"})):
            return asyncio.run(registry.get_live_endpoint(7))

    def test_incompatible_codec_reports_degraded_mjpeg_without_webrtc(self):
        body = self._run({"state": "LIVE", "codec": "MPEG-4-VIDEO",
                          "webrtc": {"compatible": False, "reason": "MPEG-4 cannot be played by browser WebRTC"}})
        self.assertEqual(body["provider"], "MEDIAMTX")
        self.assertEqual(body["transport"], "MJPEG")
        self.assertEqual(body["state"], "DEGRADED")
        self.assertIn("MPEG-4", body["reason"])
        self.assertNotIn("webrtc", body)
        self.assertIn("live.mjpeg", body["path"])

    def test_compatible_codec_returns_single_webrtc_transport(self):
        body = self._run({"state": "LIVE", "codec": "H264", "webrtc": {"compatible": True, "reason": ""}})
        self.assertEqual(body["transport"], "WEBRTC")
        self.assertEqual(body["state"], "LIVE")
        self.assertTrue(body["whep"].endswith("/cam7/whep"))
        self.assertNotIn("path", body)

    def test_evidence_endpoint_falls_back_to_snapshot_when_legacy(self):
        with patch.object(registry, "mediamtx_detect_active", return_value=False):
            body = asyncio.run(registry.get_evidence_endpoint(7))
        self.assertEqual(body["provider"], "DIRECT_LEGACY")
        self.assertIn("snapshot.jpg", body["path"])

    def test_media_telemetry_offline_when_not_running(self):
        with patch.object(registry.mediamtx, "running", return_value=False):
            body = registry.media_telemetry(7)
        self.assertEqual(body["state"], "OFFLINE")
        self.assertFalse(body["control_api_ok"])


class BrowserLiveViewTests(unittest.TestCase):
    def setUp(self):
        self.html = (ROOT / "app" / "web" / "index.html").read_text(encoding="utf-8")

    def test_webrtc_uses_video_element_not_permanent_iframe(self):
        self.assertNotIn('<iframe data-role="webrtc"', self.html)
        self.assertEqual(len(re.findall(r'<video data-role="webrtc"', self.html)), 2)

    def test_camera_switch_closes_whep_reader_before_new_transport(self):
        stop_fn = self.html.split("function stopLiveSlot(")[1].split("\n    }\n")[0]
        self.assertIn("whepStop(slot)", stop_fn)
        self.assertIn("srcObject = null", stop_fn)
        whep_stop = self.html.split("function whepStop(")[1].split("\n    }\n")[0]
        self.assertIn("pc.close()", whep_stop)
        self.assertIn('method: "DELETE"', whep_stop)

    def test_webrtc_pane_never_also_starts_mjpeg_or_snapshot_polling(self):
        start_fn = self.html.split("async function startLiveSlot(")[1].split("\n    }\n")[0]
        webrtc_branch = start_fn.split('ep.transport === "WEBRTC"')[1].split("} catch (err) {")[0]
        webrtc_branch = re.sub(r"//[^\n]*", "", webrtc_branch)  # ignore comments
        self.assertNotIn("startMjpegLive", webrtc_branch)
        self.assertNotIn("snapshot.jpg", webrtc_branch)
        self.assertIn("clearInterval(snapshotTimers[slot])", webrtc_branch)
        self.assertIn("refreshPlates(slot);\n          return;", webrtc_branch)

    def test_states_are_displayed(self):
        for label in ("LIVE (WebRTC", "DEGRADED", "OFFLINE"):
            self.assertIn(label, self.html)
        self.assertIn("renderMediaMtxTelemetry", self.html)
        self.assertIn("RTP loss", self.html)


if __name__ == "__main__":
    unittest.main()
