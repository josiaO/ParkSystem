"""Site lane layout: each numbered lane is entry + exit.

Each side has three devices. Only the camera is an SDK device:

- Camera (`InIPCapture*` / `OutIPCapture*`): QY NetSDK on port 30000
- Controller (`Board*`): barrier I/O board — do not SDK-connect
- Display (`IpAddr*`): LEDSender2010 UDP screen — do not SDK-connect
"""

from __future__ import annotations

import asyncio
import configparser
import socket
from pathlib import Path

from app.config import settings

# Canonical IPs when a site INI is not shipped with the USB kit.
_CANONICAL_LANES = (
    {
        "name": "1#",
        "note": "Lane 1# (camera / controller / display).",
        "sides": (
            {
                "name": "Entry",
                "lane_direction": "ENTRY",
                "camera_ip": "192.168.1.144",
                "controller_ip": "192.168.1.61",
                "display_ip": "192.168.1.62",
            },
            {
                "name": "Exit",
                "lane_direction": "EXIT",
                "camera_ip": "192.168.1.145",
                "controller_ip": "192.168.1.69",
                "display_ip": "192.168.1.70",
            },
        ),
    },
    {
        "name": "2#",
        "note": "Lane 2# (camera / controller / display).",
        "sides": (
            {
                "name": "Entry",
                "lane_direction": "ENTRY",
                "camera_ip": "192.168.1.49",
                "controller_ip": "192.168.1.65",
                "display_ip": "192.168.1.66",
            },
            {
                "name": "Exit",
                "lane_direction": "EXIT",
                "camera_ip": "192.168.1.50",
                "controller_ip": "192.168.1.67",
                "display_ip": "192.168.1.68",
            },
        ),
    },
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def site_ini_path() -> Path:
    """Optional site INI with camera/controller/display IPs. Not required at runtime."""
    return repo_root() / "ParkingSystem" / "ParkWatch" / "ParkWatch.ini"


def _read_ini_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "gbk", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def _ini_get(parser: configparser.ConfigParser, section: str, key: str, default: str = "") -> str:
    if not parser.has_section(section):
        return default
    return (parser.get(section, key, fallback=default) or default).strip()


def _side(name: str, direction: str, camera_ip: str, controller_ip: str, display_ip: str) -> dict:
    return {
        "name": name,
        "lane_direction": direction,
        "camera_ip": camera_ip,
        "controller_ip": controller_ip,
        "display_ip": display_ip,
    }


def _lanes_from_ini(path: Path) -> tuple[dict, ...] | None:
    if not path.is_file():
        return None
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        parser.read_string(_read_ini_text(path))
    except configparser.Error:
        return None
    lane1_in = _ini_get(parser, "Communication", "InIPCapture")
    lane1_out = _ini_get(parser, "Communication", "OutIPCapture")
    lane2_in = _ini_get(parser, "Communication", "InIPCapture2")
    lane2_out = _ini_get(parser, "Communication", "OutIPCapture2")
    if not all((lane1_in, lane1_out, lane2_in, lane2_out)):
        return None
    return (
        {
            "name": "1#",
            "note": "Lane 1# (camera / controller / display).",
            "sides": (
                _side(
                    "Entry",
                    "ENTRY",
                    lane1_in,
                    _ini_get(parser, "Communication", "BoardIn"),
                    _ini_get(parser, "Setup", "IpAddr1"),
                ),
                _side(
                    "Exit",
                    "EXIT",
                    lane1_out,
                    _ini_get(parser, "Communication", "BoardOut"),
                    _ini_get(parser, "Setup", "IpAddr11"),
                ),
            ),
        },
        {
            "name": "2#",
            "note": "Lane 2# (camera / controller / display).",
            "sides": (
                _side(
                    "Entry",
                    "ENTRY",
                    lane2_in,
                    _ini_get(parser, "Communication", "BoardIn2"),
                    _ini_get(parser, "Setup", "IpAddr2"),
                ),
                _side(
                    "Exit",
                    "EXIT",
                    lane2_out,
                    _ini_get(parser, "Communication", "BoardOut2"),
                    _ini_get(parser, "Setup", "IpAddr22"),
                ),
            ),
        },
    )


def load_site_lanes(ini_path: Path | None = None) -> tuple[dict, ...]:
    parsed = _lanes_from_ini(ini_path or site_ini_path())
    if parsed is not None:
        return parsed
    return tuple(dict(lane) for lane in _CANONICAL_LANES)


KNOWN_SITE_LANES = load_site_lanes()
# Gate rows are the numbered lanes (1# / 2#), not a single camera IP.
KNOWN_SITE_GATES = KNOWN_SITE_LANES


def flatten_site_cameras(lanes=KNOWN_SITE_LANES) -> tuple[dict, ...]:
    rows = []
    for lane in lanes:
        for side in lane["sides"]:
            rows.append(
                {
                    "lane_name": lane["name"],
                    "side": side["name"],
                    "gate_name": lane["name"],
                    "name": f'{lane["name"]} {side["name"]}',
                    "ip_address": side["camera_ip"],
                    "camera_ip": side["camera_ip"],
                    "controller_ip": side["controller_ip"],
                    "display_ip": side["display_ip"],
                    "lane_direction": side["lane_direction"],
                }
            )
    return tuple(rows)


KNOWN_SITE_CAMERAS = flatten_site_cameras()


def site_camera_ips() -> tuple[str, ...]:
    return tuple(row["ip_address"] for row in KNOWN_SITE_CAMERAS)


def site_controller_ips() -> tuple[str, ...]:
    return tuple(row["controller_ip"] for row in KNOWN_SITE_CAMERAS if row["controller_ip"])


def site_display_ips() -> tuple[str, ...]:
    return tuple(row["display_ip"] for row in KNOWN_SITE_CAMERAS if row["display_ip"])


def side_label(lane_direction: str | None) -> str:
    if (lane_direction or "").upper() == "EXIT":
        return "Exit"
    if (lane_direction or "").upper() == "ENTRY":
        return "Entry"
    return lane_direction or ""


def site_layout() -> dict:
    lanes = []
    for lane in KNOWN_SITE_LANES:
        entry = next(side for side in lane["sides"] if side["lane_direction"] == "ENTRY")
        exit_side = next(side for side in lane["sides"] if side["lane_direction"] == "EXIT")
        lanes.append(
            {
                "name": lane["name"],
                "note": lane.get("note") or "",
                "entry": {
                    "camera_ip": entry["camera_ip"],
                    "controller_ip": entry["controller_ip"],
                    "display_ip": entry["display_ip"],
                },
                "exit": {
                    "camera_ip": exit_side["camera_ip"],
                    "controller_ip": exit_side["controller_ip"],
                    "display_ip": exit_side["display_ip"],
                },
            }
        )
    return {
        "source": "site",
        "sdk_port": 30000,
        "http_port": 80,
        "username": "admin",
        "lanes": lanes,
        "gates": lanes,
        "camera_ips": list(site_camera_ips()),
        "controller_ips": list(site_controller_ips()),
        "display_ips": list(site_display_ips()),
        "actuators": {
            "camera_gpio": "Net_GateSetup (1=open) then Net_WriteGPIOState pulse on the live camera relay",
            "controller_board": "Board* TCP I/O on port 5000 (stx_open / tw_open frames)",
            "led_display": "LEDSender2010 UDP IpAddr* on port 6666 (PKC_NOTIFY + ROOT_PLAY)",
        },
        "note": (
            "Each numbered lane (1# / 2#) is an entry+exit pair. "
            "Cameras use NetSDK port 30000. Open barrier uses GPIO + Board TCP + LED UDP."
        ),
    }


def site_camera_defaults() -> dict:
    return {
        "sdk_port": settings.default_hvx_sdk_port,
        "username": "admin",
        "password": settings.default_camera_password,
    }


async def tcp_open(ip: str, port: int, timeout: float = 0.4) -> bool:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception:
        return False


def local_ipv4s() -> list[str]:
    ips: list[str] = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    return ips


def scan_prefix(local_ip: str) -> str | None:
    parts = local_ip.split(".")
    if len(parts) != 4:
        return None
    if parts[0] == "192" and parts[1] == "168":
        return ".".join(parts[:3])
    return None


async def probe_ips(ips: list[str], port: int) -> dict[str, bool]:
    unique = []
    for ip in ips:
        if ip and ip not in unique:
            unique.append(ip)

    async def one(ip: str):
        return ip, await tcp_open(ip, port)

    rows = await asyncio.gather(*[one(ip) for ip in unique])
    return {ip: ok for ip, ok in rows}


async def lan_sdk_candidates(port: int) -> list[str]:
    prefixes = []
    for ip in local_ipv4s():
        prefix = scan_prefix(ip)
        if prefix and prefix not in prefixes:
            prefixes.append(prefix)
    if not prefixes:
        prefixes = ["192.168.1"]
    ips = [f"{prefix}.{n}" for prefix in prefixes[:1] for n in range(1, 255)]
    found = await probe_ips(ips, port)
    return [ip for ip, ok in found.items() if ok]


def match_known(ip: str) -> dict | None:
    for row in KNOWN_SITE_CAMERAS:
        if row["ip_address"] == ip:
            return dict(row)
    return None


def camera_spec_for_ip(ip: str) -> dict:
    known = match_known(ip)
    defaults = site_camera_defaults()
    return {
        "name": (known or {}).get("name") or f"Camera {ip}",
        "ip_address": ip,
        "lane_direction": (known or {}).get("lane_direction") or "ENTRY",
        "lane_name": (known or {}).get("lane_name") or "",
        "side": (known or {}).get("side") or side_label((known or {}).get("lane_direction") or "ENTRY"),
        "controller_ip": (known or {}).get("controller_ip") or "",
        "display_ip": (known or {}).get("display_ip") or "",
        "gate_name": (known or {}).get("gate_name") or "",
        **defaults,
    }


def discovery_row(ip: str, *, tcp_open: bool, hvx_found: bool, existing: dict | None = None) -> dict:
    spec = camera_spec_for_ip(ip)
    return {
        **spec,
        "tcp_open": tcp_open,
        "hvx_found": hvx_found,
        "known_site": match_known(ip) is not None,
        "already_added": existing is not None,
        "camera_id": None if existing is None else existing.get("id"),
        "camera_status": None if existing is None else existing.get("status"),
        "reachable": tcp_open or hvx_found,
        "note": (
            "TCP open on 30000 is reachability only — not an SDK login"
            if tcp_open
            else "No TCP response on SDK port 30000"
        ),
    }
