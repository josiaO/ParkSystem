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


# SITE-PC01, 23 Nov 2026: after every restart the watchdog reset cameras 0.4 s
# into their reconnect, by the session numbers stored before the restart.
# That broke logins in progress, reshuffled the numbers and once kept 2# Exit
# disconnected for 20 minutes.

def _sdk_camera_deps(connections, status_by_handle):
    async def hvx_info():
        return {"available": True, "connections": connections}

    async def video_status(handle):
        return status_by_handle.get(handle, {})

    return _deps(
        list_cameras=lambda: [{"id": 4, "name": "2# Exit", "sdk": True, "sdk_handle": 1, "ip": "192.168.10.50"}],
        hvx_info=hvx_info,
        hvx_video_status=video_status,
    )


def test_watchdog_checks_and_resets_the_session_that_belongs_to_the_camera_ip():
    # Stored number 1 now belongs to 192.168.10.144; this camera's session is 3.
    deps, events, disconnects, _ = _sdk_camera_deps(
        [{"handle": 1, "ip": "192.168.10.144"}, {"handle": 3, "ip": "192.168.10.50"}],
        {1: {"callback_age_ms": 50}, 3: {"callback_age_ms": 45000}},
    )
    report = asyncio.run(PipelineWatchdog(clock=_Clock()).run_once(deps))
    assert disconnects == [3]                    # never camera 1's session
    assert report["cameras"][0]["sdk_handle"] == 3


def test_watchdog_leaves_a_camera_that_is_still_connecting_alone():
    clock = _Clock()
    deps, events, disconnects, _ = _sdk_camera_deps([{"handle": 2, "ip": "192.168.10.50"}], {2: {}})
    dog = PipelineWatchdog(clock=clock)
    first = asyncio.run(dog.run_once(deps))
    assert disconnects == [] and first["cameras"][0]["reason"] == "camera session starting"
    clock.now += dog.startup_grace_seconds + 1     # still no video after the grace: reset it
    asyncio.run(dog.run_once(deps))
    assert disconnects == [2]


def test_watchdog_does_not_reset_by_number_when_the_camera_is_not_connected():
    deps, events, disconnects, _ = _sdk_camera_deps([{"handle": 1, "ip": "192.168.10.144"}],
                                                    {1: {"callback_age_ms": 45000}})
    report = asyncio.run(PipelineWatchdog(clock=_Clock()).run_once(deps))
    assert disconnects == []                     # the restore loop logs it in
    assert report["cameras"][0]["reason"] == "not connected on this PC's camera SDK host"
