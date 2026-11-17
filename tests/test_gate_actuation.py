"""Boom commands go to the right camera and are not held up by a dead Board relay."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services import gates
from app.services.board_tcp import BoardResult
from app.services.led_udp import LedResult


def _camera(**kw):
    base = dict(id=4, name="2# Exit", ip_address="192.168.1.50", sdk_handle=0, lane_direction="EXIT",
                enabled=True, controller_ip="192.168.1.67", display_ip="192.168.1.68")
    return SimpleNamespace(**{**base, **kw})


def test_live_handle_wins_over_stale_stored_handle():
    handle, note = gates.resolve_live_handle(_camera(sdk_handle=0), {"192.168.1.49": 0, "192.168.1.50": 1})
    assert handle == 1 and "stale" in note


def test_camera_not_connected_on_this_host_is_refused():
    handle, note = gates.resolve_live_handle(_camera(), {"192.168.1.49": 0})
    assert handle is None and "not connected" in note


def test_unknown_host_list_falls_back_to_stored_handle():
    assert gates.resolve_live_handle(_camera(sdk_handle=1), None)[0] == 1


def test_gpio_pulse_uses_live_handle_and_never_pulses_an_unconnected_camera():
    hvx = SimpleNamespace(gpio_pulse=AsyncMock(return_value={"ok": True}))
    result = asyncio.run(gates._gpio_pulse(hvx, _camera(sdk_handle=0), dry_run=False, connections={"192.168.1.50": 1}))
    assert hvx.gpio_pulse.await_args.kwargs["handle"] == 1 and result["handle_note"]
    hvx.gpio_pulse.reset_mock()
    result = asyncio.run(gates._gpio_pulse(hvx, _camera(), dry_run=False, connections={}))
    assert result["ok"] is False and hvx.gpio_pulse.await_count == 0


def _open(board_delay: float, gpio_ok: bool):
    async def slow_board(*a, **k):
        await asyncio.sleep(board_delay)
        return BoardResult(False, "192.168.1.67", 5000, "stx_open", "", "Board TCP failed: timed out")

    gate = SimpleNamespace(name="2#")
    with patch.object(gates, "_host_connections", AsyncMock(return_value={"192.168.1.50": 1})), \
            patch.object(gates, "_gpio_pulse", AsyncMock(return_value={"ok": gpio_ok})), \
            patch.object(gates, "send_board_command", slow_board), \
            patch.object(gates, "send_led_text", AsyncMock(return_value=LedResult(True, "x", 6666, "t", 3, "ok"))), \
            patch.object(gates, "HVXHostClient", lambda: SimpleNamespace()):
        started = time.perf_counter()
        result = asyncio.run(gates.PhysicalGateController().open(gate, [_camera()], "test", side="EXIT"))
        return result, time.perf_counter() - started


def test_dead_board_does_not_delay_a_successful_camera_relay():
    result, seconds = _open(board_delay=1.5, gpio_ok=True)
    assert result.ok is True
    assert seconds < 1.0, seconds
    assert "grace" in result.actuators[0]["board"]["message"]


def test_board_is_awaited_when_the_camera_relay_failed():
    result, seconds = _open(board_delay=0.6, gpio_ok=False)
    assert result.ok is False and seconds >= 0.6
