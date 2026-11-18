"""Ground-loop I/O boards: the UDP protocol read from Park.exe, and Zirp's listener.

Boards push ``7E <direction> <event> ...`` from port 8000: event 0 car come,
1 car go, 2 ticket button, 6 card, 7 reset. ParkWatch opens the barrier by
sending ``7E <direction> 09 01 <xor>`` (a 200-byte buffer) to the board's
port 8000. Zirp listens itself, so loops need neither ParkWatch nor camera wiring.
"""

from __future__ import annotations

import asyncio
import socket
from unittest.mock import AsyncMock, patch

from app.services import loop_board


def test_board_frames_decode_like_parkwatch():
    come = loop_board.parse_frame(bytes([0x7E, 1, 0, 1, 0]), "192.168.1.61", 8000)
    go = loop_board.parse_frame(bytes([0x7E, 2, 1, 1, 2]), "192.168.1.69", 8000)
    card = loop_board.parse_frame(bytes([0x7E, 1, 6, 5, 0, 0x00, 0x12, 0xD6, 0x87, 0]), "192.168.1.61", 8000)
    assert (come.kind, come.occupied, come.direction) == ("car_come", True, 1)
    assert (go.kind, go.occupied, go.direction) == ("car_go", False, 2)
    assert card.kind == "card" and card.card == "0001234567" and card.occupied is None
    assert loop_board.parse_frame(bytes([0x7E, 1, 2]), "x").kind == "print"
    assert loop_board.parse_frame(b"\x55\x03\x00\x00", "x") is None      # not a board frame
    assert loop_board.parse_frame(b"\x7E", "x") is None


def test_open_gate_command_matches_parkwatch_send_routine():
    entry = loop_board.command_frame(loop_board.COMMAND_OPEN_GATE, loop_board.DIRECTION_ENTRY)
    exit_ = loop_board.command_frame("0901", loop_board.DIRECTION_EXIT)
    assert len(entry) == 200 and not any(entry[5:])
    assert entry[:5] == bytes([0x7E, 0x01, 0x09, 0x01, 0x01 ^ 0x09 ^ 0x01])
    assert exit_[:5] == bytes([0x7E, 0x02, 0x09, 0x01, 0x02 ^ 0x09 ^ 0x01])
    # ParkWatch passes 3 for "exit, accepted"; anything but 1 is the exit board.
    assert loop_board.command_frame("1401", 3)[:5] == bytes([0x7E, 0x02, 0x14, 0x01, 0x02 ^ 0x14 ^ 0x01])


def _free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_listener_receives_board_datagrams_and_sends_commands():
    port = _free_udp_port()
    seen: list[loop_board.BoardEvent] = []

    async def handler(event):
        seen.append(event)

    async def run():
        server = asyncio.create_task(loop_board.serve(handler, host="127.0.0.1", port=port))
        await asyncio.sleep(0.1)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as board:
            board.bind(("127.0.0.1", 0))
            board.settimeout(2)
            board.sendto(bytes([0x7E, 1, 0, 1, 0]), ("127.0.0.1", port))
            board.sendto(b"noise", ("127.0.0.1", port))
            board.sendto(bytes([0x7E, 1, 1, 1, 1]), ("127.0.0.1", port))
            await asyncio.sleep(0.2)
            stats = loop_board.stats()
            # The open command leaves from the listening port, as ParkWatch's does.
            result = await loop_board.send_command("127.0.0.1", "0901", direction=1,
                                                   port=board.getsockname()[1])
            data, addr = board.recvfrom(512)
        server.cancel()
        await asyncio.gather(server, return_exceptions=True)
        return stats, result, data, addr

    stats, result, data, addr = asyncio.run(run())
    assert [e.kind for e in seen] == ["car_come", "car_go"]
    assert stats["frames"] == 2 and stats["ignored"] == 1 and stats["listening"]
    assert result["ok"] and data[:5] == bytes([0x7E, 1, 9, 1, 9]) and addr[1] == port
    assert loop_board.stats() == {"listening": False}


def test_board_edges_drive_the_lane_like_a_loop_report():
    from app import api_main as api
    from app.services.presence import coil_watch

    passages: list[int] = []

    async def passage(camera_id):
        passages.append(camera_id)

    async def run():
        with patch.object(api, "_camera_for_board", return_value=(4402, 11)), \
             patch.object(api, "LOOP_CAPTURE_WAIT_SECONDS", 0.05), \
             patch.object(api, "_complete_passage_from_sensor", side_effect=passage), \
             patch.object(api, "_read_presence_now", new=AsyncMock()) as snapshot:
            states = []
            for frame in (bytes([0x7E, 1, 0, 1, 0]), bytes([0x7E, 1, 2, 1, 0]), bytes([0x7E, 1, 1, 1, 1])):
                await api._on_board_event(loop_board.parse_frame(frame, "192.168.1.61", 8000))
                states.append(coil_watch.occupied(4402))
                await asyncio.sleep(0.1)
            return states, snapshot.await_args_list

    try:
        states, snapshots = asyncio.run(run())
    finally:
        coil_watch.reported_edge(4402, False, source="test")
    assert states == [True, True, False]       # come, ticket button (no loop change), go
    assert passages == [4402]                  # car go completes the passage
    # The camera stayed silent after the loop tripped, so Zirp snapped it.
    assert [call.args[:2] for call in snapshots] == [(4402, 11)]


def test_unmapped_board_is_ignored():
    from app import api_main as api

    with patch.object(api, "_camera_for_board", return_value=None), \
         patch.object(api, "_apply_loop_edge", new=AsyncMock()) as edge:
        asyncio.run(api._on_board_event(loop_board.parse_frame(bytes([0x7E, 1, 0]), "10.0.0.9", 8000)))
    assert edge.await_count == 0


def test_udp7e_board_frame_opens_through_the_loop_board():
    from app.services import board_tcp

    with patch.object(board_tcp.settings, "board_tcp_frame", "udp7e_open"), \
         patch.object(board_tcp, "_board_direction", new=AsyncMock(return_value=2)):
        opened = asyncio.run(board_tcp.send_board_command("192.168.1.69", action="open", dry_run=True))
        closed = asyncio.run(board_tcp.send_board_command("192.168.1.69", action="close", dry_run=True))
    assert opened.ok and opened.frame_name == "udp7e_open" and opened.sent_hex.startswith("7e 02 09 01 0a")
    assert closed.ok and "no close" in closed.message


def test_mediamtx_leaves_udp_8000_to_the_boards():
    from app.services import mediamtx

    with patch.object(mediamtx, "config_path") as path:
        written = {}
        path.return_value.write_text.side_effect = lambda text, **_: written.setdefault("text", text)
        path.return_value.parent.mkdir.return_value = None
        try:
            mediamtx.write_config({})
        except Exception:
            pass
    text = written.get("text", "")
    assert "rtpAddress: :8050" in text and "rtcpAddress: :8051" in text
