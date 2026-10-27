"""Media-only camera lab.

Observes the running SmartPark media engine, or starts that engine alone when
Site Service is stopped. It does not create parking sessions, receipts, gate
commands, payments, or recognition captures.

Examples:

    python -m tools.camera_lab --camera 1 --duration 60
    python -m tools.camera_lab --all --duration 300
    python -m tools.camera_lab --camera 1 --duration 60 --recognition
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from app.infrastructure.media.diagnostics import (
    DEGRADED,
    FAIL,
    PASS,
    overall,
    scrub,
    summarize_samples,
    verdict_for,
)

def password_candidates(explicit: str = "") -> list[str]:
    """Passwords to try, without printing them. The install file comes first."""
    found: list[str] = []

    def add(value: str) -> None:
        value = (value or "").strip()
        if value and value not in found:
            found.append(value)

    add(explicit)
    add(os.environ.get("SMARTPARK_PASSWORD", ""))
    add(os.environ.get("SMARTPARK_BOOTSTRAP_PASSWORD", ""))
    bases: list[Path] = []
    programdata = os.environ.get("PROGRAMDATA")
    if programdata:
        bases.append(Path(programdata) / "SmartParkEdge")
    bases.append(Path.home() / "SmartParkEdge")
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        bases.append(Path(xdg) / "smartpark-edge")
    bases.append(Path.home() / ".local" / "share" / "smartpark-edge")
    for base in bases:
        path = base / "bootstrap_password.txt"
        try:
            if path.is_file():
                add(path.read_text(encoding="utf-8"))
        except OSError:
            continue
    add("SmartPark1!")
    add("admin")
    return found


def get_json(base: str, path: str, token: str | None = None, *, timeout: float = 8.0) -> Any:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{base.rstrip('/')}{path}", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


def service_up(base: str) -> bool:
    try:
        body = get_json(base, "/health/live", timeout=3)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return False
    return isinstance(body, dict)


def login(base: str, username: str, passwords: list[str]) -> str:
    last = "login failed"
    for password in passwords:
        req = urllib.request.Request(
            f"{base.rstrip('/')}/auth/login",
            data=json.dumps({"username": username, "password": password}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as res:
                body = json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}"
            continue
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            last = "Site Service did not accept login"
            continue
        token = str(body.get("access_token") or body.get("token") or "")
        if token:
            return token
        last = "login returned no token"
    raise RuntimeError(last)


def _wanted(camera_id: int | None, row_id: int) -> bool:
    return camera_id is None or int(row_id) == int(camera_id)


def sample_running(base: str, token: str, camera_id: int | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    body = get_json(base, "/media/gateway", token, timeout=8)
    if not isinstance(body, dict):
        return [], {}
    rows = []
    for row in body.get("cameras") or []:
        if isinstance(row, dict) and _wanted(camera_id, int(row.get("camera_id") or 0)):
            rows.append(row)
    mediamtx = body.get("mediamtx") if isinstance(body.get("mediamtx"), dict) else {}
    for name, path in (body.get("mediamtx_paths") or {}).items():
        if not isinstance(path, dict) or not name.startswith("cam") or not name[3:].isdigit():
            continue
        path_camera_id = int(name[3:])
        if not _wanted(camera_id, path_camera_id):
            continue
        rows = [row for row in rows if int(row.get("camera_id") or 0) != path_camera_id]
        rows.append({
            "camera_id": path_camera_id,
            "source": "mediamtx",
            "measurement": "transport",
            "connection_state": "STREAMING" if path.get("ready") else "DISCONNECTED",
            "bytes_received": path.get("bytes_received", 0),
            "codec": path.get("codec", ""),
            "reconnects": path.get("reconnects", 0),
        })
    return rows, mediamtx


def run_attach(args: argparse.Namespace) -> int:
    passwords = password_candidates(args.password)
    try:
        token = login(args.url, args.username, passwords)
    except RuntimeError as exc:
        print("FAIL")
        print(str(exc))
        print("Sign-in was rejected. The picture was not checked.")
        print(r"The first-run password is in %ProgramData%\SmartParkEdge\bootstrap_password.txt")
        print(r"If you already changed it, run: Run-CameraLab.bat -Password <the password you use in SmartPark>")
        return 1
    names = _camera_names(args.url, token)
    scope = get_json(args.url, "/runtime/recognition-scope", token)
    local_ids = {int(row["id"]) for row in scope.get("cameras", [])}
    buckets: dict[int, list[dict[str, Any]]] = {}
    mediamtx: dict[str, Any] = {}
    deadline = time.monotonic() + float(args.duration)
    camera_filter = None if args.all or args.gate else int(args.camera)
    selected = None
    if args.gate:
        cameras = get_json(args.url, "/cameras", token)
        selected = {int(row["id"]) for row in cameras if int(row.get("gate_id") or 0) == args.gate}
        if not selected:
            print("FAIL\nNo cameras assigned to this gate.")
            return 1
    realtime = {}
    while True:
        try:
            rows, mediamtx = sample_running(args.url, token, camera_filter)
            if args.latency:
                realtime = get_json(args.url, "/health/realtime", token)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
            rows = []
        for row in rows:
            if selected is not None and int(row.get("camera_id") or 0) not in selected:
                continue
            buckets.setdefault(int(row.get("camera_id") or 0), []).append(row)
        if time.monotonic() >= deadline:
            break
        time.sleep(max(0.2, float(args.interval)))
    code = _report(buckets, mediamtx, names, duration_s=float(args.duration), mode="attach")
    if args.recognition:
        _print_recognition(args, token, camera_filter)
    if args.latency:
        worker = realtime.get("worker") or {}
        print("\nLatency: worker measurements, most recent 200 samples per camera/stage")
        print(f"  warmup: {scrub(worker.get('warmup') or {})}")
        print(f"  resources: {scrub(worker.get('resources') or {})}")
        for row in worker.get("cameras") or []:
            camera_id = int(row.get("camera_id") or 0)
            if camera_filter is not None and camera_id != camera_filter:
                continue
            if selected is not None and camera_id not in selected:
                continue
            print(json.dumps(scrub({key: row.get(key) for key in (
                "camera_id", "state", "decoder_first_frame_ms", "input_frame_age_ms", "sampled_fps",
                "queue_depth", "decoder_pid", "reconnects", "latency_ms", "consensus", "timeline", "last_error",
            )}), indent=2))
        if not worker.get("ok"):
            print("  No healthy worker: recognition timings are unmeasured.")
        for row in realtime.get("cameras") or []:
            camera_id = int(row.get("camera_id") or 0)
            if camera_filter is not None and camera_id != camera_filter:
                continue
            if selected is not None and camera_id not in selected:
                continue
            print(f"  camera {camera_id} vehicle-to-business stage latency ms: {row.get('visit_latency_ms') or 'unmeasured'}")
    return code


def _camera_names(base: str, token: str) -> dict[int, str]:
    try:
        body = get_json(base, "/health/realtime", token, timeout=8)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return {}
    names = {}
    if isinstance(body, dict):
        for row in body.get("cameras") or []:
            if isinstance(row, dict):
                names[int(row.get("camera_id") or 0)] = str(row.get("camera_name") or "")
    return names


async def run_direct(args: argparse.Namespace) -> int:
    from app.infrastructure.media.service import MediaService
    from app.services.media_gateway import LocalMediaGateway

    engine = LocalMediaGateway()
    service = MediaService(engine)
    cameras = _load_camera_rows(None if args.all else int(args.camera))
    if not cameras:
        print("FAIL\nNo configured camera matched. The lab did not create a parking session.")
        return 1
    names = {int(row["id"]): str(row["name"]) for row in cameras}
    adapters = {int(row["id"]): str(row.get("adapter_id") or "hvx") for row in cameras}
    for row in cameras:
        service.register_camera(int(row["id"]), {**row, "need_detect": True, "password": row.get("password") or ""})
    buckets: dict[int, list[dict[str, Any]]] = {}
    deadline = time.monotonic() + float(args.duration)
    try:
        while True:
            for row in cameras:
                buckets.setdefault(int(row["id"]), []).append(service.health(int(row["id"])))
            if time.monotonic() >= deadline:
                break
            await asyncio.sleep(max(0.2, float(args.interval)))
    finally:
        service.stop_all()
    summaries_extra = adapters
    return _report(buckets, {}, names, duration_s=float(args.duration), mode="direct", adapters=summaries_extra)


def _load_camera_rows(camera_id: int | None) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Camera

    rows: list[dict[str, Any]] = []
    with SessionLocal() as db:
        stmt = select(Camera).order_by(Camera.id)
        if camera_id is not None:
            stmt = stmt.where(Camera.id == int(camera_id))
        for cam in db.scalars(stmt):
            from app.services.node_scope import camera_in_recognition_scope
            if not camera_in_recognition_scope(cam, db=db):
                continue
            if not bool(getattr(cam, "enabled", True)):
                continue
            rows.append({
                "id": int(cam.id),
                "name": cam.name,
                "ip": cam.ip_address,
                "username": cam.username or "",
                "password": cam.password_secret or "",
                "rtsp_url": cam.rtsp_url or "",
                "sdk_handle": cam.sdk_handle,
                "adapter_id": cam.adapter_id or "hvx",
                "ffmpeg_profile": cam.ffmpeg_profile or "",
                "transport": cam.rtsp_transport or "TCP",
                "stream_profiles": dict(cam.stream_profiles or {}),
            })
    return rows


def _report(
    buckets: dict[int, list[dict[str, Any]]],
    mediamtx: dict[str, Any],
    names: dict[int, str],
    *,
    duration_s: float,
    mode: str,
    adapters: dict[int, str] | None = None,
) -> int:
    print(f"SmartPark camera lab ({mode}, {duration_s:.0f}s)")
    print("Media only. No parking session, receipt, gate command, or payment was created.")
    mtx = scrub(mediamtx) if mediamtx else {}
    if mtx:
        running = "running" if mtx.get("running") else "not running"
        print(f"MediaMTX: {running}")
        if mtx.get("control_api_error"):
            print(f"Control API: {mtx['control_api_error']}")
        if mtx.get("last_error"):
            print(f"MediaMTX error: {mtx['last_error']}")
        print(f"Registered paths: {', '.join(mtx.get('paths') or []) or 'none in API process'}")
    elif mode == "attach":
        print("MediaMTX: not reported")
    else:
        print("MediaMTX: not used (direct acquisition)")
    if not buckets:
        print("FAIL")
        print("reason: no camera media session was visible")
        return 1
    results: list[tuple[str, list[str]]] = []
    for camera_id in sorted(buckets):
        summary = summarize_samples(
            buckets[camera_id],
            name=names.get(camera_id, ""),
            adapter=(adapters or {}).get(camera_id, ""),
        )
        state, reasons = verdict_for(summary, duration_s=duration_s)
        results.append((state, reasons))
        _print_camera(scrub(summary), state, reasons)
    final = overall(results)
    print(final)
    if final != PASS:
        print("Streaming is not accepted until this lab passes on the physical cameras.")
    return {PASS: 0, DEGRADED: 2, FAIL: 1}.get(final, 1)


def _print_camera(summary: dict[str, Any], state: str, reasons: list[str]) -> None:
    cid = summary.get("camera_id")
    name = summary.get("name") or ""
    title = f"camera {cid}" + (f" {name}" if name else "")
    print(f"\n{title}  [{state}]")
    fields = [
        ("adapter", summary.get("adapter")),
        ("source", summary.get("source")),
        ("LIVE role", summary.get("live_role")),
        ("DETECT role", summary.get("detect_role")),
        ("connection", summary.get("connection_state")),
        ("measurement", summary.get("measurement")),
        ("stream bytes received", summary.get("bytes_received")),
        ("source FPS", summary.get("source_fps")),
        ("decoded FPS", summary.get("live_fps")),
        ("frames received", summary.get("frames_received")),
        ("frames changed", summary.get("frames_changed")),
        ("duplicate frames", summary.get("duplicate_frames")),
        ("frames dropped", summary.get("frames_dropped")),
        ("LIVE frame age ms", summary.get("live_frame_age_ms")),
        ("DETECT frame age ms", summary.get("detect_frame_age_ms")),
        ("max LIVE frame age ms", summary.get("max_live_frame_age_ms")),
        ("avg interval ms", summary.get("frame_interval_avg_ms")),
        ("p50 interval ms", summary.get("frame_interval_p50_ms")),
        ("p95 interval ms", summary.get("frame_interval_p95_ms")),
        ("max interval ms", summary.get("frame_interval_max_ms")),
        ("reconnects", summary.get("reconnects")),
        ("decoder restarts", summary.get("decoder_restarts")),
        ("ffmpeg pid", summary.get("ffmpeg_pid")),
        ("codec", summary.get("codec") or "n/a"),
        ("resolution", _resolution(summary)),
        ("GOP", summary.get("gop") or "n/a"),
        ("bitrate bps", summary.get("bitrate_bps") or "n/a"),
        ("transport", summary.get("transport") or "n/a"),
        ("browser/live transport", summary.get("transport") or "n/a"),
        ("url", summary.get("url_redacted") or ""),
    ]
    for label, value in fields:
        if value in ("", None):
            continue
        print(f"  {label}: {value}")
    if summary.get("last_error"):
        print(f"  last error: {summary.get('last_error')}")
    for reason in reasons:
        print(f"  - {reason}")


def _resolution(summary: dict[str, Any]) -> str:
    width = int(summary.get("width") or 0)
    height = int(summary.get("height") or 0)
    if width and height:
        return f"{width}x{height}"
    return "n/a"


def _print_recognition(args: argparse.Namespace, token: str, camera_filter: int | None) -> None:
    """Worker health plus a bounded detect/crop/OCR sample. Never a parking event."""

    print("\nRecognition")
    print("No parking session, receipt, gate command, or payment is created.")
    health = (get_json(args.url, "/health/realtime", token) or {}).get("worker") or {}
    if not health.get("ok"):
        print("  worker: not running (software reads stay with Site Service until the heartbeat is fresh)")
    else:
        rows = [row for row in health.get("cameras") or [] if isinstance(row, dict)]
        if camera_filter is not None:
            rows = [row for row in rows if int(row.get("camera_id") or 0) == int(camera_filter)]
        if not rows:
            print("  worker: running, no matching lane")
        for row in rows:
            print(f"  camera {row.get('camera_id')}:")
            for label, key in (
                ("state", "state"),
                ("sample fps", "sample_fps"),
                ("sampled fps", "sampled_fps"),
                ("frame age source", "last_frame_at"),
                ("queue depth", "queue_depth"),
                ("decoder pid", "decoder_pid"),
                ("reconnects", "reconnects"),
                ("ocr paused", "ocr_paused"),
                ("inference ms", "infer_ms"),
                ("stale dropped", "stale_dropped"),
                ("media owner", "media_owner"),
            ):
                if row.get(key) not in (None, ""):
                    print(f"    {label}: {row.get(key)}")
    if camera_filter is None:
        print("  benchmark: pass --camera N --recognition to OCR one frame. That still does not publish a parking event.")
        return
    try:
        jpeg = _snapshot_jpeg(args.url, token, int(camera_filter))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        print(f"  benchmark: no snapshot ({exc.__class__.__name__})")
        return
    if jpeg[:2] != b"\xff\xd8":
        print("  benchmark: snapshot was not a JPEG")
        return
    print(f"  benchmark: {scrub(benchmark_frame(jpeg))}")


def _snapshot_jpeg(base: str, token: str, camera_id: int) -> bytes:
    req = urllib.request.Request(
        f"{base.rstrip('/')}/cameras/{int(camera_id)}/snapshot.jpg",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=8) as res:
        return res.read()


def benchmark_frame(jpeg: bytes) -> dict[str, Any]:
    """One detect → crop → OCR pass. The result is not published."""
    from app.services.alpr import recognize_arrival_bytes

    result = recognize_arrival_bytes(jpeg, camera_label="camera-lab", save_evidence=False)
    best = result.get("best") if isinstance(result.get("best"), dict) else {}
    bbox = best.get("bbox") if isinstance(best.get("bbox"), dict) else {}
    crop = bbox.get("crop") if isinstance(bbox.get("crop"), dict) else {}
    return {
        "pipeline": result.get("pipeline") or "",
        "latency_ms": result.get("latency_ms"),
        "normalized_plate": best.get("plate_normalized") or "",
        "confidence": best.get("confidence"),
        "detector_ms": result.get("detector_ms"),
        "timings": best.get("timings") or {},
        "crop_width": (int(crop["x2"]) - int(crop["x1"])) if crop else None,
        "crop_height": (int(crop["y2"]) - int(crop["y1"])) if crop else None,
        "detail": result.get("detail") or "",
        "published_parking_event": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sample SmartPark media acquisition without parking logic.")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--camera", type=int, help="Camera id to sample")
    target.add_argument("--all", action="store_true", help="Sample every configured camera")
    target.add_argument("--gate", type=int, help="Observe the assigned ENTRY and EXIT cameras")
    parser.add_argument("--duration", type=float, required=True, help="Seconds to sample")
    parser.add_argument("--interval", type=float, default=0.5, help="Seconds between samples")
    parser.add_argument("--url", default="http://127.0.0.1:8760")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="")
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Start the media engine in this process. Refused while Site Service is already running.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="With --direct, start anyway even if Site Service is running. Can add a second decoder.",
    )
    parser.add_argument(
        "--recognition",
        action="store_true",
        help="Also report the recognition worker and benchmark a few frames. Does not publish a parking event.",
    )
    parser.add_argument("--latency", action="store_true", help="Collect worker stage p50/p95/max and visit timelines without publishing events")
    return parser


def main(argv: list[str] | None = None) -> int:
    # The original option-based CLI observes configured physical cameras. The
    # recorded-footage subcommands are kept in a separate module so that
    # existing Windows/operator invocations remain compatible.
    replay_commands = {"inspect", "serve", "test-video", "test-image", "benchmark", "multi-camera", "failure-test", "report", "ground-truth"}
    candidate = list(sys.argv[1:] if argv is None else argv)
    if candidate and candidate[0] in replay_commands:
        from tools.camera_lab_replay import main as replay_main

        return replay_main(candidate)
    args = build_parser().parse_args(argv)
    if args.duration <= 0:
        print("FAIL\nreason: duration must be greater than 0")
        return 1
    if args.direct and (args.gate or args.latency or args.recognition):
        print("FAIL\nGate/recognition/latency diagnostics require a running Site Service; omit --direct.")
        return 1
    up = service_up(args.url)
    if args.direct and up and not args.force:
        print("FAIL")
        print("Site Service is already running. Re-run without --direct so this lab only observes it.")
        print("A second acquisition process can open another decoder on the same camera.")
        return 1
    if args.direct:
        return asyncio.run(run_direct(args))
    if not up:
        print("FAIL")
        print(f"Site Service is not answering at {args.url}.")
        print("Start SmartPark, then re-run this command.")
        print("If Site Service is intentionally stopped, add --direct to exercise media acquisition alone.")
        return 1
    return run_attach(args)


if __name__ == "__main__":
    sys.exit(main())
