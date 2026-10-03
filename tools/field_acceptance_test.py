"""Automated field acceptance test for a live parking site.

Run this on the Windows parking PC while cars use the lanes. It talks only to
the local Site Service. Stdlib only — no extra packages.

Expected behaviour (PASS):
  P1  Site Service answers /health/live
  P2  Database is ready
  P3  Operator login works
  P4  At least one camera is configured
  P5  Configured cameras are SDK_CONNECTED or VIDEO_CONNECTED
  P6  /health/realtime returns per-camera rows
  P7  HVX host answers when this PC is Windows (warn elsewhere)
  S1  Recognition pending queue depth stays <= 1
  S2  Connected cameras are not OFFLINE for the whole soak
  S3  Live frame age p95 < 500 ms (warn), < 2500 ms (fail)
  S4  AI frame age p50 < 1000 ms (warn), < 4000 ms (fail)
  S5  FastALPR software_reads or native events increase while cars pass
  S6  A stall on one camera does not freeze every other camera
  S7  Empty lane (vehicle_present=false) does not keep a plate
  S8  Sessions do not multiply beyond published visits
  S9  Global OCR inflight stays within the scheduler cap
  S10 Optional: published events >= --expected-cars

Usage (installed PC):

    powershell -ExecutionPolicy Bypass -File Run-FieldAcceptanceTest.ps1
    python tools\\field_acceptance_test.py --minutes 8 --expected-cars 6
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"
SKIP = "SKIP"

FRAME_AGE_WARN_MS = 500.0
FRAME_AGE_FAIL_MS = 2500.0
AI_AGE_WARN_MS = 1000.0
AI_AGE_FAIL_MS = 4000.0
QUEUE_MAX = 1
CONNECTED = {"SDK_CONNECTED", "VIDEO_CONNECTED", "CONNECTED"}


def _check(cid: str, title: str, status: str, detail: str) -> dict[str, str]:
    return {"id": cid, "title": title, "status": status, "detail": detail}


def _delta(series: list[float]) -> float:
    if len(series) < 2:
        return float(series[-1]) if series else 0.0
    return float(series[-1] - series[0])


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    idx = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * 0.95))))
    return ordered[idx]


def login(base: str, username: str, password: str) -> str:
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


def get_json(base: str, path: str, token: str | None = None, *, timeout: float = 8.0) -> dict | list:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{base.rstrip('/')}{path}", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


def collect_cameras(samples: list[dict]) -> dict[int, dict[str, Any]]:
    by_cam: dict[int, dict[str, Any]] = {}
    for snap in samples:
        for row in snap.get("cameras") or []:
            cid = int(row.get("camera_id") or 0)
            bucket = by_cam.setdefault(cid, {
                "camera_id": cid,
                "camera_name": row.get("camera_name") or f"camera {cid}",
                "live_providers": [],
                "live_connected": [],
                "frame_ages": [],
                "ai_ages": [],
                "pending": [],
                "dropped": [],
                "stalls": [],
                "restarts": [],
                "native": [],
                "software": [],
                "published": [],
                "duplicates": [],
                "sessions": [],
                "reconnects": [],
                "inflight": [],
                "empty_with_plate": 0,
                "empty_samples": 0,
            })
            if row.get("live_provider"):
                bucket["live_providers"].append(str(row["live_provider"]))
            bucket["live_connected"].append(bool(row.get("live_connected")))
            if row.get("estimated_frame_age_ms") is not None:
                bucket["frame_ages"].append(float(row["estimated_frame_age_ms"]))
            if row.get("ai_frame_age_ms") is not None:
                bucket["ai_ages"].append(float(row["ai_frame_age_ms"]))
            if row.get("pending_queue_depth") is not None:
                bucket["pending"].append(int(row["pending_queue_depth"]))
            bucket["inflight"].append(bool(row.get("recognition_inflight")))
            for key, dest in (
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
            present = bool(row.get("vehicle_present"))
            plate = str(row.get("last_plate") or "").strip()
            if not present:
                bucket["empty_samples"] += 1
                if plate:
                    bucket["empty_with_plate"] += 1
    return by_cam


def evaluate_preflight(
    *,
    live: dict | None,
    ready: dict | None,
    cameras: list | None,
    realtime: dict | None,
    login_ok: bool,
    login_error: str = "",
    windows: bool = False,
) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    if live and live.get("ok"):
        checks.append(_check("P1", "Site Service live", PASS, str(live.get("status") or "live")))
    else:
        checks.append(_check("P1", "Site Service live", FAIL, "GET /health/live failed"))

    if ready and ready.get("ok"):
        db = (ready.get("db") or {}).get("ok")
        checks.append(_check("P2", "Database ready", PASS if db else FAIL, "sqlite/db ping"))
    else:
        checks.append(_check("P2", "Database ready", FAIL, "GET /health/ready failed or not ready"))

    if login_ok:
        checks.append(_check("P3", "Operator login", PASS, "token issued"))
    else:
        checks.append(_check("P3", "Operator login", FAIL, login_error or "login failed"))

    rows = cameras if isinstance(cameras, list) else []
    if rows:
        checks.append(_check("P4", "Cameras configured", PASS if len(rows) >= 1 else FAIL, f"{len(rows)} camera(s)"))
        if len(rows) < 4:
            checks.append(_check("P4b", "Four-camera site", WARN, f"expected 4 lanes, found {len(rows)}"))
        connected = [c for c in rows if str(c.get("status") or "").upper() in CONNECTED]
        checks.append(_check(
            "P5", "Cameras connected",
            PASS if connected else FAIL,
            f"{len(connected)}/{len(rows)} SDK_CONNECTED or VIDEO_CONNECTED",
        ))
    else:
        checks.append(_check("P4", "Cameras configured", FAIL, "Add site cameras then Connect all"))
        checks.append(_check("P5", "Cameras connected", FAIL, "no cameras"))

    rt_cams = (realtime or {}).get("cameras") if isinstance(realtime, dict) else None
    if rt_cams:
        checks.append(_check("P6", "Realtime diagnostics", PASS, f"{len(rt_cams)} realtime rows"))
    else:
        checks.append(_check("P6", "Realtime diagnostics", FAIL, "GET /health/realtime returned no cameras"))

    hvx = (ready or {}).get("hvx_host") or {}
    if hvx.get("ok"):
        checks.append(_check("P7", "HVX host", PASS, "32-bit NetSDK host answering"))
    elif windows and hvx.get("required"):
        checks.append(_check("P7", "HVX host", FAIL, hvx.get("note") or "HVX host not answering"))
    else:
        checks.append(_check("P7", "HVX host", WARN, hvx.get("note") or "HVX host not required on this OS"))
    return checks


def evaluate_soak(
    samples: list[dict],
    *,
    sessions: list | None = None,
    expected_cars: int = 0,
    connected_ids: set[int] | None = None,
) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    if not samples:
        return [_check("S0", "Soak samples", FAIL, "no /health/realtime samples")]

    by_cam = collect_cameras(samples)
    if not by_cam:
        return [_check("S0", "Soak samples", FAIL, "realtime samples had no cameras")]

    queue_max = 0
    for bucket in by_cam.values():
        if bucket["pending"]:
            queue_max = max(queue_max, max(bucket["pending"]))
    checks.append(_check(
        "S1", "Latest-frame queue bounded",
        PASS if queue_max <= QUEUE_MAX else FAIL,
        f"pending_queue_depth max={queue_max} (limit {QUEUE_MAX})",
    ))

    offline_fail = []
    age_fail = []
    age_warn = []
    ai_fail = []
    ai_warn = []
    stale = []
    activity = []
    stalled = []
    live_ok = []
    for cid, bucket in by_cam.items():
        name = bucket["camera_name"]
        providers = bucket["live_providers"]
        last = providers[-1] if providers else "OFFLINE"
        mostly_offline = providers and all(p == "OFFLINE" for p in providers)
        if connected_ids and cid in connected_ids and mostly_offline:
            offline_fail.append(name)
        elif last != "OFFLINE" or any(bucket["live_connected"]):
            live_ok.append(name)
        p95 = _p95(bucket["frame_ages"])
        if p95 is not None:
            if p95 >= FRAME_AGE_FAIL_MS:
                age_fail.append(f"{name} {p95:.0f}ms")
            elif p95 >= FRAME_AGE_WARN_MS:
                age_warn.append(f"{name} {p95:.0f}ms")
        ai = statistics.median(bucket["ai_ages"]) if bucket["ai_ages"] else None
        if ai is not None:
            if ai >= AI_AGE_FAIL_MS:
                ai_fail.append(f"{name} {ai:.0f}ms")
            elif ai >= AI_AGE_WARN_MS:
                ai_warn.append(f"{name} {ai:.0f}ms")
        sw = _delta(bucket["software"])
        native = _delta(bucket["native"])
        published = _delta(bucket["published"])
        if sw > 0 or native > 0 or published > 0:
            activity.append(name)
        if _delta(bucket["stalls"]) > 0:
            stalled.append(name)
        if bucket["empty_samples"] and bucket["empty_with_plate"]:
            stale.append(f"{name} ({bucket['empty_with_plate']}/{bucket['empty_samples']} empty samples still showed a plate)")

    if connected_ids and offline_fail:
        checks.append(_check("S2", "Live video present", FAIL, "OFFLINE entire soak: " + ", ".join(offline_fail)))
    elif live_ok:
        checks.append(_check("S2", "Live video present", PASS, ", ".join(live_ok)))
    else:
        checks.append(_check("S2", "Live video present", WARN, "no live JPEG observed — open Live Gates or wait for a frame"))

    if age_fail:
        checks.append(_check("S3", "Live frame age", FAIL, "; ".join(age_fail) + f" (fail >= {FRAME_AGE_FAIL_MS:.0f} ms)"))
    elif age_warn:
        checks.append(_check("S3", "Live frame age", WARN, "; ".join(age_warn) + f" (target < {FRAME_AGE_WARN_MS:.0f} ms)"))
    elif any(b["frame_ages"] for b in by_cam.values()):
        checks.append(_check("S3", "Live frame age", PASS, f"p95 under {FRAME_AGE_WARN_MS:.0f} ms"))
    else:
        checks.append(_check("S3", "Live frame age", WARN, "no frame-age samples (open live view or enable MediaMTX)"))

    if ai_fail:
        checks.append(_check("S4", "AI frame age", FAIL, "; ".join(ai_fail)))
    elif ai_warn:
        checks.append(_check("S4", "AI frame age", WARN, "; ".join(ai_warn) + f" (target < {AI_AGE_WARN_MS:.0f} ms)"))
    elif any(b["ai_ages"] for b in by_cam.values()):
        checks.append(_check("S4", "AI frame age", PASS, f"p50 under {AI_AGE_WARN_MS:.0f} ms"))
    else:
        checks.append(_check("S4", "AI frame age", WARN, "no AI frame-age samples"))

    if activity:
        checks.append(_check("S5", "FastALPR / native activity", PASS, "reads increased on " + ", ".join(activity)))
    else:
        checks.append(_check(
            "S5", "FastALPR / native activity", WARN,
            "no software_reads or native events during soak — pass cars through the lanes",
        ))

    others_dead = False
    if stalled and len(by_cam) > 1:
        stalled_ids = set()
        for cid, bucket in by_cam.items():
            if _delta(bucket["stalls"]) > 0:
                stalled_ids.add(cid)
        live_others = [
            cid for cid, bucket in by_cam.items()
            if cid not in stalled_ids and (
                _delta(bucket["software"]) > 0 or _delta(bucket["native"]) > 0 or _delta(bucket["published"]) > 0
            )
        ]
        frozen_others = [
            bucket["camera_name"] for cid, bucket in by_cam.items()
            if cid not in stalled_ids
            and _delta(bucket["software"]) == 0
            and _delta(bucket["native"]) == 0
            and _delta(bucket["published"]) == 0
        ]
        others_dead = bool(frozen_others) and not live_others and len(stalled_ids) < len(by_cam)
        if others_dead:
            checks.append(_check("S6", "Per-camera isolation", FAIL, "stall on " + ", ".join(stalled) + " froze " + ", ".join(frozen_others)))
        else:
            checks.append(_check("S6", "Per-camera isolation", PASS, "stalls stayed on " + ", ".join(stalled)))
    else:
        checks.append(_check("S6", "Per-camera isolation", PASS, "no recognition stalls, or only one camera"))

    if stale:
        checks.append(_check("S7", "Empty lane clears plate", FAIL, "; ".join(stale)))
    else:
        checks.append(_check("S7", "Empty lane clears plate", PASS, "no plate shown while vehicle_present=false"))

    pub = sum(_delta(b["published"]) for b in by_cam.values())
    sess = sum(_delta(b["sessions"]) for b in by_cam.values())
    if pub > 0 and sess > pub * 2:
        checks.append(_check("S8", "Exactly-once sessions", FAIL, f"sessions +{sess:.0f} vs published +{pub:.0f}"))
    elif sess > pub and pub > 0:
        checks.append(_check("S8", "Exactly-once sessions", WARN, f"sessions +{sess:.0f} vs published +{pub:.0f}"))
    else:
        checks.append(_check("S8", "Exactly-once sessions", PASS, f"sessions +{sess:.0f}, published +{pub:.0f}"))

    dup_visits = 0
    if sessions:
        seen: dict[tuple, int] = {}
        for row in sessions:
            visit = str(row.get("visit_id") or "").strip()
            cam = row.get("camera_id")
            if visit and cam is not None:
                key = (int(cam), visit)
                seen[key] = seen.get(key, 0) + 1
        dup_visits = sum(1 for count in seen.values() if count > 1)
    if dup_visits:
        checks.append(_check("S8b", "Visit uniqueness", FAIL, f"{dup_visits} visit_id(s) mapped to more than one ParkingSession"))
    elif sessions is not None:
        checks.append(_check("S8b", "Visit uniqueness", PASS, "no duplicate (camera, visit_id) in recent sessions"))

    cap_fail = False
    for snap in samples:
        sched = snap.get("scheduler") or {}
        inflight = int(sched.get("inflight") or 0)
        cap = int(sched.get("max_concurrency") or 4)
        if inflight > cap:
            cap_fail = True
            break
    checks.append(_check(
        "S9", "OCR scheduler cap",
        FAIL if cap_fail else PASS,
        "inflight exceeded max_concurrency" if cap_fail else "inflight stayed within cap",
    ))

    if expected_cars > 0:
        status = PASS if pub >= expected_cars else FAIL
        checks.append(_check("S10", "Expected cars recognized", status, f"published +{pub:.0f}, expected {expected_cars}"))
    else:
        checks.append(_check("S10", "Expected cars recognized", SKIP, "pass --expected-cars N to enforce a count"))
    return checks


def overall_status(checks: list[dict[str, str]]) -> str:
    if any(c["status"] == FAIL for c in checks):
        return FAIL
    if any(c["status"] == WARN for c in checks):
        return WARN
    return PASS


def render_report(report: dict) -> str:
    lines = [
        "SmartPark field acceptance test",
        f"Started: {report.get('started_at')}",
        f"Samples: {report.get('samples')}   Duration: {report.get('minutes')} min",
        f"Overall: {report.get('overall')}",
        "",
        f"{'ID':<5} {'STATUS':<6}  CHECK",
        "-" * 72,
    ]
    for row in report.get("checks") or []:
        lines.append(f"{row['id']:<5} {row['status']:<6}  {row['title']}")
        if row.get("detail"):
            lines.append(f"            {row['detail']}")
    lines.append("")
    lines.append("PASS means the live system matched the ParkWatch-style camera-JPEG → FastALPR path.")
    lines.append("WARN is acceptable to finish a soak but should be reviewed before production.")
    lines.append("FAIL must be fixed; do not treat unit tests as a substitute for this report.")
    return "\n".join(lines)


def _try_login(url: str, username: str, passwords: list[str]) -> tuple[str, str]:
    last = ""
    for password in passwords:
        if not password:
            continue
        try:
            return login(url, username, password), ""
        except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError) as exc:
            last = str(exc)
    return "", last


def _default_report_dir() -> Path:
    programdata = os.environ.get("PROGRAMDATA")
    if programdata:
        path = Path(programdata) / "SmartParkEdge" / "logs"
    else:
        path = Path.cwd() / "field-acceptance"
    path.mkdir(parents=True, exist_ok=True)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PASS/FAIL soak while cars use the live cameras.")
    parser.add_argument("--url", default="http://127.0.0.1:8760")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="")
    parser.add_argument("--minutes", type=float, default=8.0)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--expected-cars", type=int, default=0, dest="expected_cars")
    parser.add_argument("--report-dir", default="")
    args = parser.parse_args(argv)

    started = datetime.now(timezone.utc).isoformat()
    windows = sys.platform.startswith("win")
    passwords = [args.password] if args.password else ["SmartPark1!", "admin"]

    live = ready = None
    try:
        live = get_json(args.url, "/health/live", timeout=4)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        live = None
    try:
        live_or_ready = get_json(args.url, "/health/ready", timeout=6)
        ready = live_or_ready if isinstance(live_or_ready, dict) else None
    except urllib.error.HTTPError as exc:
        try:
            ready = json.loads(exc.read().decode("utf-8"))
        except Exception:
            ready = None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        ready = None

    token, login_error = _try_login(args.url, args.username, passwords)
    cameras = realtime0 = sessions = None
    if token:
        try:
            cameras = get_json(args.url, "/cameras", token)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            login_error = f"cameras: {exc}"
        try:
            realtime0 = get_json(args.url, "/health/realtime", token)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            login_error = f"realtime: {exc}"

    checks = evaluate_preflight(
        live=live if isinstance(live, dict) else None,
        ready=ready if isinstance(ready, dict) else None,
        cameras=cameras if isinstance(cameras, list) else None,
        realtime=realtime0 if isinstance(realtime0, dict) else None,
        login_ok=bool(token),
        login_error=login_error,
        windows=windows,
    )
    if not token:
        report = {
            "started_at": started,
            "minutes": args.minutes,
            "samples": 0,
            "overall": overall_status(checks),
            "checks": checks,
        }
        print(render_report(report))
        return 2

    connected_ids = {
        int(c["id"]) for c in (cameras or [])
        if str(c.get("status") or "").upper() in CONNECTED and c.get("id") is not None
    }
    samples: list[dict] = []
    if isinstance(realtime0, dict):
        samples.append(realtime0)
    deadline = time.time() + max(30.0, float(args.minutes) * 60.0)
    print(f"Sampling {args.url}/health/realtime for {args.minutes} minutes while cars pass…")
    while time.time() < deadline:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        time.sleep(min(float(args.interval), remaining))
        try:
            samples.append(get_json(args.url, "/health/realtime", token))
            print(f"  sample {len(samples)} ok")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"  sample failed: {exc}", file=sys.stderr)

    try:
        sessions = get_json(args.url, "/sessions", token)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        sessions = None

    checks.extend(evaluate_soak(
        samples,
        sessions=sessions if isinstance(sessions, list) else None,
        expected_cars=int(args.expected_cars or 0),
        connected_ids=connected_ids,
    ))
    report = {
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "url": args.url,
        "minutes": args.minutes,
        "samples": len(samples),
        "expected_cars": args.expected_cars,
        "overall": overall_status(checks),
        "checks": checks,
        "cameras": list(collect_cameras(samples).values()),
    }
    text = render_report(report)
    print()
    print(text)
    out_dir = Path(args.report_dir) if args.report_dir else _default_report_dir()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"field_acceptance_{stamp}.json"
    txt_path = out_dir / f"field_acceptance_{stamp}.txt"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    txt_path.write_text(text + "\n", encoding="utf-8")
    print()
    print(f"Wrote {json_path}")
    print(f"Wrote {txt_path}")
    return 0 if report["overall"] != FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
