# Phase 2 baseline — 2026-09-30

## Source state

Branch: `main`. After `git fetch origin`, HEAD and origin/main both point to
`e30d36987df3cccc13a98b6529a927d2fa75d130` (merge of stabilization PR #2).
No rebase was needed. The local working tree already contained media, recognition,
desktop, plate-policy and CI changes before this session; those were preserved.
The remote stabilization branches are `origin/chatgpt/stabilize-media-p0` and
`origin/chatgpt/stabilize-media-p0-v2`.

## Exact initial checks

- `.venv/bin/python -m compileall -q app tools`: exit 0.
- `.venv/bin/python -m pytest -q`: **261 passed, 1 warning in 25.71s**.
- Failing tests and import/collection errors: none.
- Warning: `StarletteDeprecationWarning`, using `httpx` with
  `starlette.testclient` is deprecated; upstream suggests `httpx2`.
- System `python` and `pytest` commands were unavailable; the existing Python
  3.12 virtual environment was used. No dependency versions were changed.
- Sandbox launches intermittently failed with `bwrap: loopback: Failed
  RTM_NEWADDR: Operation not permitted`; required checks ran with approved
  escalation.

## Runtime snapshot

Local configuration read through `SessionLocal`, `flags(db)`, `load_config(db)`
and `mediamtx.health()`:

- FFmpeg process count: **0**, from `ps -eo comm`.
- MediaMTX binary installed at `vendor/mediamtx/mediamtx`; running/healthy: false.
- Registered process-local sources: none. Media Control API/metrics addresses:
  `127.0.0.1:9997` / `127.0.0.1:9998`.
- `media_gateway_enabled=false`, `fastalpr_new_pipeline_enabled=false`,
  `webrtc_live_enabled=false`, `native_alpr_enabled=true`.
- Live provider: `DIRECT_LEGACY`; recognition pipeline: `FASTALPR_LEGACY`.
- Module profile: `PARKING_LITE`, onboarding complete.
- Enabled modules: core identity/sites/devices/audit, camera management,
  media streaming, recognition ALPR, gates, parking sessions/subscribers/tariffs,
  payment core/kiosk and reports.

These values describe this Linux development environment, not a running camera
site. No Windows SDK, camera, gate, payment-provider or soak verification is claimed.

## Findings and implemented remediation

The incoming worker used an in-process decoder (not another process's gateway),
but synchronous inference blocked its event loop. It also ignored persisted site
plate policy, sampled without a configured rate cap, accepted widely separated
reads as consensus, and did not await camera tasks during removal/shutdown.
The shared JSONL outbox could lose concurrent producer writes during acknowledgement.

Remediation moves model inference off the event loop, serializes worker inference
while taking the latest frame only after model capacity is available, enforces
freshness and sampling, uses persisted policy and numeric lane ownership, awaits
decoder shutdown, and expires stale consensus. The worker handles software-only
cameras; native/hybrid lanes retain the existing Site Service fusion path until a
process-safe native/software fusion implementation is verified.

The runtime outbox now uses SQLite transactions and bounded queries. Legacy
JSONL is imported once, with original IDs, and retained for controlled rollback.
Delivery is at least once: a crash after business processing and before ACK can
redeliver a row. This change does not claim exactly-once business side effects.

See `ALPR-EVALUATION.md` for the fixed-label evaluation harness and
`PHASE-2-ACCEPTANCE.md` for pending software and hardware gates.

## Verification after these edits

- Compilation: exit 0.
- Full suite: **286 passed, 1 warning in 52.05s**. The warning is the same
  Starlette/httpx deprecation recorded in the initial baseline.
- Evaluation CLI synthetic metrics smoke check: exit 0, report at
  `/tmp/alpr-smoke.json`. No measured model accuracy is claimed.
- `git diff --check`: exit 0.

Concurrent desktop/UI edits appeared while this session was running and were
preserved. These results describe the workspace tested at the end of the session;
this report does not attribute those concurrent edits to the recognition changes.

## Slices after the baseline

| Slice | Tests after | Verification |
| --- | --- | --- |
| §4 MediaMTX (`468a841`) | 306 | compileall 0, full suite green, `git diff --check` 0 |
| §6.3 Hybrid fusion (`45ea6ce`) | 326 | compileall 0, full suite green, `git diff --check` 0 |
| §8 Payments (Flutterwave TEST, ClickPesa live-disabled, public ingress) (`a2a6543`) | 364 | compileall 0, full suite green, `git diff --check` 0 |
| §7 ONVIF Media2 discovery + Profile M plate-event poller (`31a8932`) | 385 | compileall 0, full suite green, `git diff --check` 0; fake SOAP device only |
| §11/§12 Alembic runner, site-scoped constraints, SecretStore + redaction (`23c4776`) | 403 | compileall 0, full suite green, `git diff --check` 0; migration also run against a copy of a real pre-Alembic evaluation file; DPAPI not executed (Linux host) |
| §9 AIReviewProvider / Gemini, disabled by default | 421 | compileall 0, full suite green, `git diff --check` 0; faked HTTP only, no real Gemini call |

Payment provider behaviour was implemented from the official Flutterwave v3 and
ClickPesa documentation and exercised only against faked HTTP in tests. No real
sandbox transaction or merchant webhook was executed in this environment.
