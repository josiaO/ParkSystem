# Phase 2 acceptance and remaining gates

This phase is **not complete**. Current edits establish the baseline and repair
recognition isolation, event transport, capture policy and route entitlement.
No external payment provider or cloud AI was activated. Existing HVX SDK host,
vendor bindings and physical gate adapters were preserved.

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

Latest automated result: **286 tests passed**, with one pre-existing
Starlette/httpx deprecation warning; compilation, evaluation CLI smoke check and
diff whitespace checks pass.

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

Flutterwave end-to-end tests and duplicate webhook tests must be added to this
procedure once that adapter and its verification/reconciliation path are built.
ClickPesa must remain live-disabled until documented merchant testing is approved.

## Outstanding engineering requirements

- Real immutable ALPR images/labels and measured camera/night/country accuracy.
- Process-safe native/FastALPR hybrid fusion and durable business-event
  idempotency across crashes; confidence calibration and tracking beyond exact
  adjacent text consensus.
- Complete stream-role modelling and shared-upstream deduplication, MediaMTX
  path/packet telemetry, real video-reader lifecycle integration and codec errors.
- Verified ONVIF Media2 discovery and capability-driven Profile M events.
- Flutterwave TEST adapter, authenticated verified callbacks, exact money/reference
  checks, reconciliation and end-to-end test transactions.
- ClickPesa adapter based on current official documentation, live-disabled safety
  configuration, and restricted public ingress.
- Optional Gemini reviewer with privacy/budget/timeouts and no gate authority.
- Alembic migrations, site-scoped constraints, PostgreSQL acceptance, SecretStore
  integration and complete diagnostics redaction.
- Full API-router extraction and runtime supervision/health enforcement for every
  disabled optional background/scheduled job.
- The hardware and soak procedure above.
