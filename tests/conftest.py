"""Shared test setup."""

import pytest


@pytest.fixture(autouse=True)
def _reset_login_throttle():
    """Sign-in failures in one test must not lock accounts in the next."""
    from app.services import login_throttle

    login_throttle.reset()
    yield
    login_throttle.reset()
