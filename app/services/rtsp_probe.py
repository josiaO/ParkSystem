from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from urllib.parse import quote

from app.config import settings


@dataclass
class ProbeResult:
    ok: bool
    url_redacted: str
    codec: str | None = None
    width: int | None = None
    height: int | None = None
    fps: str | None = None
    error: str = ""


def redact_url(url: str) -> str:
    return re.sub(r"(://[^:/@]+:)[^@]+(@)", r"\1********\2", url)


def vendor_candidates(
    ip: str,
    username: str,
    password: str,
    explicit: str = "",
    *,
    prefer_qy: bool = False,
) -> list[str]:
    out=[]
    if explicit:
        out.append(explicit)
    u=quote(username, safe="")
    p=quote(password, safe="")
    # OcxConfig/NetSDK negotiates the QY picture service on port 40000 and
    # builds /video and /subvideo URLs from that negotiated port.  Port 554 is
    # common for Dahua/Hikvision, but is actively refused by the gate cameras
    # in the supplied site.  Keep the QY candidates ahead of generic RTSP only
    # when the caller has identified the native HVX/QY adapter.
    qy = [
        f"rtsp://{u}:{p}@{ip}:40000/subvideo",
        f"rtsp://{u}:{p}@{ip}:40000/video",
        f"rtsp://{ip}:40000/subvideo",
        f"rtsp://{ip}:40000/video",
    ]
    # The vendor camera exposes ``RTSP://<ip>:<port>/video`` and ``/subvideo``
    # continuous video.  Put credential-bearing variants first so MediaMTX can
    # authenticate without relying on the vendor SDK process.  OcxConfig's
    # av0_0/av0_1 forms remain fallbacks for older QY firmware.
    generic = [
        f"rtsp://{u}:{p}@{ip}:554/subvideo",
        f"rtsp://{u}:{p}@{ip}:554/video",
        f"rtsp://{ip}:554/subvideo",
        f"rtsp://{ip}:554/video",
        f"rtsp://{ip}/av0_1&user={u}&password={p}",
        f"rtsp://{ip}/av0_0&user={u}&password={p}",
        f"rtsp://{u}:{p}@{ip}:554/Streaming/Channels/101",
        f"rtsp://{u}:{p}@{ip}:554/Streaming/Channels/102",
        f"rtsp://{u}:{p}@{ip}:554/h264/ch1/main/av_stream",
        f"rtsp://{u}:{p}@{ip}:554/cam/realmonitor?channel=1&subtype=0",
        f"rtsp://{u}:{p}@{ip}:554/cam/realmonitor?channel=1&subtype=1",
        f"rtsp://{u}:{p}@{ip}:554/stream1",
        f"rtsp://{u}:{p}@{ip}:554/live",
    ]
    out += (qy + generic) if prefer_qy else (generic + qy)
    seen=[]
    for x in out:
        if x not in seen:
            seen.append(x)
    return seen


async def probe(url: str, *, timeout_seconds: float | None = None) -> ProbeResult:
    cmd=[
        "ffprobe", "-v", "error",
        "-rtsp_transport", "tcp",
        "-show_streams", "-select_streams", "v:0",
        "-of", "json", url,
    ]
    try:
        proc=await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            timeout = float(timeout_seconds or settings.rtsp_probe_timeout_seconds)
            stdout, stderr=await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill(); await proc.wait()
            return ProbeResult(False, redact_url(url), error="FFprobe timeout")
        if proc.returncode != 0:
            return ProbeResult(False, redact_url(url), error=stderr.decode(errors="replace")[-600:])
        data=json.loads(stdout.decode() or "{}")
        streams=data.get("streams") or []
        if not streams:
            return ProbeResult(False, redact_url(url), error="No video stream returned")
        s=streams[0]
        return ProbeResult(True, redact_url(url), s.get("codec_name"), s.get("width"), s.get("height"), s.get("avg_frame_rate"))
    except FileNotFoundError:
        return ProbeResult(False, redact_url(url), error="ffprobe not installed or not on PATH")
    except Exception as exc:
        return ProbeResult(False, redact_url(url), error=str(exc))
