"""Sample JPEGs from local MediaMTX RTSP into the gateway DETECT buffer (latest-frame, bounded)."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from app.config import settings
from app.services.media_gateway import gateway

if TYPE_CHECKING:
    from app.services.media_gateway import CameraLiveSpec

_consumers: dict[int, asyncio.Task] = {}


def _detect_url(camera_id: int) -> str:
    return f"rtsp://127.0.0.1:8554/cam{int(camera_id)}_detect"


async def _consume(spec: "CameraLiveSpec") -> None:
    from app.infrastructure.media.registry import mediamtx_detect_active
    from app.services import mediamtx
    from app.services.preview import viewers_for

    camera_id = int(spec.id)
    local_url = _detect_url(camera_id)
    ai_fps = float(getattr(settings, "detect_fps", 5.0) or 5.0)
    interval = 1.0 / max(ai_fps, 1.0)
    row = gateway._session_for(spec)
    row.detect_consumers = max(row.detect_consumers, 1)
    last_sample = 0.0
    while mediamtx_detect_active(camera_id) and (row.detect_consumers > 0 or viewers_for(camera_id) > 0):
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
                if not mediamtx_detect_active(camera_id):
                    break
                if row.detect_consumers <= 0 and viewers_for(camera_id) <= 0:
                    break
                now = time.monotonic()
                if now - last_sample >= interval:
                    gateway.publish_detect(
                        camera_id,
                        jpeg,
                        source="mediamtx",
                        url=local_url,
                    )
                    last_sample = now
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            row.last_error = str(exc)[:300]
            await asyncio.sleep(1.0)
        finally:
            if stream is not None:
                try:
                    await stream.aclose()
                except Exception:
                    pass
    row.detect_consumers = max(0, row.detect_consumers - 1)


def ensure_detect_consumer(spec: "CameraLiveSpec") -> None:
    from app.infrastructure.media.registry import mediamtx_detect_active

    camera_id = int(spec.id)
    if not mediamtx_detect_active(camera_id):
        return
    task = _consumers.get(camera_id)
    if task is not None and not task.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _consumers[camera_id] = loop.create_task(_consume(spec), name=f"mediamtx-detect-{camera_id}")


def stop_detect_consumer(camera_id: int) -> None:
    task = _consumers.pop(int(camera_id), None)
    if task is not None and not task.done():
        task.cancel()
    gateway.release_detect(int(camera_id))


def stop_all() -> None:
    for camera_id in list(_consumers):
        stop_detect_consumer(camera_id)
