# Prompt for Claude Code on the Ubuntu server: Zirp production simulation

Copy everything below the line into Claude Code on the Ubuntu PC. Before you start:
- Copy `C:\SmartParkEdge\handoff-ubuntu\` from SERVER01 to `~/zirp-handoff/` on Ubuntu (USB or `scp`).
- Fill in the four IP addresses at the top of the prompt.

---

You are setting up an Ubuntu PC as the **central server of a production-like test site** for Zirp (SmartPark Edge), a parking system. Work carefully and verify every step. This is a test bench, but it must behave like the real site.

## Site layout (fill in before starting)

| Machine | Role | IP |
|---|---|---|
| This Ubuntu PC | Site Server (Zirp Site Service, no cameras), PostgreSQL, fake internet services | `UBUNTU_IP=192.168.1.___` |
| SERVER01 (Windows) | Edge Node, lane 2# (cameras .49 and .50) | `LANE2_IP=192.168.1.240` |
| Lane 1 PC (Windows) | Edge Node, lane 1# (cameras .144 and .145) | `LANE1_IP=192.168.1.___` |
| A phone on the LAN Wi-Fi | Drivers' phone: receipt QR, pay page, mock USSD approval | — |

The Windows lane PCs are configured separately (not by you). Your job ends when the Ubuntu side is ready, a fake lane can complete a paid visit through it end to end, and you have written the exact values the Windows Edge Nodes need.

## Hard rules

1. **No real money and no real outside services.** Never call `api.clickpesa.com`, Africa's Talking, Flutterwave or any external SMTP. Every "online" service is a local mock on this PC. Generate fake keys; never ask for or use real ones.
2. **No secrets in git.** Keep passwords, keys and checksum keys in `.env` files with `chmod 600` and in Zirp's secret store, and list them only by location in your report.
3. **Work on a branch** `ubuntu-sim` created from `production-readiness`. Commit small, logical changes. Never push. Never rewrite history.
4. **Don't weaken production safety to make the simulation pass.** In particular: the payment ledger must only credit from a verified webhook or status query, and webhook checksums stay mandatory. If something needs a code change, make it as a real, tested feature (e.g. an explicit mock mode), not a bypass.
5. **Measure before claiming.** Report what you ran and what you saw, and mark anything you could not verify.

## Inputs in `~/zirp-handoff/`

- `zirp-production-readiness.bundle`: git bundle with `main` and `production-readiness`.
  Clone with: `git clone -b production-readiness ~/zirp-handoff/zirp-production-readiness.bundle ~/zirp`
- `smartpark-bench.dump`: `pg_dump -Fc` (PostgreSQL **18**) of the bench database: users, sites, gates, lanes, cameras, tariffs, node assignments and bench history.

Read first, in this order:
1. `ZIRP_PRODUCTION_READINESS.md`
2. `ZIRP_ENGINEERING_HANDOVER.md`, sections 5 (architecture), 6 (subsystems), 10 (defects) and 17 (recent work)
3. `app/deployment.py`, `app/database_config.py`, `app/config.py` (settings use the `SMARTPARK_` prefix and `.env` in `SMARTPARK_HOME`)
4. `app/services/node_scope.py`, `app/services/node_authorization.py`
5. `app/infrastructure/payments/clickpesa.py`, `app/services/mobile_payments.py`, `app/api/payments.py`, `app/api/runtime_parts/07_payments.py`
6. `app/services/alerts.py`

## Step 1: Base system

- Ubuntu updates; `ufw` enabled.
- Python 3.11 (deadsnakes PPA if needed): the Windows kit uses 3.11.9.
- **PostgreSQL 18** from the PGDG apt repository. The dump is v18, and `pg_restore` must be at least that version.
- Samba, Caddy, Mailpit (SMTP mock with web UI), and `git`/`build-essential`/`libpq-dev`.
- Set the time zone to Africa/Dar_es_Salaam and enable NTP. Clock skew between nodes matters to Zirp (`app/services/clock_skew.py`).

## Step 2: PostgreSQL as the shared site database

- Create role `smartpark` (strong generated password) and database `smartpark` owned by it.
- `listen_addresses` = localhost + `UBUNTU_IP`.
- `pg_hba.conf`: `scram-sha-256` only, allowing `smartpark` from `127.0.0.1`, `LANE1_IP` and `LANE2_IP`. Nothing else.
- Restore: `pg_restore --no-owner --role=smartpark -d smartpark ~/zirp-handoff/smartpark-bench.dump`.
- Firewall: 5432/tcp only from the two lane IPs.
- Check: from this PC, `psql` as `smartpark` works. Report the row counts of `cameras`, `gates`, `nodes`, `node_gate_assignments`, `users` and `tariffs`.

## Step 3: Zirp Site Server on Linux (no cameras)

- Clone to `~/zirp`, create `~/zirp/.venv`, and install `requirements-runtime.txt`. Skip any Windows-only package and record which ones you skipped.
- Run the test suite (`pytest -q`) once to get a **Linux baseline**. Report failures, grouped by cause. Do not "fix" tests to pass; only fix real Linux bugs, each with its own commit.
- Configure as **SITE_SERVER** with PostgreSQL. Data dir: `~/.local/share/smartpark-edge` by default, or set `XDG_DATA_HOME`. Use the app's own configuration path (`deployment.json` through `app/deployment.py` / the CLI in `app/cli.py`, not hand-written JSON if a supported command exists). The PostgreSQL password goes in the file secret store (`app/infrastructure/secrets`), referenced by `postgres_secret_reference`.
  - `server_bind_host=0.0.0.0`, `server_bind_port=8760`
  - `SMARTPARK_PUBLIC_BASE_URL=https://zirp.test` (Step 6)
  - `SMARTPARK_DEPLOYMENT_PROFILE=PRODUCTION`
- Schema: on a Site Server, startup runs Alembic to head. Confirm the head revision (`0017_manual_open_alerts` or later).
- Run `python -m app.site_service` under **systemd** (`zirp-site.service`), as a dedicated user, `Restart=on-failure`, after `postgresql.service`. Don't run it as root.
- There is no HVX camera host on Linux, and this server owns no cameras.
  - Confirm that `/health/ready` reports core readiness, not hardware.
  - Check what the Site Server does with gates whose Edge Node is offline (`node_scope.edge_node_gate_ids`, heartbeat liveness 45 s). On Linux it cannot take those cameras over. Make sure it fails clearly (gate reported down/unowned) rather than looping on HVX connection attempts. If it loops or spams logs, fix it as a feature: e.g. "this Site Server has no camera host; never take over camera gates". Add a test.

## Step 4: Shared evidence storage

- Edge Nodes write snapshots and crops to `SMARTPARK_SHARED_MEDIA_DIR`. Create `/srv/zirp/media`, served by Samba as share `zirp-media`.
  - SMB3 only, a dedicated user `zirpmedia` (generated password), writeable.
  - Firewall: 445/tcp from the lane IPs only.
- Point the Site Server's media dir at the same folder.
- Check that `/media/<kind>/<name>` URLs served by the Site Server resolve to files written into the share.

## Step 5: Fake internet services (all on this PC)

Create `~/zirp-sim/` with its own venv and a small FastAPI app per service, each a systemd unit. Write tests for the mocks.

### 5a. Mock ClickPesa: already in the repo, run it (don't rebuild it)

The repo ships `app/mock_services/clickpesa.py`:
- the real API shape (token, preview, USSD push, status query, checksummed webhooks);
- a phone page at `/phone` (approve, decline, ignore, reverse);
- fault switches at `/admin` (late, dropped, duplicated or forged webhooks, underpayment, outage).

The ClickPesa adapter has an explicit **MOCK mode**: a private base URL means no live flags are needed and no real money can move, while checksums are still required. Read both files and `tests/test_payments_mock_clickpesa.py` first.

- Configure with the env tool (validates values, keeps `.env` tidy, generates test credentials):
  `python -m app.cli env preset mock-payments --lan-ip UBUNTU_IP`, then `python -m app.cli env check`.
- Run it as a systemd unit `zirp-mock-clickpesa`: `python -m app.mock_services.clickpesa --host 0.0.0.0 --port 9100`, with the same `SMARTPARK_HOME`/`.env` as the Site Service so the credentials match.
- Webhooks: set `SMARTPARK_MOCK_CLICKPESA_WEBHOOK_URL=https://zirp.test/api/webhooks/clickpesa` so they travel the same public path a real provider would use (Caddy → portal → Site Service).
- Firewall: 9100/tcp from the LAN only.
- If you find a gap in the mock or the payment flow, fix it as a tested change on `ubuntu-sim`.

### 5b. Mock SMS: `zirp-mock-sms`, port 9200

Implement the Africa's Talking messaging endpoint that `app/services/alerts.py` calls (read the code for the path, form fields and response shape). Store messages and show them at `/inbox`. Point `SMARTPARK_ALERTS_AFRICASTALKING_BASE_URL` at it, with a fake username and key.

### 5c. Email

Use Mailpit (SMTP 1025, UI 8025). Set `SMARTPARK_ALERTS_SMTP_HOST=127.0.0.1`, `PORT=1025`, no TLS.

### 5d. Alert webhook receiver: `zirp-mock-hooks`, port 9300

Verify the signature the way `alerts.py` signs it, store deliveries, and show them at `/hooks`.

### 5e. "Internet" on/off switch

Write a script `~/zirp-sim/internet.sh up|down` that blocks or unblocks the mock services' ports (or stops their units). It's used to rehearse provider outages and recovery.

## Step 6: Portal and public entry point (simulated internet-facing HTTPS)

The repo ships a Next.js portal in `portal/` (read `portal/README.md`):
- a public pay page at `/p/<code>`, with `/s/<code>` from the receipt QR;
- a back office at `/admin`;
- pass-through for `/api/public/*` and `/api/webhooks/*`.

Steps:
- Install Node.js 22 LTS (NodeSource or nvm), then in `~/zirp/portal` run `./start-portal.sh --api http://127.0.0.1:8760` once to build.
- Run it as systemd `zirp-portal`, using the unit in `portal/README.md`.
- Caddy with an internal CA:
  - `zirp.test` → portal (`127.0.0.1:3000`): the driver and provider entry point.
  - `zirp-admin.test` → portal as well, restricted to the LAN. Back-office users sign in at `/admin`.
  - Do not expose the Site Service port (8760) beyond the LAN.
  - Set `ZIRP_SECURE_COOKIES=true` in `portal/.env.local`.
- Set the site's public base URL to `https://zirp.test` (Zirp settings), so printed QR codes open the portal.
- Phones and lane PCs resolve `zirp.test` to `UBUNTU_IP`. Use dnsmasq on Ubuntu, or document the hosts-file lines; the phone probably needs the Ubuntu box as its DNS.
- Export Caddy's root certificate to `~/zirp-handoff/zirp-test-root.crt` for the phone and Windows PCs to trust.

## Step 7: Prepare for the two Edge Nodes

- In the database, register or confirm two nodes and their gate assignments: lane 1# gate → lane 1 PC, lane 2# gate → SERVER01. Use the app's supported way (admin API or desktop flow); read `node_authorization.py` for how node credentials are issued.
- Write `~/zirp-handoff/EDGE_NODE_SETUP.md` with the exact values each Windows PC needs:
  - role `EDGE_NODE`;
  - PostgreSQL host, port and database, plus how to supply the password (not in the file: say where it is on Ubuntu);
  - `SMARTPARK_SHARED_MEDIA_DIR=\\UBUNTU_IP\zirp-media` and the share credentials' location;
  - `SMARTPARK_NODE_ID`, `recognition_gate_id`;
  - Site Server URL `http://UBUNTU_IP:8760` (or `https://zirp-admin.test`);
  - `SMARTPARK_PUBLIC_BASE_URL=https://zirp.test`;
  - the root certificate to trust.

## Step 8: End-to-end rehearsal without lane hardware

Before the Windows nodes join, prove the server side with a script `~/zirp-sim/rehearse.py`. It uses the Site Server's own APIs, the same calls a lane makes; read the simulation endpoints (e.g. `/sim/...` routes), and don't write to tables directly. For each scenario record PASS/FAIL, timings and the ledger result:

1. Entry by plate → session → receipt token → `https://zirp.test/s/<token>` opens on the phone and shows the amount due.
2. Mobile payment: initiate from the receipt page → push appears on `/phone` → **Approve** → webhook → session PAID → exit allowed.
3. Same with **Decline**; then **Ignore** (time-out).
4. Webhook dropped → reconciliation settles it within `payments_reconcile_seconds`.
5. Duplicate webhook → one ledger credit.
6. Amount mismatch → not settled, visible to an operator.
7. Bad checksum → rejected (4xx), nothing credited.
8. Provider down during initiation → clear error to the driver, no stuck intent; payment works after `internet.sh up`.
9. Kiosk payment through the kiosk page (`/api/public/payment-intents` + status polling), and kiosk cash disabled when `kiosk_cash_enabled=false`.
10. Manual barrier open with an unpaid session → SMS in `/inbox`, email in Mailpit, signed webhook in `/hooks`, each with plate, amount owed and a working photo link.
11. Grace period: pay → exceed grace → re-quote → top-up recorded → exit.
12. Restart the Site Server and PostgreSQL mid-flow → no lost or double payments.

## Step 9: Report

Write `~/zirp-handoff/UBUNTU_SIM_REPORT.md` and commit a copy to `ubuntu-sim` as `docs/UBUNTU_SIM_REPORT.md`. Include:
- What runs where: services, ports, units, firewall rules.
- Where every secret lives (paths only).
- Linux test baseline.
- Each code change, with its commit and tests.
- Rehearsal results table (scenario, PASS/FAIL, timing, evidence).
- What you could not verify, and what the Windows nodes must do next.
- Exact commands to stop and start the whole simulation.

Stop and ask before anything that would touch a real payment provider, expose this server to the actual internet, or change the Windows PCs.
