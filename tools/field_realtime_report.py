"""Windows-friendly field report for the four-camera live/recognition path.

Sample GET /health/realtime for several minutes and print a per-camera summary.
Does not require cloud services.

Usage (from an operator/admin shell on the site PC):

    python tools\\field_realtime_report.py
    python tools\\field_realtime_report.py --minutes 8 --url http://127.0.0.1:8760

The process prints a final table. It never stores camera passwords.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request


def _login(base: str, username: str, password: str) -> str:
    req = urllib.request.Request(
        f"{base.rstrip('/')}/auth/login",
        data=json.dumps({"username": username, "password": password}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=8) as res:
        body = json.loads(res.read().decode("utf-8"))
    token = body.get("access_token") or body.get("token") or ""
    if not token:
        raise RuntimeError("Login succeeded but no access token was returned")
    return token


def _get(base: str, path: str, token: str) -> dict:
    req = urllib.request.Request(
        f"{base.rstrip('/')}{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=8) as res:
        return json.loads(res.read().decode("utf-8"))


def _summarize(samples: list[dict], *, interval: float = 5.0) -> dict:
    by_cam: dict[int, dict] = {}
    for snap in samples:
        for row in snap.get("cameras") or []:
            cid = int(row.get("camera_id") or 0)
            bucket = by_cam.setdefault(cid, {
                "camera_id": cid,
                "camera_name": row.get("camera_name"),
                "live_providers": [],
                "frame_ages": [],
                "ai_ages": [],
                "fps": [],
                "frame_seq": [],
                "infer_p50": [],
                "infer_p95": [],
                "infer_max": [],
                "dropped": [],
                "stalls": [],
                "restarts": [],
                "native": [],
                "software": [],
                "published": [],
                "duplicates": [],
                "sessions": [],
                "reconnects": [],
                "states": [],
                "plates": [],
            })
            if row.get("live_provider"):
                bucket["live_providers"].append(row["live_provider"])
            if row.get("estimated_frame_age_ms") is not None:
                bucket["frame_ages"].append(float(row["estimated_frame_age_ms"]))
            if row.get("ai_frame_age_ms") is not None:
                bucket["ai_ages"].append(float(row["ai_frame_age_ms"]))
            if row.get("fps") is not None:
                bucket["fps"].append(float(row["fps"]))
            if row.get("frame_seq") is not None:
                bucket["frame_seq"].append(int(row["frame_seq"]))
            for key, dest in (
                ("inference_ms_p50", "infer_p50"),
                ("inference_ms_p95", "infer_p95"),
                ("inference_ms_max", "infer_max"),
                ("dropped_ai_frames", "dropped"),
                ("recognition_stalls", "stalls"),
                ("recognition_restarts", "restarts"),
                ("native_events_received", "native"),
                ("software_reads", "software"),
                ("published_events", "published"),
                ("duplicate_events_suppressed", "duplicates"),
                ("sessions_created", "sessions"),
                ("reconnects", "reconnects"),
            ):
                if row.get(key) is not None:
                    bucket[dest].append(float(row[key]))
            bucket["states"].append(str(row.get("recognition_state") or ""))
            if row.get("last_plate"):
                bucket["plates"].append(str(row["last_plate"]))
    report = {}
    for cid, bucket in by_cam.items():
        ages = bucket["frame_ages"]
        ai_ages = bucket["ai_ages"]
        fps_samples = bucket["fps"]
        seqs = bucket["frame_seq"]
        seq_fps = None
        if len(seqs) >= 2 and len(samples) >= 2:
            elapsed = max(1.0, float(len(samples) - 1) * float(interval))
            seq_fps = round(max(0, seqs[-1] - seqs[0]) / elapsed, 2)
        software = int(bucket["software"][-1]) if bucket["software"] else 0
        native = int(bucket["native"][-1]) if bucket["native"] else 0
        report[cid] = {
            "camera_id": cid,
            "camera_name": bucket["camera_name"],
            "live_provider": bucket["live_providers"][-1] if bucket["live_providers"] else "OFFLINE",
            "live_provider_seen": sorted(set(bucket["live_providers"])),
            "fps": round(statistics.median(fps_samples), 2) if fps_samples else seq_fps,
            "frame_rate_from_seq": seq_fps,
            "frame_age_ms_p50": round(statistics.median(ages), 1) if ages else None,
            "frame_age_ms_p95": round(sorted(ages)[max(0, int(len(ages) * 0.95) - 1)], 1) if ages else None,
            "frame_age_ms_max": round(max(ages), 1) if ages else None,
            "ai_frame_age_ms_p50": round(statistics.median(ai_ages), 1) if ai_ages else None,
            "inference_ms_p50": bucket["infer_p50"][-1] if bucket["infer_p50"] else None,
            "inference_ms_p95": bucket["infer_p95"][-1] if bucket["infer_p95"] else None,
            "inference_ms_max": bucket["infer_max"][-1] if bucket["infer_max"] else None,
            "recognition_throughput": software + native,
            "dropped_ai_frames": int(bucket["dropped"][-1]) if bucket["dropped"] else 0,
            "recognition_stalls": int(bucket["stalls"][-1]) if bucket["stalls"] else 0,
            "recognition_restarts": int(bucket["restarts"][-1]) if bucket["restarts"] else 0,
            "native_events_received": native,
            "software_reads": software,
            "published_events": int(bucket["published"][-1]) if bucket["published"] else 0,
            "duplicate_events_suppressed": int(bucket["duplicates"][-1]) if bucket["duplicates"] else 0,
            "sessions_created": int(bucket["sessions"][-1]) if bucket["sessions"] else 0,
            "reconnects": int(bucket["reconnects"][-1]) if bucket["reconnects"] else 0,
            "recognition_states": sorted(set(bucket["states"])),
            "current_plates_seen": sorted(set(bucket["plates"])),
        }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sample SmartPark realtime diagnostics on the site PC.")
    parser.add_argument("--url", default="http://127.0.0.1:8760", help="Site Service base URL")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--minutes", type=float, default=8.0)
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args(argv)
    try:
        token = _login(args.url, args.username, args.password)
    except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError) as exc:
        print(f"Could not log in to {args.url}: {exc}", file=sys.stderr)
        return 2
    deadline = time.time() + max(30.0, float(args.minutes) * 60.0)
    samples: list[dict] = []
    print(f"Sampling {args.url}/health/realtime for {args.minutes} minutes…")
    while time.time() < deadline:
        try:
            samples.append(_get(args.url, "/health/realtime", token))
            print(f"  sample {len(samples)} ok ({len((samples[-1].get('cameras') or []))} cameras)")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            print(f"  sample failed: {exc}", file=sys.stderr)
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        time.sleep(min(float(args.interval), remaining))
    report = _summarize(samples, interval=float(args.interval))
    print(json.dumps({"samples": len(samples), "cameras": list(report.values())}, indent=2))
    print()
    print("Targets: live frame age < 500 ms; AI age < 1000 ms; pending queue <= 1;")
    print("one stalled camera must not stop the others; empty lane must not keep a plate.")
    print("This report does not prove the physical site is healthy by itself — compare it to cars you saw.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
