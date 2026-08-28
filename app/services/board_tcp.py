"""Board* TCP I/O for barrier controllers.

BoardIn / BoardOut are parking controllers, not cameras. Do not SDK-connect them.
Default TCP port is 5000 (camera NetSDK stays 30000).

Frames come from the common TW parking I/O boards:

- ``stx_open`` / ``stx_close``: STX + ASCII command + ETX (``\\x021\\x03`` open)
- ``tw_open`` / ``tw_close``: ``AA 55`` header, XOR checksum (TW-series I/O)
"""

from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass

from app.config import settings

BOARD_TCP_PORT = 5000


def _xor(data: bytes) -> int:
    value = 0
    for byte in data:
        value ^= byte
    return value & 0xFF


def tw_frame(command: int, relay: int = 1) -> bytes:
    body = bytes([0x01, command & 0xFF, 0x00, relay & 0xFF])
    return b"\xAA\x55" + body + bytes([_xor(body)])


FRAMES = {
    "stx_open": b"\x02\x31\x03",
    "stx_close": b"\x02\x32\x03",
    "stx_stop": b"\x02\x33\x03",
    "tw_open": tw_frame(0x02, 1),
    "tw_close": tw_frame(0x03, 1),
}


def frame_for(name: str | None = None) -> bytes:
    key = (name or settings.board_tcp_frame or "stx_open").strip()
    if key not in FRAMES:
        raise ValueError(f"Unknown board frame {key!r}. Use one of: {', '.join(FRAMES)}")
    return FRAMES[key]


@dataclass
class BoardResult:
    ok: bool
    ip: str
    port: int
    frame_name: str
    sent_hex: str
    message: str
    dry_run: bool = False


def frame_name_for(action: str, style: str | None = None) -> str:
    chosen = (style or settings.board_tcp_frame or "stx_open").strip()
    if chosen.startswith("tw"):
        return {"open": "tw_open", "close": "tw_close"}.get(action, "tw_open")
    return {"open": "stx_open", "close": "stx_close", "stop": "stx_stop"}.get(action, "stx_open")


async def send_board_command(
    ip: str,
    *,
    action: str = "open",
    port: int | None = None,
    timeout: float | None = None,
    dry_run: bool = False,
) -> BoardResult:
    if not ip:
        return BoardResult(False, "", 0, "", "", "No Board* IP on this side", dry_run)
    name = frame_name_for(action)
    payload = FRAMES[name]
    dest_port = int(port or settings.board_tcp_port or BOARD_TCP_PORT)
    wait = float(timeout if timeout is not None else settings.board_tcp_timeout_seconds)
    hex_payload = payload.hex(" ")
    if dry_run:
        return BoardResult(True, ip, dest_port, name, hex_payload, f"dry-run {action} {ip}:{dest_port}", True)

    def _send() -> None:
        with socket.create_connection((ip, dest_port), timeout=wait) as sock:
            sock.settimeout(wait)
            sock.sendall(payload)
            try:
                sock.recv(64)
            except OSError:
                pass

    try:
        await asyncio.to_thread(_send)
        return BoardResult(True, ip, dest_port, name, hex_payload, f"Board TCP {action} sent to {ip}:{dest_port}", False)
    except Exception as exc:
        return BoardResult(False, ip, dest_port, name, hex_payload, f"Board TCP failed: {exc}", False)
