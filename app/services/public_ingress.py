"""Narrow public surface for the payments tunnel.

Cameras, MediaMTX, the HVX host, gate APIs, PostgreSQL and the admin API are
never exposed to the internet. A public tunnel / reverse proxy (for example a
Cloudflare Tunnel `ingress` rule) forwards only the hostnames listed in
``SMARTPARK_PUBLIC_INGRESS_HOSTS`` to this Site Service, and this middleware
refuses everything on those hostnames except the payment surface below.

The Site Service itself keeps binding to 127.0.0.1; the tunnel connector is a
separate process (PublicIngressProvider) that is optional and never required
for local parking, cash or kiosk payments.
"""

from __future__ import annotations

from collections import defaultdict, deque
import threading
import time

from app.config import settings

PUBLIC_EXACT_PATHS: tuple[str, ...] = ("/health",)
PUBLIC_PROVIDER_WEBHOOKS: frozenset[str] = frozenset({
    "/api/webhooks/flutterwave",
    "/api/webhooks/clickpesa",
})


class _RateLimiter:
    """Small process-local guard for the public surface.

    A reverse proxy should provide the production/distributed limit. This
    guard is still useful on a single Site Server and deliberately keys only
    on the client and route family; receipt tokens are never retained.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def allow(self, key: tuple[str, str], *, limit: int, window_seconds: float) -> bool:
        now = time.monotonic()
        cutoff = now - max(1.0, float(window_seconds))
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= max(1, int(limit)):
                return False
            bucket.append(now)
            # Bound memory when a public hostname sees many short-lived clients.
            if len(self._hits) > 10_000:
                stale = [name for name, values in self._hits.items() if not values or values[-1] <= cutoff]
                for name in stale[:2_000]:
                    self._hits.pop(name, None)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


_rate_limiter = _RateLimiter()


def reset_rate_limiter() -> None:
    """Clear in-process buckets for tests and controlled local restarts."""
    _rate_limiter.reset()


def _ticket_route(path: str) -> tuple[str, str] | None:
    parts = [part for part in (path or "").split("/") if part]
    if len(parts) == 2 and parts[0] == "p":
        return "receipt", "page"
    if len(parts) == 3 and parts[0] == "p":
        return "receipt", parts[2]
    return None


def public_route_category(path: str, method: str | None = None) -> str | None:
    """Return the public route family, or ``None`` for a private route.

    ``method=None`` is useful for documentation/tests that ask whether a path
    belongs to the public surface at all. The middleware always supplies the
    actual method and therefore enforces the method-aware policy.
    """
    verb = (method or "").upper()
    ticket = _ticket_route(path)
    if ticket:
        _, leaf = ticket
        if leaf == "page" and (not verb or verb in {"GET", "HEAD"}):
            return "receipt-page"
        if leaf in {"status", "snapshot.jpg", "crop.jpg", "qr.png"} and (not verb or verb in {"GET", "HEAD"}):
            return f"receipt-{leaf.split('.', 1)[0]}"
        # Simulated payment and kiosk cash are intentionally not reachable via
        # the public hostname, even though their route handlers have defense-
        # in-depth checks of their own.
        return None
    parts = [part for part in (path or "").split("/") if part]
    if len(parts) == 2 and parts[0] == "s" and (not verb or verb in {"GET", "HEAD"}):
        return "receipt-short-link"
    if path == "/api/public/payment-intents" and (not verb or verb == "POST"):
        return "payment-intent"
    if (path or "").startswith("/api/public/payment-status/") and (not verb or verb in {"GET", "HEAD"}):
        return "payment-status"
    if path in PUBLIC_PROVIDER_WEBHOOKS and (not verb or verb == "POST"):
        return "provider-webhook"
    if path in PUBLIC_EXACT_PATHS and (not verb or verb in {"GET", "HEAD"}):
        return "health"
    return None


def is_public_path(path: str, method: str | None = None) -> bool:
    return public_route_category(path, method) is not None


def ingress_hosts() -> frozenset[str]:
    raw = settings.public_ingress_hosts or ""
    return frozenset(h.strip().lower() for h in raw.split(",") if h.strip())


def host_of(headers: dict[str, str]) -> str:
    """Hostname as seen by the tunnel (X-Forwarded-Host wins), without port."""
    host = headers.get("x-forwarded-host") or headers.get("host") or ""
    host = host.split(",")[0].strip().lower()
    if host.startswith("["):  # IPv6 literal
        return host.split("]")[0] + "]"
    return host.split(":")[0]


def is_public_ingress_request(headers: dict[str, str]) -> bool:
    hosts = ingress_hosts()
    if not hosts:
        return False
    return host_of(headers) in hosts


def request_allowed(path: str, headers: dict[str, str], method: str | None = None) -> bool:
    """True unless the request arrived via the public tunnel for a non-public path."""
    if not is_public_ingress_request(headers):
        return True
    return is_public_path(path, method)


def privacy_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-store, no-cache, must-revalidate, private",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
    }


def describe() -> dict:
    return {
        "enabled": bool(ingress_hosts()),
        "hosts": sorted(ingress_hosts()),
        "public_paths": [
            "GET /p/{token}",
            "GET /s/{token}",
            "GET /p/{token}/status",
            "GET /p/{token}/snapshot.jpg",
            "GET /p/{token}/crop.jpg",
            "GET /p/{token}/qr.png",
            "POST /api/public/payment-intents",
            "GET /api/public/payment-status/{token}",
            "POST /api/webhooks/flutterwave",
            "POST /api/webhooks/clickpesa",
            "GET /health",
        ],
    }


class PublicIngressGuard:
    """Pure-ASGI middleware: 404 for non-public paths on public hostnames."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
        path = scope.get("path") or "/"
        method = (scope.get("method") or "GET").upper()
        public_request = is_public_ingress_request(headers)
        if request_allowed(path, headers, method):
            if public_request:
                category = public_route_category(path, method) or "public"
                client = headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
                client = client or headers.get("x-real-ip", "").strip()
                client = client or str((scope.get("client") or ("unknown", 0))[0])
                limits = {
                    "payment-intent": (10, 60.0),
                    "provider-webhook": (120, 60.0),
                    "payment-status": (120, 60.0),
                }
                limit, window = limits.get(category, (180, 60.0))
                if not _rate_limiter.allow((client, category), limit=limit, window_seconds=window):
                    body = b'{"detail":"Too many requests"}'
                    await send({
                        "type": "http.response.start",
                        "status": 429,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                            (b"retry-after", str(int(window)).encode()),
                            *[(key.lower().encode(), value.encode()) for key, value in privacy_headers().items()],
                        ],
                    })
                    await send({"type": "http.response.body", "body": body})
                    return

                async def send_public(message):
                    if message.get("type") == "http.response.start":
                        existing = {key.lower(): value for key, value in message.get("headers", [])}
                        for key, value in privacy_headers().items():
                            existing.setdefault(key.lower().encode(), value.encode())
                        message = {**message, "headers": list(existing.items())}
                    await send(message)

                await self.app(scope, receive, send_public)
                return
            await self.app(scope, receive, send)
            return
        body = b'{"detail":"Not Found"}'
        await send({
            "type": "http.response.start",
            "status": 404,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        })
        await send({"type": "http.response.body", "body": body})
