# ZIRP audit against spec sections 8B–8E (LAN-first, kiosk payments, cache, performance)

Date: 2026-11-19 · Branch: `production-readiness` · Method: code reading only. No code changed, no tests run, no measurements taken.

## Verdict

The core is LAN-first. Kiosk, desktop and operator screens load only local assets. Cash is written to PostgreSQL before the kiosk gets a reply, and duplicate clicks are absorbed by unique keys. Recognition events go into a durable SQLite outbox and wait out a database outage. There is no Redis, so none of the Redis risks in 8C apply.

The gaps are in **mobile money under failure**, **cash policy details** (amount tendered, overpayment, refunds) and **health reporting** (no internet indicator). One mobile-money issue can lose a driver's money.

## Findings, most severe first

### 1. A mobile-money request that times out is recorded as FAILED and never checked again (high) — FIXED 2026-11-19

**Fix applied:** `ProviderHTTP` now tells a failed connect (`connect_failed`, the request never left) apart from a lost answer (`unreachable`). A lost answer or a 5xx on the push/charge request leaves the intent PENDING with `outcome_unknown`, so reconciliation asks the provider and expires it if the provider never heard of it. `settle_intent` re-checks FAILED intents on a verified webhook, as it already did for EXPIRED, and flags a late credit with `late_success_after`. Tests: `tests/test_payments_mock_clickpesa.py`.

- `app/infrastructure/payments/clickpesa.py:247`: any `ProviderError`, timeouts included, returns `status: "FAILED"`.
- `app/services/mobile_payments.py:299`: `settle_intent` returns early for `FAILED` without asking the provider.
- `app/services/mobile_payments.py:428`: the webhook handler calls `settle_intent` and acknowledges with 200.

**Failure:** the USSD push reaches the phone but the response times out (slow uplink), so the intent becomes FAILED. The driver approves and pays, and the provider's success webhook arrives. `settle_intent` sees FAILED and returns without crediting, so the money is taken and the session still shows unpaid. Reconciliation won't fix it either, because `pending_intents` only scans CREATED/PENDING.

This breaks the 8B rule "Never assume a payment succeeded because a request timed out". The code assumes the opposite, failure, and with real money that is just as wrong.

**Fix:** a timeout or network error on initiate should give a new `UNKNOWN` status (or PENDING) that reconciliation queries. A verified success webhook should always reach `query_status`, even for a FAILED intent, the way EXPIRED is already re-checked.

### 2. The configured exit grace period is ignored (medium) — FIXED 2026-11-19

**Fix applied:** the ledger reads `payment_exit_grace_seconds` from the parking settings when it settles (`configured_exit_grace_seconds`), and 0 now means no grace. `mark_paid` no longer re-applies it. Tests: `tests/test_payment_exit_grace.py`.

- `app/infrastructure/payments/ledger.py:83` sets `payment_exit_grace_until` only when it is empty.
- `record_succeeded_payment` calls `apply_session_payment_state` with no `grace_seconds`, so the default of 15 minutes gets set first.
- `mark_paid` (`app/services/simulation/40_exit.py:48`) then passes the configured value, but the field is already set, so nothing changes. The kiosk QR path (`public_pay.py`) never passes it at all.
- `int(cfg.get(...) or 15*60)` also turns a configured `0` into 900 seconds.

**Effect:** whatever the site sets for `payment_exit_grace_seconds` (0–7200 allowed by the schema), exits get 15 minutes.

### 3. Cash records don't capture the amount received, overpayment or change (medium)
- `app/services/public_pay.py:79`: an amount above the remaining fee is silently reduced to the remaining fee.
- The ledger stores only the amount credited. There is no tendered amount, no change given and no field for a cashier session or shift.

8B step 4 asks to "record amount received", and 8B requires overpayment and cash reconciliation. As it stands, a cash drawer can't be reconciled against the ledger.

### 4. Refunds, voids and cash reconciliation aren't implemented (medium)
- The status constants `REFUNDED` and `PARTIALLY_REFUNDED` exist, and providers have a `refund()` method, but no API or service calls it.
- No void or cancel exists for a mistaken cash entry.
- A reversal after a mobile success is only flagged for an operator (`mobile_payments.py:417`), which is reasonable, but there is no tool to act on the flag.

### 5. No internet health indicator, and mobile money is offered when it can't work (medium)
- `app/services/health.py` reports database, cameras, workers and payment providers. Provider `available` is a **configuration** check (`clickpesa.py:142`), not a reachability check. Only the circuit-breaker snapshot reflects real reachability.
- Nothing probes internet reachability separately from the LAN or the provider.
- `public_session_payload` (`public_pay.py:33`) offers `MOBILE_MONEY` whenever a provider is configured, even with the breaker open or the internet down. The driver then gets a failure after a timeout.

8B requires separate Site Server, LAN, internet and provider indicators. LAN, Site Server and Edge Node liveness exist through node heartbeats (`node_scope.py`) and the database link probe (`db_link.py`). Internet and provider-reachability indicators are missing.

**Fix:** add a cheap internet probe and a provider reachability state from the breaker plus the last result. Hide or mark "mobile money unavailable" on the kiosk when either is down.

### 6. A mobile-money call has no overall deadline (low–medium)
- `ProviderHTTP` (`common.py:145`) uses one 8 s httpx timeout per request, with a circuit breaker and no retries. No retries is correct for initiate.
- One `initiate_collection` makes up to three sequential calls (token, preview, initiate), so a kiosk request can block for about 24 s.
- 8D asks for separate connect and read timeouts plus an overall operation deadline. Wrap the whole call in `asyncio.wait_for` and set `httpx.Timeout(connect=…, read=…)`.

### 7. Lists without pagination (low)
| Endpoint | Today |
|---|---|
| `GET /sessions` | Cursor (`before_id`), filters, cap of 1000. Meets the spec. |
| `GET /payments` | Fixed newest 100, no filter, no paging (`ledger.py:228`) |
| `GET /audit` | Fixed newest 200, no filter, no paging (`08_admin.py:468`) |
| `GET /vehicles`, `GET /users` | Whole table. `joinedload` avoids N+1. |
| `GET /captures` | `limit` has no upper cap (`06_parking.py:38`) |

After a few days of traffic, payment history and the audit log can't be browsed past the newest rows. Give them the same `before_id` cursor that sessions use.

### 8. The payment audit entry is a separate transaction (low)
`write_audit` commits on its own after the payment commits (`payment_handlers.py:621`). A crash in between leaves a payment with no audit row. The ledger row still holds `operator_id`, so attribution isn't lost. To be strict, add the audit row inside the payment transaction.

## What already matches the spec

- **Local assets:** `app/web/index.html` loads only `/assets/*`. There are no CDN fonts or scripts. The desktop app is PySide6, and the only external URLs are help links.
- **Cash commit before reply:** `record_succeeded_payment` commits before returning, and the session's paid state is recomputed from the ledger (`paid_total`) inside the same transaction.
- **Duplicate cash submissions:** `cash_settlement_key` plus unique constraints, with a race-safe `IntegrityError` path.
- **Operators can't record mobile money:** `_operator_payment_method` allows cash only, and unattended kiosks refuse cash.
- **Mobile money is credited only after verification:** webhooks are signature-checked, and the result is then confirmed with `query_status`. Reconciliation runs as a background job.
- **No disposable cache for authoritative writes:** there is no Redis. In-process TTL caches cover only the dashboard (3 s), health (1 s) and URLs. Entitlements are read straight from PostgreSQL, so no stale revocation can open a gate.
- **Durable outbox:** recognition events go into a SQLite outbox. A database link failure is treated as "link-down" (event kept, no retry counted), not as a poison message. Stale gate actions older than 20 s are not executed.
- **Connection pool:** pool size, overflow, `pool_timeout`, `pool_pre_ping`, `pool_recycle`, `connect_timeout`, `statement_timeout` and `idle_in_transaction_session_timeout` are all set (`app/db.py:32-68`).
- **Barrier ownership:** a migration enforces exclusive gate ownership (0012), and node liveness takes over gates.
- **N+1:** the sessions list fetches captures in one batch (`captures_for_sessions`) and vehicles use `joinedload`.

## Known gap, already planned

**Edge Node offline policy:** with the database link down, an Edge Node fails fast and only queues events. It can't decide entry or exit. The snapshot and journal design is in `docs/ZIRP_HIGH_THROUGHPUT_ARCHITECTURE.md` §6 (step 7, off by default). Until that ships, a Site Server outage stops automatic barrier decisions and leaves operators with manual opens only. Sites should know this.

## 8E: not done

There is no baseline or before-and-after report for the 13 demonstrations listed in 8E. `tools/db_hotpath_bench.py`, `tools/critical_path_report.py` and `tools/latency_report.py` exist as building blocks. No performance claims should be made until they have been run against a defined workload.

## Second pass: remaining 8B–8D items (2026-11-19)

### 9. Kiosk logins can browse every payment, session and vehicle photo (medium) — FIXED 2026-11-19

**Fix applied:** the Kiosk Operator role is now `kiosk.use` + `payments.create` only. `GET /sessions` and `GET /payments` no longer accept `kiosk.use`, and without `dashboard.view` the revenue dashboard is closed to kiosks too. A kiosk keeps receipt or plate lookup, cash, mobile money, receipt reprint for the looked-up visit, and plate correction (`kiosk.use` was added to `correct-plate`, which it previously reached through `sessions.view`). The desktop and web kiosk screens hide the session list and the Payments and Dashboard pages for such logins. Staff roles are unchanged. System roles re-sync at start-up, so existing kiosks lose the extra permissions on the next Site Server start. Test: `test_kiosk_device_sees_only_the_visit_it_looks_up`.

**Still open:** a kiosk can look a visit up by typing any plate, and the receipt endpoints take a session id. Someone at an unattended kiosk who knows a plate, or guesses ids, can still see that one visit.

- The Kiosk Operator role (`01_bootstrap.py:238`) carries `payments.view`, `sessions.view` and `dashboard.view`.
- `GET /payments` accepts `kiosk.use` (`payment_handlers.py:48`), and `STAFF_PHOTO_PERMISSIONS` includes `kiosk.use` (`payment_handlers.py:707`).
- The desktop parking page loads the full sessions list for a kiosk login.

**Effect:** on an unattended kiosk (`kiosk_cash_enabled` off), anyone at the screen, or anyone holding the device token, can see other drivers' plates, photos, amounts and payment history. 8B says history lookup must follow permissions. A driver-facing kiosk should only look up the visit on the scanned receipt.

### 10. The desktop kiosk tells the cashier to take cash when mobile money has no answer (medium) — FIXED 2026-11-19

**Fix applied:** both kiosks now say "take cash" only for FAILED or BLOCKED, where nothing was taken. On no answer, EXPIRED or MISMATCH they say not to take cash, and to look the visit up again (or ask a supervisor, for MISMATCH). Test: `test_unconfirmed_mobile_money_never_advises_taking_cash`.

`30_parking.py:519`: after 180 s with no result, or on EXPIRED, it shows "Try again or take cash".

**Effect:** a push can still succeed later. That is the case finding 1 now handles: it gets credited after the cashier has already taken cash, so the driver pays twice, and there is no refund tool (finding 4).

The web kiosk's wording ("No answer from the provider yet. Check Payments before retrying.") is the safe one.

### 11. Kiosk screens can't tell a LAN or Site Server failure from a refusal (low–medium)
- **Web** (`api.js:348`): a network failure surfaces as the raw "Failed to fetch". Requests other than camera calls have no timeout. Any abort is reported as "Camera took too long".
- **Desktop** (`desktop/api.py:271`): raw httpx exceptions reach a message box. Calls run on the UI thread, so the kiosk freezes while the LAN is slow.

**Effect:** with a lost cash response, the cashier sees an error although the payment may already be saved. Retrying is safe, because the server re-quotes and answers "already settled". The screen should say "Couldn't reach the Site Server: look the visit up again before taking more money", and should show a "Site Server unreachable" state distinct from internet or ClickPesa being down (8B).

### 12. The kiosk can only take the full amount (low, part of finding 3)
Both kiosks send cash with no amount, so the server records the full remaining fee. A partial payment, or recording a larger note and its change, isn't possible from the screens.

### 13. The mobile-money button ignores whether mobile money can work (low, part of finding 5)
The web and desktop buttons are enabled whenever a fee is due. They ignore `online_payment_available`, `pay_methods`, the provider's breaker and internet health.

### 14. No query-count tests (low)
8D asks for query-count tests on important endpoints. None exist. Add them for `/sessions`, `/sessions/lookup`, `/dashboard`, `/payments` and the exit decision.

### 15. Plate search can't use an index (low, measure first)
`/sessions?q=` uses `plate.contains()` (`LIKE '%…%'`), which a B-tree index can't serve. This is fine at current volumes. Measure it before considering `pg_trgm`.

### 16. Dependency candidate (low)
`websockets` is pinned, but the app has no WebSocket routes. Uvicorn only needs it for those. Verify, and rebuild the installer, before removing it. All other runtime packages are used, directly or indirectly (`psycopg` through SQLAlchemy, `yaml` through fast-plate-ocr, `tzdata` for zoneinfo, `multipart` for forms).

### Checked and OK
- **LAN exposure:** the Site Server binds `0.0.0.0` (`deployment.py:156`). The installer's firewall rules allow `RemoteAddress LocalSubnet` only.
- **Stable addressing:** the setup wizard defaults to the `smartpark-server` hostname. I found no documentation telling installers to give the Site Server a fixed IP or DHCP reservation, or to confirm that the name resolves without internet DNS. A short install note would close this.
- **LAN traffic is plain HTTP.** This isn't a spec requirement, but tokens cross the LAN unencrypted. Worth noting for sites with shared or Wi-Fi networks.
- **Config and entitlement propagation:** Edge Nodes read PostgreSQL directly. The only in-process caches live 1–10 s (modules config, boom index, dashboard, health). A revoked entitlement takes effect on the next event, so 8C's write-through and invalidation machinery isn't needed.
- **Outbox durability:** the SQLite outbox uses the default rollback journal with `synchronous=FULL`, so it survives power loss. Ack and processed-mark commit together.
- **Outbound timeouts:** present on HVX, ONVIF, HTTP snapshots, board TCP, LED UDP, SMTP and webhook alerts, the AI review (`asyncio.wait_for`) and backup upload (30 s).
- **The AI review**, the one internet call near recognition, is scheduled as a background task and never blocks a lane.
- **Duplicate vehicle events:** unique partial indexes on visit id and camera (0007), on capture identity (0014) and on entry claims prevent duplicate sessions.
- **Indexes:** payment transactions (`session_id, status`), intents (`provider_id, status, id`), session `public_token`, plate, status and the 0010 hot-path partial indexes cover the lookups read in this audit. Some single-column status indexes overlap composites. Measure their write cost before dropping any.
- **Background jobs** (outbox, reconciliation, sweeper, alerts, diagnostics) run as asyncio tasks in the single Site Server process. No durable commit or access decision is deferred to them.
- **Kiosk functions present:** QR scanning (USB scanner or webcam), plate and vehicle photo, entry time and stay duration, server-side fee, cash, mobile push with status polling, receipt reprint ("Show / print receipt"). Nothing prints a payment receipt automatically after cash is taken.

### Still not covered
- **8E:** no baseline or before-and-after measurements, and none of the 13 demonstrations run. This includes a real internet-disconnected kiosk test.
- **Front-end rendering:** not profiled, which needs the app running. The operator UI is plain JavaScript plus PySide6; only the public pay portal is React.

## Suggested order
1. ~~Finding 1~~ and ~~finding 2~~ (fixed)
2. ~~Findings 9 and 10~~ (fixed)
3. Findings 5, 11 and 13 (internet and ClickPesa health; clear LAN-failure messages; hide mobile money when it can't work)
4. Findings 3, 4 and 12 (cash tendered and change, refunds and voids, drawer reconciliation). These need a business policy first.
5. Findings 6–8 and 14–16
6. The 8E baseline run
