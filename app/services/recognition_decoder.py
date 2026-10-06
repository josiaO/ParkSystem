"""Lightweight recognition decoder.

MediaMTX owns the camera. This process only decodes the local MediaMTX RTSP
path into JPEGs for FastALPR. It does not reconnect the physical camera, fan
out browsers, or keep a media session.
"""

from __future__ import annotations

import asyncio
from contextlib import aclosing
from urllib.parse import urlparse

from app.services.frame_grab import ffmpeg_bin

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
_JPEG_SOI = b"\xff\xd8"
_JPEG_EOI = b"\xff\xd9"


def _latest_jpeg(buf: bytes) -> tuple[bytes, bytes]:
    """Keep the newest complete JPEG and drop frames already stacked in the pipe."""
    latest = b""
    while True:
        start = buf.find(_JPEG_SOI)
        if start < 0:
            return latest, (buf[-1:] if buf.endswith(b"\xff") else b"")
        end = buf.find(_JPEG_EOI, start + 2)
        if end < 0:
            return latest, buf[start:]
        latest = buf[start:end + 2]
        buf = buf[end + 2:]


def require_local_mediamtx(url: str) -> str:
    """Recognition may read only the MediaMTX listener on this machine."""
    parsed = urlparse(str(url or "").strip())
    host = (parsed.hostname or "").lower()
    port = parsed.port or (554 if parsed.scheme == "rtsp" else 0)
    path = parsed.path or ""
    if parsed.scheme != "rtsp" or host not in _LOCAL_HOSTS or port != 8554 or path in {"", "/"}:
        raise ValueError("recognition decoder reads only rtsp://127.0.0.1:8554/<path>")
    return str(url).strip()


def decoder_command(url: str, *, sample_fps: float, scale: int = 960) -> list[str]:
    """Remux is MediaMTX's job. This command only decodes, at the sample rate."""
    binary = ffmpeg_bin()
    if not binary:
        raise RuntimeError("ffmpeg is not installed")
    local = require_local_mediamtx(url)
    fps = max(1.0, min(float(sample_fps), 10.0))
    width = max(160, min(int(scale), 1920))
    return [
        binary,
        "-hide_banner",
        "-loglevel", "error",
        "-rtsp_transport", "tcp",
        "-fflags", "nobuffer+discardcorrupt",
        "-flags", "low_delay",
        "-probesize", "32",
        "-analyzeduration", "0",
        "-i", local,
        "-an",
        "-vf", f"fps={fps:g},scale={width}:-2",
        "-f", "image2pipe",
        "-vcodec", "mjpeg",
        "-q:v", "8",
        "pipe:1",
    ]


async def _drain_bounded(stream, sink: bytearray, limit: int = 4096) -> None:
    if stream is None:
        return
    try:
        while True:
            chunk = await stream.read(1024)
            if not chunk:
                return
            sink.extend(chunk)
            if len(sink) > limit:
                del sink[: len(sink) - limit]
    except asyncio.CancelledError:
        raise
    except Exception:
        return


async def _terminate(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    try:
        proc.terminate()
    except ProcessLookupError:
        await proc.wait()
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=2.0)
    except Exception:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=1.0)
        except Exception:
            pass


class RecognitionDecoder:
    """One FFmpeg process for one recognition lane. Callers reconnect."""

    def __init__(self) -> None:
        self.pid: int | None = None
        self.last_error: str = ""
        self._proc: asyncio.subprocess.Process | None = None

    async def frames(self, url: str, *, sample_fps: float, scale: int = 960):
        if self._proc is not None and self._proc.returncode is None:
            await _terminate(self._proc)
            self._proc = None
            self.pid = None
        cmd = decoder_command(url, sample_fps=sample_fps, scale=scale)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=256 * 1024,
        )
        self._proc = proc
        self.pid = proc.pid
        if proc.stdout is None:
            await _terminate(proc)
            self._proc = None
            self.pid = None
            raise RuntimeError("recognition decoder produced no output")
        errors = bytearray()
        stderr_task = asyncio.create_task(_drain_bounded(proc.stderr, errors))
        buf = b""
        from app.config import settings

        timeout = float(getattr(settings, "stream_read_timeout_seconds", 3.0) or 3.0)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        try:
            while True:
                # Partial bytes must not keep a broken stream alive forever.
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise TimeoutError("recognition decoder produced no complete frame")
                chunk = await asyncio.wait_for(proc.stdout.read(65536), timeout=remaining)
                if not chunk:
                    text = errors.decode(errors="replace").strip()
                    raise RuntimeError(text[-300:] or "recognition decoder ended")
                buf += chunk
                if len(buf) > 1_000_000:
                    start = buf.rfind(_JPEG_SOI)
                    buf = buf[start:] if start > 0 else b""
                jpeg, buf = _latest_jpeg(buf)
                if jpeg[:2] == _JPEG_SOI and jpeg.endswith(_JPEG_EOI):
                    deadline = loop.time() + timeout
                    yield jpeg
        finally:
            stderr_task.cancel()
            await asyncio.gather(stderr_task, return_exceptions=True)
            await _terminate(proc)
            if self._proc is proc:
                self._proc = None
                self.pid = None
            if errors and not self.last_error:
                self.last_error = errors.decode(errors="replace")[-300:]


async def iter_jpegs(url: str, *, sample_fps: float, scale: int = 960, on_pid=None):
    """One decoder lifetime. The worker closes this before opening another."""
    decoder = RecognitionDecoder()
    async with aclosing(decoder.frames(url, sample_fps=sample_fps, scale=scale)) as frames:
        async for jpeg in frames:
            if on_pid is not None and decoder.pid:
                on_pid(decoder.pid)
            yield jpeg
