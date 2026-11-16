"""tools/latency_report.py on recorded and synthetic trace data."""

from __future__ import annotations

import io
import json
from pathlib import Path

from tools import latency_report

SAMPLE = Path(__file__).parent / "fixtures" / "latency" / "fake-sdk-dryrun"


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _row(stage: str, perf_ms: float, proc: str = "site-service", **fields) -> dict:
    return {"ts": 1_800_000_000 + perf_ms / 1000, "perf_ns": int(perf_ms * 1_000_000),
            "mono_ns": int(perf_ms * 1_000_000), "proc": proc, "pid": 1, "stage": stage, **fields}


def synthetic_capture(directory: Path) -> None:
    """Two phases, two boom commands, one fresh and one stale decision."""
    capture = [
        _row("capture.phase_start", 0, "latency-capture", phase="idle"),
        _row("gate.command_created", 100, "latency-capture", trace="g1"),
        _row("gate.http_sent", 300, "latency-capture", trace="g1", camera=1, client_create_ms=200.0),
        _row("gate.http_received", 860, "latency-capture", trace="g1", camera=1, ok=True, round_trip_ms=560.0),
        _row("capture.phase_end", 1000, "latency-capture", phase="idle"),
        _row("capture.phase_start", 2000, "latency-capture", phase="viewers"),
        _row("gate.command_created", 2100, "latency-capture", trace="g2"),
        _row("gate.http_sent", 2120, "latency-capture", trace="g2", camera=1, client_create_ms=20.0),
        _row("gate.http_received", 5700, "latency-capture", trace="g2", camera=1, ok=True, round_trip_ms=3580.0),
        _row("capture.phase_end", 6000, "latency-capture", phase="viewers"),
    ]
    host = [
        _row("host.gpio.request_received", 310, "hvx-host", trace="g1", camera=1, queue_wait_ms=1.0),
        _row("host.gpio.sdk_start", 311, "hvx-host", trace="g1", camera=1),
        _row("host.gpio.relay_on", 340, "hvx-host", trace="g1", camera=1, write_on_ms=29.0),
        _row("host.gpio.request_received", 5150, "hvx-host", trace="g2", camera=1, queue_wait_ms=3000.0),
        _row("host.gpio.sdk_start", 5151, "hvx-host", trace="g2", camera=1),
        _row("host.gpio.relay_on", 5180, "hvx-host", trace="g2", camera=1, write_on_ms=29.0),
        _row("host.frame.served", 2500, "hvx-host", camera=1, age_ms=40.0),
        _row("host.frame.served", 2600, "hvx-host", camera=1, age_ms=900.0),
        _row("host.heartbeat.stall", 2700, "hvx-host", lag_ms=450.0),
    ]
    site = [
        _row("lane.gate_requested", 2050, visit_id="v1", camera=1, command_uuid="c1"),
        _row("decision.source_age", 2050, visit_id="v1", camera=1, at_stage="gate_requested",
             source="frame", age_ms=120.0, stale=False),
        _row("decision.source_age", 2400, visit_id="v2", camera=1, at_stage="gate_requested",
             source="native_event", age_ms=4200.0, stale=True),
        _row("recognition.native_event", 2300, visit_id="v2", camera=1, capture_token="tok",
             age_after_media_ms=4100.0, stale=True),
        "this line was cut by a crash",
    ]
    _write(directory / "latency-trace-latency-capture.jsonl", capture)
    _write(directory / "latency-trace-hvx-host.jsonl", host)
    (directory / "latency-trace-site-service.jsonl.1").write_text(
        "".join((json.dumps(r) if isinstance(r, dict) else r) + "\n" for r in site), encoding="utf-8")


def test_gate_commands_are_rebuilt_across_processes(tmp_path):
    synthetic_capture(tmp_path)
    report = latency_report.build_report([tmp_path])
    assert report["unreadable_lines"] == 1
    assert report["processes"] == ["hvx-host", "latency-capture", "site-service"]
    spans = {span["trace"]: span for span in report["gate_commands"]}
    assert spans["g1"]["phase"] == "idle" and spans["g2"]["phase"] == "viewers"
    assert spans["g1"]["command_to_relay_on_ms"] == 240.0
    assert spans["g1"]["command_to_http_sent_ms"] == 200.0
    assert spans["g2"]["command_to_relay_on_ms"] == 3080.0
    assert spans["g2"]["host_queue_wait_ms"] == 3000.0
    assert spans["g2"]["http_sent_to_host_received_ms"] == 3030.0


def test_stage_table_is_split_by_phase_and_camera(tmp_path):
    synthetic_capture(tmp_path)
    report = latency_report.build_report([tmp_path])
    rows = {(r["phase"], r["stage"], r["field"], r["group"]): r for r in report["stages"]}
    served = rows[("viewers", "host.frame.served", "age_ms", "cam 1")]
    assert served["count"] == 2 and served["max"] == 900.0 and served["p50"] == 470.0
    assert rows[("idle", "gate.http_sent", "client_create_ms", "cam 1")]["p50"] == 200.0
    assert rows[("viewers", "decision.source_age", "age_ms", "cam 1 @gate_requested")]["count"] == 2


def test_stale_counts_and_worst_traces(tmp_path):
    synthetic_capture(tmp_path)
    report = latency_report.build_report([tmp_path], worst_count=1)
    stale = {(r["stage"], r["group"]): r for r in report["stale"]}
    assert stale[("decision.source_age", "cam 1 @gate_requested")] == {
        "phase": "viewers", "stage": "decision.source_age", "group": "cam 1 @gate_requested",
        "checked": 2, "stale": 1}
    worst = {block["label"]: block for block in report["worst"]}
    boom = worst["boom: command -> relay on"]["events"][0]
    assert boom["value_ms"] == 3080.0 and boom["row"]["trace"] == "g2"
    assert [step["stage"] for step in boom["trace"]][:2] == ["gate.command_created", "gate.http_sent"]
    decision = worst["recognition: decision source age"]["events"][0]
    # the stale decision is joined to its native event by visit id
    assert {step["stage"] for step in decision["trace"]} == {"decision.source_age", "recognition.native_event"}


def test_text_and_json_output(tmp_path):
    synthetic_capture(tmp_path)
    out = tmp_path / "out" / "report.json"
    assert latency_report.main([str(tmp_path), "--json", str(out), "--worst", "2"]) == 0
    data = json.loads(out.read_text())
    assert data["records"] == 23  # 10 capture + 9 host + 4 site (1 cut line skipped)
    buffer = io.StringIO()
    latency_report.render_text(data, out=buffer)
    text = buffer.getvalue()
    for heading in ("== 1. Stages", "== 2. Boom commands", "== 3. Stale checks", "== 4. Worst events"):
        assert heading in text
    assert "CMD>RELAY" in text and "3080.0" in text


def test_runs_on_recorded_fake_sdk_sample():
    report = latency_report.build_report([SAMPLE])
    assert report["records"] > 100 and report["unreadable_lines"] == 0
    assert set(report["phases"]) >= {"idle", "viewers", "saturate"}
    spans = report["gate_commands"]
    assert len(spans) == 9
    saturated = [s for s in spans if s["phase"] == "saturate"]
    # the H1 upper bound recorded on the dry run: every worker held, pulse queued for seconds
    assert all(s["host_queue_wait_ms"] > 5000 for s in saturated)
    idle = [s for s in spans if s["phase"] == "idle"]
    assert all(s["host_queue_wait_ms"] < 50 for s in idle)
    buffer = io.StringIO()
    latency_report.render_text(report, out=buffer)
    assert "saturate" in buffer.getvalue()


def test_empty_folder_reports_no_records(tmp_path):
    assert latency_report.main([str(tmp_path)]) == 1
