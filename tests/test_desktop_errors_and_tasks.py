"""Desktop errors say "can't reach" vs "refused"; buttons show work in progress."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from app.desktop import common  # noqa: E402
from app.desktop.api import ApiClient, ApiError, SiteServerUnreachable, friendly_error  # noqa: E402

_APP = QApplication.instance() or QApplication([])


def test_unreachable_server_is_reported_as_unreachable(monkeypatch):
    client = ApiClient(base_url="http://192.0.2.10:8760")

    def refuse(*_args, **_kwargs):
        raise httpx.ConnectError("[WinError 10061] No connection could be made")

    monkeypatch.setattr(httpx, "get", refuse)
    with pytest.raises(SiteServerUnreachable) as caught:
        client.get("/sessions")
    text = str(caught.value)
    assert text.startswith("Can't reach the Site Server at 192.0.2.10")
    assert "10061" not in text


def test_timeout_is_not_reported_as_refusal(monkeypatch):
    client = ApiClient(base_url="http://server:8760")

    def slow(*_args, **_kwargs):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(httpx, "post", slow)
    with pytest.raises(SiteServerUnreachable) as caught:
        client.post("/sessions/1/pay", {})
    assert caught.value.timed_out
    assert "did not answer in time" in str(caught.value)


def test_refusal_keeps_the_server_reason_and_status():
    error = ApiError(409, "Visit already closed")
    assert error.status_code == 409
    assert error.detail == "Visit already closed"
    assert str(error) == "The Site Server refused: Visit already closed"
    assert str(ApiError(404, "No visit matches that QR code")) == "No visit matches that QR code"
    assert "Sign in again" in str(ApiError(401, "Invalid token"))
    assert friendly_error(httpx.ConnectError("boom")).startswith("Can't reach the Site Server")


def test_run_task_disables_the_button_while_working_and_reports_result(monkeypatch):
    monkeypatch.setattr(common, "TASKS_INLINE", True)
    button = QPushButton("Save")
    seen = []

    def work():
        seen.append((button.isEnabled(), button.text()))
        return 42

    common.run_task(None, work, lambda result: seen.append(result), buttons=button, busy_text="Saving…")
    assert seen == [(False, "Saving…"), 42]
    assert button.isEnabled() and button.text() == "Save"


def test_run_task_shows_plain_error(monkeypatch):
    monkeypatch.setattr(common, "TASKS_INLINE", True)
    button = QPushButton("Save")
    errors = []

    def work():
        raise httpx.ConnectError("[Errno 111] Connection refused")

    common.run_task(None, work, buttons=button, on_error=lambda message, exc: errors.append((message, type(exc))))
    assert errors and errors[0][0].startswith("Can't reach the Site Server")
    assert button.isEnabled()


def test_run_task_runs_off_the_ui_thread(monkeypatch):
    import threading

    monkeypatch.setattr(common, "TASKS_INLINE", False)
    button = QPushButton("Load")
    threads = []
    done = []
    worker = common.run_task(None, lambda: threads.append(threading.current_thread()) or "ok",
                             lambda result: done.append(result), buttons=button)
    assert not button.isEnabled()
    worker.wait(5000)
    for _ in range(50):
        _APP.processEvents()
        if done:
            break
    assert done == ["ok"]
    assert threads and threads[0] is not threading.main_thread()
    assert button.isEnabled()
