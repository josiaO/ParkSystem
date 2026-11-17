# Zirp: Improvement Plan, informed by how ParkWatch runs Rock City Mall today

Date: 2026-11-16. Companion to `ZIRP_ENGINEERING_HANDOVER.md` (defect numbers D1–D31 refer to it).

**Sources**
- The ParkWatch installation in `Current_ParkSystem_configs/`: `ParkWatch.ini`, runtime logs (Jan–Feb 2024), table backups, vendor headers `DUCP.h` / `DVNetSDK.h` / `Net_Interface.h`.
- The existing Ghidra audits and full `Park.exe` disassembly in `research/parkwatch/`.
- Live measurements on the SITE-PC01 test bench.

**Limits**
- No Ghidra decompilation was run in this pass: the 543 MB download ran at about 2.5 MB/min and was stopped. Where a fact still needs confirming, a cheaper field method is given instead.
- Customer records in the backups were examined only as aggregate counts.

---

## 1. What ParkWatch actually does (evidence)

| Area | ParkWatch behaviour | Evidence |
|---|---|---|
| **Identity** | Ticket/card first, plate second: TG800 card reader, `CardCollect=ON`; 33% of 69,198 exit records carry no plate | `ParkWatch.ini [Card]`; `Backup/OutRecord.bdb` |
| **Cameras** | One native owner per camera: `DVNetSDK` → `IPC_QY.dll` → `NetSDK`/`PlaySdk` with a continuous decode worker and a bounded reopen path; event images arrive via the QY image callback, separate from display | `research/parkwatch/PARKWATCH-FRESH-GHIDRA-AUDIT-2026-11-02.md` |
| **Boom (automatic)** | `DV_Exec` (command 102 → `Net_GateSetup` OPEN) over the camera's control connection. 2,220 OK / 51 failed (2.2%, code 2 = camera link down) in the Feb 2024 log; **no retry** after a failure | `Logs/Park.exe.txt`; `PARKWATCH_GATE_CONTROL.md` |
| **Display & voice** | LED text and TTS sent as **KF DUCP frames over RS-485 *through the camera*** (`Net_TransRS485HexDataEx`). For example `0x62` text "Please pay: 0", `0x30` TTS "Pay 0", then the gate opens, then TTS "Have a good journey". Every vehicle event also sends a fixed DUCP `SYS_SET_IO` frame (`0F 06 … 0A`) | 69,655 RS-485 frames in `Park.exe.txt`; command table in `DUCP.h` |
| **"Board" devices** (`BoardIn*` .61/.69/.65/.67) | Used by the **manual "Arm Raise"** handlers: after `DV_Exec`, `Park.exe` sends the ASCII command `0901` to the board IP. The boards accept **no TCP connection** on 44 common ports, so the transport is UDP (`Park.exe` embeds Indy UDP). Port not yet confirmed | `Park.exe` `FUN_004b1b50`/`004b1e30`/`004cf2ec`/`004cf5cc`, string `0x8de8aa "0901\0Unknown Vehicle No.(Entry Arm Raise"`, globals `0x935f54–60` from `[Communication] BoardIn…`; bench TCP probe |
| **Manual opens** | Four handlers (entry/exit × lanes 1#/2#): operator confirms → camera relay + board `0901` → record written as **plate "Unknown", type "Unknown", fee 0, operator name**. 34 such exits out of 69,198 | Disassembly strings; `OutRecord.bdb` columns 3–5, 20, 25, 26 |
| **Receipts** | QuickReport `PrintBill` form to a Windows printer; `AutoPrint=ON`, `QRPrint=ON` (zint library); entry/exit text templates `In.rtf`/`Out.rtf` | `Park.exe` RTTI strings; `.ini` |
| **Payments & cash control** | Cashier/shift model: `ParkDiary` records each shift handover (operator out → in, cash totals, in/out counts); `Selfpayment=ON` | `Backup/ParkDiary.bdb`; `.ini` |
| **Security** | MSSQL `sa` login with its password **in plaintext** in `ParkWatch.ini` on both stations; plaintext `SuperPassword`; camera admin password in the ini | `ParkWatch.ini`, `ParkWachServer/.../ParkWatch.ini` |

**Takeaways**
- ParkWatch is reliable at the device layer: one native camera owner, with display, voice and boom all over the camera's own control link.
- It is weak at accountability: manual opens are anonymous and unpriced, and there are no gate retries, no passage confirmation, and plaintext credentials.
- Zirp should copy the device-layer patterns and keep its stronger business and audit model.

---

## 2. Security

| # | Change | Why (evidence) |
|---|---|---|
| S1 | Individual accounts per operator and cashier; disable shared `admin` for daily work; MFA or PIN for supervisors who can open barriers manually | Only `admin` + kiosk + node exist (D30); ParkWatch also attributes everything to "Administrator"/cashier names |
| S2 | Split permissions: `gates.open_manual` (supervisor), `payments.cash` (cashier), `kiosk.pay_mobile` (kiosk). Remove cash from the kiosk device role unless the kiosk is staffed | Kiosk device can record cash today (D29) |
| S3 | Distinct strong passwords for PostgreSQL `postgres` and `smartpark`; `ssl=on` with `db_sslmode=require` for the `.241` lane link | Same trivial password, `ssl=off` (D30) |
| S4 | Shared secret on the HVX host HTTP API (header checked by `hvx_host.py`), even on loopback | Any local process can pulse GPIO (D9) |
| S5 | TLS (or at least an allow-list) on the Site Service LAN port 8760; stop `/auth/setup` naming the admin on non-loopback requests | LAN probe (D30) |
| S6 | Require a camera password at camera creation (drop `default_camera_password="admin"`) | D9 |
| S7 | Never put DB or super passwords in `.ini`/`.env` (Zirp already uses DPAPI secrets; keep it) | ParkWatch's plaintext `sa` is the anti-pattern |

---

## 3. Stable camera control and connection

Zirp's HVX host already follows the ParkWatch pattern for display: one SDK owner, with native draw-data callbacks (verified live: about 10 fps, frame age p50 47–63 ms). What remains:

| # | Change | Why |
|---|---|---|
| C1 | **Push native plate events, decide on text first.** Host forwards the QY image-callback metadata immediately (long-poll or websocket); the Site Service decides on plate + score, then fetches panorama/crop asynchronously for evidence | Event-to-decision is 3.6 s p50 / 10.6 s max today (D26); the controller itself needs about 60 ms |
| C2 | **Resolve SDK handle by camera IP at use time**; clear `sdk_handle`/status on host loss and on disconnect | 10 s wrong-boom window after a host restart; stale `SDK_CONNECTED` rows (D6, D21) |
| C3 | **Run the HVX host as a service** after `Test-HvxHostAsService.ps1` passes (or auto-logon kiosk account) | Host was down after restarts; it is a logon task (D5) |
| C4 | Fix the hidden-window class lifetime in `40_video.py` (module-level `WNDPROC`) | Access-violation crash (D22) |
| C5 | Rotate or silence the host's per-request stdout log | about 30 MB/day (D20) |
| C6 | Clean service shutdown (handle NSSM stop/Ctrl-C, bounded task cancel) and NSSM stop timeouts | All three services ignore stop; worker hangs in StopPending (D28) |
| C7 | Make recognition mode honest: either feed native QY plates into fusion, or drop `HYBRID` for QY cameras | 0 native-sourced captures out of 7,916 (D18) |
| C8 | Consider the QY **main stream** for OCR evidence (the host serves stream_type 1, 704×576) | Exit/entry plate agreement only about 40% on bench data (D17) |
| C9 | Health and alert on **camera control-link down**, which also means no boom and no display | ParkWatch's 2.2% gate failures were all link-down (code 2) with no retry |

---

## 4. Boom control

| # | Change | Why |
|---|---|---|
| B1 | **Per-lane hardware profile**: GPIO output index and pulse, loop input index and polarity, optional board relay (protocol, port), optional display link (RS-485-via-camera or UDP) | Today these are global settings; lane 2# reality differs (D25, D27) |
| B2 | **Remove the TCP "Board" relay** path for lanes whose boards are UDP. When the board protocol is confirmed, add a `KfBoardUdp` actuator. Fire the camera relay and the board **in parallel**, never sequentially | Every open waits 1.5 s on a dead TCP connect (D27) |
| B3 | Confirm the board protocol in 5 minutes on the **ParkWatch PC**: `pktmon filter add -i 192.168.10.65` → `pktmon start --capture` → operator presses "Arm Raise" on lane 2# entry → `pktmon stop` → `pktmon etl2pcap`. This gives the UDP port and exact bytes (expected ASCII `0901`). No install needed | Static analysis found the payload and transport, not the port |
| B4 | **Retry once on link-down**, then route to an operator with a clear message; never pulse twice without the command UUID check | ParkWatch never retries; Zirp has idempotent command UUIDs already |
| B5 | **Passage confirmation**: wire and learn the loop input per lane (lane 2# inputs 1–4 read a constant `1` today); add an operator "vehicle passed" button and a time-out to review | D2, D25 |
| B6 | Optional: send the same **DUCP text and voice** ParkWatch uses ("Please pay X", "Have a good journey") over the camera's RS-485 (`Net_TransRS485HexDataEx`). The host already wraps the SDK, so this is a small endpoint, and it removes the dependency on the UDP LED path | ParkWatch logs prove this path works on these cameras |

---

## 5. Payments: mobile and kiosk

| # | Change | Why |
|---|---|---|
| P1 | **Fix cash top-up** after the grace period (cash idempotency key per amount/operation, not per session) | Reproduced: top-up silently lost (D3) |
| P2 | **Kiosk mobile money**: wire the kiosk "Mobile" button to the real intent flow (`/api/public/payment-intents` → push prompt → provider webhook → server-side verification). Today it posts `MOBILE_SIMULATED`, which production refuses | D29 |
| P3 | Configure one real provider (Flutterwave or ClickPesa) in sandbox, run the push → webhook → reconcile cycle, then live with `payments_live_provider_confirmed` | Payments health shows `simulated`, no provider configured |
| P4 | **Cashier shifts**: open/close shift with counted cash vs. ledger cash, per operator (what ParkWatch's `ParkDiary` does), and a shift report | Accountability for cash; ParkWatch staff are used to it |
| P5 | Unattended kiosk: QR scan → show amount → mobile money only; cash only on a staffed kiosk or cash-acceptor hardware | Removes "press cash to leave free" (D29) |
| P6 | Remove or guard the legacy `POST /sessions/{id}/exit` route | Reproduced: closes unpaid sessions (D4) |

---

## 6. Reliable receipt printing

Zirp already renders receipts with QR and supports ESC/POS over TCP, Windows RAW spool and CUPS. Gaps:

| # | Change | Why |
|---|---|---|
| R1 | **Printer readiness before session creation**: if the lane printer is offline or paper-out, show "Assistance" without creating a stranded session | D8 (reproduced) |
| R2 | ESC/POS status polling (`DLE EOT` paper, cover, error) on network thermal printers; alert on paper-low or paper-out | Prevents silent failures; ParkWatch has none either |
| R3 | **Receipt-taken**: buy a presenter printer that reports "ticket taken", or fit a beam at the slot into a camera GPIO input, then implement `CAP_TAKEN_SENSOR` | D1: today every casual entry needs an operator override |
| R4 | Reprint and duplicate receipt from the operator desk and kiosk (by plate or token), audited | Lost-ticket handling (ParkWatch: `CardCollect`, lost-card flows) |
| R5 | Bench-test the chosen printer with the existing `/printers/test` and a 500-ticket soak before go-live | No printer available on the bench today |

---

## 7. Manual-opening alerts with plate and amount owed (new feature)

**Goal:** every barrier opening that the parking engine did not authorize produces an alert containing the car (photo), its plate, the lane, who or what opened it, and how much the visit owed at that moment.

### 7.1 What counts as a manual opening

| Source | How Zirp sees it today | Needed |
|---|---|---|
| Zirp operator presses "Open gate" (`POST /gates/{id}/open`, `/cameras/{id}/barrier/open`, admit-without-receipt) | One audit line, no plate or fee | Enrich (7.2) |
| Opening by another system or a person outside Zirp (ParkWatch "Arm Raise", camera web UI, OcxConfig, remote fob, barrier push button) | **Invisible** | Detect (7.3) |

### 7.2 Enrich Zirp-initiated manual opens

At the moment of the manual open, the Site Service builds a `ManualOpenEvent`:

```text
gate, side, operator (user id + name), reason (required text), time
car:    latest VehicleCapture on that camera within N seconds (plate, confidence, photo, crop)
visit:  active session for that plate (site-wide), entry time, duration
money:  fresh quote at this moment (quote_stay) − paid_total → amount_owed, currency
result: GateCommandRecord (command uuid, actuator results)
```

Then:
1. Persist it: a new `manual_open_events` table, or `AccessDecision` with outcome `MANUAL_OPEN` plus these fields.
2. Write it to `AuditLog`.
3. Queue the alert (7.4).

If no plate was read within the window, the alert says **"unidentified vehicle"** and attaches the latest lane photo. Unlike ParkWatch, it is never silently recorded as "Unknown, fee 0".

If an exit is opened manually for a car that owed money, that amount is recorded as **unrecovered revenue** on the session, which stays flagged (not silently closed) until a supervisor resolves it.

### 7.3 Detect openings Zirp did not command

**Needs one hardware input per boom.** Wire the barrier controller's "open" or limit-switch contact (or a beam under the boom) into a free camera alarm input (lane 2# cameras expose inputs 1–7; 5–7 read `0` today). The existing `gpio-scan` polling (`_poll_coil_and_read`) can watch it.

When the input shows "boom up" and no Zirp `GateCommandRecord` for that gate exists within the last T seconds (for example 5 s), raise a `ManualOpenEvent` with `source=UNCOMMANDED` and the same car, visit and money enrichment.

Without that input, Zirp can only infer an opening (an exit-camera read followed by no open command and the car disappearing). That is too weak for alerts, so it should only be a report.

While ParkWatch still runs the lanes, its "Arm Raise" also sends `0901` to the board. A UDP listener could detect it, but that is a transitional trick, not the design.

### 7.4 Delivering the alert

| Requirement | Design |
|---|---|
| Content | Plate (or "unidentified"), lane and side, time, operator or "uncommanded", reason, **amount owed** and currency, link to the evidence photo (signed, short-lived URL), session reference |
| Channels | Configurable list. **SMS** through a Tanzanian aggregator (e.g. Africa's Talking or Beem), **WhatsApp Business** or **email** for supervisors and management, plus a red banner and sound in the desktop app. Photo goes by link (WhatsApp/email can attach) |
| Reliability | Durable outbox (reuse `queues.py` pattern): retries with back-off, dead letter, delivery status shown in the UI. Alerts must still be recorded when the internet is down and sent when it returns |
| Noise control | Thresholds: alert immediately if amount owed > 0 or the source is uncommanded; daily digest for zero-fee supervisor opens; per-operator counts in the shift report |
| Security | Recipients and API keys in the secret store (DPAPI); no customer phone numbers in alerts; the photo link expires |
| Audit | Alert row linked to the `ManualOpenEvent`; acknowledgement by a supervisor recorded |

### 7.5 Implementation status (2026-11-16, uncommitted in the working tree)

Built:

| Piece | Where |
|---|---|
| `ManualOpenEvent`, `AlertDelivery` tables; migration `0017_manual_open_alerts` (verified up/down/up on PostgreSQL 18) | `app/models/alerts.py`, `app/migrations/alembic/versions/0017_manual_open_alerts.py` |
| Recorder: latest plate read on the opened side (within 120 s), open visit, owed snapshot (subscriber / payment-grace / tariff, never modifies the session), photo and crop copied to `media/manual/` | `app/services/manual_open.py` |
| Wired into `POST /gates/{id}/open`, `POST /cameras/{id}/barrier/open` (opens only, not close or dry-run; reason of at least 3 characters now required) and `POST /sessions/{id}/admit-without-receipt` (only when a barrier command was issued) | `app/api/runtime_parts/06_parking.py` |
| Alert rules (unidentified, owed > 0 and uncommanded always; zero-fee and failed commands configurable), SMS via Africa's Talking, SMTP e-mail with photo attached, signed JSON webhook (e.g. a WhatsApp bridge) | `app/services/alerts.py` |
| Durable delivery: atomic row claim, retry with back-off 15 s → 1 h, dead after 8 attempts, runs only on the Site Server | `alerts.delivery_loop`, started in `lifespan` |
| API: `GET /manual-opens`, `GET /manual-opens/{id}`, `POST /manual-opens/{id}/acknowledge` (not by the person who opened, unless Admin), signed `GET /manual-opens/{id}/photo.jpg` (24 h, also reachable via the public tunnel), `GET/PUT /settings/alerts`, `POST /settings/alerts/test` | `app/api/alerts.py` |
| Permissions `alerts.view` (Admin, Developer) and `alerts.acknowledge` (Admin) | `DEFAULT_ROLES`, `access.gates` module |
| Desktop: red banner with plate, lane, owed amount, operator and reason, beep on new events, Acknowledge with note | `app/desktop/main/80_window.py`, `desk.manual_open_banner` |
| Uncommanded detection: configured boom-up input per camera (`boom_inputs`) is scanned with the loop inputs, kept out of loop learning, and a rising edge with no Zirp command in 8 s is recorded as `UNCOMMANDED` | `observe_boom_input`, `_poll_coil_and_read` |
| 23 tests | `tests/test_manual_open_alerts.py` |

Configuration on the Site Server (`.env` next to the install, or service environment):

```text
SMARTPARK_ALERTS_AFRICASTALKING_USERNAME=...      # "sandbox" for testing
SMARTPARK_ALERTS_AFRICASTALKING_API_KEY=...
SMARTPARK_ALERTS_AFRICASTALKING_SENDER_ID=...     # optional registered sender
SMARTPARK_ALERTS_SMTP_HOST=... / _PORT=587 / _USERNAME=... / _PASSWORD=... / _FROM=...
SMARTPARK_ALERTS_WEBHOOK_SECRET=...               # signs webhook bodies (X-Zirp-Signature)
SMARTPARK_PUBLIC_BASE_URL=https://...             # so SMS photo links open off-site
```

Then `PUT /settings/alerts` with `{"recipients": [{"channel": "sms", "to": "07…"}, {"channel": "email", "to": "…"}]}` and `POST /settings/alerts/test`.

**Bench deployment and live test (SITE-PC01, 2026-11-16 21:05–21:21)**

Preparation:
- 19 files copied into the installed kit; the replaced originals are backed up.
- The database was dumped first, at revision 0016.
- The Site Service applied `0017_manual_open_alerts` on restart (`/health/database` reports revision = head).

Results:

| Step | Result |
|---|---|
| `PUT /settings/alerts` (webhook recipient) and `POST /settings/alerts/test` | Saved; test alert received at the local webhook receiver |
| One supervised `POST /gates/2/open` side EXIT, as admin, with a reason | GPIO OK on handle 1 (= exit camera .50, matching the DB) |
| `ManualOpenEvent` #1 | Lane "2# Exit", operator, reason, plate `BT163EGK` read 40 s earlier (confidence 0.85), no open visit, owed 0; car photo (35 KB) and plate crop copied to `media/manual/` |
| Alert delivery | Webhook received the alert **4 s** after the opening; event `alert_status=SENT` |
| Signed photo link | Valid signature → 200 with the JPEG; tampered signature → 403 |
| Evidence quality | The photo shows a two-row plate **T163 EGK**; the OCR added a stray "B". The photo lets a supervisor correct it (see D17) |

Found during deployment:
- **Site setting `public_base_url` is `http://192.168.10.240/8760`** (slash instead of `:`). Alert photo links, and every **receipt QR code**, are built from it, so both point to a broken URL. The value was entered by hand, and `PATCH /settings/site` does not validate it. Fix the value and add validation.
- **Admin-owned log files block a normal start.** Log files first created by an elevated process are writable only by `PC` and Administrators, so the kit's `run-hvx-host.bat` started by another Windows user fails silently: the `>>` redirect is refused before Python runs, and `hvx_host.py` cannot open `hvx-host.log`. For the test the host was started with a bench copy of the launcher logging to a scratch folder. Fix: grant the SmartPark users group Modify on `C:\ProgramData\SmartParkEdge\logs` in the installer, and have the host fall back to stderr if its log file cannot be opened.

Not done yet:
- A settings screen in the desktop/web UI (the API exists).
- Wiring a boom-up input on lane 2# and setting `boom_inputs` (needs the electrician).
- Choosing and paying for an SMS sender.
- Deploying to the bench and running the live test.

### 7.6 Tasks (in order)

1. `ManualOpenEvent` model + migration; enrich the three Zirp manual-open routes (7.2); require a reason. Tests for: plate found, no plate, owed > 0, subscriber.
2. Alert outbox + SMS/email adapters + desktop banner; settings page for recipients and thresholds.
3. Wire and learn a "boom up" input on lane 2#; add uncommanded-open detection (7.3).
4. Shift report: manual opens per operator, unrecovered revenue.

---

## 8. Suggested order of work

1. **Field, no code:** loop input wiring and polarity on lane 2# (D25); `pktmon` capture of the board protocol (B3); choose the receipt printer and taken sensor (R3); choose the SMS provider (7.4).
2. **Revenue and safety correctness:** P1 cash top-up, P6 legacy route, R1 printer-before-session, C2 handle-by-IP, B2 parallel/no TCP board.
3. **Speed:** C1 push events and decide on text first (the measured cause of the slow boom).
4. **Manual-open alerts:** section 7 tasks 1–2, then 3 when the boom-up input is wired.
5. **Payments:** P2 kiosk mobile money, P3 provider sandbox to live, P4 cashier shifts.
6. **Platform hardening:** C3 host as service, C4–C6, S1–S6.
