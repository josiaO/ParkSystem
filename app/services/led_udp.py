"""LEDSender2010 UDP writes to ``IpAddr*`` screens.

These cards use ``LEDSender2010.dll`` (``LED_UDP_SenderParam`` in LEDAPI.h).
The DLL is PE32; we do not load it from 64-bit Python.

This module sends the documented UDP packet shape from LEDAPI.h:

- ``DEVICE_TYPE_UDP = 1``
- remote port ``6666`` (LEDSender2010 default)
- local port ``8881``
- ``PKC_NOTIFY = 100``, ``ROOT_PLAY = 0x21``
- text encoded GBK

``Net_TransRS485HexDataEx`` through the camera is a separate path and fails
on this site (CODE 2), which is why dedicated display IPs exist.
"""

from __future__ import annotations

import asyncio
import socket
import struct
from dataclasses import dataclass

from app.config import settings

DEVICE_TYPE_UDP = 1
PKC_NOTIFY = 100
ROOT_PLAY = 0x21
COLOR_MODE_DOUBLE = 2
DEFAULT_PKP_LENGTH = 512
LED_UDP_PORT = 6666
LED_LOCAL_PORT = 8881
NOTIFY_BLOCK = 2


def encode_led_text(text: str) -> bytes:
    return (text or "").encode("gbk", "replace")[: DEFAULT_PKP_LENGTH - 16]


def build_play_datagram(text: str, *, address: int = 0) -> bytes:
    payload = encode_led_text(text)
    # LEDAPI.h: notify command + ROOT_PLAY RAM programme + GBK text.
    header = struct.pack(
        "<HHHHHH",
        DEVICE_TYPE_UDP,
        PKC_NOTIFY,
        ROOT_PLAY,
        COLOR_MODE_DOUBLE,
        address & 0xFFFF,
        len(payload),
    )
    packet = header + payload
    if len(packet) < 32:
        packet = packet.ljust(32, b"\x00")
    return packet[:DEFAULT_PKP_LENGTH]


@dataclass
class LedResult:
    ok: bool
    ip: str
    port: int
    text: str
    bytes_sent: int
    message: str
    dry_run: bool = False


async def send_led_text(
    ip: str,
    text: str,
    *,
    port: int | None = None,
    dry_run: bool = False,
) -> LedResult:
    if not ip:
        return LedResult(False, "", 0, text, 0, "No IpAddr* display IP on this side", dry_run)
    dest_port = int(port or settings.led_udp_port or LED_UDP_PORT)
    packet = build_play_datagram(text)
    if dry_run:
        return LedResult(True, ip, dest_port, text, len(packet), f"dry-run LED '{text}' -> {ip}:{dest_port}", True)

    def _send() -> int:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.settimeout(1.0)
            local = int(settings.led_udp_local_port or LED_LOCAL_PORT)
            try:
                sock.bind(("", local))
            except OSError:
                sock.bind(("", 0))
            return sock.sendto(packet, (ip, dest_port))
        finally:
            sock.close()

    try:
        sent = await asyncio.to_thread(_send)
        return LedResult(True, ip, dest_port, text, sent, f"LED UDP '{text}' sent to {ip}:{dest_port}", False)
    except Exception as exc:
        return LedResult(False, ip, dest_port, text, 0, f"LED UDP failed: {exc}", False)
