"""Grab a JPEG from the camera HTTP UI (port 80). No ffmpeg required.

Live video is SDK callbacks. HTTP snapshots are the fallback when
the QY camera still serves a still image on its web port.
"""

from __future__ import annotations

import logging

import httpx

from app.db import short_session
from app.services.rtsp_probe import redact_url
from app.services.site_cameras import tcp_open

JPEG_SOI = b"\xff\xd8"
log = logging.getLogger("smartpark")

SNAPSHOT_PATHS = (
    "/cgi-bin/snapshot.cgi",
    "/cgi-bin/snapshot.cgi?channel=1",
    "/cgi-bin/snapshot.cgi?1",
    "/snapshot.jpg",
    "/picture.jpg",
    "/jpg/image.jpg",
    "/ISAPI/Streaming/channels/101/picture",
    "/ISAPI/Streaming/channels/1/picture",
    "/onvif-http/snapshot",
    "/tmpfs/auto.jpg",
)

# Hikvision web UI is often 8000; some DVRs use 8080. Browser HTTPS is 443.
WEB_PORTS = (80, 8000, 8080)


def _http_base(ip: str, port: int, *, tls: bool = False) -> str:
    scheme = "https" if tls else "http"
    if not tls and port == 80:
        return f"{scheme}://{ip}"
    if tls and port == 443:
        return f"{scheme}://{ip}"
    return f"{scheme}://{ip}:{port}"


def camera_allows_insecure_tls(ip: str) -> bool:
    """True only if a saved camera at *ip* explicitly opted out of TLS checks."""
    from sqlalchemy import select

    from app.models import Camera

    try:
        db = short_session()
        try:
            return bool(db.scalar(
                select(Camera.id).where(Camera.ip_address == ip, Camera.allow_insecure_tls.is_(True)).limit(1)
            ))
        finally:
            db.close()
    except Exception:
        log.debug("TLS opt-in lookup failed for %s; verifying certificates", ip, exc_info=True)
        return False


async def grab_http_snapshot(ip: str, username: str, password: str, *, allow_insecure_tls: bool | None = None) -> dict:
    attempts = []
    basic = httpx.BasicAuth(username, password) if username else None
    digest = httpx.DigestAuth(username, password) if username else None
    timeout = httpx.Timeout(1.2, connect=0.5)
    targets: list[tuple[int, bool]] = [(80, False)]
    for port in (8000, 8080):
        if await tcp_open(ip, port, timeout=0.35):
            targets.append((port, False))
    if await tcp_open(ip, 443, timeout=0.35):
        targets.append((443, True))
    # Camera credentials must never follow a redirect to an unexpected host.
    # HTTPS certificates are verified unless this camera is saved with
    # allow_insecure_tls (self-signed web UI); there is no blanket opt-out.
    for port, tls in targets:
        if tls:
            insecure = camera_allows_insecure_tls(ip) if allow_insecure_tls is None else bool(allow_insecure_tls)
            client_kwargs = {"verify": not insecure}
        else:
            client_kwargs = {}
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False, **client_kwargs) as client:
            for path in SNAPSHOT_PATHS:
                url = f"{_http_base(ip, port, tls=tls)}{path}"
                try:
                    response = await client.get(url, auth=basic)
                    if response.status_code in (401, 403) and digest is not None:
                        response = await client.get(url, auth=digest)
                except Exception as exc:
                    attempts.append({"url_redacted": redact_url(url), "error": str(exc)})
                    continue
                if response.status_code == 200 and len(response.content) <= 12 * 1024 * 1024 and response.content[:2] == JPEG_SOI:
                    return {
                        "ok": True,
                        "jpeg": response.content,
                        "bytes": len(response.content),
                        "url": url,
                        "url_redacted": redact_url(url),
                        "source": "http",
                    }
                attempts.append({"url_redacted": redact_url(url), "status": response.status_code})
    return {
        "ok": False,
        "error": "no HTTP JPEG from the camera web UI",
        "attempts": attempts,
        "source": "http",
    }
