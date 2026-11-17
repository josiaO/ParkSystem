"""Plate-event draining is not held up by slow GPIO input scans."""

from __future__ import annotations

import asyncio
import io
from types import SimpleNamespace
from unittest.mock import patch

import app.api_main as runtime


def test_unlearned_loop_reads_one_pin_between_full_learning_scans():
    runtime._coil_full_scan_at.clear()
    with patch.object(runtime.coil_watch, "learned_index", return_value=None):
        first = runtime._coil_indexes(77)
        second = runtime._coil_indexes(77)
        assert len(first) > 1                  # learning scan
        assert second == [int(runtime.settings.coil_gpio_index or 1)]
        runtime._coil_full_scan_at[77] -= runtime.COIL_FULL_SCAN_SECONDS + 1
        assert len(runtime._coil_indexes(77)) > 1
    with patch.object(runtime.coil_watch, "learned_index", return_value=3):
        assert runtime._coil_indexes(77) == [3]


def test_coil_poll_runs_in_the_background_one_at_a_time():
    calls = []
    gate = asyncio.Event()

    async def slow_poll(camera_id, handle, background=False):
        calls.append(camera_id)
        await gate.wait()

    async def run():
        with patch.object(runtime, "_poll_coil_and_read", slow_poll):
            runtime._schedule_coil_poll(5, 1)
            runtime._schedule_coil_poll(5, 1)      # still running: not stacked
            await asyncio.sleep(0)
            assert calls == [5]
            gate.set()
            await asyncio.sleep(0.01)
            runtime._schedule_coil_poll(5, 1)
            await asyncio.sleep(0)
            assert calls == [5, 5]
            gate.set()
            await asyncio.sleep(0.01)

    asyncio.run(run())


def test_host_logs_only_failed_requests():
    import importlib.util
    import pathlib
    import sys

    host_dir = pathlib.Path(runtime.__file__).resolve().parents[2] / "tools" / "hvx_sdk_host"
    sys.path.insert(0, str(host_dir))
    try:
        spec = importlib.util.spec_from_file_location("hvx_host_under_test", host_dir / "hvx_host.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(host_dir))
    handler = module.Handler.__new__(module.Handler)
    handler.requestline = "GET /events/0 HTTP/1.1"
    handler.path = "/events/0"
    out = io.StringIO()
    with patch.object(module.sys, "stdout", out):
        handler.log_request(200, "-")
        assert out.getvalue() == ""
        handler.log_request(404, "-")
        assert "404" in out.getvalue()
