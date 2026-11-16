"""Summarise SmartPark latency traces (latency-trace-*.jsonl).

Usage::

    python tools/latency_report.py <folder or files> [--json report.json] [--worst 10]

Reads every ``latency-trace-*.jsonl`` (and rotated ``.jsonl.N``) under the
given folders. Standard library only, so it runs on Ubuntu and on the
Windows PC with either bundled Python.

Sections:

1. Stage table: for every stage and every numeric ``*_ms`` field, per camera
   (and per endpoint for HTTP), count / p50 / p95 / p99 / max.
2. Gate commands: one row per trace id, from command creation to the camera
   relay closing, split into app, HTTP queue, host and SDK time.
3. Stale: decisions, native events and frames flagged older than the limit.
4. Worst N: for the headline metrics, the worst events with their full trace
   (every record that shares the trace id or visit id), in clock order.

If the capture driver recorded phases (``capture.phase_start`` /
``capture.phase_end``), every table is split by phase.

All cross-process arithmetic uses ``perf_ns`` (QueryPerformanceCounter on
Windows, CLOCK_MONOTONIC on Linux), which is shared by processes on one PC.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

NO_PHASE = "-"

# (label, stage, field) — the numbers that answer the three symptoms.
HEADLINE = [
    ("boom: command -> relay on", "gate.span", "command_to_relay_on_ms"),
    ("boom: host queue wait", "host.gpio.request_received", "queue_wait_ms"),
    ("boom: client round trip", "gate.http_received", "round_trip_ms"),
    ("recognition: decision source age", "decision.source_age", "age_ms"),
    ("recognition: native event age", "recognition.native_event", "age_after_media_ms"),
    ("display: frame age at client", "frame.received", "age_ms"),
    ("display: frame age at host serve", "host.frame.served", "age_ms"),
    ("host: scheduling stall", "host.heartbeat.stall", "lag_ms"),
]


def percentile(values, pct):
    values = sorted(values)
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    rank = (len(values) - 1) * pct / 100.0
    low = int(rank)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (rank - low)


def summarise(values) -> dict:
    return {
        "count": len(values),
        "p50": _round(percentile(values, 50)),
        "p95": _round(percentile(values, 95)),
        "p99": _round(percentile(values, 99)),
        "max": _round(max(values)) if values else None,
    }


def _round(value):
    return None if value is None else round(float(value), 1)


def find_files(inputs) -> list[Path]:
    files: list[Path] = []
    for item in inputs:
        path = Path(item)
        if path.is_dir():
            # Run-LatencyCapture.ps1 prefixes copied files with their source folder.
            for pattern in ("**/*latency-trace-*.jsonl", "**/*latency-trace-*.jsonl.*"):
                files.extend(Path(p) for p in glob.glob(str(path / pattern), recursive=True))
        elif path.is_file():
            files.append(path)
        else:
            files.extend(Path(p) for p in glob.glob(str(item)))
    return sorted(set(files))


def load(files) -> tuple[list[dict], int]:
    rows, bad = [], 0
    for path in files:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    bad += 1  # a line cut by a crash or a copy mid-write
                    continue
                if isinstance(row, dict) and "stage" in row:
                    rows.append(row)
    rows.sort(key=lambda r: (int(r.get("perf_ns") or 0), r.get("proc", "")))
    return rows, bad


def assign_phases(rows) -> None:
    """Label each record with the capture phase whose perf window contains it."""
    windows = []
    open_phases = {}
    for row in rows:
        if row["stage"] == "capture.phase_start":
            open_phases[row.get("phase")] = int(row["perf_ns"])
        elif row["stage"] == "capture.phase_end" and row.get("phase") in open_phases:
            windows.append((open_phases.pop(row["phase"]), int(row["perf_ns"]), row["phase"]))
    for name, start in open_phases.items():
        windows.append((start, 1 << 62, name))
    windows.sort()
    for row in rows:
        stamp = int(row.get("perf_ns") or 0)
        row["_phase"] = NO_PHASE
        for start, end, name in windows:
            if start <= stamp <= end:
                row["_phase"] = name
                break


def group_of(row) -> str:
    camera = row.get("camera")
    group = f"cam {camera}" if camera is not None else "all"
    if row.get("endpoint"):
        group += f" {row['endpoint']}"
    if row.get("at_stage"):
        group += f" @{row['at_stage']}"
    return group


def gate_spans(rows) -> list[dict]:
    """Rebuild each boom command from the records that share its trace id."""
    by_trace = defaultdict(list)
    for row in rows:
        if row.get("trace") and (row["stage"].startswith("gate.") or row["stage"].startswith("host.gpio.")):
            by_trace[row["trace"]].append(row)
    spans = []
    for trace, items in by_trace.items():
        first = {}
        for row in items:
            first.setdefault(row["stage"], row)
        start = first.get("gate.command_created") or first.get("gate.open_start") or first.get("gate.http_sent")
        relay = first.get("host.gpio.relay_on")
        if start is None:
            continue

        def ms(a, b):
            if a is None or b is None:
                return None
            return round((int(b["perf_ns"]) - int(a["perf_ns"])) / 1e6, 1)

        received = first.get("gate.http_received") or {}
        result = first.get("gate.open_result") or {}
        actuators = first.get("gate.actuators") or {}
        spans.append({
            "stage": "gate.span",
            "trace": trace,
            "perf_ns": start["perf_ns"],
            "ts": start.get("ts"),
            "camera": (relay or received or {}).get("camera"),
            "_phase": start.get("_phase", NO_PHASE),
            "phase": start.get("_phase", NO_PHASE),
            "command_to_http_sent_ms": ms(start, first.get("gate.http_sent")),
            "http_sent_to_host_received_ms": ms(first.get("gate.http_sent"), first.get("host.gpio.request_received")),
            "host_queue_wait_ms": (first.get("host.gpio.request_received") or {}).get("queue_wait_ms"),
            "host_received_to_sdk_start_ms": ms(first.get("host.gpio.request_received"), first.get("host.gpio.sdk_start")),
            "sdk_start_to_relay_on_ms": ms(first.get("host.gpio.sdk_start"), relay),
            "command_to_relay_on_ms": ms(start, relay),
            "relay_on_to_response_ms": ms(relay, first.get("gate.http_received")),
            "round_trip_ms": received.get("round_trip_ms"),
            "board_after_open_ms": actuators.get("board_started_after_open_ms") if actuators.get("board_configured") else None,
            "command_to_result_ms": ms(start, first.get("gate.open_result")),
            "ok": result.get("ok", received.get("ok")),
            "relay_seen": relay is not None,
        })
    spans.sort(key=lambda s: int(s["perf_ns"]))
    return spans


def stage_table(rows) -> dict:
    table = defaultdict(list)
    for row in rows:
        for key, value in row.items():
            if not key.endswith("_ms") or isinstance(value, bool):
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            table[(row.get("_phase", NO_PHASE), row["stage"], key, group_of(row))].append(number)
    return {key: summarise(values) for key, values in table.items()}


def stale_table(rows) -> dict:
    counts = defaultdict(lambda: [0, 0])
    for row in rows:
        if "stale" not in row or row["stale"] is None:
            continue
        key = (row.get("_phase", NO_PHASE), row["stage"], group_of(row))
        counts[key][0] += 1
        counts[key][1] += 1 if row["stale"] else 0
    return {key: {"checked": total, "stale": stale} for key, (total, stale) in counts.items()}


def related(rows, row) -> list[dict]:
    keys = {(k, row.get(k)) for k in ("trace", "visit_id", "capture_token") if row.get(k)}
    if not keys:
        return [row]
    return [r for r in rows if any(r.get(k) == v for k, v in keys)] or [row]


def worst(rows, spans, count: int) -> list[dict]:
    pool = rows + spans
    out = []
    for label, stage, field in HEADLINE:
        candidates = [r for r in pool if r["stage"] == stage and isinstance(r.get(field), (int, float))
                      and not isinstance(r.get(field), bool)]
        candidates.sort(key=lambda r: float(r[field]), reverse=True)
        items = []
        for row in candidates[:count]:
            items.append({
                "value_ms": _round(row[field]),
                "row": _public(row),
                "trace": [_public(r) for r in related(rows, row)],
            })
        out.append({"label": label, "stage": stage, "field": field, "events": items})
    return out


def _public(row) -> dict:
    return {k: v for k, v in row.items() if not k.startswith("_")}


def build_report(inputs, worst_count: int = 10) -> dict:
    files = find_files(inputs)
    rows, bad = load(files)
    assign_phases(rows)
    spans = gate_spans(rows)
    table = stage_table(rows + spans)
    phases = sorted({row.get("_phase", NO_PHASE) for row in rows})
    return {
        "files": [str(f) for f in files],
        "records": len(rows),
        "unreadable_lines": bad,
        "phases": phases,
        "processes": sorted({row.get("proc", "?") for row in rows}),
        "stages": [
            {"phase": phase, "stage": stage, "field": field, "group": group, **summary}
            for (phase, stage, field, group), summary in sorted(table.items())
        ],
        "gate_commands": [_public(span) for span in spans],
        "stale": [
            {"phase": phase, "stage": stage, "group": group, **counts}
            for (phase, stage, group), counts in sorted(stale_table(rows).items())
        ],
        "worst": worst(rows, spans, worst_count),
    }


def _fmt(value) -> str:
    return "-" if value is None else (f"{value:.1f}" if isinstance(value, float) else str(value))


def render_text(report: dict, out=sys.stdout, worst_trace_lines: int = 40) -> None:
    w = out.write
    w(f"Latency report: {report['records']} records from {len(report['files'])} file(s)")
    w(f", processes: {', '.join(report['processes']) or '-'}\n")
    if report["unreadable_lines"]:
        w(f"  {report['unreadable_lines']} unreadable line(s) skipped\n")
    if not report["records"]:
        w("No records. Is SMARTPARK_LATENCY_TRACE=0, or is this the wrong folder?\n")
        return

    w("\n== 1. Stages (ms) ==\n")
    header = f"{'phase':<14} {'stage':<34} {'field':<34} {'group':<26} {'count':>6} {'p50':>9} {'p95':>9} {'p99':>9} {'max':>9}\n"
    w(header)
    for row in report["stages"]:
        w(f"{row['phase'][:14]:<14} {row['stage'][:34]:<34} {row['field'][:34]:<34} {row['group'][:26]:<26} "
          f"{row['count']:>6} {_fmt(row['p50']):>9} {_fmt(row['p95']):>9} {_fmt(row['p99']):>9} {_fmt(row['max']):>9}\n")

    w("\n== 2. Boom commands (ms, one row per command) ==\n")
    cols = ["command_to_http_sent_ms", "host_queue_wait_ms", "http_sent_to_host_received_ms",
            "host_received_to_sdk_start_ms", "sdk_start_to_relay_on_ms", "command_to_relay_on_ms",
            "relay_on_to_response_ms", "board_after_open_ms"]
    short = ["cmd>send", "hostQ", "send>host", "host>sdk", "sdk>relay", "CMD>RELAY", "relay>resp", "board+"]
    w(f"{'phase':<14} {'trace':<14} {'cam':>4} {'ok':>5} " + " ".join(f"{s:>10}" for s in short) + "\n")
    for span in report["gate_commands"]:
        w(f"{str(span.get('phase', '-'))[:14]:<14} {str(span['trace'])[:14]:<14} {_fmt(span.get('camera')):>4} "
          f"{_fmt(span.get('ok')):>5} " + " ".join(f"{_fmt(span.get(c)):>10}" for c in cols) + "\n")
    if not report["gate_commands"]:
        w("  (no gate commands in this capture)\n")

    w("\n== 3. Stale checks ==\n")
    if not report["stale"]:
        w("  (no records carry a stale flag)\n")
    for row in report["stale"]:
        w(f"{row['phase'][:14]:<14} {row['stage']:<34} {row['group']:<26} stale {row['stale']} of {row['checked']}\n")

    w("\n== 4. Worst events ==\n")
    for block in report["worst"]:
        if not block["events"]:
            continue
        w(f"\n-- {block['label']} ({block['stage']}.{block['field']}) --\n")
        for index, item in enumerate(block["events"], 1):
            row = item["row"]
            w(f"  #{index} {item['value_ms']} ms  cam={row.get('camera', '-')} trace={row.get('trace', '-')} "
              f"visit={row.get('visit_id', '-')} ts={row.get('ts', '-')}\n")
            trace = item["trace"]
            if len(trace) > 1:
                base = int(trace[0].get("perf_ns") or 0)
                for step in trace[:worst_trace_lines]:
                    offset = (int(step.get("perf_ns") or 0) - base) / 1e6
                    extras = {k: v for k, v in step.items()
                              if k not in {"ts", "perf_ns", "mono_ns", "pid", "stage", "proc", "trace"}}
                    w(f"      +{offset:9.1f} ms  {step.get('proc', '?'):<18} {step['stage']:<32} {json.dumps(extras, default=str)[:160]}\n")
                if len(trace) > worst_trace_lines:
                    w(f"      ... {len(trace) - worst_trace_lines} more\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("inputs", nargs="+", help="trace folders or files")
    parser.add_argument("--json", dest="json_path", help="also write the full report as JSON")
    parser.add_argument("--worst", type=int, default=10, help="worst events per headline metric")
    args = parser.parse_args(argv)
    report = build_report(args.inputs, args.worst)
    render_text(report)
    if args.json_path:
        Path(args.json_path).parent.mkdir(parents=True, exist_ok=True)
        with open(args.json_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=1, default=str)
    return 0 if report["records"] else 1


if __name__ == "__main__":
    sys.exit(main())
