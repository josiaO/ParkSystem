"""Zirp's snapshot is taken when the plate is inside the calibration.

The camera takes Zirp's snapshot about half a second after it is asked. The
capture gate tracks the plate on the live video and fires that much early, so
the snapshot (and its crop) shows the plate inside the zone. A snapshot that
misses the plate falls back to the last in-zone live frame.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.services import capture_calibration as cc
from app.services import zirp_trigger

# Zone from y 0.40 to 0.98 (normalised), travel downwards, live picture 704 x 576.
ZONE = [[0.10, 0.40], [0.90, 0.40], [0.95, 0.98], [0.05, 0.98]]
W, H = 704, 576


def _config(**extra):
    return {**cc.DEFAULTS, "enabled": True, "zone": ZONE, "trigger_line": None, "end_line": None,
            "reference_width": W, "enforce": dict(cc.DEFAULT_ENFORCE), **extra}


def _frame(gate, cy, t, lead):
    x, y = 0.5 * W, cy * H
    box = {"x1": x - 40, "y1": y - 12, "x2": x + 40, "y2": y + 12, "image_width": W, "image_height": H,
           "confidence": 0.9}
    candidates = cc.evaluate_frame(b"", [box], gate.config)
    return gate.observe(candidates, [box], b"\xff\xd8frame\xff\xd9", t, lead_seconds=lead)


def _gate():
    gate = cc.CaptureGate()
    gate.configure(_config())
    return gate


def test_moving_plate_fires_before_it_reaches_the_zone_by_the_snapshot_delay():
    gate = _gate()
    # 0.2 of the picture per second towards the zone. Delay 0.55 s, aimed with
    # a 0.2 s margin: 0.35 s ahead = 0.07 of the picture.
    assert _frame(gate, 0.20, 0.00, 0.55) == "far"
    assert _frame(gate, 0.25, 0.25, 0.55) == "far"       # aimed 0.32: outside
    assert _frame(gate, 0.30, 0.50, 0.55) == "far"       # aimed 0.37: outside
    assert _frame(gate, 0.35, 0.75, 0.55) == "ready"     # aimed 0.42: inside even if the snapshot comes early
    assert gate.fired_on_prediction
    assert gate.last_eligible is None                     # nothing in the zone yet to fall back on


def test_a_plate_stopped_before_the_zone_never_fires():
    gate = _gate()
    for i in range(8):
        assert _frame(gate, 0.30, i * 0.25, 0.55) == "far"


def test_a_plate_already_inside_the_zone_fires_at_once_without_a_collecting_window():
    gate = _gate()
    assert _frame(gate, 0.60, 0.0, 0.55) == "ready"
    assert not gate.fired_on_prediction
    assert gate.last_eligible is not None and gate.selected is gate.last_eligible


def test_without_a_snapshot_the_gate_still_collects_the_best_live_frame():
    gate = _gate()                                         # lead 0: the live frame itself is read
    assert _frame(gate, 0.60, 0.0, 0.0) == "collecting"


def test_snapshot_delay_is_learned_per_camera():
    zirp_trigger.reset()
    assert zirp_trigger.lead_seconds(7) == pytest.approx(zirp_trigger.DEFAULT_DELAY_SECONDS)
    with patch.object(zirp_trigger.time, "perf_counter_ns", return_value=1_000_000_000):
        zirp_trigger.fired(7, mode="snapshot")
    assert not zirp_trigger.claim(8, 1_800_000_000)       # another camera's picture
    assert zirp_trigger.claim(7, 1_800_000_000)           # 0.8 s later
    assert zirp_trigger.lead_seconds(7) == pytest.approx(0.55 + 0.3 * (0.8 - 0.55), abs=0.001)
    assert not zirp_trigger.claim(7, 1_900_000_000)       # one answer per request
    zirp_trigger.reset()


def test_a_picture_long_after_the_request_is_not_its_answer():
    zirp_trigger.reset()
    with patch.object(zirp_trigger.time, "perf_counter_ns", return_value=1_000_000_000):
        zirp_trigger.fired(7, mode="snapshot")
    assert not zirp_trigger.claim(7, 4_000_000_000)       # 3 s later: not ours
    assert not zirp_trigger.expire(7)
    zirp_trigger.reset()


def test_a_missed_snapshot_reads_the_last_in_zone_live_frame():
    from app import api_main as api

    gate = cc.gate_for(9911)
    gate.reset()
    gate.configure(_config())
    assert _frame(gate, 0.60, api.time.monotonic(), 0.55) == "ready"
    in_zone = gate.last_eligible
    with patch.object(api, "_read_fallback_frame", new=AsyncMock()) as fallback:
        async def run():
            api._zirp_snapshot_missed(9911, "calibration_refused")
            await asyncio.sleep(0)
        asyncio.run(run())
    fallback.assert_awaited_once()
    assert fallback.await_args.args[1] is in_zone
    assert gate.last_eligible is None                     # used once


def test_a_missed_snapshot_without_an_in_zone_frame_lets_the_gate_try_again():
    from app import api_main as api

    gate = cc.gate_for(9912)
    gate.reset()
    gate.configure(_config())
    for cy, t in ((0.20, 0.0), (0.25, 0.25), (0.30, 0.5), (0.35, 0.75)):
        _frame(gate, cy, t, 0.55)
    assert gate._fired
    api._zirp_snapshot_missed(9912, "no_plate_box")
    assert not gate._fired and gate._ocr_count == 1


def test_only_misses_trigger_the_fallback():
    from app import api_main as api

    assert api.ZIRP_SNAPSHOT_MISSES == {"no_plate_box", "calibration_refused", "unread", "not_run"}
    with patch.object(api, "_zirp_snapshot_missed") as missed:
        api._note_event_result(1, {"zirp_requested": True}, b"", {"ok": True, "best": {"plate": "T123ABC"}}, False)
        missed.assert_not_called()
        api._note_event_result(1, {"zirp_requested": True}, b"",
                               {"ok": True, "best": None, "calibration_refused": True}, False)
        missed.assert_called_once_with(1, "calibration_refused")
        api._note_event_result(1, {}, b"", {"ok": True, "best": None, "calibration_refused": True}, False)
        assert missed.call_count == 1                     # not Zirp's snapshot: no fallback
