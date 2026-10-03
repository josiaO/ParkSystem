"""Media-only camera lab.

Observes the running SmartPark media engine, or starts that engine alone when
Site Service is stopped. It does not create parking sessions, receipts, gate
commands, payments, or recognition captures.

Examples:

    python -m tools.camera_lab --camera 1 --duration 60
    python -m tools.camera_lab --all --duration 300
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
    buckets: dict[int, list[dict[str, Any]]] = {}
    mediamtx: dict[str, Any] = {}
    deadline = time.monotonic() + float(args.duration)
    camera_filter = None if args.all else int(args.camera)
    while True:
        try:
            rows, mediamtx = sample_running(args.url, token, camera_filter)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
            rows = []
        for row in rows:
            buckets.setdefault(int(row.get("camera_id") or 0), []).append(row)
        if time.monotonic() >= deadline:
            break
        time.sleep(max(0.2, float(args.interval)))
    return _report(buckets, mediamtx, names, duration_s=float(args.duration), mode="attach")


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sample SmartPark media acquisition without parking logic.")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--camera", type=int, help="Camera id to sample")
    target.add_argument("--all", action="store_true", help="Sample every configured camera")
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.duration <= 0:
        print("FAIL\nreason: duration must be greater than 0")
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
