"""Zirp application package."""

# httpx builds a new TLS context (about 1 s of CPU on the site PC) for every
# HTTP client; reuse one per process. See app/http_tls.py.
try:
    from app import http_tls as _http_tls

    _http_tls.install()
except Exception:  # pragma: no cover - never block start-up over an optimisation
    pass
