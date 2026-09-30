# Phase 2 acceptance and remaining gates

This phase is **not complete**. The baseline commit repaired recognition
isolation, event transport, capture policy and route entitlement. Four Codex
slices have since landed on top of it, each behind a rollback flag:

| Slice | Commit | Rollback |
| --- | --- | --- |
| §4 MediaMTX role-aware paths, Control API telemetry, WHEP, codec reporting | `468a841` | `live_view_provider=DIRECT_LEGACY`, `media_gateway_enabled=false` |
| §6.3 Process-safe native/FastALPR hybrid fusion, weighted consensus, durable event idempotency | `45ea6ce` | camera `recognition_mode` ≠ HYBRID; `fastalpr_new_pipeline_enabled=false` |
| §8 Flutterwave TEST + ClickPesa (live-disabled) providers, verified settlement, reconciliation, public ingress guard | `a2a6543` | `SMARTPARK_PAYMENTS_MOBILE_PROVIDER=simulated` (default) |
| §7 ONVIF Media2 discovery (GetServices/GetProfiles/GetStreamUri/GetSnapshotUri), Profile M plate events → recognition contract | this slice | `PATCH /cameras/{id}/onvif/events {"enabled": false}` or `adapter_id=rtsp` |

No external payment provider is *active* by default and no cloud AI was
activated. Existing HVX SDK host, vendor bindings and physical gate adapters
were preserved. See `docs/MEDIAMTX-INTEGRATION.md`, `docs/FASTALPR-PIPELINE.md`
`docs/MOBILE-MONEY-PROVIDERS.md` and `docs/ONVIF-MEDIA2-PROFILE-M.md` for each slice.

## Automated checks

From the repository root, use the project Python environment:

```bash
.venv/bin/python -m compileall -q app tools
.venv/bin/python -m pytest -q
.venv/bin/python -m tools.evaluate_alpr tests/fixtures/alpr/smoke.jsonl \
  --predictions tests/fixtures/alpr/smoke-predictions.jsonl --output /tmp/alpr-smoke.json
git diff --check
```

New checks exercise process-safe producer/consumer acknowledgements, legacy
outbox import, dropped frames under slow inference, decoder cancellation,
persisted plate policy, expired consensus, stale worker ownership, neutral
capture thresholds, hybrid disagreement review, disabled APIs, profile changes
without restart, LPR captures with zero parking sessions, and evaluation metrics.

Later slices add MediaMTX telemetry/path-plan tests, hybrid-fusion coordinator
and consensus tests, and payment tests: invalid webhook signature rejected,
signed webhook still requires server-side verification, duplicate webhooks
never double-credit, wrong amount/currency/reference never credits,
reconciliation converts PENDING→SUCCEEDED exactly once and expires stale
intents, provider outage leaves cash/kiosk working, ClickPesa live-disabled
with no network call, official ClickPesa checksum algorithm, and the public
ingress guard hiding every non-payment route on tunnel hostnames.

Latest automated result: **385 tests passed** (baseline 286 → 326 after fusion
→ 364 after payments → 385 after ONVIF), with one pre-existing Starlette/httpx deprecation
warning; compilation, evaluation CLI smoke check and diff whitespace checks pass.

## Outbox upgrade and rollback

Stop the Site Service and Recognition Worker before upgrading. The new runtime
queue is `data_dir/outbox/parking-events.sqlite3`. Existing
`parking-events.jsonl` rows import once with their original IDs in a transaction.
Invalid legacy records fail migration visibly rather than being silently lost.
The original JSONL file is retained and is no longer the active queue.

The Site Service is the sole consumer. Delivery is at least once; this transport
does not provide exactly-once gate side effects. Existing domain/adapter
idempotency still matters. SQLite is a local site queue, not a multi-site
PostgreSQL outbox implementation.

Before reverting to a JSONL-only build, stop both services and back up both queue
files. Export **only currently pending SQLite rows** into the legacy JSONL format
(`id`, `kind`, `payload`, `ts`) before starting the old build. Do not blindly
restore the retained pre-upgrade JSONL: already acknowledged events would replay.
An empty pending queue can be rolled back with an empty legacy file. Never run
old and new queue implementations concurrently.

Feature rollback remains `fastalpr_new_pipeline_enabled=false` and
`live_view_provider=DIRECT_LEGACY`. Neither requires replacing the HVX adapter.

## Windows/site technician procedure

All items here are **HARDWARE-VERIFICATION-REQUIRED**. Capture logs and metrics;
do not infer successful hardware operation from unit tests.

1. Install the validated build with rollout flags off. Boot Windows and verify
   Site Service, x86 HVX host and Media Service start. Record `/health/details`,
   `/modules/health`, `/media/gateway`, and HVX `/info` (32-bit, available).
2. Connect existing HVX cameras. Confirm SDK login on port 30000, native plate
   callbacks and snapshots using the established adapter. Confirm physical gate
   verification/commissioning settings before operating the existing gate path.
3. Roll out MediaMTX to one camera using the procedure in
   `MEDIAMTX-INTEGRATION.md`. Check local Control API and metrics. View through
   browser WebRTC and desktop MJPEG; inspect browser requests for absence of
   concurrent snapshot polling. Switch cameras repeatedly and check reader and
   FFmpeg counts settle.
4. Add a generic ONVIF/RTSP camera and enable the worker on that camera in
   software-only mode. Start `python -m app.recognition_worker` with the same data
   directory as Site Service. Confirm a fresh worker heartbeat and persisted
   plate policy, then close both UIs. Plate events and captures must continue.
5. Drive labelled test vehicles through. Check one capture/event per consensus
   window, raw OCR evidence, policy holds, and no new session on duplicate entry.
   Measure input age (<1000 ms normally) and operator frame age (<500 ms normally).
6. Unplug one camera. Other cameras, native callbacks and Site Service must
   continue. Reconnect and check capped backoff, recovery and stable child count.
7. Kill Recognition Worker. Native ALPR and video must continue; after the stale
   heartbeat window the legacy software loop becomes eligible. Restart the
   worker and check ownership returns without duplicate business actions.
8. Kill MediaMTX. Site Service and native ALPR must remain alive. Media Service
   must restart its owned process and streams must recover. No other process
   should spawn a second MediaMTX instance.
9. Switch to LPR_ONLY with zero gates. Detection/history must work; session,
   payment and gate APIs must return 404 and no parking sessions may be created.
10. Run 24-hour, then 72-hour soak. Record CPU, RAM, threads, FFmpeg children,
    MediaMTX readers, frame ages, packet loss/jitter, reconnects and inference
    p95. Counts/memory must stabilize; repeated multi-second backlog fails.

11. **Payments (merchant-dependent).** With Flutterwave TEST keys and a public
    tunnel hostname configured (`docs/MOBILE-MONEY-PROVIDERS.md`): open a
    receipt `/p/{token}` on a phone, start a payment, approve the sandbox
    prompt, and confirm the ledger gains exactly one `SUCCEEDED` row after the
    webhook (or, with the webhook URL deliberately wrong, after reconciliation
    ≤ 60 s later). Replay the webhook from the dashboard and confirm no second
    row. On the tunnel hostname, `GET /cameras`, `/gates`, `/docs` and
    `/auth/login` must return 404. ClickPesa must remain `LIVE_DISABLED` in
    `/payments/health` until documented merchant testing is approved.
12. **ONVIF (hardware-dependent).** On a generic ONVIF camera run
    `POST /cameras/{id}/onvif/discover` and confirm `media_version=2` (or 1 with a
    reason), stream URIs match the device, and no credential appears in the
    response. If the camera advertises plate topics, run
    `POST /cameras/{id}/onvif/events/pull` while a vehicle passes and confirm a
    normalised capture; then leave the poller running and confirm one
    `VehicleCapture` per read, snapshot evidence attached, and reconnect backoff
    after unplugging the camera. Cameras without plate topics must keep the
    Recognition Worker path.

## Outstanding engineering requirements

- Real immutable ALPR images/labels and measured camera/night/country accuracy.
- Confidence calibration and tracking beyond similarity-weighted text consensus
  (process-safe hybrid fusion and durable event idempotency landed in `45ea6ce`).
- Real video-reader lifecycle integration and soak evidence for the MediaMTX
  path plan/telemetry landed in `468a841`.
- Real-camera verification of ONVIF Media2 discovery and Profile M plate topics
  (capability-driven discovery, pull-point poller and normalisation landed in this slice).
- End-to-end Flutterwave TEST transaction against the real sandbox and ClickPesa
  merchant testing (adapters, verification, reconciliation, idempotency and the
  public ingress guard landed in this slice; refunds remain dashboard-only).
- Optional Gemini reviewer with privacy/budget/timeouts and no gate authority.
- Alembic migrations, site-scoped constraints, PostgreSQL acceptance, SecretStore
  integration and complete diagnostics redaction.
- Full API-router extraction and runtime supervision/health enforcement for every
  disabled optional background/scheduled job.
- The hardware and soak procedure above.
