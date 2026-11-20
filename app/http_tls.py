"""Build httpx's default TLS context once per process, not once per HTTP client.

httpx 0.28 builds a fresh ``ssl.SSLContext`` (loading the whole certifi CA
bundle) for every ``httpx.Client``/``AsyncClient`` and for every module-level
``httpx.get``/``post`` call. On the site PC that costs ~0.9-1.0 s of CPU each
time: the desktop's few API calls per second used 2.5-2.9 CPU cores and made
the live video stutter. The context only depends on the CA bundle and SSL
environment variables, so one shared context per combination is identical
and safe (SSLContext is thread-safe for creating connections).

Only the default case (``verify=True``, no client certificate) is cached;
anything else goes to httpx unchanged.
"""

from __future__ import annotations

import os
import threading

_lock = threading.Lock()
_cache: dict[tuple, object] = {}
_installed = False


def install() -> bool:
    """Patch httpx so default clients reuse one TLS context. Safe to call repeatedly."""
    global _installed
    if _installed:
        return True
    try:
        import httpx._config as config
        import httpx._transports.default as transports
    except Exception:
        return False
    original = getattr(transports, "create_ssl_context", None)
    if original is None or getattr(original, "_zirp_cached", False):
        _installed = True
        return True

    def create_ssl_context(verify=True, cert=None, trust_env=True):
        if verify is not True or cert is not None:
            return original(verify=verify, cert=cert, trust_env=trust_env)
        key = (bool(trust_env), os.environ.get("SSL_CERT_FILE") if trust_env else None,
               os.environ.get("SSL_CERT_DIR") if trust_env else None)
        context = _cache.get(key)
        if context is None:
            with _lock:
                context = _cache.get(key)
                if context is None:
                    context = original(verify=verify, cert=cert, trust_env=trust_env)
                    _cache[key] = context
        return context

    create_ssl_context._zirp_cached = True
    transports.create_ssl_context = create_ssl_context
    config.create_ssl_context = create_ssl_context
    _installed = True
    return True
