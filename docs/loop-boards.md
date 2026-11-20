# Ground-loop I/O boards: protocol and Zirp wiring

Each lane side has a small network I/O board. On SERVER01 these are:

| Board | IP | Lane side | Camera |
|---|---|---|---|
| BoardIn | 192.168.1.61 | Lane 1# entry | .144 |
| BoardOut | 192.168.1.69 | Lane 1# exit | .145 |
| BoardIn2 | 192.168.1.65 | Lane 2# entry | .49 |
| BoardOut2 | 192.168.1.67 | Lane 2# exit | .50 |

The ground loops, the ticket button and the barrier relay are wired to these boards. The legacy ParkWatch program talked to them, and that is where this protocol was read from. Zirp now talks to them directly; nothing in Zirp loads or calls ParkWatch.

## Where the protocol comes from

The protocol was read from `Park.exe`, a Delphi program:

- **Receiving:** the receive handler is the published method `TFormInOut.IdUDPServer1UDPRead`, at code address `0x4e31f8`. It is an Indy `TIdUDPServer` handler.
- **Opening the socket:** `FormShow` binds the UDP server to **port 8000** (`DefaultPort := 0x1f40`, then `Active := True`). It also opens a second UDP server on port 8900, which has no handler.
- **Sending:** the send routine is at `0x49c7c8` and the XOR checksum routine is at `0x49c7a0`.
- **Callers of the send routine:** there are 18 calls, including `bbOpenGateInClick`, `bbOpenGateOutClick`, `bbOutOkClick`, `bbOutFreeClick`, `TimerProcessTimer` (lane 1) and `TimerProcess2Timer` (lane 2).
- **Board addresses:** ParkWatch keeps them in `ParkWatch.ini [Communication]` as `BoardIn`, `BoardOut`, `BoardIn2` and `BoardOut2`.

## Board to PC

The board sends UDP from its port 8000 to the PC's port 8000.

| Byte | Meaning |
|---|---|
| 0 | `0x7E`: start of frame. ParkWatch drops anything else. |
| 1 | Direction: 1 is an entry board, 2 is an exit board. |
| 2 | Event (see the table below). |
| 3 | Length. |
| … | Data, then an XOR checksum. ParkWatch does not check this checksum on receive. |

Event codes in byte 2:

| Code | ParkWatch log text | Meaning |
|---|---|---|
| 0 | " Car Come" | A car arrived on the loop. ParkWatch sets its "car present" flag. |
| 1 | " Car go" | The loop cleared. ParkWatch clears the flag. |
| 2 | " Print..." | The ticket button was pressed. This only comes from entry boards. |
| 6 | (none) | A card was read. The card number is in bytes 5–8 as a big-endian integer, padded to 10 digits. Zirp does not use cards. |
| 7 | " Reset" | The board reset. |

ParkWatch only accepts a frame when both of these are true:

- the peer IP equals one of the four board IPs;
- the peer port is 8000.

Zirp accepts any source port and records it in the trace.

## PC to board

The PC sends to the board's port 8000. ParkWatch always sends a 200-byte buffer, padded with zeros:

```
7E  <direction>  <command>  <length>  <XOR of bytes 1..length+2>  00 …
```

- **Direction:** 1 for an entry board. Any other value (2, or 3 for an accepted exit) puts 2 in this byte.
- **Example:** to open the barrier at an entry board, send `7E 01 09 01 09`.

| Command | When ParkWatch sends it |
|---|---|
| `0901` | Open the barrier. Sent by the manual open buttons, and automatically by the lane timers. |
| `0D01` | Sent to all four boards at start-up. |
| `1401` | Sent to the exit board when an exit is accepted as paid or free (`bbOutOkClick`, `bbOutFreeClick`). |

There is no close command; the boom closes by itself.

## How Zirp uses it

### Listener

`app/services/loop_board.py` listens on UDP `loop_board_port` (8000). It starts with the Site Service and is supervised: if the bind fails, it retries every 30 s.

### Mapping a board to a camera

A board is matched to a camera through the camera's **Controller IP** field (`controller_ip`, which is the board IP). This field is set in the camera dialog. Datagrams from boards that are not mapped are traced as `board.unmapped` and ignored.

### Loop edges

"Car come" and "car go" go through the same path as the camera's own loop-detector report (`_apply_loop_edge`):

- **Rising edge (car come):**
  1. The lane is marked occupied.
  2. If the camera does not deliver its own capture within 1.5 s, Zirp commands a snapshot.
- **Falling edge (car go):** completes the passage for a session whose gate is open.

The ticket button, card and reset events are only traced, as `board.event`.

### Opening the barrier through the board

This is opt-in. Set:

```
SMARTPARK_BOARD_TCP_FRAME=udp7e_open
```

With that set, a gate open also sends `0901` to the camera's board. The default (`stx_open`) leaves the board alone, and the camera relay opens the boom as before.

### MediaMTX

By default MediaMTX binds UDP 8000/8001 for RTSP-server RTP. Zirp now moves it to 8050/8051 so that port 8000 is free for the boards. Zirp's readers use TCP, so nothing else changes.

### Traces

| Trace | Meaning |
|---|---|
| `board.frame` | Every datagram received (board, port, kind, first bytes). |
| `lane.loop_edge source=loop-board` | A loop edge from a board. |
| `lane.loop_snapshot_commanded` | Zirp commanded a snapshot after a loop edge. |

## Moving a lane from ParkWatch to Zirp

1. **Check where the boards send.** They send to the IP of the PC that ran ParkWatch, on port 8000. Either:
   - give the Zirp lane PC that IP; or
   - set each board's destination IP to the Zirp PC with the board vendor's tool.

   Only one program can own port 8000 on a PC, so ParkWatch must be stopped on that PC.
2. **Allow inbound UDP 8000.** Run this once, as administrator, on the Zirp PC:

   ```
   netsh advfirewall firewall add rule name="Zirp loop boards" dir=in action=allow protocol=UDP localport=8000
   ```
3. **Fill in the Controller IP on each camera:**

   | Camera | Controller IP |
   |---|---|
   | .144 | .61 |
   | .145 | .69 |
   | .49 | .65 |
   | .50 | .67 |
4. **Check that it works.** Drive over a loop and look for `board.frame` and `lane.loop_edge source=loop-board` in the latency trace.
