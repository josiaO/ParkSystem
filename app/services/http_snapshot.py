"""Grab a JPEG from the camera HTTP UI (port 80). No ffmpeg required.

Live video is SDK callbacks. HTTP snapshots are the fallback when
the QY camera still serves a still image on its web port.
"""

from __future__ import annotations

import httpx

from app.services.rtsp_probe import redact_url

JPEG_SOI = b"\xff\xd8"

SNAPSHOT_PATHS = (
    "/cgi-bin/snapshot.cgi",
    "/snapshot.jpg",
    "/picture.jpg",
    "/ISAPI/Streaming/channels/101/picture",
)


async def grab_http_snapshot(ip: str, username: str, password: str) -> dict:
    attempts = []
    basic = httpx.BasicAuth(username, password) if username else None
    digest = httpx.DigestAuth(username, password) if username else None
    timeout = httpx.Timeout(1.2, connect=0.5)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for path in SNAPSHOT_PATHS:
            url = f"http://{ip}{path}"
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
