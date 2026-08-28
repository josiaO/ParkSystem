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


def vendor_candidates(ip: str, username: str, password: str, explicit: str = "") -> list[str]:
    out=[]
    if explicit:
        out.append(explicit)
    u=quote(username, safe="")
    p=quote(password, safe="")
    # Literal templates from OcxConfig/RtspRecvSdk.dll, using configured credentials
    # instead of the sample admin/admin baked into that DLL.
    out += [
        f"rtsp://{ip}/av0_0&user={u}&password={p}",
        f"rtsp://{ip}/av0_1&user={u}&password={p}",
        f"rtsp://{ip}:554/video",
        f"rtsp://{ip}:554/subvideo",
        f"rtsp://{u}:{p}@{ip}:554/video",
        f"rtsp://{u}:{p}@{ip}:554/subvideo",
    ]
    seen=[]
    for x in out:
        if x not in seen:
            seen.append(x)
    return seen


async def probe(url: str) -> ProbeResult:
    cmd=[
        "ffprobe", "-v", "error",
        "-rtsp_transport", "tcp",
        "-show_streams", "-select_streams", "v:0",
        "-of", "json", url,
    ]
    try:
        proc=await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, stderr=await asyncio.wait_for(proc.communicate(), timeout=settings.rtsp_probe_timeout_seconds)
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
