"""Ground loops on the cameras' vehicle-detector input (REPORT_MESS_LOOP_DETECTOR).

ParkWatch never commanded the snapshots (1 Net_ImageSnap in 2,124 captures):
the camera snaps when its loop trips and reports the loop edge. Zirp reads
the same report, so a lane needs no legacy system and no extra wiring.
"""

from __future__ import annotations

import asyncio
import ctypes
import sys
import threading
from collections import deque
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT / "tools" / "hvx_sdk_host", ROOT / "tests" / "fakes"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import hvx_sdk  # noqa: E402


def test_host_decodes_the_loop_detector_report():
    sdk = object.__new__(hvx_sdk.HVXSDK)
    sdk._lock = threading.RLock()
    sdk._pending_reports = {}
    for state in (1, 0):
        message = (ctypes.c_ubyte * 4)(0, state, 0, 0)
        assert sdk._on_report(3, 7, ctypes.addressof(message), None) == 0
    rows = list(sdk._pending_reports[3])
    assert [(r["msg_type"], r["loop_index"], r["loop_state"]) for r in rows] == [(7, 0, 1), (7, 0, 0)]


def _run_poll(reports, *, camera_captures: bool):
    from app import api_main as api
    from app.services.presence import coil_watch

    host = AsyncMock()
    host.scan_gpio.return_value = []
    host.drain_reports.side_effect = [list(r) for r in reports]
    calls = {"passage": 0}

    async def passage(_camera_id):
        calls["passage"] += 1

    async def run():
        with patch.object(api, "HVXHostClient", return_value=host), \
             patch.object(api, "LOOP_CAPTURE_WAIT_SECONDS", 0.05), \
             patch.object(api, "_complete_passage_from_sensor", side_effect=passage), \
             patch.object(api, "_read_presence_now", new=AsyncMock()) as snapshot, \
             patch("app.services.manual_open.boom_indexes_cached", return_value=set()):
            states = []
            for _ in reports:
                await api._poll_coil_and_read(4401, 9, background=True)
                states.append(coil_watch.occupied(4401))
                if camera_captures:
                    api._last_native_event_at[4401] = api.time.monotonic() + 1
                await asyncio.sleep(0.12)
            return states, snapshot.await_count

    try:
        states, snapshots = asyncio.run(run())
    finally:
        api._last_native_event_at.pop(4401, None)
        coil_watch.reported_edge(4401, False, source="test")
    return states, snapshots, calls["passage"]


def test_loop_edges_give_presence_and_passage_without_a_duplicate_snapshot():
    states, snapshots, passages = _run_poll(
        [[{"msg_type": 7, "loop_index": 0, "loop_state": 1}], [{"msg_type": 7, "loop_index": 0, "loop_state": 0}]],
        camera_captures=True,
    )
    assert states == [True, False]           # car on the loop, then off it
    assert passages == 1                     # the falling edge confirms passage
    assert snapshots == 0                    # the camera snapped by itself


def test_a_silent_camera_gets_a_commanded_snapshot_on_the_loop_edge():
    _states, snapshots, _passages = _run_poll(
        [[{"msg_type": 7, "loop_index": 0, "loop_state": 1}]], camera_captures=False,
    )
    assert snapshots == 1
