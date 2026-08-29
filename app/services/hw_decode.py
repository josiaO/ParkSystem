"""Detect Windows hardware decode. Never hard-code a decoder that may not exist."""

from __future__ import annotations

import asyncio
import shutil
from functools import lru_cache


def ffmpeg_bin() -> str | None:
    return shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")


def _parse_hwaccels(text: str) -> list[str]:
    names: list[str] = []
    for line in (text or "").splitlines():
        name = line.strip().lower()
        if not name or name.startswith("hardware") or name.startswith("ffmpeg"):
            continue
        if name not in names:
            names.append(name)
    return names


async def list_hwaccels() -> list[str]:
    binary = ffmpeg_bin()
    if not binary:
        return []
    try:
        proc = await asyncio.create_subprocess_exec(
            binary, "-hide_banner", "-hwaccels",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3.0)
    except (FileNotFoundError, asyncio.TimeoutError, Exception):
        return []
    return _parse_hwaccels(stdout.decode(errors="replace"))


def summarize(hwaccels: list[str]) -> dict:
    names = [str(item).lower() for item in hwaccels]
    intel = any(item in names for item in ("qsv", "vaapi"))
    nvidia = any(item in names for item in ("cuda", "nvdec", "cuvid"))
    amd = any(item in names for item in ("amf", "d3d11va", "dxva2"))
    # Prefer software until Hardware Lab measures a stable gain.
    return {
        "ffmpeg": bool(ffmpeg_bin()),
        "hwaccels": names,
        "intel": intel,
        "nvidia": nvidia,
        "amd": amd,
        "path": "software",
        "enabled": False,
        "note": "Hardware decoding is reported only. SmartPark uses software decode until a site measures it as stable and faster.",
    }


@lru_cache(maxsize=1)
def cached_summary() -> dict:
    return summarize([])


async def detect_decode_path() -> dict:
    names = await list_hwaccels()
    return summarize(names)
