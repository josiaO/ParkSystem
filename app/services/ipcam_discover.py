"""Find Dahua / Hikvision / generic IP cameras on the LAN.

HVX cameras (TCP 30000) stay on the NetSDK path. These hosts are web/RTSP
only: username + password, live JPEG, FastALPR. Open HTTP or RTSP is not
SDK_CONNECTED.
"""

from __future__ import annotations

import asyncio

import httpx

from app.services.site_cameras import (
    camera_spec_for_ip,
    local_ipv4s,
    match_known,
    scan_prefix,
    site_controller_ips,
    site_display_ips,
    tcp_open,
)

HTTP_PORT = 80
HIK_WEB_PORT = 8000
RTSP_PORT = 554
SDK_PORT = 30000
SCAN_TIMEOUT = 0.35
FINGERPRINT_TIMEOUT = 0.7
SCAN_CONCURRENCY = 48

_VENDOR_HINTS = (
    ("hikvision", ("hikvision", "app-webs", "dvrdvs", "isapi", "hik")),
    ("dahua", ("dahua", "dhweb", "rpc2", "webcamxt", "dh-")),
)

_CAMERA_PATHS = (
    "/",
    "/index.html",
    "/ISAPI/System/deviceInfo",
    "/cgi-bin/magicBox.cgi?action=getDeviceType",
    "/cgi-bin/snapshot.cgi",
    "/ISAPI/Streaming/channels/101/picture",
)


def lan_prefixes() -> list[str]:
    prefixes: list[str] = []
    for ip in local_ipv4s():
        prefix = scan_prefix(ip)
        if prefix and prefix not in prefixes:
            prefixes.append(prefix)
    return prefixes[:1] or ["192.168.1"]


def lan_host_ips() -> list[str]:
    skip = set(local_ipv4s()) | set(site_controller_ips()) | set(site_display_ips())
    ips = [f"{prefix}.{n}" for prefix in lan_prefixes() for n in range(1, 255)]
    return [ip for ip in ips if ip not in skip]


def _vendor_from_text(blob: str) -> str | None:
    lowered = blob.lower()
    for vendor, hints in _VENDOR_HINTS:
        if any(hint in lowered for hint in hints):
            return vendor
    return None


async def fingerprint_http(ip: str, port: int = HTTP_PORT) -> str | None:
    timeout = httpx.Timeout(FINGERPRINT_TIMEOUT, connect=SCAN_TIMEOUT)
    base = f"http://{ip}" if port == 80 else f"http://{ip}:{port}"
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for path in _CAMERA_PATHS:
            url = f"{base}{path}"
            try:
                response = await client.get(url)
            except Exception:
                continue
            header = " ".join(
                str(response.headers.get(name) or "")
                for name in ("server", "www-authenticate", "www-authenticate")
            )
            blob = f"{header} {response.text[:1500]}"
            vendor = _vendor_from_text(blob)
            if vendor:
                return vendor
            if response.status_code in (401, 403) and "ISAPI" in path:
                return "hikvision"
            if response.status_code in (401, 403) and "cgi-bin" in path:
                return "dahua"
            if response.status_code in (401, 403) and "digest" in blob.lower():
                return "ipcam"
    return None


def adapter_for(*, sdk_open: bool, vendor: str | None, http_open: bool, rtsp_open: bool) -> str | None:
    if sdk_open:
        return "hvx"
    if vendor in {"dahua", "hikvision"}:
        return vendor
    if rtsp_open or http_open:
        return "rtsp"
    return None


async def probe_host(ip: str, semaphore: asyncio.Semaphore) -> dict:
    async with semaphore:
        sdk_open, http_80, http_8000, rtsp_open = await asyncio.gather(
            tcp_open(ip, SDK_PORT, timeout=SCAN_TIMEOUT),
            tcp_open(ip, HTTP_PORT, timeout=SCAN_TIMEOUT),
            tcp_open(ip, HIK_WEB_PORT, timeout=SCAN_TIMEOUT),
            tcp_open(ip, RTSP_PORT, timeout=SCAN_TIMEOUT),
        )
    http_open = http_80 or http_8000
    vendor = None
    if not sdk_open and http_open:
        vendor = await fingerprint_http(ip, HTTP_PORT if http_80 else HIK_WEB_PORT)
    elif not sdk_open and rtsp_open:
        vendor = await fingerprint_http(ip)
    kind = adapter_for(sdk_open=sdk_open, vendor=vendor, http_open=http_open, rtsp_open=rtsp_open)
    return {
        "ip": ip,
        "sdk_open": sdk_open,
        "http_open": http_open,
        "rtsp_open": rtsp_open,
        "vendor": vendor,
        "kind": kind,
        "adapter_id": kind,
    }


async def scan_lan_devices() -> list[dict]:
    semaphore = asyncio.Semaphore(SCAN_CONCURRENCY)
    rows = await asyncio.gather(*[probe_host(ip, semaphore) for ip in lan_host_ips()])
    return [row for row in rows if row.get("kind")]


def generic_discovery_row(device: dict, existing: dict | None = None) -> dict:
    ip = device["ip"]
    adapter_id = device.get("adapter_id") or "rtsp"
    spec = camera_spec_for_ip(ip)
    spec["adapter_id"] = adapter_id
    label = {"dahua": "Dahua", "hikvision": "Hikvision", "rtsp": "IP camera"}.get(adapter_id, "IP camera")
    if match_known(ip) is None:
        spec["name"] = f"{label} {ip}"
    return {
        **spec,
        "tcp_open": bool(device.get("sdk_open")),
        "hvx_found": False,
        "http_open": bool(device.get("http_open")),
        "rtsp_open": bool(device.get("rtsp_open")),
        "kind": adapter_id,
        "adapter_id": adapter_id,
        "vendor": device.get("vendor") or adapter_id,
        "plate_engine": "fastalpr",
        "known_site": match_known(ip) is not None,
        "already_added": existing is not None,
        "camera_id": None if existing is None else existing.get("id"),
        "camera_status": None if existing is None else existing.get("status"),
        "reachable": True,
        "note": (
            f"{label} web/RTSP camera. Username and password only. "
            "FastALPR reads plates. Not SDK_CONNECTED."
        ),
    }
