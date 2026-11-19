"""Per-camera capture distance, desktop direct-from-host live view, loop monitor."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.services import camera_framing, loop_monitor


# The per-camera capture distance and arrival-gate tests that were here
# covered the removed detection-zone mechanism; see test_capture_calibration.py.


def test_local_host_handle_matches_the_camera_ip():
    from app.desktop import streams

    client = MagicMock()
    client.get.return_value.json.return_value = {"connections": [{"handle": 0, "ip": "192.168.1.49"}, {"handle": 1, "ip": "192.168.1.50"}]}
    assert streams.local_host_handle(client, "192.168.1.50") == 1
    assert streams.local_host_handle(client, "192.168.1.144") is None
    client.get.side_effect = OSError("no host here")
    assert streams.local_host_handle(client, "192.168.1.50") is None


def test_loop_monitor_records_lag_and_stalls():
    loop_monitor._lags.clear()
    loop_monitor._stalls.update(count=0, worst_ms=0.0, last_at=0.0)

    async def run():
        task = asyncio.create_task(loop_monitor.monitor_loop())
        await asyncio.sleep(0.25)
        import time
        time.sleep(0.35)                 # block the loop on purpose
        await asyncio.sleep(0.25)
        task.cancel()

    asyncio.run(run())
    stats = loop_monitor.stats()
    assert stats["samples"] >= 3 and stats["stalls_over_250ms"] >= 1 and stats["max_ms"] >= 250


def test_loop_monitor_names_the_code_that_blocked_the_loop():
    loop_monitor._culprits.clear()

    def block_here():
        import time
        time.sleep(0.4)

    async def run():
        task = asyncio.create_task(loop_monitor.monitor_loop())
        await asyncio.sleep(0.25)
        block_here()
        await asyncio.sleep(0.25)
        task.cancel()

    asyncio.run(run())
    sources = loop_monitor.stats()["stall_sources"]
    assert sources and "block_here" in sources[0]
