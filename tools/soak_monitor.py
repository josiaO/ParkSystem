"""72-hour soak monitor for a 4-camera site (Phase 6.7). Standard library only.

Samples the Site Service and the PC every --interval seconds for --hours and
writes one JSON line per sample, then a PASS/FAIL summary:

* memory growth (MB/hour) per process: Site Service, Recognition Worker,
  Media Service, MediaMTX, FFmpeg decoders, HVX SDK host;
* decoder restarts and reconnects per camera;
* frame age at recognition (p95) per camera;
* gate command latency and failures;
* watchdog problems, and database link outages.

It only reads (/health/*, process lists); it never opens a gate. Stop it
early with Ctrl+C: the summary is still written.

    python -m tools.soak_monitor --hours 72 --out C:\\ProgramData\\SmartParkEdge\\soak
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROLES = {
    "app.site_service": "site_service",
    "app.recognition_worker": "recognition_worker",
    "app.media_service": "media_service",
    "hvx_host.py": "hvx_host",
    "mediamtx": "mediamtx",
    "ffmpeg": "ffmpeg",
}

THRESHOLDS = {
    "memory_growth_mb_per_hour": 5.0,     # per process role, after a 1 h warm-up
    "decoder_restarts_per_day": 3.0,       # per camera
    "frame_age_p95_ms": 300.0,             # median of the per-sample p95
    "gate_latency_ms": 1000.0,             # average command latency
}


# --- collection ---------------------------------------------------------------

def _role(command: str) -> str | None:
    text = (command or "").replace("\\", "/").lower()
    for marker, role in ROLES.items():
        if marker.lower() in text:
            return role
    return None


def process_memory() -> dict[str, dict[str, float]]:
    """Resident memory (MB) and count per SmartPark process role."""
    rows: list[tuple[str, float]] = []
    if os.name == "nt":
        script = ("Get-CimInstance Win32_Process | Select-Object CommandLine,Name,WorkingSetSize | "
                  "ConvertTo-Json -Compress")
        try:
            out = subprocess.run(["powershell.exe", "-NoProfile", "-Command", script],
                                 capture_output=True, text=True, timeout=30).stdout
            for item in json.loads(out or "[]"):
                role = _role(str(item.get("CommandLine") or item.get("Name") or ""))
                if role:
                    rows.append((role, float(item.get("WorkingSetSize") or 0) / 1e6))
        except (OSError, subprocess.TimeoutExpired, ValueError):
            pass
    else:
        for proc in Path("/proc").glob("[0-9]*"):
            try:
                command = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="ignore")
                role = _role(command)
                if not role:
                    continue
                for line in (proc / "status").read_text().splitlines():
                    if line.startswith("VmRSS:"):
                        rows.append((role, float(line.split()[1]) / 1000))
            except OSError:
                continue
    out: dict[str, dict[str, float]] = {}
    for role, mb in rows:
        entry = out.setdefault(role, {"mb": 0.0, "count": 0})
        entry["mb"] = round(entry["mb"] + mb, 1)
        entry["count"] += 1
    return out


def extract_sample(details: dict, live: dict, processes: dict, *, at: float) -> dict[str, Any]:
    """Flatten the figures the soak needs from one /health/details + /health/live."""
    cameras: dict[str, dict[str, Any]] = {}
    for lane in ((details.get("recognition_worker") or {}).get("cameras") or []):
        if not isinstance(lane, dict):
            continue
        cid = str(lane.get("camera_id") or lane.get("id") or "")
        cameras[cid] = {
            "frame_age_p95_ms": lane.get("frame_age_at_consumption_ms_p95"),
            "decoder_restarts": int(lane.get("decoder_restarts") or lane.get("reconnects") or 0),
            "dropped_ai_frames": int(lane.get("dropped_ai_frames") or 0),
            "inference_p95_ms": lane.get("inference_ms_p95"),
        }
    for lane in ((details.get("recognition_runtime") or {}).get("cameras") or []):
        if isinstance(lane, dict):
            cid = str(lane.get("camera_id") or "")
            row = cameras.setdefault(cid, {"decoder_restarts": 0})
            row.setdefault("frame_age_p95_ms", lane.get("frame_age_at_consumption_ms_p95"))
            row["recognition_restarts"] = int(lane.get("recognition_restarts") or 0)
    process = details.get("process") or {}
    gates = details.get("gates") or {}
    watchdog = details.get("watchdog") or {}
    link = (live or {}).get("db_link") or {}
    return {
        "at": at,
        "time": datetime.fromtimestamp(at, timezone.utc).isoformat(),
        "site_service_rss_mb": round(float(process.get("rss_bytes") or 0) / 1e6, 1),
        "site_service_threads": process.get("thread_count"),
        "site_service_restarts": process.get("restart_count"),
        "worker_ram_mb": round(float(((details.get("recognition_worker") or {}).get("resources") or {}).get("ram_bytes") or 0) / 1e6, 1),
        "processes": processes,
        "cameras": cameras,
        "gate_ok": int(gates.get("ok") or 0),
        "gate_failed": int(gates.get("failed") or 0),
        "gate_avg_latency_ms": gates.get("avg_latency_ms"),
        "watchdog_problems": len(watchdog.get("problems") or []),
        "db_link": str(link.get("state") or "UNKNOWN"),
    }


# --- analysis -----------------------------------------------------------------

def _slope_per_hour(points: list[tuple[float, float]]) -> float | None:
    if len(points) < 3:
        return None
    xs = [p[0] / 3600.0 for p in points]
    ys = [p[1] for p in points]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    return round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den, 2)


def summarize(samples: list[dict], *, warmup_seconds: float = 3600.0) -> dict[str, Any]:
    if not samples:
        return {"verdict": "NO DATA", "checks": {}}
    start = samples[0]["at"]
    hours = (samples[-1]["at"] - start) / 3600.0
    steady = [s for s in samples if s["at"] - start >= warmup_seconds] or samples
    memory: dict[str, float | None] = {}
    roles = {role for s in steady for role in (s.get("processes") or {})}
    for role in sorted(roles):
        memory[role] = _slope_per_hour([(s["at"] - start, s["processes"][role]["mb"]) for s in steady if role in (s.get("processes") or {})])
    memory["site_service(api)"] = _slope_per_hour([(s["at"] - start, s["site_service_rss_mb"]) for s in steady if s.get("site_service_rss_mb")])
    cameras: dict[str, dict[str, Any]] = {}
    for cid in sorted({cid for s in samples for cid in (s.get("cameras") or {})}):
        series = [s["cameras"][cid] for s in samples if cid in (s.get("cameras") or {})]
        restarts = max(0, series[-1].get("decoder_restarts", 0) - series[0].get("decoder_restarts", 0))
        ages = [row["frame_age_p95_ms"] for row in series if row.get("frame_age_p95_ms") is not None]
        cameras[cid] = {
            "decoder_restarts": restarts,
            "decoder_restarts_per_day": round(restarts / max(hours / 24.0, 1 / 24.0), 2),
            "frame_age_p95_ms_median": round(statistics.median(ages), 1) if ages else None,
            "frame_age_p95_ms_max": round(max(ages), 1) if ages else None,
        }
    latencies = [s["gate_avg_latency_ms"] for s in samples if s.get("gate_avg_latency_ms") is not None]
    interval = statistics.median([b["at"] - a["at"] for a, b in zip(samples, samples[1:])]) if len(samples) > 1 else 0
    link_down_seconds = round(sum(interval for s in samples if s.get("db_link") == "DOWN"), 1)
    checks = {
        "memory_growth": all(v is None or v <= THRESHOLDS["memory_growth_mb_per_hour"] for v in memory.values()),
        "decoder_restarts": all(c["decoder_restarts_per_day"] <= THRESHOLDS["decoder_restarts_per_day"] for c in cameras.values()),
        "frame_age": all(c["frame_age_p95_ms_median"] is None or c["frame_age_p95_ms_median"] <= THRESHOLDS["frame_age_p95_ms"] for c in cameras.values()),
        "gate_latency": (statistics.mean(latencies) <= THRESHOLDS["gate_latency_ms"]) if latencies else True,
        "gate_failures": samples[-1].get("gate_failed", 0) - samples[0].get("gate_failed", 0) == 0,
        "database_link": link_down_seconds == 0,
    }
    return {
        "verdict": "PASS" if all(checks.values()) else "FAIL",
        "hours": round(hours, 2),
        "samples": len(samples),
        "checks": checks,
        "thresholds": THRESHOLDS,
        "memory_growth_mb_per_hour": memory,
        "cameras": cameras,
        "gate_avg_latency_ms": round(statistics.mean(latencies), 1) if latencies else None,
        "gate_avg_latency_ms_max": round(max(latencies), 1) if latencies else None,
        "gate_commands_failed": samples[-1].get("gate_failed", 0) - samples[0].get("gate_failed", 0),
        "watchdog_problem_samples": sum(1 for s in samples if s.get("watchdog_problems")),
        "database_link_down_seconds": link_down_seconds,
    }


def summary_markdown(summary: dict) -> str:
    lines = [f"# Soak result: {summary['verdict']}", "",
             f"{summary.get('hours')} h, {summary.get('samples')} samples", "", "| Check | Result |", "|---|---|"]
    for name, ok in (summary.get("checks") or {}).items():
        lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} |")
    lines += ["", "## Memory growth (MB/hour, after warm-up)", ""]
    for role, slope in (summary.get("memory_growth_mb_per_hour") or {}).items():
        lines.append(f"- {role}: {slope}")
    lines += ["", "## Cameras", "", "| Camera | Decoder restarts | per day | Frame age p95 median / max (ms) |", "|---|---|---|---|"]
    for cid, row in (summary.get("cameras") or {}).items():
        lines.append(f"| {cid} | {row['decoder_restarts']} | {row['decoder_restarts_per_day']} | {row['frame_age_p95_ms_median']} / {row['frame_age_p95_ms_max']} |")
    lines += ["", f"Gate latency avg {summary.get('gate_avg_latency_ms')} ms (max sample {summary.get('gate_avg_latency_ms_max')} ms), "
              f"failed commands {summary.get('gate_commands_failed')}.",
              f"Watchdog problem samples: {summary.get('watchdog_problem_samples')}. "
              f"Database link down: {summary.get('database_link_down_seconds')} s."]
    return "\n".join(lines) + "\n"


# --- main -------------------------------------------------------------------

def _get(url: str, token: str = "", timeout: float = 10.0) -> dict:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"} if token else {})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    from tools.field_acceptance_test import _try_login, password_candidates

    parser = argparse.ArgumentParser(description="SmartPark 72-hour soak monitor (read-only)")
    parser.add_argument("--url", default="http://127.0.0.1:8760")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="")
    parser.add_argument("--hours", type=float, default=72.0)
    parser.add_argument("--interval", type=float, default=60.0)
    parser.add_argument("--out", default="soak-results")
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    samples_path = out / "samples.jsonl"
    token, error = _try_login(args.url, args.username, password_candidates(args.password))
    if not token:
        print(f"Sign-in failed: {error}")
        return 2
    samples: list[dict] = []
    end = time.time() + args.hours * 3600
    print(f"Soak started; {args.hours} h, every {args.interval:.0f} s. Samples: {samples_path}")
    try:
        while time.time() < end:
            at = time.time()
            try:
                details = _get(f"{args.url}/health/details", token)
                live = _get(f"{args.url}/health/live")
            except urllib.error.HTTPError as exc:
                if exc.code == 401:
                    token, _ = _try_login(args.url, args.username, password_candidates(args.password))
                details, live = {}, {"db_link": {"state": f"HTTP {exc.code}"}}
            except (urllib.error.URLError, OSError, ValueError) as exc:
                details, live = {}, {"db_link": {"state": f"UNREACHABLE: {str(exc)[:60]}"}}
            sample = extract_sample(details, live, process_memory(), at=at)
            samples.append(sample)
            with samples_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(sample) + "\n")
            time.sleep(max(1.0, args.interval - (time.time() - at)))
    except KeyboardInterrupt:
        print("Stopped early; writing the summary.")
    summary = summarize(samples)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "summary.md").write_text(summary_markdown(summary), encoding="utf-8")
    print(summary_markdown(summary))
    return 0 if summary["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
