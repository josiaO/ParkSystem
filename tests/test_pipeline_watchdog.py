"""Phase 3.3: pipeline watchdog checks frames, database and HVX host."""

from __future__ import annotations

import asyncio

from app.services.pipeline_watchdog import PipelineWatchdog, WatchdogDeps


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _deps(**overrides):
    events, disconnects, restarts = [], [], []

    async def hvx_info():
        return {"available": True}

    async def video_status(handle):
        return {"callback_age_ms": 200}

    async def disconnect(handle):
        disconnects.append(handle)

    base = dict(
        check_database=lambda: 0.002,
        list_cameras=lambda: [{"id": 1, "name": "A in", "sdk": True, "sdk_handle": 7},
                              {"id": 2, "name": "B in", "sdk": False, "sdk_handle": None}],
        hvx_info=hvx_info,
        hvx_video_status=video_status,
        hvx_disconnect=disconnect,
        mediamtx_camera=lambda cid: {"roles": {"LIVE": {"ready": True, "bytes_received": 1000}}},
        restart_hvx_service=lambda: restarts.append(1) or True,
        record_event=lambda action, target, detail: events.append((action, target, detail)),
    )
    base.update(overrides)
    return WatchdogDeps(**base), events, disconnects, restarts


def test_healthy_pipeline_reports_ok_and_does_nothing():
    deps, events, disconnects, restarts = _deps()
    report = asyncio.run(PipelineWatchdog().run_once(deps))
    assert report["ok"] is True
    assert events == [] and disconnects == [] and restarts == []


def test_frozen_hvx_camera_gets_one_sdk_reset_per_cooldown():
    async def frozen(handle):
        return {"callback_age_ms": 45000}

    deps, events, disconnects, _ = _deps(hvx_video_status=frozen)
    clock = _Clock()
    dog = PipelineWatchdog(clock=clock)
    report = asyncio.run(dog.run_once(deps))
    assert report["ok"] is False
    assert disconnects == [7]
    assert events and events[0][0] == "watchdog.camera" and events[0][1] == "1"
    asyncio.run(dog.run_once(deps))          # still frozen, inside cooldown
    assert disconnects == [7]
    clock.now += dog.restart_cooldown_seconds + 1
    asyncio.run(dog.run_once(deps))
    assert disconnects == [7, 7]


def test_generic_camera_with_no_new_bytes_is_flagged_without_a_restart():
    deps, events, disconnects, _ = _deps()
    dog = PipelineWatchdog()
    assert asyncio.run(dog.run_once(deps))["ok"] is True       # first sample
    report = asyncio.run(dog.run_once(deps))                   # same byte count
    stalled = [row for row in report["cameras"] if row["camera_id"] == 2][0]
    assert stalled["ok"] is False and stalled["reason"] == "no new video bytes"
    assert disconnects == []
    assert any(event[0] == "watchdog.camera" and event[1] == "2" for event in events)


def test_hvx_host_restarted_only_after_repeated_failures():
    async def down():
        raise ConnectionError("refused")

    deps, events, _, restarts = _deps(hvx_info=down)
    dog = PipelineWatchdog()
    asyncio.run(dog.run_once(deps))
    assert restarts == []                     # one miss is not enough
    report = asyncio.run(dog.run_once(deps))
    assert restarts == [1]
    assert report["hvx_host"]["ok"] is False
    assert any(event[0] == "watchdog.hvx_host" for event in events)


def test_database_failure_is_reported_and_skips_camera_checks():
    def broken():
        raise RuntimeError("could not connect to server")

    deps, events, disconnects, _ = _deps(check_database=broken)
    report = asyncio.run(PipelineWatchdog().run_once(deps))
    assert report["database"]["ok"] is False
    assert report["cameras"] == []
    assert events[0][0] == "watchdog.database"
    assert disconnects == []


def test_desktop_health_summary_names_watchdog_problems():
    from app.desktop.desk import health_sentences

    text = health_sentences({"status": "ok", "watchdog": {"ok": False, "problems": [
        {"component": "camera:2", "detail": "no new video bytes"}]}})
    assert "camera:2" in text and "no new video bytes" in text


def test_watchdog_snapshot_feeds_health_details():
    from app.services import health, pipeline_watchdog

    dog = pipeline_watchdog.watchdog()
    dog.last_report = {"ok": False, "problems": [{"component": "database", "detail": "x"}]}
    try:
        assert health._watchdog_status()["problems"][0]["component"] == "database"
    finally:
        dog.last_report = {}
    source = open(health.__file__, encoding="utf-8").read()
    assert '"watchdog": _watchdog_status()' in source
