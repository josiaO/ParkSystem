"""Ground-loop I/O boards (BoardIn / BoardOut): Zirp's own UDP listener.

Each lane side has a small network I/O board (192.168.1.61/.69/.65/.67 on
SERVER01) that the ground loops, ticket button and barrier are wired to.
The protocol below was read from the legacy ParkWatch program
(``TFormInOut.IdUDPServer1UDPRead`` and its send routine in Park.exe); see
``docs/LOOP_BOARD_PROTOCOL.md``. Nothing here depends on ParkWatch.

Board -> PC (UDP, from the board's port 8000 to the PC's port 8000)::

    byte 0   0x7E                start of frame
    byte 1   direction           1 entry board, 2 exit board
    byte 2   event               0 car come (loop occupied)
                                 1 car go   (loop cleared)
                                 2 ticket button (entry boards)
                                 6 card read, card number in bytes 5..8
                                 7 reset
    byte 3   length
    ...      data, then an XOR checksum

PC -> board (UDP to the board's port 8000), built as ParkWatch does::

    7E, direction, command, length, XOR(bytes 1..3), zero padded to 200 bytes
    "0901" open the barrier       "0D01" sent to every board at start-up
    "1401" sent to the exit board when a paid/free exit is accepted
"""

from __future__ import annotations

import asyncio
import logging
import socket
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

log = logging.getLogger("smartpark.loop_board")

BOARD_UDP_PORT = 8000
FRAME_START = 0x7E
FRAME_BYTES = 200                 # ParkWatch sends a fixed 200-byte buffer

DIRECTION_ENTRY = 1
DIRECTION_EXIT = 2

EVENT_CAR_COME = 0
EVENT_CAR_GO = 1
EVENT_PRINT = 2
EVENT_CARD = 6
EVENT_RESET = 7
EVENT_NAMES = {
    EVENT_CAR_COME: "car_come",
    EVENT_CAR_GO: "car_go",
    EVENT_PRINT: "print",
    EVENT_CARD: "card",
    EVENT_RESET: "reset",
}

COMMAND_OPEN_GATE = "0901"
COMMAND_HELLO = "0D01"
COMMAND_EXIT_DONE = "1401"


def _xor(data: bytes) -> int:
    value = 0
    for byte in data:
        value ^= byte
    return value & 0xFF


@dataclass(frozen=True)
class BoardEvent:
    board_ip: str
    peer_port: int
    direction: int
    event: int
    kind: str
    card: str = ""
    raw: bytes = field(default=b"", repr=False)

    @property
    def occupied(self) -> bool | None:
        """Loop state carried by this event (None when it is not a loop event)."""
        if self.event == EVENT_CAR_COME:
            return True
        if self.event == EVENT_CAR_GO:
            return False
        return None


def parse_frame(data: bytes, peer_ip: str = "", peer_port: int = 0) -> BoardEvent | None:
    """Decode one board datagram; ``None`` for anything that is not a board frame."""
    if len(data) < 3 or data[0] != FRAME_START:
        return None
    event = int(data[2])
    card = ""
    if event == EVENT_CARD and len(data) >= 9:
        card = str(int.from_bytes(data[5:9], "big")).zfill(10)
    return BoardEvent(
        board_ip=str(peer_ip or ""), peer_port=int(peer_port or 0), direction=int(data[1]),
        event=event, kind=EVENT_NAMES.get(event, f"unknown_{event}"), card=card, raw=bytes(data[:32]),
    )


def command_frame(code: str, direction: int) -> bytes:
    """Build a PC -> board command exactly as ParkWatch's send routine does."""
    body = bytes.fromhex(code)
    if len(body) < 2:
        raise ValueError(f"board command {code!r} needs a command and a length byte")
    frame = bytearray(FRAME_BYTES)
    frame[0] = FRAME_START
    frame[1] = DIRECTION_ENTRY if int(direction) == DIRECTION_ENTRY else DIRECTION_EXIT
    frame[2:2 + len(body)] = body
    length = frame[3]
    frame[length + 3] = _xor(bytes(frame[1:length + 3]))
    return bytes(frame)


def direction_for(lane_direction: str | None) -> int:
    return DIRECTION_EXIT if (lane_direction or "").upper() == "EXIT" else DIRECTION_ENTRY


async def send_command(ip: str, code: str, *, direction: int, port: int | None = None,
                       dry_run: bool = False) -> dict:
    """Send one command datagram to a board (no reply is expected)."""
    from app.config import settings

    dest_port = int(port or getattr(settings, "loop_board_port", BOARD_UDP_PORT) or BOARD_UDP_PORT)
    frame = command_frame(code, direction)
    result = {"ok": False, "ip": ip, "port": dest_port, "command": code,
              "sent_hex": frame[:8].hex(" "), "dry_run": dry_run}
    if not ip:
        result["message"] = "no board IP"
        return result
    if dry_run:
        result.update(ok=True, message=f"dry-run {code} -> {ip}:{dest_port}")
        return result
    listener = _listener
    try:
        if listener is not None and listener.transport is not None:
            # From the bound port 8000: boards may only accept their peer's port.
            listener.transport.sendto(frame, (ip, dest_port))
        else:
            def _send() -> None:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.sendto(frame, (ip, dest_port))

            await asyncio.to_thread(_send)
        result.update(ok=True, message=f"board {code} sent to {ip}:{dest_port}")
    except OSError as exc:
        result["message"] = f"board send failed: {exc}"
    return result


EventHandler = Callable[[BoardEvent], Awaitable[None]]


class BoardListener(asyncio.DatagramProtocol):
    """Receives board datagrams and hands decoded events to ``handler``."""

    def __init__(self, handler: EventHandler | None = None) -> None:
        self.handler = handler
        self.transport: asyncio.DatagramTransport | None = None
        self.stats: dict = {"frames": 0, "ignored": 0, "by_kind": {}, "boards": {}, "last": None}

    def connection_made(self, transport) -> None:  # pragma: no cover - asyncio plumbing
        self.transport = transport

    def datagram_received(self, data: bytes, addr) -> None:
        peer_ip, peer_port = str(addr[0]), int(addr[1])
        event = parse_frame(data, peer_ip, peer_port)
        if event is None:
            self.stats["ignored"] += 1
            return
        self.stats["frames"] += 1
        self.stats["by_kind"][event.kind] = self.stats["by_kind"].get(event.kind, 0) + 1
        self.stats["boards"][peer_ip] = self.stats["boards"].get(peer_ip, 0) + 1
        self.stats["last"] = {"board": peer_ip, "port": peer_port, "kind": event.kind, "at": time.time()}
        _trace("board.frame", board=peer_ip, port=peer_port, kind=event.kind,
               direction=event.direction, raw=bytes(data[:12]).hex(" "))
        if self.handler is not None:
            task = asyncio.get_running_loop().create_task(self._dispatch(event), name="loop-board-event")
            _pending.add(task)
            task.add_done_callback(_pending.discard)

    async def _dispatch(self, event: BoardEvent) -> None:
        try:
            await self.handler(event)
        except Exception:
            log.exception("loop board event failed board=%s kind=%s", event.board_ip, event.kind)


_listener: BoardListener | None = None
_pending: set[asyncio.Task] = set()


def _trace(stage: str, **fields) -> None:
    try:
        from app.core import latency_trace

        latency_trace.emit(stage, **fields)
    except Exception:
        pass


def stats() -> dict:
    listener = _listener
    if listener is None:
        return {"listening": False}
    return {"listening": listener.transport is not None, **listener.stats}


async def serve(handler: EventHandler, *, host: str = "0.0.0.0", port: int = BOARD_UDP_PORT) -> None:
    """Listen for board datagrams until cancelled."""
    global _listener
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: BoardListener(handler), local_addr=(host, int(port)), family=socket.AF_INET,
    )
    _listener = protocol
    log.info("loop boards: listening on UDP %s:%s", host, port)
    try:
        await asyncio.Event().wait()
    finally:
        transport.close()
        if _listener is protocol:
            _listener = None
