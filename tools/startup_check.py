"""Startup check for a Windows SmartPark PC.

Run this after SmartPark has started. It talks only to the local Site Service.
It does not open a barrier, print a ticket, or create a parking session.

  V1  Each connected camera's picture changes during the sample window
  V2  Live frame age stays inside the field limit
  R1  The recognition worker heartbeat is fresh
  R2  One software read runs on each connected camera
  G1  Each lane answers a dry-run open. The barrier is not pulsed.

Usage (installed PC):

    powershell -ExecutionPolicy Bypass -File Run-StartupCheck.ps1
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

try:
    from field_acceptance_test import (
        CONNECTED,
        FAIL,
        PASS,
        SKIP,
        WARN,
        _check,
        _p95,
        _try_login,
        get_json,
        overall_status,
        password_candidates,
    )
except ImportError:  # imported as tools.startup_check from the unit tests
    from tools.field_acceptance_test import (
        CONNECTED,
        FAIL,
        PASS,
        SKIP,
        WARN,
        _check,
        _p95,
        _try_login,
        get_json,
        overall_status,
        password_candidates,
    )

FRAME_AGE_WARN_MS = 500.0
FRAME_AGE_FAIL_MS = 2500.0


def gate_sides(gate: dict) -> list[str | None]:
    """One dry-run per barrier. A two-sided lane must name ENTRY and EXIT."""
    cameras = list(gate.get("cameras") or [])
    directions: list[str] = []
    for camera in cameras:
        direction = str(camera.get("lane_direction") or "").upper()
        if direction in {"ENTRY", "EXIT"} and direction not in directions:
            directions.append(direction)
    if len(directions) >= 2:
        return directions
    if len(cameras) > 1:
        return directions or ["ENTRY", "EXIT"]
    return [directions[0]] if directions else [None]


def gate_request(gate: dict, side: str | None) -> dict[str, Any]:
    """Body for POST /gates/{id}/open. dry_run stays true."""
    body: dict[str, Any] = {
        "reason": "SmartPark startup check. Dry run only.",
        "dry_run": True,
        "action": "open",
    }
    if side:
        body["side"] = side
    return body


def _series(samples: list[dict], camera_id: int, key: str) -> list[Any]:
    values = []
    for snap in samples:
        for row in snap.get("cameras") or []:
            if int(row.get("camera_id") or 0) == int(camera_id) and row.get(key) is not None:
                values.append(row.get(key))
    return values


def _increased(values: list[Any]) -> bool:
    numbers = []
    for value in values:
        try:
            numbers.append(float(value))
        except (TypeError, ValueError):
            continue
    return len(numbers) >= 2 and numbers[-1] > numbers[0]


def evaluate_video(samples: list[dict], connected_ids: set[int]) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    if len(samples) < 2:
        checks.append(_check("V1", "Live picture changes", FAIL, "fewer than two realtime samples"))
        return checks
    if not connected_ids:
        checks.append(_check(
            "V1", "Live picture changes", FAIL,
            "no camera is SDK_CONNECTED or VIDEO_CONNECTED. Connect all, then run this again.",
        ))
        return checks

    moving = 0
    details: list[str] = []
    ages: list[float] = []
    for camera_id in sorted(connected_ids):
        name = ""
        live = []
        frozen = []
        for snap in samples:
            for row in snap.get("cameras") or []:
                if int(row.get("camera_id") or 0) != camera_id:
                    continue
                name = str(row.get("camera_name") or name or f"camera {camera_id}")
                live.append(bool(row.get("live_connected")))
                if row.get("frozen") is not None:
                    frozen.append(bool(row.get("frozen")))
                if row.get("estimated_frame_age_ms") is not None:
                    ages.append(float(row["estimated_frame_age_ms"]))
        changed = _increased(_series(samples, camera_id, "frame_seq")) or _increased(
            _series(samples, camera_id, "frames_changed")
        )
        media_flowing = _increased(_series(samples, camera_id, "media_bytes_received"))
        label = name or f"camera {camera_id}"
        if media_flowing:
            moving += 1
        elif not any(live):
            details.append(f"{label}: no JPEG")
        elif not changed:
            reason = "frozen" if frozen and all(frozen) else "picture did not change"
            details.append(f"{label}: {reason}")
        else:
            moving += 1
    if moving == len(connected_ids):
        checks.append(_check("V1", "Live media advances", PASS, f"{moving} camera(s) delivered new frames or MediaMTX stream bytes"))
    else:
        checks.append(_check("V1", "Live picture changes", FAIL, "; ".join(details) or "picture did not change"))

    p95 = _p95(ages)
    if p95 is None:
        checks.append(_check("V2", "Live frame age", WARN, "frame age was not reported"))
    elif p95 >= FRAME_AGE_FAIL_MS:
        checks.append(_check("V2", "Live frame age", FAIL, f"p95 {p95:.0f} ms"))
    elif p95 >= FRAME_AGE_WARN_MS:
        checks.append(_check("V2", "Live frame age", WARN, f"p95 {p95:.0f} ms"))
    else:
        checks.append(_check("V2", "Live frame age", PASS, f"p95 {p95:.0f} ms"))
    return checks


def _plate_text(body: dict) -> str:
    best = body.get("best") if isinstance(body.get("best"), dict) else {}
    for value in (best.get("plate"), body.get("plate"), body.get("text")):
        text = str(value or "").strip()
        if text:
            return text
    for item in body.get("candidates") or body.get("plates") or []:
        if isinstance(item, dict):
            text = str(item.get("plate") or item.get("text") or "").strip()
            if text:
                return text
    return ""


def evaluate_recognition(worker: dict | None, reads: list[dict]) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    if worker and worker.get("ok"):
        age = worker.get("heartbeat_age_seconds")
        detail = "heartbeat fresh" if age is None else f"heartbeat age {age}s"
        checks.append(_check("R1", "Recognition worker", PASS, detail))
    else:
        state = (worker or {}).get("state") or "missing"
        checks.append(_check("R1", "Recognition worker", FAIL, f"worker {state}"))

    if not reads:
        checks.append(_check("R2", "Recognition read", FAIL, "no connected camera to read"))
        return checks

    failed: list[str] = []
    empty: list[str] = []
    found: list[str] = []
    for read in reads:
        label = str(read.get("camera_name") or read.get("camera_id"))
        if not read.get("http_ok"):
            failed.append(f"{label}: {read.get('error') or 'request failed'}")
            continue
        body = read.get("body") if isinstance(read.get("body"), dict) else {}
        if body.get("ok") is False:
            failed.append(f"{label}: {body.get('detail') or 'read failed'}")
            continue
        plate = _plate_text(body)
        if plate:
            found.append(f"{label} {plate}")
        else:
            source = body.get("evidence_source") or "frame"
            empty.append(f"{label} ({source}, no plate in the picture)")
    if failed:
        checks.append(_check("R2", "Recognition read", FAIL, "; ".join(failed)))
    elif empty and not found:
        checks.append(_check(
            "R2", "Recognition read", WARN,
            "engine ran; " + "; ".join(empty),
        ))
    else:
        detail = ", ".join(found)
        if empty:
            detail = detail + "; no plate on " + ", ".join(empty)
        checks.append(_check("R2", "Recognition read", PASS, detail or "engine ran"))
    return checks


def evaluate_gates(results: list[dict]) -> list[dict[str, str]]:
    if not results:
        return [_check("G1", "Gate dry-run", FAIL, "no gate is configured")]
    problems: list[str] = []
    notes: list[str] = []
    for row in results:
        label = str(row.get("label") or "gate")
        if row.get("skipped"):
            notes.append(f"{label}: skipped ({row.get('detail') or 'disabled'})")
            continue
        body = row.get("body") if isinstance(row.get("body"), dict) else {}
        if not row.get("request_dry_run"):
            problems.append(f"{label}: request was not a dry-run")
            continue
        if not row.get("http_ok") or not body.get("ok"):
            problems.append(f"{label}: {row.get('error') or body.get('message') or 'dry-run failed'}")
            continue
        if body.get("simulated") is False and "dry-run" not in str(body.get("message") or "").lower():
            problems.append(f"{label}: response was not a dry-run")
            continue
        notes.append(f"{label}: {body.get('message') or 'dry-run accepted'}")
    if problems:
        return [_check("G1", "Gate dry-run", FAIL, "; ".join(problems))]
    if notes and all("skipped" in note for note in notes):
        return [_check("G1", "Gate dry-run", SKIP, "; ".join(notes))]
    return [_check("G1", "Gate dry-run", PASS, "; ".join(notes) or "dry-run accepted")]


def render_report(report: dict) -> str:
    lines = [
        "SmartPark startup check",
        f"Started: {report.get('started_at')}",
        f"Samples: {report.get('samples')}   Window: {report.get('seconds')} s",
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
    lines.append("The gate check is a dry-run. It does not pulse the barrier.")
    lines.append("WARN means the picture or the engine answered, but a plate was not in the frame.")
    lines.append("FAIL means video, recognition, or the gate path did not answer. Do not treat this PC as ready.")
    return "\n".join(lines)


def post_json(base: str, path: str, token: str, payload: dict, *, timeout: float = 20.0) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base.rstrip('/')}{path}",
        data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            body = json.loads(res.read().decode("utf-8") or "{}")
            return int(res.status), body if isinstance(body, dict) else {"ok": True, "body": body}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"message": raw or str(exc)}
        if isinstance(parsed, dict) and "detail" in parsed and "message" not in parsed:
            parsed["message"] = parsed.get("detail")
        return int(exc.code), parsed if isinstance(parsed, dict) else {"message": str(parsed)}


def _wait_until_live(url: str, timeout_s: float) -> dict | None:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        try:
            body = get_json(url, "/health/live", timeout=4)
            if isinstance(body, dict) and body.get("ok"):
                return body
            last = body if isinstance(body, dict) else None
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
            last = None
        time.sleep(2)
    return last


def _connected_ids(cameras: list) -> set[int]:
    return {
        int(camera["id"])
        for camera in cameras
        if camera.get("id") is not None and str(camera.get("status") or "").upper() in CONNECTED
    }


def _sample(url: str, token: str, seconds: float, interval: float) -> list[dict]:
    samples: list[dict] = []
    deadline = time.time() + max(4.0, seconds)
    while True:
        try:
            body = get_json(url, "/health/realtime", token, timeout=8)
            if isinstance(body, dict):
                samples.append(body)
                print(f"  sample {len(samples)} ok")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"  sample failed: {exc}", file=sys.stderr)
        if time.time() >= deadline:
            break
        time.sleep(max(0.5, interval))
    return samples


def _read_cameras(url: str, token: str, cameras: list, connected: set[int]) -> list[dict]:
    names = {int(camera["id"]): camera.get("name") or f"camera {camera['id']}" for camera in cameras if camera.get("id") is not None}
    reads = []
    for camera_id in sorted(connected):
        label = str(names.get(camera_id) or f"camera {camera_id}")
        print(f"  recognition read {label}")
        try:
            status, body = post_json(
                url,
                f"/cameras/{camera_id}/commissioning/recognition/read",
                token,
                {},
                timeout=45,
            )
            reads.append({
                "camera_id": camera_id,
                "camera_name": label,
                "http_ok": status < 400,
                "body": body,
                "error": "" if status < 400 else body.get("message") or f"HTTP {status}",
            })
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            reads.append({
                "camera_id": camera_id,
                "camera_name": label,
                "http_ok": False,
                "body": {},
                "error": str(exc),
            })
    return reads


def _dry_run_gates(url: str, token: str, gates: list) -> list[dict]:
    results = []
    for gate in gates:
        name = str(gate.get("name") or f"gate {gate.get('id')}")
        if gate.get("enabled") is False:
            results.append({"label": name, "skipped": True, "detail": "disabled", "request_dry_run": True})
            continue
        for side in gate_sides(gate):
            label = name if not side else f"{name} {side}"
            payload = gate_request(gate, side)
            print(f"  gate dry-run {label}")
            try:
                status, body = post_json(url, f"/gates/{int(gate['id'])}/open", token, payload, timeout=20)
                results.append({
                    "label": label,
                    "http_ok": status < 400 and bool(body.get("ok")),
                    "request_dry_run": payload.get("dry_run") is True,
                    "body": body,
                    "error": "" if status < 400 else body.get("message") or f"HTTP {status}",
                })
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                results.append({
                    "label": label,
                    "http_ok": False,
                    "request_dry_run": True,
                    "body": {},
                    "error": str(exc),
                })
    return results


def _write_report(report: dict, report_dir: str) -> None:
    try:
        from field_acceptance_test import _default_report_dir
    except ImportError:
        from tools.field_acceptance_test import _default_report_dir
    from pathlib import Path

    out_dir = Path(report_dir) if report_dir else _default_report_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    text = render_report(report)
    json_path = out_dir / f"startup_check_{stamp}.json"
    txt_path = out_dir / f"startup_check_{stamp}.txt"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    txt_path.write_text(text + "\n", encoding="utf-8")
    print()
    print(text)
    print()
    print(f"Wrote {json_path}")
    print(f"Wrote {txt_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check video, recognition, and a gate dry-run after SmartPark starts.")
    parser.add_argument("--url", default="http://127.0.0.1:8760")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="")
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--wait", type=float, default=90.0, help="Seconds to wait for Site Service after startup")
    parser.add_argument("--report-dir", default="")
    args = parser.parse_args(argv)

    started = datetime.now(timezone.utc).isoformat()
    print(f"Waiting up to {args.wait:.0f}s for {args.url} ...")
    live = _wait_until_live(args.url, float(args.wait))
    checks: list[dict[str, str]] = []
    if not (isinstance(live, dict) and live.get("ok")):
        checks.append(_check("P1", "Site Service live", FAIL, "SmartPark is not answering /health/live"))
        report = {"started_at": started, "seconds": args.seconds, "samples": 0, "overall": FAIL, "checks": checks}
        _write_report(report, args.report_dir)
        return 2
    checks.append(_check("P1", "Site Service live", PASS, str(live.get("status") or "live")))

    token, login_error = _try_login(args.url, args.username, password_candidates(args.password))
    if not token:
        checks.append(_check("P3", "Operator login", FAIL, login_error or "login failed"))
        report = {"started_at": started, "seconds": args.seconds, "samples": 0, "overall": FAIL, "checks": checks}
        _write_report(report, args.report_dir)
        return 2
    checks.append(_check("P3", "Operator login", PASS, "token issued"))

    try:
        cameras = get_json(args.url, "/cameras", token)
        gates = get_json(args.url, "/gates", token)
        scope = get_json(args.url, "/runtime/recognition-scope", token)
        local_ids = {int(row["id"]) for row in scope.get("cameras", [])}
        cameras = [row for row in cameras if int(row["id"]) in local_ids]
        gates = [row for row in gates if row.get("id") == scope.get("gate_id")]
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        checks.append(_check("P4", "Site configuration", FAIL, str(exc)))
        report = {"started_at": started, "seconds": args.seconds, "samples": 0, "overall": FAIL, "checks": checks}
        _write_report(report, args.report_dir)
        return 2
    cameras = cameras if isinstance(cameras, list) else []
    gates = gates if isinstance(gates, list) else []
    connected = _connected_ids(cameras)

    print(f"Sampling live video for {args.seconds:.0f}s ...")
    samples = _sample(args.url, token, float(args.seconds), float(args.interval))
    checks.extend(evaluate_video(samples, connected))
    worker = (samples[-1].get("worker") if samples else None) if samples else None
    print("Running one recognition read per connected camera ...")
    reads = _read_cameras(args.url, token, cameras, connected)
    checks.extend(evaluate_recognition(worker if isinstance(worker, dict) else None, reads))
    print("Dry-run gate open (the barrier is not pulsed) ...")
    checks.extend(evaluate_gates(_dry_run_gates(args.url, token, gates)))

    report = {
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "url": args.url,
        "seconds": args.seconds,
        "samples": len(samples),
        "overall": overall_status(checks),
        "checks": checks,
    }
    _write_report(report, args.report_dir)
    return 0 if report["overall"] != FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
