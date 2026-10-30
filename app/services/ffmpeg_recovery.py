"""Small, shared FFmpeg decoder-fault detector.

RTSP cameras commonly keep the TCP session open after losing the H.264
parameter sets needed to decode the next picture.  In that state FFmpeg can
write an endless stream of ``no frame`` diagnostics while never producing a
usable JPEG.  Treat a short burst of those diagnostics as a decoder boundary
and let the owning camera loop reconnect cleanly.
"""

from __future__ import annotations

import asyncio
import time


FAULT_MARKERS = (
    "non-existing pps",
    "decode_slice_header error",
    "no frame",
    "invalid nal",
    "error while decoding",
    "corrupt decoded frame",
)


def _fault_line(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in FAULT_MARKERS)


async def drain_stderr(
    stream,
    sink: bytearray,
    *,
    fault_event: asyncio.Event | None = None,
    fault_detail: list[str] | None = None,
    limit: int = 4096,
    burst_limit: int = 6,
    burst_seconds: float = 1.5,
) -> None:
    """Drain FFmpeg stderr and signal a repeated decode fault promptly."""
    if stream is None:
        return
    fault_count = 0
    first_fault_at = 0.0
    try:
        while True:
            chunk = await stream.read(1024)
            if not chunk:
                return
            sink.extend(chunk)
            if len(sink) > limit:
                del sink[: len(sink) - limit]
            if fault_event is None:
                continue
            now = time.monotonic()
            for line in chunk.decode(errors="replace").splitlines():
                if not _fault_line(line):
                    continue
                if not first_fault_at or now - first_fault_at > burst_seconds:
                    first_fault_at = now
                    fault_count = 0
                fault_count += 1
                if fault_detail is not None:
                    fault_detail[:] = [line.strip()[:300]]
                if fault_count >= burst_limit:
                    fault_event.set()
                    return
    except asyncio.CancelledError:
        raise
    except Exception:
        return
