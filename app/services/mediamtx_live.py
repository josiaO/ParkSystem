"""Fill the LIVE JPEG cache from the MediaMTX live path.

Desktop and ``/live.mjpeg`` read that cache. They must not poll one-shot
FFmpeg snapshots when MediaMTX is the live provider. One persistent decoder
per watched camera reads ``cam{id}``; the detect consumer separately reads
``cam{id}_detect``.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.services.media_gateway import gateway

if TYPE_CHECKING:
    from app.services.media_gateway import CameraLiveSpec

_consumers: dict[int, asyncio.Task] = {}


def _live_url(camera_id: int) -> str:
    from app.services.mediamtx import live_endpoint

    return str(live_endpoint(camera_id).get("rtsp") or "")


async def _consume(spec: "CameraLiveSpec") -> None:
    from app.infrastructure.media.registry import mediamtx_live_active
    from app.services import mediamtx
    from app.services.preview import viewers_for

    camera_id = int(spec.id)
    local_url = _live_url(camera_id)
    row = gateway._session_for(spec)
    while mediamtx_live_active(camera_id) and viewers_for(camera_id) > 0:
        if not mediamtx.running():
            await asyncio.sleep(1.0)
            continue
        stream = None
        try:
            stream = gateway.ffmpeg_jpeg_stream(
                local_url,
                scale=960,
                transport="TCP",
                session=row,
            )
            async for jpeg in stream:
                if not mediamtx_live_active(camera_id) or viewers_for(camera_id) <= 0:
                    break
                gateway.publish(
                    camera_id,
                    jpeg,
                    source="mediamtx",
                    url=local_url,
                    detect=False,
                )
                row.state = "STREAMING"
                row.source = "mediamtx"
                row.url = local_url
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            row.last_error = str(exc)[:300]
            row.state = "DEGRADED"
            await asyncio.sleep(1.0)
        finally:
            if stream is not None:
                try:
                    await stream.aclose()
                except Exception:
                    pass


def ensure_live_consumer(spec: "CameraLiveSpec") -> None:
    from app.infrastructure.media.registry import mediamtx_live_active

    camera_id = int(spec.id)
    if not mediamtx_live_active(camera_id):
        return
    task = _consumers.get(camera_id)
    if task is not None and not task.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _consumers[camera_id] = loop.create_task(_consume(spec), name=f"mediamtx-live-{camera_id}")


def stop_live_consumer(camera_id: int) -> None:
    task = _consumers.pop(int(camera_id), None)
    if task is not None and not task.done():
        task.cancel()


def stop_all() -> None:
    for camera_id in list(_consumers):
        stop_live_consumer(camera_id)
