"""HVX host instrumentation, run against the real host code on the fake NetSDK.

These tests measure mechanisms, they do not prove anything about the Windows
rig: the fake DLL's timings are knobs. What they do prove is that the trace
and /metrics will show each hypothesis (H1 queueing, H6 frame age, H8 stalls)
when it happens.
"""

from __future__ import annotations

import asyncio
import http.client
import json
import socket
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT / "tools" / "hvx_sdk_host", ROOT / "tests" / "fakes"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import fake_hvx_sdk  # noqa: E402
import hvx_host  # noqa: E402
import hvx_sdk  # noqa: E402

from app.core import latency_trace  # noqa: E402


def _rows(directory: Path) -> list[dict]:
    rows = []
    for path in sorted(directory.glob("latency-trace-*.jsonl")):
        rows.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return rows


@pytest.fixture
def host(tmp_path, monkeypatch):
    """Real HTTP server + real HVXSDK over the fake DLL, one camera live."""
    monkeypatch.setenv("SMARTPARK_LATENCY_TRACE_FRAME_EVERY", "1")
    tracer = latency_trace.configure("hvx-host", tmp_path, enabled=True)
    sdk, dll = fake_hvx_sdk.make_sdk_and_dll(hvx_sdk.HVXSDK, tmp_path, fps=25, width=320, height=180)
    monkeypatch.setattr(hvx_host, "sdk", sdk)
    monkeypatch.setattr(hvx_host.Handler, "keepalive_timeout", 1.0)
    server = hvx_host.BoundedHTTPServer(("127.0.0.1", 0), hvx_host.Handler, max_workers=4, max_pending=8)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    handle = sdk.add_and_connect("10.0.0.5", 30000, 3, "", "")["handle"]
    port = server.server_address[1]
    yield SimpleNamespace(sdk=sdk, dll=dll, port=port, url=f"http://127.0.0.1:{port}",
                          handle=handle, tracer=tracer, trace_dir=tmp_path)
    server.shutdown()
    server.server_close()
    sdk.close()
    tracer.close()
    monkeypatch.setattr(latency_trace, "_tracer", None)


def _get(port: int, path: str, timeout: float = 5.0):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request("GET", path)
        response = conn.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        conn.close()


def test_live_frames_report_age_and_monotonic_sequence(host):
    seqs = []
    after = 0
    for _ in range(6):
        status, headers, body = _get(host.port, f"/live-jpeg/{host.handle}?after={after}&wait_ms=1500")
        assert status == 200 and body[:2] == b"\xff\xd8"
        seq = int(headers["X-Frame-Seq"])
        assert seq > after  # a long-poll never returns an already-seen frame as new
        assert 0 <= float(headers["X-Frame-Age-Ms"]) < 1000
        assert int(headers["X-Frame-Captured-Perf-Ns"]) <= time.perf_counter_ns()
        seqs.append(seq)
        after = seq
    assert seqs == sorted(set(seqs))
    host.tracer.flush()
    stages = {row["stage"] for row in _rows(host.trace_dir)}
    assert {"host.frame.stored", "host.frame.served", "host.http.request"} <= stages


def test_frozen_decoder_serves_no_frame_as_new(host):
    _, headers, _ = _get(host.port, f"/live-jpeg/{host.handle}?after=0&wait_ms=1500")
    seq = int(headers["X-Frame-Seq"])
    host.dll.freeze(host.handle)
    time.sleep(0.2)
    _, headers, _ = _get(host.port, f"/live-jpeg/{host.handle}?after=0&wait_ms=0")
    latest = int(headers["X-Frame-Seq"])
    status, headers, body = _get(host.port, f"/live-jpeg/{host.handle}?after={latest}&wait_ms=400")
    assert status == 204 and body == b"" and int(headers["X-Frame-Seq"]) == latest
    host.dll.resume(host.handle)
    status, headers, _ = _get(host.port, f"/live-jpeg/{host.handle}?after={latest}&wait_ms=1500")
    assert status == 200 and int(headers["X-Frame-Seq"]) > latest >= seq


def test_metrics_endpoint_reports_host_self_measurements(host):
    _get(host.port, f"/live-jpeg/{host.handle}?after=0&wait_ms=1500")
    status, _, body = _get(host.port, "/metrics")
    assert status == 200
    payload = json.loads(body)
    histograms = payload["histograms_ms"]
    for name in ("http.connection_queue_wait", "callback.draw_data", "frame.encode", "frame.age_at_serve",
                 "http.handler.GET /live-jpeg"):
        assert histograms[name]["count"] >= 1, name
    assert payload["gauges"]["http.max_workers"] == 4
    assert payload["gauges"][f"capture_mode.{host.handle}"] == "sdk_draw_data"
    assert payload["cameras"][str(host.handle)]["capture_mode"] == "sdk_draw_data"
    assert payload["fake_sdk"] is True and payload["clock"] == "perf_counter_ns"
    assert payload["trace"]["enabled"] is True
    assert payload["counters"][f"frames.callbacks.{host.handle}"] > 0


def test_gpio_pulse_is_traced_end_to_end_with_one_trace_id(host):
    from app.services.hvx_client import HVXHostClient

    host.dll.gpio_write_delay_ms = 30
    host.dll.gate_setup_delay_ms = 20
    app_tracer = host.tracer  # same process in this test; the proc label differs on Windows

    async def pulse():
        with latency_trace.trace_context("cmd-123"):
            return await HVXHostClient(host.url).gpio_pulse(handle=host.handle, index=0, pulse_ms=100)

    result = asyncio.run(pulse())
    assert result["ok"] is True
    timing = result["timing"]
    assert timing["gate_setup_ms"] >= 20 and timing["write_on_ms"] >= 30
    assert timing["relay_on_perf_ns"] - timing["sdk_start_perf_ns"] >= 50_000_000
    assert result["host_timing"]["queue_wait_ms"] is not None
    app_tracer.flush()
    rows = [row for row in _rows(host.trace_dir) if row.get("trace") == "cmd-123"]
    stages = [row["stage"] for row in rows]
    for stage in ("gate.http_sent", "host.gpio.request_received", "host.gpio.sdk_start", "host.gpio.relay_on",
                  "host.gpio.sdk_done", "host.http.request", "gate.http_received"):
        assert stage in stages, stage
    received = next(row for row in rows if row["stage"] == "gate.http_received")
    assert received["sent_to_relay_on_ms"] >= 50
    # The response only arrives after the hold: the relay closed ~hold earlier.
    assert received["round_trip_ms"] >= received["sent_to_relay_on_ms"] + received["hold_ms"] - 5


def test_idle_keepalive_connections_delay_a_boom_command(host):
    """H1 mechanism: every worker held by an idle keep-alive viewer delays /gpio/pulse.

    Four workers, four idle keep-alive connections. A fresh pulse connection
    has to wait for one of them to time out (keepalive_timeout = 1 s here,
    10 s in production). The measurement must show it as queue wait.
    """
    sockets = []
    for _ in range(4):
        sock = socket.create_connection(("127.0.0.1", host.port))
        sock.sendall(b"GET /info HTTP/1.1\r\nHost: x\r\nConnection: keep-alive\r\n\r\n")
        sock.recv(65536)
        sockets.append(sock)  # stay open and idle: the worker stays reserved
    try:
        time.sleep(0.1)
        started = time.perf_counter()
        conn = http.client.HTTPConnection("127.0.0.1", host.port, timeout=5)
        conn.request("POST", "/gpio/pulse", body=json.dumps({"handle": host.handle, "pulse_ms": 50}),
                     headers={"Content-Type": "application/json", "X-Trace-Id": "h1"})
        payload = json.loads(conn.getresponse().read())
        elapsed = time.perf_counter() - started
        conn.close()
    finally:
        for sock in sockets:
            sock.close()
    assert payload["ok"] is True
    assert elapsed >= 0.7
    assert payload["host_timing"]["queue_wait_ms"] >= 700
    host.tracer.flush()
    received = [row for row in _rows(host.trace_dir)
                if row.get("trace") == "h1" and row["stage"] == "host.gpio.request_received"]
    assert received and received[0]["queue_wait_ms"] >= 700
    assert hvx_sdk.HOST_METRICS.snapshot()["histograms_ms"]["http.connection_queue_wait"]["max"] >= 700


def test_native_event_carries_capture_clock_and_drain_age(host):
    host.dll.emit_plate(host.handle, "T123ABC")
    time.sleep(0.05)
    status, _, body = _get(host.port, f"/events/{host.handle}")
    events = json.loads(body)["events"]
    assert status == 200 and len(events) == 1
    event = events[0]
    assert event["plate"] == "T123ABC" and event["capture_token"]
    age = latency_trace.age_ms_from_perf(event["captured_perf_ns"])
    assert 40 <= age < 2000
    status, _, jpeg = _get(host.port, f"/event-jpeg/{host.handle}?capture_token={event['capture_token']}")
    assert status == 200 and jpeg[:2] == b"\xff\xd8"
    host.tracer.flush()
    drained = [row for row in _rows(host.trace_dir) if row["stage"] == "host.event.drained"]
    assert drained and drained[0]["capture_token"] == event["capture_token"] and drained[0]["age_ms"] >= 40


def test_fake_sdk_mode_is_selected_by_flag(monkeypatch, tmp_path):
    assert hvx_host.fake_sdk_requested(["hvx_host.py", "--fake-sdk"]) is True
    monkeypatch.delenv("SMARTPARK_HVX_FAKE_SDK", raising=False)
    assert hvx_host.fake_sdk_requested(["hvx_host.py"]) is False
    sdk = hvx_host.create_sdk(fake=True)
    try:
        assert sdk.fake_sdk is True and hasattr(sdk, "fake_dll")
    finally:
        sdk.close()


def test_endpoint_keys_do_not_explode_per_handle():
    assert hvx_host._endpoint_key("GET", "/live-jpeg/12") == "GET /live-jpeg"
    assert hvx_host._endpoint_key("POST", "/gpio/pulse") == "POST /gpio/pulse"
    assert hvx_host._endpoint_key("GET", "/gpio/3") == "GET /gpio"
    assert hvx_host._endpoint_key("GET", "/") == "GET /"


def test_gate_controller_traces_each_actuator_in_order(host, monkeypatch):
    """Each actuator is traced; the GPIO call includes the relay hold.

    The Board relay now runs alongside the camera relay (it used to start only
    after the GPIO call returned, adding its full timeout to every open).
    """
    from app.services import gates

    monkeypatch.setattr(gates.settings, "hvx_host_url", host.url)
    monkeypatch.setattr(gates.settings, "gpio_pulse_ms", 120)
    camera = SimpleNamespace(id=5, name="Entry cam", enabled=True, lane_direction="ENTRY", ip_address="10.0.0.5",
                             sdk_handle=host.handle, controller_ip="", display_ip="")
    gate = SimpleNamespace(name="Lane 1")

    async def open_gate():
        with latency_trace.trace_context("cmd-gate"):
            return await gates.PhysicalGateController().open(gate, [camera], "test", side="ENTRY")

    result = asyncio.run(open_gate())
    assert result.ok is True
    host.tracer.flush()
    rows = [row for row in _rows(host.trace_dir) if row.get("trace") == "cmd-gate"]
    stages = [row["stage"] for row in rows]
    assert stages.index("gate.open_start") < stages.index("gate.http_sent") < stages.index("gate.actuators")
    actuators = next(row for row in rows if row["stage"] == "gate.actuators")
    assert actuators["gpio_ms"] >= 120  # includes the relay hold
    assert next(row for row in rows if row["stage"] == "gate.open_result")["ok"] is True


@pytest.fixture
def host10(tmp_path, monkeypatch):
    """Same host, camera at 10 fps like the QY sub-streams on SERVER01."""
    monkeypatch.setenv("SMARTPARK_LATENCY_TRACE_FRAME_EVERY", "1")
    tracer = latency_trace.configure("hvx-host", tmp_path, enabled=True)
    sdk, dll = fake_hvx_sdk.make_sdk_and_dll(hvx_sdk.HVXSDK, tmp_path, fps=10, width=320, height=180)
    monkeypatch.setattr(hvx_host, "sdk", sdk)
    server = hvx_host.BoundedHTTPServer(("127.0.0.1", 0), hvx_host.Handler, max_workers=4, max_pending=8)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    handle = sdk.add_and_connect("10.0.0.6", 30000, 3, "", "")["handle"]
    yield SimpleNamespace(sdk=sdk, port=server.server_address[1], handle=handle, tracer=tracer, trace_dir=tmp_path)
    server.shutdown()
    server.server_close()
    sdk.close()
    tracer.close()
    monkeypatch.setattr(latency_trace, "_tracer", None)


def test_each_camera_frame_is_encoded_on_arrival_and_none_is_skipped(host10):
    """The encoder used to tick on its own 15/s timer: 0-70 ms added per frame
    and a skipped frame whenever two callbacks fell between ticks."""
    after, seqs = 0, []
    status, headers, _ = _get(host10.port, f"/live-jpeg/{host10.handle}?after=0&wait_ms=2000")
    after = int(headers["X-Frame-Seq"])
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        status, headers, body = _get(host10.port, f"/live-jpeg/{host10.handle}?after={after}&wait_ms=1500")
        assert status == 200 and body[:2] == b"\xff\xd8"
        after = int(headers["X-Frame-Seq"])
        seqs.append(after)
    steps = [b - a for a, b in zip(seqs, seqs[1:])]
    assert len(seqs) >= 20                                  # ~10 fps for 3 s
    assert sum(1 for step in steps if step > 1) <= 1, steps  # no frame dropped between camera and viewer
    host10.tracer.flush()
    stored = sorted(row["callback_to_stored_ms"] for row in _rows(host10.trace_dir)
                    if row.get("stage") == "host.frame.stored")
    print("callback->stored ms p50", stored[len(stored) // 2], "max", stored[-1], "skips", sum(1 for s in steps if s > 1))
    assert stored and stored[len(stored) // 2] < 25, stored  # encoded on arrival (was ~37 ms median)
