"""Shared test setup."""

import os

import pytest

# The latency trace is on by default in the product. Tests that check it build
# their own TraceWriter in a temporary folder; everything else must not write
# trace files into the developer's log folders.
os.environ.setdefault("SMARTPARK_LATENCY_TRACE", "0")
os.environ.setdefault("SMARTPARK_LOOP_BOARD_ENABLED", "false")  # never bind the live board port (UDP 8000)


@pytest.fixture(autouse=True)
def _reset_lane_stays():
    """Repeated-capture stays live in memory per camera; never leak between tests."""
    from app.services import lane_stay

    lane_stay.reset()
    yield
    lane_stay.reset()


@pytest.fixture(autouse=True)
def _reset_login_throttle():
    """Sign-in failures in one test must not lock accounts in the next."""
    from app.services import login_throttle

    login_throttle.reset()
    yield
    login_throttle.reset()


@pytest.fixture(autouse=True)
def _reset_public_rate_limits():
    """Process-wide request budgets must not leak between tests."""
    from app.services import payment_prompt_guard
    from app.services.public_ingress import reset_rate_limiter

    reset_rate_limiter()
    payment_prompt_guard.reset()
    yield
    reset_rate_limiter()
    payment_prompt_guard.reset()


@pytest.fixture(autouse=True, scope="module")
def _collect_qt_garbage_on_main_thread():
    """Free Qt wrappers on the thread that created them.

    Desktop tests leave PySide6 objects behind. If Python's cyclic GC happens
    to run on a TestClient worker thread, Shiboken queues their deletion for
    the main thread, and running that queue later crashed the interpreter
    (SIGSEGV in BindingManager::runDeletionInMainThread, seen intermittently
    in test_simulation). Collecting on the main thread after each module
    keeps Qt garbage from reaching a later module's worker threads (per test
    tripled the suite's run time).
    """
    yield
    import sys

    if "PySide6" in sys.modules:
        import gc

        gc.collect()


@pytest.fixture(autouse=True)
def _secrets_never_touch_the_site():
    r"""Keep test credentials out of the real secret store.

    Without this, every Camera(password_secret=...) a test made wrote a DPAPI
    file into C:\ProgramData\SmartParkEdge\secrets on the site PC (about 150
    per full run; 4,700 files had piled up on SITE-PC01). Tests that need a
    specific store still install their own with set_secret_store().
    """
    from app.infrastructure.secrets import MemorySecretStore, set_secret_store

    set_secret_store(MemorySecretStore())
    yield
    set_secret_store(None)


@pytest.fixture(autouse=True)
def _fresh_read_counts(monkeypatch):
    """Every test starts with no car read yet, in memory, never the site's Redis."""
    from app.services import read_budget
    from app.services.shared_cache import SharedCache

    monkeypatch.setattr(read_budget, "cache", SharedCache(url=""))
    yield
