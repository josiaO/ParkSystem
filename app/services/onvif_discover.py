"""Capability-driven ONVIF discovery. Not the default camera login path.

Order of operations (each step is optional; failure falls back, never guesses):

1. ``GetServices`` (Device service) → XAddr per namespace: Media2 (ver20),
   Media1 (ver10), Events, Analytics. Falls back to ``GetCapabilities``.
2. Media2 ``GetProfiles`` / ``GetStreamUri`` / ``GetSnapshotUri`` when the
   device advertises Media2; otherwise the Media1 equivalents.
3. Events ``GetEventProperties`` → topic set. Vehicle / licence-plate topics
   mark the camera as a Profile M metadata source. Profile M is *only*
   claimed when Media2 + Events + Analytics are present; plate metadata is
   only claimed when a plate-like topic is advertised.

Requests carry a WS-Security UsernameToken (PasswordDigest) header, which is
what ONVIF devices expect; HTTP Basic is also sent for devices that use it.
Stream URIs returned by the camera are used as-is (credentials injected only
when the device omitted them). Manual RTSP remains the fallback elsewhere.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import os
import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

import httpx

from app.services.rtsp_probe import redact_url

NS_DEVICE = "http://www.onvif.org/ver10/device/wsdl"
NS_MEDIA1 = "http://www.onvif.org/ver10/media/wsdl"
NS_MEDIA2 = "http://www.onvif.org/ver20/media/wsdl"
NS_EVENTS = "http://www.onvif.org/ver10/events/wsdl"
NS_ANALYTICS = "http://www.onvif.org/ver20/analytics/wsdl"
NS_SCHEMA = "http://www.onvif.org/ver10/schema"

_NS = {
    "s": "http://www.w3.org/2003/05/soap-envelope",
    "tds": NS_DEVICE,
    "trt": NS_MEDIA1,
    "tr2": NS_MEDIA2,
    "tev": NS_EVENTS,
    "tt": NS_SCHEMA,
}

_DEVICE_PATHS = (
    "/onvif/device_service",
    "/onvif/device",
    "/onvif/Devices",
    "/device_service",
)

PLATE_TOPIC_RE = re.compile(r"licen[cs]e\s*plate|plate|lpr|anpr|vehicle", re.IGNORECASE)


class ONVIFError(RuntimeError):
    pass


# ----------------------------------------------------------------- xml utils --
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


def _parse_root(xml: str) -> ET.Element:
    return ET.fromstring(xml)


def _int(value: str) -> int | None:
    return int(value) if str(value).isdigit() else None


# ------------------------------------------------------------- soap plumbing --
def _ws_security(username: str, password: str) -> str:
    """WS-Security UsernameToken with PasswordDigest (ONVIF Core Spec §5.12)."""
    if not username:
        return ""
    nonce = os.urandom(16)
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    digest = base64.b64encode(hashlib.sha1(nonce + created.encode() + (password or "").encode()).digest()).decode()
    return (
        '<wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"'
        ' xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">'
        "<wsse:UsernameToken>"
        f"<wsse:Username>{_xml_escape(username)}</wsse:Username>"
        '<wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">'
        f"{digest}</wsse:Password>"
        '<wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">'
        f"{base64.b64encode(nonce).decode()}</wsse:Nonce>"
        f"<wsu:Created>{created}</wsu:Created>"
        "</wsse:UsernameToken></wsse:Security>"
    )


def _xml_escape(value: str) -> str:
    return (value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _envelope(body: str, *, action: str, username: str = "", password: str = "", header_extra: str = "") -> str:
    header = _ws_security(username, password) + header_extra
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"'
        f' xmlns:tds="{NS_DEVICE}" xmlns:trt="{NS_MEDIA1}" xmlns:tr2="{NS_MEDIA2}"'
        f' xmlns:tev="{NS_EVENTS}" xmlns:tt="{NS_SCHEMA}"'
        ' xmlns:wsa="http://www.w3.org/2005/08/addressing"'
        ' xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2">'
        f"<s:Header>{header}</s:Header>"
        f"<s:Body>{body}</s:Body>"
        "</s:Envelope>"
    )


def _auth_url(url: str, username: str, password: str) -> str:
    parsed = urlparse(url)
    if parsed.username or not username:
        return url
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    user = quote(username or "", safe="")
    pw = quote(password or "", safe="")
    netloc = f"{user}:{pw}@{host}" if user else host
    return urlunparse((parsed.scheme or "http", netloc, parsed.path or "/", parsed.params, parsed.query, parsed.fragment))


async def _post(
    url: str,
    body: str,
    *,
    username: str,
    password: str,
    action: str,
    timeout: float = 3.0,
    header_extra: str = "",
) -> str:
    headers = {
        "Content-Type": f'application/soap+xml; charset=utf-8; action="{action}"',
        "SOAPAction": action,
    }
    auth = (username, password) if username else None
    envelope = _envelope(body, action=action, username=username, password=password, header_extra=header_extra)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.post(url, content=envelope, headers=headers, auth=auth)
        response.raise_for_status()
        return response.text


# ------------------------------------------------------------------ parsers --
def parse_media_xaddr(xml: str) -> str:
    root = _parse_root(xml)
    for cap in _all(root, "Media"):
        xaddr = _find(cap, "XAddr")
        if xaddr is not None and _text(xaddr):
            return _text(xaddr)
    match = re.search(r"<[^>]*XAddr[^>]*>([^<]+)</", xml)
    return (match.group(1).strip() if match else "")


def parse_capabilities(xml: str) -> dict[str, str]:
    """GetCapabilities → {namespace: xaddr} for Media/Events/Analytics."""
    root = _parse_root(xml)
    out: dict[str, str] = {}
    mapping = {"media": NS_MEDIA1, "events": NS_EVENTS, "analytics": NS_ANALYTICS, "device": NS_DEVICE}
    for name, ns in mapping.items():
        for cap in _all(root, name):
            xaddr = _find(cap, "XAddr")
            if xaddr is not None and _text(xaddr):
                out[ns] = _text(xaddr)
                break
    return out


def parse_services(xml: str) -> dict[str, str]:
    """GetServices → {namespace: xaddr}. Media2 shows up as the ver20 media namespace."""
    root = _parse_root(xml)
    out: dict[str, str] = {}
    for service in _all(root, "Service"):
        ns = _text(_find(service, "Namespace"))
        xaddr = _text(_find(service, "XAddr"))
        if ns and xaddr:
            out[ns] = xaddr
    return out


def _profile_row(profile: ET.Element, *, media_version: int) -> dict[str, Any]:
    token = profile.attrib.get("token") or _text(_find(profile, "token"))
    name = _text(_find(profile, "Name")) or token
    encoder = _find(profile, "VideoEncoderConfiguration", "VideoEncoder")
    if encoder is None:
        encoder = profile
    codec = _text(_find(encoder, "Encoding"))
    width = _text(_find(encoder, "Width"))
    height = _text(_find(encoder, "Height"))
    fps = _text(_find(encoder, "FrameRateLimit")) or _text(_find(encoder, "FrameRate"))
    bitrate = _text(_find(encoder, "BitrateLimit"))
    gop = _text(_find(encoder, "GovLength"))
    fps_value: Any = _int(fps)
    if fps_value is None and fps:
        try:
            fps_value = float(fps)
        except ValueError:
            fps_value = fps
    return {
        "token": token,
        "name": name,
        "protocol": "onvif",
        "media_version": media_version,
        "codec": codec.lower() if codec else "",
        "width": _int(width),
        "height": _int(height),
        "fps": fps_value,
        "bitrate": _int(bitrate),
        "gop": _int(gop),
        "has_metadata": _find(profile, "MetadataConfiguration", "Metadata") is not None,
    }


def parse_profiles(xml: str) -> list[dict[str, Any]]:
    """Media1 GetProfilesResponse (``Profiles`` elements)."""
    root = _parse_root(xml)
    return [_profile_row(p, media_version=1) for p in _all(root, "Profiles")]


def parse_profiles_media2(xml: str) -> list[dict[str, Any]]:
    """Media2 GetProfilesResponse (``Profiles`` with ``Configurations``)."""
    root = _parse_root(xml)
    return [_profile_row(p, media_version=2) for p in _all(root, "Profiles")]


def parse_stream_uri(xml: str) -> str:
    root = _parse_root(xml)
    return _text(_find(root, "Uri"))


parse_snapshot_uri = parse_stream_uri


def parse_event_topics(xml: str) -> list[str]:
    """GetEventPropertiesResponse → dotted topic paths under ``TopicSet``.

    Topic elements carry ``wstop:topic="true"``; we return every path that has
    that marker or is a leaf with no children.
    """
    root = _parse_root(xml)
    topic_set = _find(root, "TopicSet")
    if topic_set is None:
        return []
    out: list[str] = []

    def walk(el: ET.Element, path: list[str]) -> None:
        for child in list(el):
            name = _local(child.tag)
            if name in {"MessageDescription", "Documentation"}:
                continue
            new_path = path + [name]
            marked = any(_local(k) == "topic" and str(v).lower() == "true" for k, v in child.attrib.items())
            has_children = any(_local(g.tag) not in {"MessageDescription", "Documentation"} for g in list(child))
            if marked or not has_children:
                out.append("/".join(new_path))
            walk(child, new_path)

    walk(topic_set, [])
    seen: set[str] = set()
    unique = []
    for t in out:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


def plate_topics(topics: list[str]) -> list[str]:
    return [t for t in topics if PLATE_TOPIC_RE.search(t)]


def summarize_capabilities(services: dict[str, str], topics: list[str]) -> dict[str, Any]:
    media2 = NS_MEDIA2 in services
    media1 = NS_MEDIA1 in services
    events = NS_EVENTS in services
    analytics = NS_ANALYTICS in services
    plates = plate_topics(topics)
    return {
        "media2": media2,
        "media1": media1,
        "events": events,
        "analytics": analytics,
        # Profile M mandates Media2 + Events + Analytics metadata. Never infer
        # licence-plate support from Profile M alone.
        "profile_m": bool(media2 and events and analytics),
        "plate_metadata": bool(plates),
        "plate_topics": plates,
        "topics": topics[:200],
    }


_SERVICE_LABELS = {
    NS_DEVICE: "device", NS_MEDIA1: "media1", NS_MEDIA2: "media2",
    NS_EVENTS: "events", NS_ANALYTICS: "analytics",
}


def _service_label(namespace: str) -> str:
    return _SERVICE_LABELS.get(namespace, namespace)


def capability_flags(capabilities: dict[str, Any]) -> list[str]:
    """Camera.media_capabilities flags derived from the ONVIF summary."""
    flags = ["ONVIF"]
    if capabilities.get("media2"):
        flags.append("ONVIF_MEDIA2")
    if capabilities.get("events"):
        flags.append("ONVIF_EVENTS")
    if capabilities.get("profile_m"):
        flags.append("ONVIF_PROFILE_M")
    if capabilities.get("plate_metadata"):
        flags.append("ONVIF_PLATE_METADATA")
    return flags


# --------------------------------------------------------------- discovery --
async def _device_services(ip: str, username: str, password: str, timeout: float) -> tuple[str, dict[str, str], str]:
    last_error = ""
    for path in _DEVICE_PATHS:
        candidate = f"http://{ip}{path}"
        try:
            xml = await _post(
                candidate,
                "<tds:GetServices><tds:IncludeCapability>false</tds:IncludeCapability></tds:GetServices>",
                username=username, password=password,
                action=f"{NS_DEVICE}/GetServices", timeout=timeout,
            )
            services = parse_services(xml)
            if services:
                return candidate, services, ""
        except Exception as exc:  # try GetCapabilities on the same path
            last_error = str(exc)
        try:
            xml = await _post(
                candidate,
                "<tds:GetCapabilities><tds:Category>All</tds:Category></tds:GetCapabilities>",
                username=username, password=password,
                action=f"{NS_DEVICE}/GetCapabilities", timeout=timeout,
            )
            services = parse_capabilities(xml)
            if not services:
                media = parse_media_xaddr(xml)
                if media:
                    services = {NS_MEDIA1: media}
            if services:
                return candidate, services, ""
        except Exception as exc:
            last_error = str(exc)
    return "", {}, last_error or "ONVIF device service not found"


async def _media2_streams(media_url: str, username: str, password: str, timeout: float) -> list[dict[str, Any]]:
    xml = await _post(
        media_url, "<tr2:GetProfiles><tr2:Type>All</tr2:Type></tr2:GetProfiles>",
        username=username, password=password, action=f"{NS_MEDIA2}/GetProfiles", timeout=timeout,
    )
    rows = parse_profiles_media2(xml)
    for row in rows:
        token = _xml_escape(row.get("token") or "")
        if not token:
            continue
        try:
            uri_xml = await _post(
                media_url,
                f"<tr2:GetStreamUri><tr2:Protocol>RtspUnicast</tr2:Protocol><tr2:ProfileToken>{token}</tr2:ProfileToken></tr2:GetStreamUri>",
                username=username, password=password, action=f"{NS_MEDIA2}/GetStreamUri", timeout=timeout,
            )
            row["stream_uri"] = parse_stream_uri(uri_xml)
        except Exception as exc:
            row["stream_error"] = str(exc)[:160]
        try:
            snap_xml = await _post(
                media_url,
                f"<tr2:GetSnapshotUri><tr2:ProfileToken>{token}</tr2:ProfileToken></tr2:GetSnapshotUri>",
                username=username, password=password, action=f"{NS_MEDIA2}/GetSnapshotUri", timeout=timeout,
            )
            row["snapshot_uri"] = parse_snapshot_uri(snap_xml)
        except Exception:
            row["snapshot_uri"] = ""
    return rows


async def _media1_streams(media_url: str, username: str, password: str, timeout: float) -> list[dict[str, Any]]:
    xml = await _post(
        media_url, "<trt:GetProfiles/>",
        username=username, password=password, action=f"{NS_MEDIA1}/GetProfiles", timeout=timeout,
    )
    rows = parse_profiles(xml)
    for row in rows:
        token = _xml_escape(row.get("token") or "")
        if not token:
            continue
        body = (
            "<trt:GetStreamUri>"
            "<trt:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream><tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport></trt:StreamSetup>"
            f"<trt:ProfileToken>{token}</trt:ProfileToken>"
            "</trt:GetStreamUri>"
        )
        try:
            uri_xml = await _post(media_url, body, username=username, password=password,
                                  action=f"{NS_MEDIA1}/GetStreamUri", timeout=timeout)
            row["stream_uri"] = parse_stream_uri(uri_xml)
        except Exception as exc:
            row["stream_error"] = str(exc)[:160]
        try:
            snap_xml = await _post(
                media_url, f"<trt:GetSnapshotUri><trt:ProfileToken>{token}</trt:ProfileToken></trt:GetSnapshotUri>",
                username=username, password=password, action=f"{NS_MEDIA1}/GetSnapshotUri", timeout=timeout,
            )
            row["snapshot_uri"] = parse_snapshot_uri(snap_xml)
        except Exception:
            row["snapshot_uri"] = ""
    return rows


async def _event_topics(events_url: str, username: str, password: str, timeout: float) -> tuple[list[str], str]:
    try:
        xml = await _post(
            events_url, "<tev:GetEventProperties/>",
            username=username, password=password, action=f"{NS_EVENTS}/GetEventProperties", timeout=timeout,
        )
        return parse_event_topics(xml), ""
    except Exception as exc:
        return [], str(exc)[:160]


def _finish_rows(rows: list[dict[str, Any]], username: str, password: str) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        row = dict(row)
        uri = row.pop("stream_uri", "") or ""
        snapshot = row.get("snapshot_uri") or ""
        if uri:
            authed = _auth_url(uri, username, password)
            row["uri"] = authed
            row["uri_redacted"] = redact_url(authed)
        if snapshot:
            authed_snapshot = _auth_url(snapshot, username, password)
            row["snapshot_uri"] = authed_snapshot
            row["snapshot_uri_redacted"] = redact_url(authed_snapshot)
        out.append(row)
    return out


async def discover_onvif(
    ip: str,
    username: str = "admin",
    password: str = "admin",
    *,
    timeout: float = 3.0,
) -> dict[str, Any]:
    """Full capability-driven discovery. Failure is normal; callers fall back."""
    device_url, services, error = await _device_services(ip, username, password, timeout)
    if not device_url:
        return {"ok": False, "onvif": False, "error": error, "profiles": [], "capabilities": {}, "services": {}}

    media2_url = services.get(NS_MEDIA2, "")
    media1_url = services.get(NS_MEDIA1, "")
    events_url = services.get(NS_EVENTS, "")
    media_url = media2_url or media1_url or f"http://{ip}/onvif/media_service"
    media_version = 0
    rows: list[dict[str, Any]] = []
    media_error = ""
    if media2_url:
        try:
            rows = await _media2_streams(media2_url, username, password, timeout)
            media_version = 2
        except Exception as exc:
            media_error = f"Media2 GetProfiles failed: {exc}"[:200]
    if not rows and (media1_url or not media2_url):
        try:
            rows = await _media1_streams(media1_url or media_url, username, password, timeout)
            media_version = 1
            media_url = media1_url or media_url
        except Exception as exc:
            media_error = media_error or f"GetProfiles failed: {exc}"[:200]
    else:
        media_url = media2_url or media_url

    topics: list[str] = []
    events_error = ""
    if events_url:
        topics, events_error = await _event_topics(events_url, username, password, timeout)
    capabilities = summarize_capabilities(services, topics)
    profiles = _finish_rows(rows, username, password)
    streams = [p for p in profiles if p.get("uri")]
    snapshot_uri = next((p.get("snapshot_uri") for p in profiles if p.get("snapshot_uri")), "")
    return {
        "ok": bool(streams),
        "onvif": True,
        "media_version": media_version,
        "device_url": device_url,
        "media_url": media_url,
        "media2_url": media2_url,
        "events_url": events_url,
        "analytics_url": services.get(NS_ANALYTICS, ""),
        "services": {_service_label(ns): url for ns, url in services.items()},
        "profiles": profiles,
        "snapshot_uri": snapshot_uri,
        "snapshot_uri_redacted": redact_url(snapshot_uri) if snapshot_uri else "",
        "capabilities": capabilities,
        "capability_flags": capability_flags(capabilities),
        "events_error": events_error,
        "error": "" if streams else (media_error or error or "No ONVIF stream URIs"),
    }


async def discover_onvif_streams(
    ip: str,
    username: str = "admin",
    password: str = "admin",
    *,
    timeout: float = 3.0,
) -> dict[str, Any]:
    """Backwards-compatible name used by stream discovery and adapters."""
    return await discover_onvif(ip, username, password, timeout=timeout)
