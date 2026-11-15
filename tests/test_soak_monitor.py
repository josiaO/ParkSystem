"""Phase 6.7: soak monitor extraction and verdicts."""

from __future__ import annotations

from tools import soak_monitor as soak


def _sample(at, *, rss=200.0, restarts=0, age=120.0, latency=250.0, failed=0, link="UP", ffmpeg_mb=40.0):
    details = {
        "process": {"rss_bytes": rss * 1e6, "thread_count": 40, "restart_count": 0},
        "recognition_worker": {"resources": {"ram_bytes": 300e6}, "cameras": [
            {"camera_id": 1, "frame_age_at_consumption_ms_p95": age, "decoder_restarts": restarts}]},
        "gates": {"ok": 10, "failed": failed, "avg_latency_ms": latency},
        "watchdog": {"problems": []},
    }
    processes = {"ffmpeg": {"mb": ffmpeg_mb, "count": 4}, "site_service": {"mb": rss, "count": 1}}
    return soak.extract_sample(details, {"db_link": {"state": link}}, processes, at=at)


def test_role_classification():
    assert soak._role(r"C:\SmartPark\python64\python.exe -m app.site_service") == "site_service"
    assert soak._role("ffmpeg -i rtsp://127.0.0.1:8554/cam1_detect") == "ffmpeg"
    assert soak._role(r"python32\python.exe tools\hvx_sdk_host\hvx_host.py") == "hvx_host"
    assert soak._role("notepad.exe") is None


def test_steady_soak_passes():
    samples = [_sample(h * 3600.0) for h in range(0, 73)]
    summary = soak.summarize(samples)
    assert summary["verdict"] == "PASS", summary
    assert summary["hours"] == 72 and summary["cameras"]["1"]["decoder_restarts"] == 0


def test_memory_leak_restarts_and_slow_frames_fail():
    samples = [_sample(h * 3600.0, rss=200 + 12 * h, restarts=h // 6, age=450.0, link="DOWN" if h == 30 else "UP")
               for h in range(0, 73)]
    summary = soak.summarize(samples)
    assert summary["verdict"] == "FAIL"
    checks = summary["checks"]
    assert checks["memory_growth"] is False and checks["decoder_restarts"] is False
    assert checks["frame_age"] is False and checks["database_link"] is False
    assert summary["memory_growth_mb_per_hour"]["site_service"] >= 11
    assert "FAIL" in soak.summary_markdown(summary)


def test_empty_soak_reports_no_data():
    assert soak.summarize([])["verdict"] == "NO DATA"
