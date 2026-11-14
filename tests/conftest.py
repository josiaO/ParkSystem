"""Shared test setup."""

import pytest


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
