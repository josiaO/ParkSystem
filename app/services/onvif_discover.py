"""ONVIF media-profile discovery. Not the default camera login path."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

import httpx

from app.services.rtsp_probe import redact_url

_NS = {
    "s": "http://www.w3.org/2003/05/soap-envelope",
    "tds": "http://www.onvif.org/ver10/device/wsdl",
    "trt": "http://www.onvif.org/ver10/media/wsdl",
    "tt": "http://www.onvif.org/ver10/schema",
}

_DEVICE_PATHS = (
    "/onvif/device_service",
    "/onvif/device",
    "/onvif/Devices",
    "/device_service",
)


def _text(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None else ""


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _find(el: ET.Element, *names: str) -> ET.Element | None:
    wanted = {name.lower() for name in names}
    for child in el.iter():
        if _local(child.tag).lower() in wanted:
            return child
    return None


def _all(el: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in el.iter() if _local(child.tag).lower() == name.lower()]


def _envelope(body: str, *, action: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"'
        ' xmlns:tds="http://www.onvif.org/ver10/device/wsdl"'
        ' xmlns:trt="http://www.onvif.org/ver10/media/wsdl"'
        ' xmlns:tt="http://www.onvif.org/ver10/schema">'
        "<s:Header/>"
        f"<s:Body>{body}</s:Body>"
        "</s:Envelope>"
    )


def _auth_url(url: str, username: str, password: str) -> str:
    parsed = urlparse(url)
    if parsed.username:
        return url
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    user = quote(username or "", safe="")
    pw = quote(password or "", safe="")
    netloc = f"{user}:{pw}@{host}" if user else host
    return urlunparse((parsed.scheme or "http", netloc, parsed.path or "/", parsed.params, parsed.query, parsed.fragment))


async def _post(url: str, body: str, *, username: str, password: str, action: str, timeout: float = 3.0) -> str:
    headers = {
        "Content-Type": "application/soap+xml; charset=utf-8",
        "SOAPAction": action,
    }
    auth = (username, password) if username else None
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.post(url, content=_envelope(body, action=action), headers=headers, auth=auth)
        response.raise_for_status()
        return response.text


def _parse_root(xml: str) -> ET.Element:
    return ET.fromstring(xml)


def parse_media_xaddr(xml: str) -> str:
    root = _parse_root(xml)
    for cap in _all(root, "Media"):
        xaddr = _find(cap, "XAddr")
        if xaddr is not None and _text(xaddr):
            return _text(xaddr)
    match = re.search(r"<[^>]*XAddr[^>]*>([^<]+)</", xml)
    return (match.group(1).strip() if match else "")


def parse_profiles(xml: str) -> list[dict[str, Any]]:
    root = _parse_root(xml)
    rows: list[dict[str, Any]] = []
    for profile in _all(root, "Profiles"):
        token = profile.attrib.get("token") or _text(_find(profile, "token"))
        name = _text(_find(profile, "Name")) or token
        encoder = _find(profile, "VideoEncoderConfiguration")
        if encoder is None:
            encoder = profile
        codec = _text(_find(encoder, "Encoding"))
        width = _text(_find(encoder, "Width"))
        height = _text(_find(encoder, "Height"))
        fps = _text(_find(encoder, "FrameRateLimit")) or _text(_find(encoder, "FrameRate"))
        bitrate = _text(_find(encoder, "BitrateLimit"))
        gop = _text(_find(encoder, "GovLength"))
        rows.append({
            "token": token,
            "name": name,
            "protocol": "onvif",
            "codec": codec.lower() if codec else "",
            "width": int(width) if str(width).isdigit() else None,
            "height": int(height) if str(height).isdigit() else None,
            "fps": int(fps) if str(fps).isdigit() else fps or None,
            "bitrate": int(bitrate) if str(bitrate).isdigit() else None,
            "gop": int(gop) if str(gop).isdigit() else None,
        })
    return rows


def parse_stream_uri(xml: str) -> str:
    root = _parse_root(xml)
    uri = _text(_find(root, "Uri"))
    return uri


async def discover_onvif_streams(
    ip: str,
    username: str = "admin",
    password: str = "admin",
    *,
    timeout: float = 3.0,
) -> dict[str, Any]:
    """GetProfiles + GetStreamUri. Failure is normal; callers fall back to vendor URLs."""
    last_error = ""
    device_url = ""
    for path in _DEVICE_PATHS:
        candidate = f"http://{ip}{path}"
        try:
            xml = await _post(
                candidate,
                "<tds:GetCapabilities><tds:Category>Media</tds:Category></tds:GetCapabilities>",
                username=username,
                password=password,
                action="http://www.onvif.org/ver10/device/wsdl/GetCapabilities",
                timeout=timeout,
            )
            media = parse_media_xaddr(xml)
            device_url = candidate
            media_url = media or f"http://{ip}/onvif/media_service"
            break
        except Exception as exc:
            last_error = str(exc)
            media_url = ""
    else:
        return {"ok": False, "onvif": False, "error": last_error or "ONVIF device service not found", "profiles": []}

    try:
        profiles_xml = await _post(
            media_url,
            "<trt:GetProfiles/>",
            username=username,
            password=password,
            action="http://www.onvif.org/ver10/media/wsdl/GetProfiles",
            timeout=timeout,
        )
        profiles = parse_profiles(profiles_xml)
    except Exception as exc:
        return {
            "ok": False,
            "onvif": True,
            "error": f"GetProfiles failed: {exc}",
            "device_url": device_url,
            "media_url": media_url,
            "profiles": [],
        }

    streams: list[dict[str, Any]] = []
    for profile in profiles:
        token = profile.get("token") or ""
        if not token:
            continue
        body = (
            "<trt:GetStreamUri>"
            "<trt:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream><tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport></trt:StreamSetup>"
            f"<trt:ProfileToken>{token}</trt:ProfileToken>"
            "</trt:GetStreamUri>"
        )
        try:
            uri_xml = await _post(
                media_url,
                body,
                username=username,
                password=password,
                action="http://www.onvif.org/ver10/media/wsdl/GetStreamUri",
                timeout=timeout,
            )
            uri = parse_stream_uri(uri_xml)
        except Exception:
            uri = ""
        if uri:
            authed = _auth_url(uri, username, password)
            streams.append({
                **profile,
                "uri": authed,
                "uri_redacted": redact_url(authed),
            })
        else:
            streams.append(profile)

    return {
        "ok": bool(streams),
        "onvif": True,
        "device_url": device_url,
        "media_url": media_url,
        "profiles": streams,
        "error": "" if streams else (last_error or "No ONVIF stream URIs"),
    }
