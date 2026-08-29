"""Grab one JPEG from a live RTSP URL. An open TCP/554 socket is not enough."""

from __future__ import annotations

import asyncio
import shutil
import uuid

from app.config import settings
from app.services.rtsp_probe import redact_url, vendor_candidates

JPEG_SOI = b"\xff\xd8"


def ffmpeg_bin() -> str | None:
    return shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")


async def capture_frame(url: str, *, timeout: float | None = None) -> dict:
    binary = ffmpeg_bin()
    if not binary:
        return {"ok": False, "error": "ffmpeg is not installed", "url_redacted": redact_url(url)}
    dest = settings.media_dir / "snapshots" / f"{uuid.uuid4().hex}.jpg"
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        binary,
        "-hide_banner",
        "-loglevel", "error",
        "-rtsp_transport", "tcp",
        "-i", url,
        "-frames:v", "1",
        "-q:v", "5",
        "-y",
        str(dest),
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            _, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout or settings.rtsp_probe_timeout_seconds
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {"ok": False, "error": "ffmpeg frame capture timed out", "url_redacted": redact_url(url)}
    except FileNotFoundError:
        return {"ok": False, "error": "ffmpeg is not installed", "url_redacted": redact_url(url)}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "url_redacted": redact_url(url)}
    if proc.returncode != 0 or not dest.is_file() or dest.stat().st_size < 32:
        return {
            "ok": False,
            "error": (stderr.decode(errors="replace")[-400:] if stderr else "ffmpeg wrote no JPEG"),
            "url_redacted": redact_url(url),
        }
    data = dest.read_bytes()
    if data[:2] != JPEG_SOI:
        return {"ok": False, "error": "ffmpeg output was not JPEG", "url_redacted": redact_url(url)}
    return {
        "ok": True,
        "jpeg": data,
        "path": str(dest),
        "bytes": len(data),
        "url_redacted": redact_url(url),
    }


async def grab_camera_frame(ip: str, username: str, password: str, explicit_rtsp: str = "") -> dict:
    attempts = []
    urls = vendor_candidates(ip, username, password, explicit_rtsp)
    hunt = min(2.0, float(settings.rtsp_probe_timeout_seconds or 5.0))
    for index, url in enumerate(urls):
        timeout = settings.rtsp_probe_timeout_seconds if index == 0 else hunt
        result = await capture_frame(url, timeout=timeout)
        attempts.append({k: v for k, v in result.items() if k != "jpeg"})
        if result.get("ok"):
            result["attempts"] = attempts
            result["url"] = url
            return result
    return {
        "ok": False,
        "error": "no live JPEG from vendor RTSP candidates",
        "attempts": attempts,
    }
