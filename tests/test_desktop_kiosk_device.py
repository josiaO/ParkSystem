"""Phase 2.3 desktop: kiosk enrolment and silent re-authentication."""

from __future__ import annotations

from unittest.mock import PropertyMock, patch

import httpx

from app.config import Settings
from app.desktop.api import ApiClient

_APP = None


class _Response:
    def __init__(self, status: int, body: dict):
        self.status_code = status
        self.is_success = 200 <= status < 300
        self._body = body
        self.text = str(body)
        self.content = b""

    def json(self):
        return self._body


def _login_body(token: str) -> dict:
    return {"token": token, "username": "kiosk-device:kiosk-1", "permissions": ["kiosk.use"],
            "navigation": [], "modules": {}}


def test_expired_kiosk_session_signs_in_again_and_retries_once():
    calls = []

    def fake_get(url, headers=None, **_kwargs):
        calls.append(("GET", headers.get("Authorization")))
        if headers.get("Authorization") == "Bearer old":
            return _Response(401, {"detail": "Session expired"})
        return _Response(200, {"ok": True})

    def fake_post(url, json=None, **_kwargs):
        calls.append(("POST", url.rsplit("/", 2)[-2:]))
        return _Response(200, _login_body("fresh" if len([c for c in calls if c[0] == "POST"]) > 1 else "old"))

    client = ApiClient(base_url="http://server:8760")
    with patch.object(httpx, "get", fake_get), patch.object(httpx, "post", fake_post):
        client.login_device("kiosk-1", "secret")
        assert client.token == "old"
        assert client.get("/p/x/status") == {"ok": True}
    assert client.token == "fresh"
    assert [c[0] for c in calls] == ["POST", "GET", "POST", "GET"]


def test_person_sessions_are_not_silently_renewed():
    def fake_get(url, headers=None, **_kwargs):
        return _Response(401, {"detail": "Session expired"})

    client = ApiClient(base_url="http://server:8760")
    client.token = "person"
    with patch.object(httpx, "get", fake_get), patch.object(httpx, "post") as post:
        try:
            client.get("/auth/me")
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 401
        else:
            raise AssertionError("expected 401")
    post.assert_not_called()


def test_kiosk_enrolment_keeps_the_credential_out_of_the_json(tmp_path):
    from app.desktop import kiosk_device
    from app.infrastructure.secrets import MemorySecretStore, set_secret_store

    set_secret_store(MemorySecretStore())
    try:
        with patch.object(Settings, "data_dir", new_callable=PropertyMock, return_value=tmp_path):
            assert kiosk_device.load_device() is None
            kiosk_device.enrol("kiosk-abc", "very-secret-credential")
            assert "very-secret-credential" not in (tmp_path / "kiosk_device.json").read_text()
            assert kiosk_device.enrolled_device_id() == "kiosk-abc"
            assert kiosk_device.load_device() == ("kiosk-abc", "very-secret-credential")
            kiosk_device.forget()
            assert kiosk_device.load_device() is None
            assert kiosk_device.enrolled_device_id() == ""
    finally:
        set_secret_store(None)


def test_admin_kiosk_section_lists_creates_and_revokes():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QMessageBox

    import app.desktop.main as desktop

    global _APP
    _APP = QApplication.instance() or QApplication([])  # keep a reference: a freed app crashes Qt
    calls = []
    devices = [{"id": 1, "device_id": "kiosk-1", "name": "Exit B", "status": "ACTIVE",
                "last_seen_at": None, "created_at": "2026-11-15T08:00:00"}]

    class FakeApi:
        def get(self, path):
            calls.append(("GET", path))
            return devices

        def post(self, path, payload=None):
            calls.append(("POST", path))
            return {**devices[0], "credential": "shown-once"}

        def can(self, permission):
            return True

    shown = []
    # Plain functions, not MagicMocks: a mock keeps the widget in call_args,
    # and freeing a QWidget tree through Python's cyclic GC crashes PySide.
    with patch.object(desktop, "api", FakeApi()), \
         patch.object(desktop.QInputDialog, "getText", new=lambda *_a, **_k: ("Exit B", True)), \
         patch.object(desktop.KioskDevicesBox, "show_credential", new=lambda _self, created: shown.append(created["credential"])), \
         patch.object(desktop.QMessageBox, "question", new=lambda *_a, **_k: QMessageBox.Yes):
        box = desktop.KioskDevicesBox()
        assert box.table.rowCount() == 1 and box.table.item(0, 0).text() == "kiosk-1"
        box.create_device()
        assert shown == ["shown-once"]
        box.table.setCurrentCell(0, 0)
        box.revoke_device()
    assert ("POST", "/kiosk-devices") in calls and ("POST", "/kiosk-devices/1/revoke") in calls
