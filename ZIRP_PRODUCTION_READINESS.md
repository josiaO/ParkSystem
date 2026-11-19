# Zirp production-readiness review (2026-11-17)

Branch `production-readiness` (head `01cbcad`, 22 commits on `main`). Evidence comes from SITE-PC01 with four live QY cameras on lanes 1# and 2#. ParkWatch still owns the booms, so no barrier was moved by Zirp. Details are in `ZIRP_ENGINEERING_HANDOVER.md` sections 16–17.

## Verdict

**Not yet ready to run an unattended lane.** It is ready for a supervised pilot: an operator present, a barrier override, and real money only after a verified payment test.

The camera, recognition and lane software is now in good shape. What is missing is mostly the physical sensing around the barrier, an end-to-end payment run, and a multi-PC run against a shared PostgreSQL. The Ubuntu simulation is designed to close the multi-PC and payment gaps.

## Done and verified on hardware

| Area | State |
|---|---|
| Cameras (QY/HVX) | Host runs as a boot-time service (Session 0, LocalSystem). All 4 cameras stream at 9.3–9.6 fps direct, with gaps ≤ 273 ms. The desktop reads frames straight from the local host. |
| Event loop / staleness | Loop p95 lag is 32–45 ms, down from 240–300 ms. Relay frame age p95 is 112–149 ms, down from 300–355 ms. A stall sampler names any new blocker. |
| Recognition | Camera event → parking decision takes 0.73–0.81 s p50 and ~1.0 s p95. The FastALPR read itself is ~130 ms. Back-to-back cars (2–3 s apart) are each captured. |
| Plate accuracy | Strict TZ slot correction (leading 1/7/I→T; digit and letter slot swaps, including J→3 and G→6), with special plates protected. A one-character misread within 10 s on the same gate no longer opens a second session. |
| Both lanes | Node heartbeat and failover: the Site Server serves the gates of an Edge Node that stops heartbeating. Measured live: lane 1# was served by SITE-PC01. |
| Capture zone | Per-camera capture distance (plate width), set in the desktop zone editor. The ground loop is not wired to camera inputs, so this is the "virtual loop". |
| Lane flow | Passage time-out (60 s). An exit read completes an entry still waiting for passage, and also an entry Zirp never opened the barrier for (`ENTRY_COMPLETED_AT_EXIT`, billed from entry). Entry attempts are no longer cancelled by a 15-min timer (it closed every casual visit on SITE-PC01 and their exits found no session); a plate read entering again supersedes its abandoned attempt (`ENTRY_SUPERSEDED`). |
| Revenue | Cash top-up after grace is recorded. Manual entry and supervised close go through the engine with permissions. Duplicates never claim the barrier opened. |
| Manual-open alerts | Plate, amount owed and photo link go to SMS (Africa's Talking), email and a signed webhook. Verified end to end via webhook. |
| Services | Stop in 2–5 s without admin. NSSM online rotation is off. The Site Service waits up to 90 s for the database. |
| Gate actuation | Uses the live SDK handle by camera IP. Camera relay, Board and LED run concurrently. |

## Not done, and what each needs before go-live

| # | Gap | Why it matters | What closes it |
|---|---|---|---|
| 1 | **Receipt-taken sensor (D1)** | Production requires "receipt taken" before the entry barrier opens. No printer adapter reports it, so every casual entry needs an operator click. | Pick the printer: a presenter printer with taken status, or a beam on a relay/GPIO input. Or decide on a "print and open" policy for this site. |
| 2 | **Real receipt printer** | Only simulated printing has run. The thermal printer path (ESC/POS / Windows spool) is untested on hardware. | Install the printer and run 50 tickets: QR legibility, cutter, paper-out alert. |
| 3 | **Passage / loop signal** | The ground loop is wired to the KF "Board" I/O controllers (UDP), not the cameras. Zirp currently assumes passage after 60 s. | Capture the Board UDP protocol (pktmon) and add a loop-input adapter, or rely on the time-out by documented policy. |
| 4 | **Mobile payment, end to end** | Proven end to end against the bundled mock ClickPesa (adapter, webhook, status query, ledger). Never run against ClickPesa itself: there are no keys and no sandbox. | One real 100 TZS payment with live keys and the operator's phone. |
| 5 | **Public reachability** | Webhooks and the receipt pay page must reach the Site Server from the internet over HTTPS. Today the server is plain HTTP on the LAN. | Reverse proxy with TLS (Caddy/nginx) or a tunnel, with only `/api/webhooks/*`, `/p/*`, `/s/*` and `/api/public/*` exposed. |
| 6 | **Multi-PC on shared PostgreSQL** | Edge Node + Site Server + shared media were implemented but never run together. Row locks and unique keys are sound in code, untested live. | The Ubuntu simulation: two lane PCs as Edge Nodes and Ubuntu as Site Server + DB. |
| 7 | **Security (D9)** | Camera passwords default to `admin`. The HVX host API has no auth. The LAN API is HTTP. Operator role can open gates. | Camera password policy, a shared secret on the HVX host, TLS or an IP allow-list on the LAN API, and a role review. |
| 8 | **Backup restore (D10)** | Backups exist but restore was never rehearsed. | Implement a restore and test it on the Ubuntu box (pg_dump → pg_restore). |
| 9 | **Reboot / power-cut test** | Services are set to start at boot, but this was never exercised by a real reboot. | Reboot each lane PC with nobody signed in. Cameras must stream and lanes decide within ~2 min. |
| 10 | **Boom feedback (D13)** | "Barrier opened" means "command accepted". There is no boom-up sensor. | Wire a boom-up contact if the barrier has one (the manual-open watcher already supports it). |
| 11 | **Same-class misreads** | e.g. T189EKP/T188EKP. Slot rules cannot fix these. | FastALPR fine-tuning on site images (the next accuracy step). |
| 12 | **ParkWatch cut-over** | ParkWatch drives the cameras (snapshot triggers) and the booms today. | A cut-over plan: Zirp triggers its own snapshots, then takes the booms lane by lane with a rollback. |

## Payments: is it architected well?

**Yes, the core design is right, and it should be kept.**
- **Provider seam:** a `PaymentProvider` protocol with `create_intent`, `initiate_collection`, `verify_callback` and `query_status`. ClickPesa, Flutterwave, a simulated provider and manual kiosk cash are implementations.
- **Ledger is the authority.** A payment is recorded only from a verified webhook or a status query, never from the push response. Unique `idempotency_key` and `provider_transaction_id` stop double credit.
- **Webhooks are authenticated.** HMAC-SHA256 checksum over canonical JSON, compared in constant time. A missing checksum key means webhooks are rejected.
- **Reconciliation loop** (`payments_reconcile_seconds`=60) settles intents whose webhook never arrived.
- **Live safety gate.** Real collection needs `CLICKPESA_LIVE_ENABLED=1` and `PAYMENTS_LIVE_PROVIDER_CONFIRMED=1`.
- **Kiosk:** mobile money uses the same intent and status flow; kiosk cash can be disabled for unattended kiosks.

Weaknesses found, now fixed (2026-11-17):
- **Mock mode.** ClickPesa runs in `MOCK` mode when its base URL is a private host (loopback, LAN address, `.test`/`.local`). Credentials and webhook checksums are still required. Real hosts keep the live gate, so "LIVE" always means real money, and `/payments/health` reports `real_money`.
- **Phone-side approval.** The bundled mock ClickPesa (`python -m app.mock_services.clickpesa`) has the real API shape, a phone page (approve, decline, ignore, reverse) and fault switches. It replaces the auto-approving simulated provider for realistic tests.
- **Two money gaps found and fixed:**
  - A driver approving *after* the local expiry was charged but never credited. It is now credited once and flagged `late_success`.
  - A reversal after success was ignored silently. It is now flagged for an operator (audit, `reversals` stat, back-office card) and never rewrites the ledger by itself.
- **End-to-end tests:** `tests/test_payments_mock_clickpesa.py` drives the real adapter and webhook route against the mock: approve, decline, timeout, dropped, duplicate and forged webhooks, underpayment, outage and recovery, late success, reversal.
- **Payments module:** `07_payments.py` is now a normal module (`app/api/payment_handlers.py`). The runtime part only re-exports it, so `app.api_main.<name>` patches still work.
- **Verified live on SITE-PC01:** pay page → mock push → approve on `/phone` → checksummed webhook → status query → ledger credited once (TZS 649,000, MOCK) → page shows "Payment received". A webhook through the portal is accepted when signed and rejected when tampered.

## Should it be rewritten in Next.js?

**No rewrite.**
- **The hard part stays in Python.** The NetSDK camera host, FastALPR, the lane engine, the ledger and gate control remain there.
- **Next.js is a separate front end.** It runs as a portal (`portal/`) that calls the existing FastAPI API:
  - public pay page (mobile first, English/Swahili, live payment status, test-mode banner);
  - back office (overview, sessions, payment ledger and provider health, reconciliation, reports, CSV);
  - one-command start (`start-portal.bat` / `start-portal.sh`).
- **No secrets in the portal.** Operator tokens stay in httpOnly cookies, and provider webhooks pass through unchanged.

## Recommended order

1. Ubuntu simulation: multi-PC, mock payments and alerts (gaps 4a, 6, 8; part of 7).
2. Printer + receipt-taken decision (1, 2), and the reboot test (9).
3. Public HTTPS endpoint (5), then one real ClickPesa payment (4b).
4. Supervised pilot on one lane, with ParkWatch cut-over for that lane only (12).
5. Loop or boom signals (3, 10), security hardening (7), then FastALPR fine-tuning (11).
