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

from app.config import settings

PUBLIC_PATH_PREFIXES: tuple[str, ...] = (
    "/p/",
    "/api/public/payment-intents",
    "/api/public/payment-status/",
    "/api/webhooks/flutterwave",
    "/api/webhooks/clickpesa",
)
PUBLIC_EXACT_PATHS: tuple[str, ...] = ("/health",)


def is_public_path(path: str) -> bool:
    p = path or "/"
    if p in PUBLIC_EXACT_PATHS:
        return True
    return any(p == prefix.rstrip("/") or p.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES)


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


def request_allowed(path: str, headers: dict[str, str]) -> bool:
    """True unless the request arrived via the public tunnel for a non-public path."""
    if not is_public_ingress_request(headers):
        return True
    return is_public_path(path)


def describe() -> dict:
    return {
        "enabled": bool(ingress_hosts()),
        "hosts": sorted(ingress_hosts()),
        "public_paths": list(PUBLIC_PATH_PREFIXES) + list(PUBLIC_EXACT_PATHS),
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
        if request_allowed(scope.get("path") or "/", headers):
            await self.app(scope, receive, send)
            return
        body = b'{"detail":"Not Found"}'
        await send({
            "type": "http.response.start",
            "status": 404,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        })
        await send({"type": "http.response.body", "body": body})
