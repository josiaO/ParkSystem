"""Live view keeps up with an SDK host restart and returns from the relay on its own."""

from __future__ import annotations

import time

import httpx
import pytest

pytest.importorskip("PySide6")

from app.desktop import cpu_watch, streams  # noqa: E402
from app.desktop.frame_mailbox import FrameOrderGuard  # noqa: E402


class _Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_order_guard_follows_a_restarted_source_after_a_short_wait():
    clock = _Clock()
    guard = FrameOrderGuard(clock=clock)
    assert guard.accept(b"a", source="camera", seq=250)
    # Host restarted and counts from 1 again (a drop smaller than RESET_GAP).
    assert not guard.accept(b"b", source="camera", seq=5)
    clock.now += 1.0
    assert not guard.accept(b"c", source="camera", seq=6)       # still treated as old
    clock.now += 1.5
    assert guard.accept(b"d", source="camera", seq=7)           # stuck > 2 s: follow the new numbering
    assert guard.accept(b"e", source="camera", seq=8)
    assert not guard.accept(b"f", source="camera", seq=7)       # and order is enforced again


def test_direct_path_adopts_the_host_numbering_after_a_restart(monkeypatch):
    """after=<old high number> must not wait forever once the host counts from 1."""
    jpeg = b"\xff\xd8frame"
    asked = []

    def reply(request):
        if request.url.path == "/info":
            return httpx.Response(200, json={"connections": [{"ip": "10.0.0.9", "handle": 0}]})
        after = int(request.url.params["after"])
        asked.append(after)
        if len(asked) == 1:
            return httpx.Response(200, content=jpeg + b"1", headers={"x-frame-seq": "4000"})
        if after >= 4000:                        # restarted host: current number is 12
            return httpx.Response(204, headers={"x-frame-seq": "12"})
        return httpx.Response(200, content=jpeg + str(after + 1).encode(), headers={"x-frame-seq": str(max(13, after + 1))})

    real = httpx.Client
    monkeypatch.setattr(streams.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(reply), **{k: v for k, v in kw.items() if k != "trust_env"}))
    monkeypatch.setattr(streams, "_camera_ip", lambda cid: "10.0.0.9")
    stream = streams.MjpegStream(3)
    got = []
    stream.mailbox.offer = lambda frame, seq=None: got.append(seq) or False
    original_sleep = time.sleep

    def stop_after_frames(seconds):
        original_sleep(0)
    monkeypatch.setattr(streams.time, "sleep", stop_after_frames)

    def offer(frame, seq=None):
        got.append(seq)
        if len(got) >= 3:
            stream._stop = True
        return False
    stream.mailbox.offer = offer
    assert stream._run_from_local_host() is True
    assert got[0] == 4000 and got[1] < 4000, got        # frames flow again after the restart
    assert 0 in asked or any(a < 4000 for a in asked[2:]), asked


def test_relay_hands_back_to_the_local_host_when_it_returns(monkeypatch):
    stream = streams.MjpegStream(3)
    calls = []

    def direct():
        calls.append("direct")
        return len(calls) >= 3          # local host is back on the second attempt

    stream._run_from_local_host = direct
    monkeypatch.setattr(stream, "_run_relay", lambda probe_local=False: calls.append(f"relay probe={probe_local}") or True)
    stream.run()
    assert calls == ["direct", "relay probe=True", "direct"]


def test_cpu_watch_names_the_busy_code():
    import threading

    stop = threading.Event()

    def busy_loop_for_test():
        while not stop.is_set():
            sum(range(2000))

    worker = threading.Thread(target=busy_loop_for_test, name="busy-test")
    worker.start()
    try:
        top = cpu_watch.sample_stacks(seconds=0.3, every=0.01)
    finally:
        stop.set()
        worker.join()
    assert any("busy-test" in place and "busy_loop_for_test" in place for place, _ in top), top


def test_http_clients_share_one_tls_context():
    """A new TLS context per request cost ~0.9 s CPU on the site PC (2.7 cores in the desktop)."""
    import app  # noqa: F401  (installs the shared context)
    import httpx._transports.default as transports

    first = httpx.Client(trust_env=False)
    second = httpx.Client(trust_env=False)
    try:
        assert first._transport._pool._ssl_context is second._transport._pool._ssl_context
    finally:
        first.close()
        second.close()
    custom = httpx.Client(verify=False)
    try:
        assert custom._transport._pool._ssl_context is not first._transport._pool._ssl_context
    finally:
        custom.close()
    assert getattr(transports.create_ssl_context, "_zirp_cached", False)
