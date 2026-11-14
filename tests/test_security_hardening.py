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
