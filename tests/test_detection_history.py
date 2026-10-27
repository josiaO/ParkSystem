from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import asyncio
from unittest.mock import patch

from app.services import preview
from app.services.captures import _dedupe_detection_rows


def _capture(number: int, seconds_ago: int, *, camera_id: int = 4, side: str = "EXIT", visit: str = ""):
    return SimpleNamespace(
        id=number,
        camera_id=camera_id,
        lane_direction=side,
        plate="T125EHK",
        plate_raw="",
        visit_id=visit,
        created_at=datetime.now(timezone.utc) - timedelta(seconds=seconds_ago),
    )


def test_detection_history_collapses_short_repeat_reads_but_keeps_later_visit():
    newest = _capture(3, 0, visit="visit-3")
    repeat = _capture(2, 4, visit="visit-2")
    later = _capture(1, 20, visit="visit-1")

    rows = _dedupe_detection_rows([newest, repeat, later], limit=10)

    assert [row.id for row in rows] == [3, 1]


def test_stale_mjpeg_closes_cleanly_and_requests_camera_only_restart():
    async def timeout(awaitable, *_args, **_kwargs):
        awaitable.close()
        raise asyncio.TimeoutError

    async def exercise():
        row = preview.PreviewState(jpeg=b"\xff\xd8live\xff\xd9", seq=1)
        with patch.object(preview, "get_state", return_value=row), \
             patch.object(preview, "live_is_current", return_value=False), \
             patch.object(preview.gateway, "restart_decoder", return_value=True) as restart, \
             patch.object(preview.asyncio, "wait_for", new=timeout):
            stream = preview.mjpeg_from_cache(4)
            first = await stream.__anext__()
            assert b"\xff\xd8live\xff\xd9" in first
            try:
                await stream.__anext__()
            except StopAsyncIteration:
                pass
            else:
                raise AssertionError("stale stream should close for browser reconnect")
            restart.assert_called_once_with(4)

    asyncio.run(exercise())
