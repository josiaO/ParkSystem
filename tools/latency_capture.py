"""Timed latency capture against a running HVX host (Windows rig or --fake-sdk).

Run by tools/windows/Run-LatencyCapture.ps1; it can also be run directly::

    python tools/latency_capture.py --out <folder> --handle 1 --pulses 5

Phases (each one is marked in the trace so the report splits by phase):

``idle``      no extra live viewers; N boom pulses spaced apart.
``viewers``   V keep-alive live-video viewers per camera (like the desktop
              live panes and a browser), then N boom pulses.
``saturate``  (``--saturate``) enough idle keep-alive connections to occupy
              every host HTTP worker, then N pulses. Upper bound for H1.
``passive``   (``--passive-seconds``) nothing scripted: drive cars through
              with the normal app so recognition and decisions are traced.

Pulses go through the app's own ``HVXHostClient.gpio_pulse`` so client
creation and HTTP cost are measured as in production. They do *not* go
through the parking decision path (that is measured by the passive phase).

Every pulse physically opens the boom. The script asks for confirmation
unless ``--yes`` is given.

Output folder: ``latency-trace-latency-capture.jsonl``, ``viewers.csv``,
``metrics.jsonl``, ``pulses.csv``, ``gpio-input.csv`` (with
``--poll-input``), ``capture.json``.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import http.client
import json
import os
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core import latency_trace  # noqa: E402


def _http_json(base: str, path: str, timeout: float = 5.0):
    url = urlparse(base)
    conn = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=timeout)
    try:
        conn.request("GET", path)
        response = conn.getresponse()
        body = response.read()
        return response.status, (json.loads(body) if body else None)
    finally:
        conn.close()


class Viewer(threading.Thread):
    """One keep-alive live-video client, the same long-poll the app uses."""

    def __init__(self, base: str, handle: int, writer, lock, stop: threading.Event, name: str):
        super().__init__(name=name, daemon=True)
        url = urlparse(base)
        self.host, self.port = url.hostname, url.port or 80
        self.handle = int(handle)
        self.writer, self.lock, self.stop_event = writer, lock, stop
        self.frames = 0
        self.errors = 0

    def run(self) -> None:
        conn = None
        after = 0
        while not self.stop_event.is_set():
            started = time.perf_counter_ns()
            try:
                if conn is None:
                    conn = http.client.HTTPConnection(self.host, self.port, timeout=3.0)
                conn.request("GET", f"/live-jpeg/{self.handle}?after={after}&wait_ms=1000")
                response = conn.getresponse()
                body = response.read()
                done = time.perf_counter_ns()
                seq = int(response.getheader("X-Frame-Seq") or 0)
                captured = response.getheader("X-Frame-Captured-Perf-Ns")
                age = round((done - int(captured)) / 1e6, 2) if captured else ""
                repeated = response.status == 200 and seq <= after
                with self.lock:
                    self.writer.writerow([round(time.time(), 3), done, self.name, self.handle, response.status,
                                          seq, after, len(body), response.getheader("X-Frame-Age-Ms") or "",
                                          age, round((done - started) / 1e6, 2), int(repeated)])
                if response.status == 200:
                    self.frames += 1
                after = max(after, seq)
            except Exception as exc:
                self.errors += 1
                with self.lock:
                    self.writer.writerow([round(time.time(), 3), time.perf_counter_ns(), self.name, self.handle,
                                          f"error:{type(exc).__name__}", "", after, 0, "", "",
                                          round((time.perf_counter_ns() - started) / 1e6, 2), 0])
                if conn is not None:
                    conn.close()
                conn = None
                self.stop_event.wait(0.2)
        if conn is not None:
            conn.close()


class IdleHolder(threading.Thread):
    """Open a keep-alive connection, make one request, then sit idle (holds a host worker)."""

    def __init__(self, base: str, stop: threading.Event):
        super().__init__(daemon=True)
        url = urlparse(base)
        self.host, self.port, self.stop_event = url.hostname, url.port or 80, stop

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                conn = http.client.HTTPConnection(self.host, self.port, timeout=30)
                conn.request("GET", "/info")
                conn.getresponse().read()
                # The host drops an idle keep-alive after its timeout; reopen.
                self.stop_event.wait(9.0)
                conn.close()
            except Exception:
                self.stop_event.wait(0.5)


class MetricsSampler(threading.Thread):
    def __init__(self, base: str, path: Path, stop: threading.Event, interval: float = 2.0):
        super().__init__(daemon=True)
        self.base, self.path, self.stop_event, self.interval = base, path, stop, interval

    def run(self) -> None:
        with open(self.path, "a", encoding="utf-8") as handle:
            while not self.stop_event.is_set():
                try:
                    status, payload = _http_json(self.base, "/metrics", timeout=3.0)
                    handle.write(json.dumps({"ts": time.time(), "perf_ns": time.perf_counter_ns(),
                                             "status": status, "metrics": payload}) + "\n")
                    handle.flush()
                except Exception as exc:
                    handle.write(json.dumps({"ts": time.time(), "error": type(exc).__name__}) + "\n")
                self.stop_event.wait(self.interval)


class InputPoller(threading.Thread):
    """Poll a camera GPIO input (e.g. a boom limit switch) and log value changes."""

    def __init__(self, base: str, handle: int, index: int, path: Path, stop: threading.Event, interval: float = 0.05):
        super().__init__(daemon=True)
        self.base, self.handle, self.index = base, int(handle), int(index)
        self.path, self.stop_event, self.interval = path, stop, interval

    def run(self) -> None:
        last = None
        with open(self.path, "a", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["ts", "perf_ns", "handle", "index", "value", "rc", "read_ms", "changed"])
            while not self.stop_event.is_set():
                started = time.perf_counter_ns()
                try:
                    status, payload = _http_json(self.base, f"/gpio/{self.handle}?index={self.index}", timeout=2.0)
                    value = (payload or {}).get("value")
                    rc = (payload or {}).get("rc")
                except Exception as exc:
                    value, rc = None, type(exc).__name__
                done = time.perf_counter_ns()
                changed = value != last
                writer.writerow([round(time.time(), 3), done, self.handle, self.index, value, rc,
                                 round((done - started) / 1e6, 2), int(changed)])
                if changed:
                    latency_trace.emit("capture.gpio_input_edge", camera=self.handle, index=self.index,
                                       value=value, previous=last)
                    handle.flush()
                last = value
                self.stop_event.wait(self.interval)


def _beep() -> None:
    try:
        import winsound

        winsound.Beep(2000, 80)
    except Exception:
        sys.stdout.write("\a")
        sys.stdout.flush()


async def _pulse(base: str, handle: int, index: int, pulse_ms: int, trace_id: str) -> dict:
    from app.services.hvx_client import HVXHostClient

    with latency_trace.trace_context(trace_id):
        latency_trace.emit("gate.command_created", camera=handle, source="latency_capture")
        try:
            return await HVXHostClient(base).gpio_pulse(handle=handle, index=index, pulse_ms=pulse_ms)
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def run_phase(args, name: str, pulses_writer, stop_all: threading.Event) -> None:
    print(f"\n=== phase {name} ===", flush=True)
    latency_trace.emit("capture.phase_start", phase=name)
    if name == "passive":
        print(f"Passive window {args.passive_seconds}s: drive vehicles through now.", flush=True)
        stop_all.wait(args.passive_seconds)
    else:
        time.sleep(args.settle_seconds)
        for number in range(1, args.pulses + 1):
            trace_id = f"cap-{name}-{number}-{int(time.time())}"
            if args.beep:
                beep_perf = time.perf_counter_ns()
                _beep()
                latency_trace.emit("capture.beep", trace=trace_id, beep_perf_ns=beep_perf)
            sent_wall = time.time()
            started = time.perf_counter_ns()
            result = asyncio.run(_pulse(args.host_url, args.handle, args.index, args.pulse_ms, trace_id))
            done = time.perf_counter_ns()
            timing = result.get("timing") or {}
            relay = timing.get("relay_on_perf_ns")
            relay_ms = round((relay - started) / 1e6, 1) if relay else ""
            pulses_writer.writerow([name, number, trace_id, round(sent_wall, 3),
                                    time.strftime("%H:%M:%S", time.localtime(sent_wall)) + f".{int(sent_wall % 1 * 1000):03d}",
                                    int(bool(result.get("ok"))), relay_ms, round((done - started) / 1e6, 1),
                                    (result.get("host_timing") or {}).get("queue_wait_ms", ""),
                                    result.get("error", "")])
            print(f"  pulse {number}/{args.pulses} at {time.strftime('%H:%M:%S', time.localtime(sent_wall))}"
                  f" ok={bool(result.get('ok'))} relay_on_after={relay_ms} ms round_trip={round((done - started) / 1e6, 1)} ms",
                  flush=True)
            if number < args.pulses and stop_all.wait(args.spacing):
                break
    latency_trace.emit("capture.phase_end", phase=name)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="SmartPark latency capture")
    parser.add_argument("--host-url", default=os.environ.get("SMARTPARK_HVX_HOST_URL", "http://127.0.0.1:8765"))
    parser.add_argument("--out", required=True)
    parser.add_argument("--handle", type=int, help="camera SDK handle wired to the boom (see /info)")
    parser.add_argument("--index", type=int, default=0, help="GPIO relay index (app default 0)")
    parser.add_argument("--pulse-ms", type=int, default=500)
    parser.add_argument("--pulses", type=int, default=5)
    parser.add_argument("--spacing", type=float, default=10.0, help="seconds between pulses (boom must close)")
    parser.add_argument("--viewers", type=int, default=4, help="live viewers per camera in the viewers phase")
    parser.add_argument("--saturate", action="store_true", help="add the worker-saturation phase")
    parser.add_argument("--passive-seconds", type=float, default=0.0)
    parser.add_argument("--settle-seconds", type=float, default=3.0)
    parser.add_argument("--beep", action="store_true", help="beep at each command (phone-video marker)")
    parser.add_argument("--poll-input", type=int, default=None, help="GPIO input index to poll during the run")
    parser.add_argument("--no-pulse", action="store_true", help="viewers and passive only, never open the boom")
    parser.add_argument("--yes", action="store_true", help="do not ask before pulsing the boom")
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    latency_trace.configure("latency-capture", out, enabled=True)

    status, info = _http_json(args.host_url, "/info")
    if status != 200 or not isinstance(info, dict):
        print(f"HVX host not reachable at {args.host_url} (status {status})", file=sys.stderr)
        return 2
    metrics_status, metrics = _http_json(args.host_url, "/metrics")
    if metrics_status != 200:
        print("The HVX host has no /metrics: it is running old code. Restart the SmartParkHvxHost service "
              "after updating the checkout, then run this again.", file=sys.stderr)
        return 3
    cameras = [row for row in info.get("connections") or [] if row.get("handle") is not None]
    handles = sorted({int(row["handle"]) for row in cameras})
    print("Connected cameras:", ", ".join(f"handle {row['handle']} ip {row.get('ip')}" for row in cameras) or "none")
    if not handles:
        print("No connected cameras on the host.", file=sys.stderr)
        return 4
    pulsing = not args.no_pulse and args.pulses > 0
    if pulsing:
        if args.handle is None:
            if len(handles) == 1:
                args.handle = handles[0]
            else:
                print("Several cameras are connected; pass --handle (the camera wired to the boom).", file=sys.stderr)
                return 5
        if args.handle not in handles:
            print(f"Handle {args.handle} is not connected (connected: {handles}).", file=sys.stderr)
            return 5
        if not args.yes:
            ip = next((row.get("ip") for row in cameras if int(row["handle"]) == args.handle), "?")
            answer = input(f"This will OPEN THE BOOM on camera handle {args.handle} ({ip}) "
                           f"{args.pulses} time(s) per phase, {args.spacing:.0f}s apart. Type OPEN to continue: ")
            if answer.strip() != "OPEN":
                print("Cancelled.")
                return 6

    with open(out / "capture.json", "w", encoding="utf-8") as handle:
        json.dump({"started": time.time(), "args": vars(args), "info": info, "metrics_at_start": metrics,
                   "video_status_at_start": {h: _http_json(args.host_url, f"/video-status/{h}")[1] for h in handles}},
                  handle, indent=1, default=str)

    stop_all = threading.Event()
    sampler = MetricsSampler(args.host_url, out / "metrics.jsonl", stop_all)
    sampler.start()
    poller = None
    if args.poll_input is not None and args.handle is not None:
        poller = InputPoller(args.host_url, args.handle, args.poll_input, out / "gpio-input.csv", stop_all)
        poller.start()
    viewers_file = open(out / "viewers.csv", "w", encoding="utf-8", newline="")
    viewers_csv = csv.writer(viewers_file)
    viewers_csv.writerow(["ts", "perf_ns", "viewer", "handle", "status", "seq", "after", "bytes",
                          "host_age_ms", "client_age_ms", "request_ms", "repeated_seq"])
    viewers_lock = threading.Lock()
    pulses_file = open(out / "pulses.csv", "w", encoding="utf-8", newline="")
    pulses_csv = csv.writer(pulses_file)
    pulses_csv.writerow(["phase", "n", "trace", "sent_epoch", "sent_local", "ok", "relay_on_after_ms",
                         "round_trip_ms", "host_queue_wait_ms", "error"])

    viewer_stop = threading.Event()
    holder_stop = threading.Event()
    viewers: list[Viewer] = []
    try:
        phases = ["idle", "viewers"] if pulsing else ["viewers"]
        if pulsing and args.saturate:
            phases.append("saturate")
        if args.passive_seconds > 0:
            phases.append("passive")
        for phase in phases:
            if phase in {"viewers", "saturate", "passive"} and not viewers:
                for camera in handles:
                    for number in range(args.viewers):
                        viewer = Viewer(args.host_url, camera, viewers_csv, viewers_lock, viewer_stop,
                                        name=f"viewer-{camera}-{number}")
                        viewer.start()
                        viewers.append(viewer)
            if phase == "saturate":
                workers = int(((metrics or {}).get("gauges") or {}).get("http.max_workers") or 24)
                for _ in range(max(0, workers - len(viewers))):
                    IdleHolder(args.host_url, holder_stop).start()
            if phase == "passive":
                holder_stop.set()
            if not pulsing and phase == "viewers":
                latency_trace.emit("capture.phase_start", phase=phase)
                stop_all.wait(30.0)
                latency_trace.emit("capture.phase_end", phase=phase)
                continue
            run_phase(args, phase, pulses_csv, stop_all)
            pulses_file.flush()
    except KeyboardInterrupt:
        print("Interrupted; saving what was captured.")
    finally:
        holder_stop.set()
        viewer_stop.set()
        for viewer in viewers:
            viewer.join(3.0)
        stop_all.set()
        sampler.join(5.0)
        if poller is not None:
            poller.join(2.0)
        viewers_file.close()
        pulses_file.close()
        try:
            _, final_metrics = _http_json(args.host_url, "/metrics")
        except Exception:
            final_metrics = None
        with open(out / "capture.json", "r+", encoding="utf-8") as handle:
            data = json.load(handle)
            data.update(finished=time.time(), metrics_at_end=final_metrics,
                        viewers={v.name: {"frames": v.frames, "errors": v.errors} for v in viewers},
                        video_status_at_end={h: _http_json(args.host_url, f"/video-status/{h}")[1] for h in handles})
            handle.seek(0)
            json.dump(data, handle, indent=1, default=str)
            handle.truncate()
        latency_trace.get_tracer().close()
    print(f"\nCapture written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
