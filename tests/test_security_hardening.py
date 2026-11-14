"""Phase 1 security hardening (see CLAUDE_CODE_TASK.md section 4)."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import PropertyMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import Base


@pytest.fixture()
def bootstrap_db(tmp_path):
    from app.api_main import ensure_roles
    from app.services import bootstrap

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with patch.object(Settings, "data_dir", new_callable=PropertyMock, return_value=tmp_path), \
         patch.object(bootstrap.settings, "bootstrap_password", ""):
        with Session() as db:
            ensure_roles(db)
        yield Session
    engine.dispose()


# 1.1 /auth/setup ---------------------------------------------------------

def test_setup_discloses_bootstrap_password_once_to_loopback(bootstrap_db):
    from app.services import bootstrap

    with bootstrap_db() as db:
        first = bootstrap.setup_status(db, local_request=True)
        assert first["password"] == bootstrap.effective_bootstrap_password()
        second = bootstrap.setup_status(db, local_request=True)
        assert second["password"] == ""
        assert str(bootstrap.bootstrap_password_path()) in second["hint"]


def test_setup_never_returns_usernames(bootstrap_db):
    from app.services import bootstrap

    with bootstrap_db() as db:
        for local in (True, False):
            assert "usernames" not in bootstrap.setup_status(db, local_request=local)


def test_setup_never_discloses_password_to_lan(bootstrap_db):
    from app.services import bootstrap

    with bootstrap_db() as db:
        remote = bootstrap.setup_status(db, local_request=False)
        assert remote["password"] == ""
        # A LAN request must not consume the one-time local disclosure.
        assert bootstrap.setup_status(db, local_request=True)["password"]


def test_setup_default_is_not_local(bootstrap_db):
    from app.services import bootstrap

    with bootstrap_db() as db:
        assert bootstrap.setup_status(db)["password"] == ""


def test_setup_does_not_disclose_after_first_run_window(bootstrap_db):
    from app.models import User
    from app.services import bootstrap

    with bootstrap_db() as db:
        bootstrap.ensure_bootstrap_admin(db)
        admin = db.scalar(select(User).where(User.username == bootstrap.settings.bootstrap_username))
        admin.created_at = admin.created_at - bootstrap.FIRST_RUN_WINDOW - timedelta(minutes=1)
        db.commit()
        assert bootstrap.setup_status(db, local_request=True)["password"] == ""


@pytest.mark.parametrize(
    ("client_host", "headers", "expected"),
    [
        ("127.0.0.1", {}, True),
        ("::1", {}, True),
        ("::ffff:127.0.0.1", {}, True),
        ("127.0.0.1", {"x-forwarded-for": "10.0.0.5"}, False),
        ("127.0.0.1", {"forwarded": "for=10.0.0.5"}, False),
        ("10.0.0.5", {}, False),
        ("testclient", {}, False),
        ("", {}, False),
    ],
)
def test_loopback_detection(client_host, headers, expected):
    from types import SimpleNamespace

    from app.api_main import _is_loopback_request

    request = SimpleNamespace(client=SimpleNamespace(host=client_host), headers=headers)
    assert _is_loopback_request(request) is expected


# 1.2 Default password strings ----------------------------------------------

@pytest.mark.parametrize("module_name", ["tools.field_acceptance_test", "tools.camera_lab"])
def test_tools_never_guess_default_passwords(module_name, tmp_path, monkeypatch):
    import importlib

    module = importlib.import_module(module_name)
    for name in ("SMARTPARK_PASSWORD", "SMARTPARK_BOOTSTRAP_PASSWORD", "PROGRAMDATA"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(module.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(module.sys.stdin, "isatty", lambda: False, raising=False)
    assert module.password_candidates("") == []
    monkeypatch.setenv("SMARTPARK_PASSWORD", "from-env-123")
    assert module.password_candidates("") == ["from-env-123"]


@pytest.mark.parametrize("module_name", ["tools.field_acceptance_test", "tools.camera_lab"])
def test_tools_prompt_when_interactive_and_nothing_configured(module_name, tmp_path, monkeypatch):
    import importlib

    module = importlib.import_module(module_name)
    for name in ("SMARTPARK_PASSWORD", "SMARTPARK_BOOTSTRAP_PASSWORD", "PROGRAMDATA"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(module.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(module.sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "typed-pass-123")
    assert module.password_candidates("") == ["typed-pass-123"]


def test_no_default_password_literals_in_scripts_or_tools():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    offenders = []
    for folder in ("tools", "scripts", "packaging"):
        for path in (root / folder).rglob("*"):
            if path.suffix in {".py", ".ps1", ".sh", ".bat", ".cmd"} and "SmartPark1!" in path.read_text(encoding="utf-8", errors="ignore"):
                offenders.append(str(path.relative_to(root)))
    assert offenders == []


# 1.3 Login throttling -----------------------------------------------------

class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _throttle():
    from app.services.login_throttle import LoginThrottle

    clock = _Clock()
    return LoginThrottle(clock=clock), clock


def test_throttle_allows_free_attempts_then_backs_off_and_locks():
    throttle, clock = _throttle()
    for _ in range(throttle.user_free_failures):
        assert throttle.check("10.0.0.5", "admin") == 0
        throttle.record_failure("10.0.0.5", "admin")
    wait = throttle.check("10.0.0.5", "admin")
    assert 0 < wait <= throttle.max_lockout_seconds
    throttle.record_failure("10.0.0.5", "admin")  # attempts while blocked are not even checked
    clock.now += wait + 0.01
    assert throttle.check("10.0.0.5", "admin") == 0
    throttle.record_failure("10.0.0.5", "admin")
    longer = throttle.check("10.0.0.5", "admin")
    assert longer > wait  # exponential backoff
    for _ in range(20):
        clock.now += throttle.check("10.0.0.5", "admin") + 0.01
        throttle.record_failure("10.0.0.5", "admin")
    assert throttle.check("10.0.0.5", "admin") <= throttle.max_lockout_seconds


def test_throttle_is_per_username_and_per_ip():
    throttle, _clock = _throttle()
    for _ in range(throttle.user_free_failures):
        throttle.record_failure("10.0.0.5", "admin")
    assert throttle.check("10.0.0.6", "admin") > 0       # same account, other PC
    assert throttle.check("10.0.0.5", "operator1") == 0  # same PC, other account
    throttle2, _ = _throttle()
    for i in range(throttle2.ip_free_failures):
        throttle2.record_failure("10.0.0.9", f"user{i}")  # spraying many accounts
    assert throttle2.check("10.0.0.9", "someone-else") > 0


def test_throttle_success_clears_account_and_failures_expire():
    throttle, clock = _throttle()
    for _ in range(throttle.user_free_failures - 1):
        throttle.record_failure("10.0.0.5", "Admin")
    throttle.record_success("10.0.0.5", "admin")  # usernames are case-insensitive
    throttle.record_failure("10.0.0.5", "admin")
    assert throttle.check("10.0.0.5", "admin") == 0
    for _ in range(throttle.user_free_failures):
        throttle.record_failure("10.0.0.7", "kiosk")
    clock.now += throttle.window_seconds + throttle.max_lockout_seconds + 1
    assert throttle.check("10.0.0.7", "kiosk") == 0


def _login_client(tmp_path):
    from app.api_main import app, ensure_roles
    from app.db import get_db
    from app.models import Role, User, UserRole
    from app.security import hash_password

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as db:
        ensure_roles(db)
        user = User(username="operator1", full_name="Op", password_hash=hash_password("right-password-1"))
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_id=db.scalar(select(Role).where(Role.name == "Operator")).id))
        db.commit()

    def override():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override
    return TestClient(app, client=("10.0.0.50", 40000)), engine


@pytest.mark.parametrize("endpoint", ["/auth/login", "/auth/token"])
def test_login_endpoints_are_throttled(endpoint, tmp_path):
    from app.api_main import app
    from app.services import login_throttle

    login_throttle.reset()
    client, engine = _login_client(tmp_path)

    def attempt(password):
        if endpoint == "/auth/login":
            return client.post(endpoint, json={"username": "operator1", "password": password})
        return client.post(endpoint, data={"username": "operator1", "password": password})

    try:
        for _ in range(login_throttle.throttle().user_free_failures):
            assert attempt("wrong").status_code == 401
        blocked = attempt("right-password-1")  # even the right password waits
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) >= 1
    finally:
        login_throttle.reset()
        client.close()
        app.dependency_overrides.clear()
        engine.dispose()
