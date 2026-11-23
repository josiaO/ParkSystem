"""At most two plate reads per car, shared through the Redis cache.

Guards the field report of 2026-11-22: a camera fired three or four triggers
per car and every one was read. Camera 2 read T922ETK three times in six
seconds; camera 3 read T669DYB correctly and then T669DVB from the next
picture of the same car.
"""

import asyncio
import socket
import threading
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.services import read_budget
from app.services.shared_cache import SharedCache


@pytest.fixture(autouse=True)
def _memory_cache(monkeypatch):
    cache = SharedCache(url="")
    monkeypatch.setattr(read_budget, "cache", cache)
    yield cache


CAM = 41


def test_confident_first_read_stops_further_reads():
    assert read_budget.allow(CAM, now=100.0)
    state = read_budget.record(CAM, "T669DYB", 0.97, now=100.5)
    assert state.settled and state.reason == "confident read"
    # The next picture of the same car is not read again.
    assert not read_budget.allow(CAM, now=101.0)
    assert not read_budget.allow(CAM, now=103.0)


def test_unsure_first_read_gets_exactly_one_more():
    read_budget.record(CAM, "T669DVB", 0.71, now=100.0)
    assert read_budget.allow(CAM, now=100.6)
    state = read_budget.record(CAM, "T669DYB", 0.93, now=101.0)
    assert state.settled
    assert state.plate == "T669DYB"            # the better of the two
    assert not read_budget.allow(CAM, now=101.5)


def test_two_unsure_reads_still_stop():
    read_budget.record(CAM, "T669DVB", 0.70, now=100.0)
    state = read_budget.record(CAM, "T669DV8", 0.65, now=101.0)
    assert state.settled and state.reason == "second read"
    assert state.plate == "T669DVB"
    assert not read_budget.allow(CAM, now=102.0)


def test_invalid_plate_is_not_confident_even_at_high_score():
    state = read_budget.record(CAM, "ZSU9000553", 0.99, valid=False, now=100.0)
    assert not state.settled
    assert read_budget.allow(CAM, now=100.5)


def test_pictures_without_a_plate_do_not_use_up_the_reads():
    for moment in (100.0, 100.5, 101.0):
        read_budget.record(CAM, "", 0.0, now=moment)
    assert read_budget.allow(CAM, now=101.5)
    assert read_budget.current(CAM, now=101.5).reads == 0


def test_next_car_after_the_lane_goes_quiet_is_read():
    read_budget.record(CAM, "T922ETK", 0.98, now=100.0)
    assert not read_budget.allow(CAM, now=102.5)          # same car, still triggering
    assert not read_budget.allow(CAM, now=105.0)          # quiet window restarted at 102.5
    assert read_budget.allow(CAM, now=110.0)              # quiet > 4 s: a new car


def test_a_car_sitting_at_the_gate_is_reread_after_the_maximum_window():
    read_budget.record(CAM, "T922ETK", 0.98, now=100.0)
    for moment in range(102, 120, 2):
        assert not read_budget.allow(CAM, now=float(moment))
    assert read_budget.allow(CAM, now=121.0)


def test_camera_reporting_a_different_plate_is_a_new_car():
    read_budget.record(CAM, "T922ETK", 0.98, now=100.0)
    assert not read_budget.allow(CAM, hint_plate="T922ETX", now=101.0)   # same car, misread hint
    assert read_budget.allow(CAM, hint_plate="T112ABC", now=101.5)


def test_loop_rising_edge_starts_a_new_car():
    from app.services.presence import PresenceWatch

    read_budget.record(CAM, "T922ETK", 0.98)
    assert not read_budget.allow(CAM)
    PresenceWatch().reported_edge(CAM, True)
    assert read_budget.allow(CAM)


def test_cameras_are_counted_separately():
    read_budget.record(CAM, "T922ETK", 0.98, now=100.0)
    assert read_budget.allow(CAM + 1, now=100.5)


def test_limit_can_be_switched_off(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "read_budget_enabled", False)
    read_budget.record(CAM, "T922ETK", 0.98, now=100.0)
    assert read_budget.allow(CAM, now=100.5)


# ---------------------------------------------------------------- Site Service read path

JPEG = b"\xff\xd8frame\xff\xd9"


def test_site_service_reads_a_confident_car_once():
    """Three camera triggers for one car: one OCR read, the rest skipped."""
    from app import api_main as api
    from app.models import Camera
    from app.services.recognition_runtime import runtime

    camera = Camera(id=CAM, name="Entry", ip_address="10.0.0.41", stream_profiles={})
    best = {"plate": "T669DYB", "plate_normalized": "T669DYB", "confidence": 0.97}
    reads = []

    def recognize(jpeg, **_):
        reads.append(jpeg)
        return {"ok": True, "backend": "fastalpr", "plates": [best], "best": best}

    async def run():
        results = []
        for _ in range(3):
            results.append(await api._run_local_alpr(None, camera, JPEG, presence=True, event_still=True))
        return results

    with patch.object(api, "should_run_local", return_value=True), \
         patch("app.services.node_scope.camera_active_on_this_installation", return_value=True), \
         patch("app.services.media_gateway.gateway.peek_detect", return_value=None), \
         patch("app.services.alpr.recognize_arrival_bytes", side_effect=recognize), \
         patch.object(api, "_persist_capture_event", AsyncMock()), \
         patch.object(api, "_crop_from_alpr", return_value=b""):
        runtime.recover(CAM)
        results = asyncio.run(run())

    assert len(reads) == 1
    assert results[0]["best"]["plate"] == "T669DYB"
    assert all(read_budget.is_skipped(r) for r in results[1:])
    from app.services import event_outcomes
    assert event_outcomes.classify(results[1]) == "skipped_already_read"


def test_operator_reads_are_never_limited():
    from app import api_main as api
    from app.models import Camera
    from app.services.recognition_runtime import runtime

    camera = Camera(id=CAM, name="Entry", ip_address="10.0.0.41", stream_profiles={})
    read_budget.record(CAM, "T669DYB", 0.97)
    calls = []
    with patch.object(api, "should_run_local", return_value=True), \
         patch("app.services.media_gateway.gateway.peek_detect", return_value=None), \
         patch("app.services.alpr.recognize_arrival_bytes",
               side_effect=lambda *a, **k: calls.append(1) or {"ok": True, "plates": [], "best": None}):
        runtime.recover(CAM)
        asyncio.run(api._run_local_alpr(None, camera, JPEG, presence=True, force=True))
    assert calls == [1]


# ---------------------------------------------------------------- shared cache


class _FakeRedis:
    """Just enough of a Redis server (GET/SET NX PX/DEL/PING) on a local port."""

    def __init__(self):
        self.data = {}
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen()
        self.port = self.sock.getsockname()[1]
        self.commands = []
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._client, args=(conn,), daemon=True).start()

    def _client(self, conn):
        f = conn.makefile("rb")
        try:
            while True:
                line = f.readline()
                if not line:
                    return
                args = []
                for _ in range(int(line[1:])):
                    size = int(f.readline()[1:])
                    args.append(f.read(size + 2)[:-2].decode())
                self.commands.append(args[0].upper())
                conn.sendall(self._run(args))
        except OSError:
            return

    def _run(self, args):
        cmd = args[0].upper()
        if cmd == "PING":
            return b"+PONG\r\n"
        if cmd == "GET":
            value = self.data.get(args[1])
            return b"$-1\r\n" if value is None else b"$%d\r\n%s\r\n" % (len(value.encode()), value.encode())
        if cmd == "SET":
            if "NX" in [a.upper() for a in args[3:]] and args[1] in self.data:
                return b"$-1\r\n"
            self.data[args[1]] = args[2]
            return b"+OK\r\n"
        if cmd == "DEL":
            return b":%d\r\n" % int(self.data.pop(args[1], None) is not None)
        return b"-ERR unknown\r\n"

    def close(self):
        self.sock.close()


def test_two_processes_share_one_count_through_redis(monkeypatch):
    server = _FakeRedis()
    try:
        url = f"redis://127.0.0.1:{server.port}/0"
        site_service, worker = SharedCache(url=url), SharedCache(url=url)
        assert site_service.backend() == "redis"
        monkeypatch.setattr(read_budget, "cache", site_service)
        read_budget.record(CAM, "T669DYB", 0.97)
        monkeypatch.setattr(read_budget, "cache", worker)
        assert not read_budget.allow(CAM)       # the worker sees the Site Service's read
        assert "zirp:reads:camera:41" in server.data
        assert "SET" in server.commands
    finally:
        server.close()


def test_cache_falls_back_to_memory_when_redis_is_down():
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()                                # nothing listens here
    cache = SharedCache(url=f"redis://127.0.0.1:{port}/0")
    started = time.monotonic()
    cache.set("k", "v", ttl=5)
    assert cache.get("k") == "v"
    assert cache.backend() == "memory"
    with cache.lock("k"):
        pass
    assert time.monotonic() - started < 2.0      # never stalls a lane


def test_memory_values_expire():
    cache = SharedCache(url="")
    cache.set("short", "x", ttl=0.05)
    time.sleep(0.1)
    assert cache.get("short") is None
