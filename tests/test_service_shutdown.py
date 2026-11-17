"""A service stop always ends the process; Ctrl+C is not reported as a crash."""

from __future__ import annotations

import sys
import threading
import time
from unittest.mock import patch

from app.services import runtime


def test_stop_returns_zero_and_arms_the_exit_deadline():
    armed = []
    with patch.object(runtime, "_exit_after", lambda seconds, code: armed.append((seconds, code))):
        def stopped():
            raise KeyboardInterrupt

        assert runtime.run_service(stopped) == 0
        assert runtime.run_service(lambda: 3) == 3
    assert armed == [(runtime.SHUTDOWN_DEADLINE_SECONDS, 0), (runtime.SHUTDOWN_DEADLINE_SECONDS, 3)]


def test_deadline_exits_hard_when_shutdown_hangs():
    exited = threading.Event()
    codes = []

    def fake_exit(code):
        codes.append(code)
        exited.set()

    with patch.object(runtime.os, "_exit", fake_exit):
        runtime._exit_after(0.5, 7)
        assert exited.wait(3.0)
    assert codes == [7]


def test_stop_signal_arms_the_deadline_immediately():
    """The deadline must start when the signal arrives, not when main() returns."""
    import signal

    armed = []
    previous = signal.getsignal(signal.SIGINT)
    try:
        with patch.object(runtime, "_exit_after", lambda seconds, code: armed.append(code)):
            runtime._arm_deadline_on_stop_signal(10.0)
            handler = signal.getsignal(signal.SIGINT)
            try:
                handler(signal.SIGINT, None)
            except KeyboardInterrupt:
                pass
            try:
                handler(signal.SIGINT, None)      # a second signal does not arm twice
            except KeyboardInterrupt:
                pass
        assert armed == [0]
    finally:
        signal.signal(signal.SIGINT, previous)


def test_keyboard_interrupt_is_not_written_as_a_crash():
    with patch.object(runtime, "write_crash") as crash:
        runtime.install_crash_hooks("TestService")
        try:
            sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
            crash.assert_not_called()
            sys.excepthook(RuntimeError, RuntimeError("boom"), None)
            crash.assert_called_once()
        finally:
            sys.excepthook = sys.__excepthook__


def test_site_service_waits_for_a_late_database_but_not_for_bad_config():
    import pytest

    from app import site_service

    calls, now = [], [0.0]

    def flaky(_deployment):
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("PostgreSQL connection failed: ConnectionTimeout")

    def sleep(seconds):
        now[0] += seconds

    with patch.object(site_service, "_database_startup_check", flaky):
        site_service._wait_for_database(None, sleep=sleep, clock=lambda: now[0])
    assert len(calls) == 3

    calls.clear(); now[0] = 0.0
    with patch.object(site_service, "_database_startup_check", lambda _d: (_ for _ in ()).throw(
            RuntimeError("PostgreSQL connection failed: refused"))):
        with pytest.raises(RuntimeError):
            site_service._wait_for_database(None, wait_seconds=10, sleep=sleep, clock=lambda: now[0])
    assert now[0] <= 10

    with patch.object(site_service, "_database_startup_check", lambda _d: (_ for _ in ()).throw(
            RuntimeError("PostgreSQL password could not be read"))):
        now[0] = 0.0
        with pytest.raises(RuntimeError):
            site_service._wait_for_database(None, sleep=sleep, clock=lambda: now[0])
        assert now[0] == 0.0
