"""Grab a JPEG from the camera HTTP UI (port 80). No ffmpeg required.

Live video is SDK callbacks. HTTP snapshots are the fallback when
the QY camera still serves a still image on its web port.
"""

from __future__ import annotations

import httpx

from app.services.rtsp_probe import redact_url
from app.services.site_cameras import tcp_open

JPEG_SOI = b"\xff\xd8"

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


async def grab_http_snapshot(ip: str, username: str, password: str) -> dict:
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
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=False) as client:
        for port, tls in targets:
            for path in SNAPSHOT_PATHS:
                url = f"{_http_base(ip, port, tls=tls)}{path}"
                try:
                    response = await client.get(url, auth=basic)
                    if response.status_code in (401, 403) and digest is not None:
                        response = await client.get(url, auth=digest)
                except Exception as exc:
                    attempts.append({"url_redacted": redact_url(url), "error": str(exc)})
                    continue
                if response.status_code == 200 and response.content[:2] == JPEG_SOI:
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
