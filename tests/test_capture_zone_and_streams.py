"""Per-camera capture distance, desktop direct-from-host live view, loop monitor."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.services import camera_framing, loop_monitor


def test_capture_distance_is_stored_per_camera_and_kept_on_later_saves():
    profiles = camera_framing.apply_framing({}, detect_roi="0.1,0.2,0.9,0.9", detect_zoom=1.0, capture_plate_width=120)
    assert camera_framing.framing_from_profiles(profiles)["capture_plate_width"] == 120
    again = camera_framing.apply_framing(profiles, detect_roi="0.1,0.2,0.9,0.9", detect_zoom=1.5)
    assert camera_framing.framing_from_profiles(again)["capture_plate_width"] == 120
    with pytest.raises(ValueError):
        camera_framing.apply_framing({}, detect_roi="", detect_zoom=1.0, capture_plate_width=900)


def test_capture_distance_zero_uses_the_site_default():
    from app.config import settings

    assert camera_framing.effective_capture_plate_width({"capture_plate_width": 0}) == int(settings.alpr_min_capture_plate_width_px)
    assert camera_framing.effective_capture_plate_width({"capture_plate_width": 150}) == 150


def test_arrival_gate_waits_until_the_plate_is_wide_enough():
    gate = camera_framing.ArrivalGate(stable_seconds=0.0, min_plate_width_px=150)
    far = {"x1": 300, "y1": 300, "x2": 380, "y2": 330, "image_width": 1280, "image_height": 720}
    near = {"x1": 300, "y1": 300, "x2": 480, "y2": 345, "image_width": 1280, "image_height": 720}
    states = [gate.observe(far, t) for t in (0.0, 0.3, 0.6)]
    assert "ready" not in states
    states = [gate.observe(near, t) for t in (1.0, 1.3, 1.6)]
    assert "ready" in states


def test_local_host_handle_matches_the_camera_ip():
    from app.desktop import streams

    client = MagicMock()
    client.get.return_value.json.return_value = {"connections": [{"handle": 0, "ip": "192.168.10.49"}, {"handle": 1, "ip": "192.168.10.50"}]}
    assert streams.local_host_handle(client, "192.168.10.50") == 1
    assert streams.local_host_handle(client, "192.168.10.144") is None
    client.get.side_effect = OSError("no host here")
    assert streams.local_host_handle(client, "192.168.10.50") is None


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
