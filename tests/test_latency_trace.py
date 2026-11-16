"""Latency trace writer, metrics, heartbeat and the lane-timeline bridge."""

from __future__ import annotations

import json
import sys
import threading
import time

import pytest

from app.core import latency_trace


def _rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture
def tracer(tmp_path, monkeypatch):
    writer = latency_trace.configure("test", tmp_path, enabled=True)
    yield writer
    writer.close()
    monkeypatch.setattr(latency_trace, "_tracer", None)


def test_records_carry_three_clocks_and_trace_context(tracer, tmp_path):
    with latency_trace.trace_context("cmd-1"):
        tracer.emit("gate.http_sent", camera=3, skipped=None)
    tracer.emit("other")
    assert tracer.flush()
    first, second = _rows(tmp_path / "latency-trace-test.jsonl")
    assert first["stage"] == "gate.http_sent" and first["trace"] == "cmd-1" and first["camera"] == 3
    assert "skipped" not in first  # None fields are omitted
    for key in ("ts", "perf_ns", "mono_ns", "proc", "pid"):
        assert key in first
    assert "trace" not in second
    assert second["perf_ns"] >= first["perf_ns"]


def test_disabled_writes_nothing(tmp_path):
    writer = latency_trace.TraceWriter("off", tmp_path, enabled=False)
    assert writer.emit("x") is None
    assert writer.flush()
    assert not (tmp_path / "latency-trace-off.jsonl").exists()


def test_env_switch_disables(monkeypatch, tmp_path):
    monkeypatch.setenv("SMARTPARK_LATENCY_TRACE", "0")
    assert latency_trace.TraceWriter("env", tmp_path).enabled is False
    monkeypatch.setenv("SMARTPARK_LATENCY_TRACE", "1")
    assert latency_trace.TraceWriter("env", tmp_path).enabled is True


def test_full_buffer_drops_and_counts_instead_of_blocking(tmp_path):
    writer = latency_trace.TraceWriter("full", tmp_path, enabled=True, buffer_size=5, flush_interval=60)
    writer._thread = threading.Thread()  # writer never drains: simulate a stuck disk
    started = time.perf_counter()
    results = [writer.emit("s", i=i) for i in range(50)]
    assert time.perf_counter() - started < 0.5
    assert sum(1 for r in results if r is not None) == 5
    assert writer.dropped == 45


def test_rotation_keeps_bounded_backups(tmp_path):
    writer = latency_trace.TraceWriter("rot", tmp_path, enabled=True, max_bytes=2_000, backups=2)
    for batch in range(6):
        for i in range(20):
            writer.emit("fill", batch=batch, i=i, pad="x" * 20)
        assert writer.flush()
    files = sorted(p.name for p in tmp_path.iterdir())
    assert files == ["latency-trace-rot.jsonl", "latency-trace-rot.jsonl.1", "latency-trace-rot.jsonl.2"]
    for path in tmp_path.iterdir():
        _rows(path)  # every file is whole JSON lines


def test_frame_sampling_is_one_in_n_per_key(tmp_path, monkeypatch):
    monkeypatch.setenv("SMARTPARK_LATENCY_TRACE_FRAME_EVERY", "5")
    writer = latency_trace.TraceWriter("s", tmp_path, enabled=True)
    picks = [writer.sample_frame(("cam", 1)) for _ in range(20)]
    assert picks.count(True) == 4 and picks[0] is True
    assert writer.sample_frame(("cam", 2)) is True  # independent per key


def test_histogram_and_registry():
    assert latency_trace.percentile([], 50) is None
    assert latency_trace.percentile(range(1, 101), 50) == pytest.approx(50.5)
    registry = latency_trace.MetricsRegistry()
    for value in range(1, 101):
        registry.observe("h", value)
    registry.incr("c", 3)
    registry.gauge("g", "sdk_draw_data")
    assert registry.adjust("busy", 2) == 2 and registry.adjust("busy", -1) == 1
    snap = registry.snapshot()
    assert snap["histograms_ms"]["h"]["count"] == 100
    assert snap["histograms_ms"]["h"]["p95"] == pytest.approx(95.05)
    assert snap["histograms_ms"]["h"]["max"] == 100
    assert snap["counters"]["c"] == 3 and snap["gauges"]["g"] == "sdk_draw_data"


def test_heartbeat_detects_a_gil_stall():
    """A thread holding the GIL is visible as heartbeat lag (hypothesis H8)."""
    registry = latency_trace.MetricsRegistry()
    stalls = []
    monitor = latency_trace.HeartbeatMonitor(registry, interval=0.01, stall_ms=80, on_stall=stalls.append).start()
    time.sleep(0.1)
    previous = sys.getswitchinterval()
    sys.setswitchinterval(1.0)  # pure-Python loop below keeps the GIL
    try:
        end = time.perf_counter() + 0.3
        while time.perf_counter() < end:
            pass
    finally:
        sys.setswitchinterval(previous)
    time.sleep(0.1)
    monitor.stop()
    summary = registry.snapshot()["histograms_ms"]["heartbeat_lag"]
    assert summary["max"] >= 80
    assert stalls and max(stalls) >= 80


def test_age_from_perf_stamp():
    now = time.perf_counter_ns()
    assert latency_trace.age_ms_from_perf(now - 250_000_000, now) == 250.0
    assert latency_trace.age_ms_from_perf(None) is None
    assert latency_trace.age_ms_from_perf("bad") is None


# -- lane timeline bridge ----------------------------------------------------

def test_decision_source_age_flags_a_stale_frame(monkeypatch):
    from app.services.lane_timing import decision_source_age

    monkeypatch.setenv("SMARTPARK_FRAME_AGE_LIMIT_MS", "500")
    timeline = {"origin_monotonic": 100.0, "stages_ms": {"vehicle_seen": 0.0, "frame_decoded": 200.0}}
    fresh = decision_source_age(timeline, now=100.5)
    assert fresh["source"] == "frame" and fresh["age_ms"] == 300.0 and fresh["stale"] is False
    stale = decision_source_age(timeline, now=101.0)
    assert stale["age_ms"] == 800.0 and stale["stale"] is True


def test_decision_source_age_uses_newest_source_and_event_limit(monkeypatch):
    from app.services.lane_timing import decision_source_age

    monkeypatch.setenv("SMARTPARK_EVENT_AGE_LIMIT_MS", "2000")
    timeline = {"origin_monotonic": 10.0, "stages_ms": {"frame_decoded": 0.0, "native_event_captured": 400.0}}
    result = decision_source_age(timeline, now=11.9)
    assert result["source"] == "native_event" and result["age_ms"] == 1500.0
    assert result["limit_ms"] == 2000 and result["stale"] is False
    assert decision_source_age({"stages_ms": {}})["source"] is None


def test_mark_emits_lane_stage_and_decision_age(tracer, tmp_path):
    from app.services.lane_timing import mark

    timeline = {"visit_id": "v1", "camera_id": 7, "command_uuid": "cmd-9"}
    now = time.monotonic()
    mark("vehicle_seen", timeline, at=now - 2.0)
    mark("frame_decoded", timeline, at=now - 1.0)
    mark("gate_requested", timeline, at=now)
    assert tracer.flush()
    rows = _rows(tmp_path / "latency-trace-test.jsonl")
    stages = [row["stage"] for row in rows]
    assert stages == ["lane.vehicle_seen", "lane.frame_decoded", "lane.gate_requested", "decision.source_age"]
    decision = rows[-1]
    assert decision["visit_id"] == "v1" and decision["camera"] == 7 and decision["command_uuid"] == "cmd-9"
    assert decision["source"] == "frame" and decision["stale"] is True
    assert decision["age_ms"] == pytest.approx(1000.0, abs=1.0)


def test_native_event_age_prefers_perf_clock_then_wall_clock():
    import app.api.runtime as runtime

    now = time.perf_counter_ns()
    assert runtime._native_event_age_ms({"captured_perf_ns": now - 300_000_000}) >= 300
    old_host = runtime._native_event_age_ms({"captured_at_epoch": time.time() - 3.0})
    assert 2900 <= old_host < 4000
    assert runtime._native_event_age_ms({}) is None


def test_native_timeline_starts_at_the_camera_callback():
    import app.api.runtime as runtime
    from app.services.lane_timing import decision_source_age

    capture = {"capture_token": "tok"}
    runtime._seed_native_timeline(4, capture, "visit-1", 1200.0)
    timeline = capture["timeline"]
    assert timeline["origin_stage"] == "native_event_captured"
    assert timeline["capture_token"] == "tok" and timeline["visit_id"] == "visit-1"
    assert timeline["stages_ms"]["native_event_ingested"] == pytest.approx(1200.0, abs=20)
    assert decision_source_age(timeline)["age_ms"] == pytest.approx(1200.0, abs=20)
