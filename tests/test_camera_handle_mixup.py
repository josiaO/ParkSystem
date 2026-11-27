"""One lane's picture and reads must never be filed under the other lane.

Field report (SITE-PC01, 21 Nov 2026): reads at 2# Entry also appeared at
2# Exit and the other way round. The same 704 px frame was stored as both
cameras 21 ms apart (byte-identical snapshot files). Cause: the SDK host
numbers its sessions 0, 1, ... in connect order and renumbers them after a
restart or reconnect, while the video session and the event poller kept the
handle stored in the shared database. 2# Exit's session kept reading handle 0,
which by then was 2# Entry's camera; only handle 0 was being polled at all.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.services import hvx_client
from app.services.hvx_client import HVXHostClient


@pytest.fixture(autouse=True)
def _clear_maps():
    hvx_client._handle_maps.clear()
    yield
    hvx_client._handle_maps.clear()


def _host(connections, calls=None):
    host = HVXHostClient()

    async def info():
        if calls is not None:
            calls.append(1)
        return {"available": True, "connections": [dict(c) for c in connections]}

    host.info = info
    return host


def test_handle_is_looked_up_by_camera_ip():
    host = _host([{"handle": 0, "ip": "192.168.10.49"}, {"handle": 1, "ip": "192.168.10.50"}])
    assert asyncio.run(host.handle_for_ip("192.168.10.50")) == 1
    assert asyncio.run(host.handle_for_ip("192.168.10.49")) == 0
    assert asyncio.run(host.handle_for_ip("192.168.10.144")) is None     # not on this PC's host


def test_connection_list_is_cached_and_refreshed():
    calls: list[int] = []
    connections = [{"handle": 0, "ip": "192.168.10.49"}, {"handle": 1, "ip": "192.168.10.50"}]
    host = _host(connections, calls)
    for _ in range(5):
        asyncio.run(host.handle_for_ip("192.168.10.49"))
    assert len(calls) == 1
    # Host restart: the order flips. After the cache age the new map is used.
    connections[:] = [{"handle": 0, "ip": "192.168.10.50"}, {"handle": 1, "ip": "192.168.10.49"}]
    key = host.base_url.rstrip("/")
    stamp, mapping = hvx_client._handle_maps[key]
    hvx_client._handle_maps[key] = (stamp - 10.0, mapping)
    assert asyncio.run(host.handle_for_ip("192.168.10.50")) == 0


def test_unreadable_host_without_a_map_raises_so_callers_can_fall_back():
    host = HVXHostClient()

    async def info():
        raise hvx_client.HVXHostUnavailable("down")

    host.info = info
    with pytest.raises(hvx_client.HVXHostUnavailable):
        asyncio.run(host.handle_for_ip("192.168.10.49"))


def test_video_session_uses_the_live_handle_not_the_stored_one(monkeypatch):
    from app.services.media_gateway import gateway

    host = _host([{"handle": 0, "ip": "192.168.10.49"}, {"handle": 1, "ip": "192.168.10.50"}])
    # 2# Exit (.50) still has the stale handle 0 stored from before a restart.
    row = SimpleNamespace(spec=SimpleNamespace(ip="192.168.10.50", sdk_handle=0), last_error="", state="")
    assert asyncio.run(gateway._sdk_handle_now(row, host)) == 1


def test_video_session_stops_when_its_camera_is_not_on_this_host():
    from app.services.media_gateway import gateway

    host = _host([{"handle": 0, "ip": "192.168.10.49"}])
    row = SimpleNamespace(spec=SimpleNamespace(ip="192.168.10.50", sdk_handle=0), last_error="", state="")
    assert asyncio.run(gateway._sdk_handle_now(row, host)) is None
    assert row.state == "DEGRADED" and "not connected" in row.last_error


def test_event_poller_drains_each_camera_on_its_own_handle(monkeypatch):
    from app import api_main as api

    connections = [{"handle": 0, "ip": "192.168.10.49"}, {"handle": 1, "ip": "192.168.10.50"}]

    async def info(self):
        return {"available": True, "connections": connections}

    monkeypatch.setattr(HVXHostClient, "info", info)
    # Stored handles are stale: both cameras claim handle 0.
    specs = [(3, 0), (4, 0), (1, 1)]
    ips = {3: "192.168.10.49", 4: "192.168.10.50", 1: "192.168.10.144"}
    resolved = asyncio.run(api._live_hvx_specs(specs, ips))
    assert resolved == [(3, 0), (4, 1)]          # camera 1 is not on this host: skipped


# --------------------------------------------------------------- display

def test_weaker_reread_of_the_same_car_keeps_the_good_plate_on_screen():
    from app.services.preview import keeps_displayed_plate

    good = {"plate": "T790DCB", "confidence": 0.99}
    assert keeps_displayed_plate(good, 2.0, {"plate": "T290DCB", "confidence": 0.97})
    assert keeps_displayed_plate(good, 2.0, {"plate": "T760DC8", "confidence": 0.995, "pending_confirmation": True})


def test_a_better_read_or_a_different_car_replaces_the_display():
    from app.services.preview import keeps_displayed_plate

    good = {"plate": "T790DCB", "confidence": 0.95}
    assert not keeps_displayed_plate(good, 2.0, {"plate": "T790DCB", "confidence": 0.80})   # same plate: refresh
    assert not keeps_displayed_plate(good, 2.0, {"plate": "T790DCE", "confidence": 0.99})   # better read
    assert not keeps_displayed_plate(good, 2.0, {"plate": "T120ENN", "confidence": 0.50,
                                                 "pending_confirmation": True})             # next car
    assert not keeps_displayed_plate(good, 30.0, {"plate": "T290DCB", "confidence": 0.90})  # old display
    held = {"plate": "T760DC8", "confidence": 0.99, "pending_confirmation": True}
    assert not keeps_displayed_plate(held, 2.0, {"plate": "T790DCB", "confidence": 0.95})   # decided beats held


# --------------------------------------------------- restore loop (rc6 churn)
# After rc6 the server re-logged into every camera about once a minute: the
# restore loop asked "is stored handle N this camera's IP?" and reconnected
# when the shared, reshuffled number did not match, although the camera was
# connected under another number.

def test_restore_loop_does_not_relogin_a_camera_connected_under_another_number(tmp_path):
    from unittest.mock import AsyncMock, patch

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    from app import api_main
    from app.db import Base
    from app.models import Camera

    engine = create_engine(f"sqlite:///{tmp_path / 'site.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add_all([Camera(id=3, name="2# Entry", ip_address="192.168.10.49", sdk_handle=0),
                    Camera(id=4, name="2# Exit", ip_address="192.168.10.50", sdk_handle=1)])
        db.commit()
    try:
        with patch.object(api_main, "short_session", factory), \
             patch.object(api_main, "_hvx_restore_attempts", {}), \
             patch.object(api_main, "apply_sdk_connect", AsyncMock()) as relogin:
            asyncio.run(api_main._restore_hvx_sessions({"available": True, "connections": [
                {"handle": 3, "ip": "192.168.10.49"}, {"handle": 1, "ip": "192.168.10.50"}]}))
            relogin.assert_not_awaited()
        with factory() as db:
            cam = db.get(Camera, 3)
            assert cam.sdk_handle == 3 and cam.stream_profiles["MAIN"]["uri"] == "sdk://handle/3"
            assert db.get(Camera, 4).sdk_handle == 1
    finally:
        engine.dispose()


def test_video_loop_follows_a_changed_session_without_failing(monkeypatch):
    """The session number changes mid-stream: keep streaming, no back-off."""
    from app.services.media_gateway import gateway

    calls = {"n": 0}

    async def handle_now(row, host):
        calls["n"] += 1
        return 0 if calls["n"] <= 2 else 3

    reads: list[int] = []

    class Host:
        last_live_seq: dict = {}
        last_live_meta: dict = {}

        async def live_jpeg(self, handle):
            reads.append(handle)
            if len(reads) >= 4:
                row.viewers = 0
                row.wanted = lambda: False
            return b"\xff\xd8frame\xff\xd9"

        async def video_status(self, handle):
            return {}

    monkeypatch.setattr("app.services.media_gateway.HVXHostClient", lambda *a, **k: Host(), raising=False)
    monkeypatch.setattr(gateway, "_sdk_handle_now", handle_now)
    monkeypatch.setattr(gateway, "publish", lambda *a, **k: object())
    monkeypatch.setattr(gateway, "_stale_fresh", lambda *a, **k: False)
    from app.services.media_gateway import StreamSession, CameraLiveSpec

    spec = CameraLiveSpec(id=3, ip="192.168.10.49", username="", password="", rtsp_url="", sdk_handle=0)
    row = StreamSession(spec=spec)
    row.viewers = 1
    result = asyncio.run(gateway._sdk_frames(row))
    assert reads[0] == 0 and set(reads[1:]) == {3}
    assert row.reconnects == 0 and row.decoder_restarts == 0
