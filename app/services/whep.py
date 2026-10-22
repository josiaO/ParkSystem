"""Browser endpoint selection and bounded WHEP signaling proxy; no media relay."""

from __future__ import annotations

from urllib.parse import urljoin, urlsplit

import httpx
from fastapi import HTTPException, Request, Response


def browser_endpoint(endpoint: dict, request: Request) -> dict:
    from app.config import settings

    if endpoint.get("provider") != "MEDIAMTX" or endpoint.get("transport") != "WEBRTC":
        return endpoint
    host = request.url.hostname or "127.0.0.1"
    authority = f"[{host}]" if ":" in host else host
    path = endpoint["mediamtx_path"]
    configured = settings.mediamtx_browser_base_url.rstrip("/")
    if configured:
        base = f"{configured}/{path}"
    elif request.url.scheme == "https":
        base = f"/cameras/{int(endpoint['camera_id'])}/live"
    else:
        base = f"http://{authority}:8889/{path}"
    if request.url.scheme == "https" and base.startswith("http:"):
        return {**endpoint, "state": "DEGRADED", "transport": "MJPEG",
                "reason": "WHEP MIXED CONTENT: configure an HTTPS browser base URL"}
    return {**endpoint, "webrtc": base, "whep": f"{base}/whep", "browser_host": host}


async def proxy_signaling(request: Request, camera_id: int, path: str, session_id: str = "") -> Response:
    if session_id and (len(session_id) > 128 or not all(char.isalnum() or char == "-" for char in session_id)):
        raise HTTPException(400, "Invalid WHEP session")
    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > 128 * 1024:
            raise HTTPException(413, "WHEP signaling body too large")
    target = f"http://127.0.0.1:8889/{path}/whep"
    if session_id:
        target += f"/{session_id}"
    headers = {key: value for key, value in request.headers.items()
               if key.lower() in {"content-type", "if-match"}}
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=False, trust_env=False) as client:
            result = await client.request(request.method, target, content=bytes(payload), headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(503, "WHEP SIGNALING FAILED: MediaMTX unavailable") from exc
    outgoing = {key: value for key, value in result.headers.items()
                if key.lower() in {"content-type", "etag", "accept-patch", "allow"}}
    location = result.headers.get("location")
    if location:
        resource = urlsplit(urljoin(target, location))
        prefix = f"/{path}/whep/"
        identifier = resource.path.removeprefix(prefix)
        if not resource.path.startswith(prefix) or not identifier or not all(char.isalnum() or char == "-" for char in identifier):
            raise HTTPException(502, "Invalid MediaMTX WHEP Location")
        outgoing["Location"] = f"/cameras/{camera_id}/live/whep/{identifier}"
    return Response(content=result.content, status_code=result.status_code, headers=outgoing)
