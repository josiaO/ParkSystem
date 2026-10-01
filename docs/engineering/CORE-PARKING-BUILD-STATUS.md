# Core parking engine — build status

Sequential build per `prompts/SmartPark_Cursor_Core_Parking_Engine_Sequential_Prompt.md`.
Branch: `cursor/core-parking-engine-v1`, based on Codex HEAD `7de6c4f` (AI slice).

Do not start mobile/public payment web, cloud AI, watchlists, or multi-site cloud dashboards until Phase 6 is green.

| Phase | Status | Commit |
| --- | --- | --- |
| 0 Baseline and safety | PASS | `6a63eb0` |
| 1 Parking domain engine | PASS | `f1c5e85` |
| 2 Recognition good enough for a session | PASS | `d5efae7` |
| 3 Receipt and QR | PASS | `b1ce995` |
| 4 Entry orchestration | PASS | `84b7d7a` |
| 5 Tariff and local payment | PASS | `4cb63fe` |
| 6 Exit orchestration | not started | |
| 7 Physical lane hardware | not started | |
| 8 Operator/kiosk usability | not started | |
| 9 Observability and soak | not started | |

---

## Phase 0 — Baseline and safety

### Implemented behavior (inventory; no engine rewrite in this phase)

#### ParkingSession (`app/models.py`)

Stored today: `id`, `plate`, `gate_id`, `camera_id`, `lane_direction`, `car_type`, `status`, `entry_time`, `exit_time`, `currency`, `amount_due`, `amount_paid`, `breakdown`, `tariff_rules`, `public_token`, `receipt_status`, `simulated`, `parker_kind`, `access_plan_id`, `vehicle_id`, `created_at`.

Open statuses (`app/services/simulation.py` + `app/domain/parking.py`): `WAITING_RECEIPT`, `ACTIVE`, `PAID`, `OPEN`. Closed: `CLOSED`.

Missing vs Phase 1 prompt (do **not** duplicate equivalents): `site_id`, `plate_raw` / `plate_status`, `entry_lane_id` / `exit_lane_id`, `entry_event_id` / `exit_event_id`, `entry_image_ref`, `receipt_printed_at` / `receipt_taken_at`, `payment_status` / `paid_at` / `payment_exit_grace_until`, `exit_camera_id`, `closed_at`, `updated_at`. `camera_id` is entry-camera equivalent; `plate` is the normalized plate; `exit_time` is used as close time.

Sessions are conceptually site-wide (exit looks up any open plate, not the entry gate) but the row has no `site_id` and stores one `gate_id` overwritten on exit.

#### Recognition event path

Camera/SDK/ONVIF/worker → `VehicleCapture` (`app/services/captures.py`) → `_persist_capture_event` in `app/api_main.py` → `handle_plate_event` in `app/services/simulation.py`. Normalized contract already exists in `app/domain/recognition.py` (`empty_vehicle_event`) and `app/domain/events.py` (`PlateRecognized`); parking still consumes plate strings, not that contract.

HYBRID fusion: `app/services/hybrid_fusion.py` + `app/core/consensus.py`. Temporal FastALPR consensus: `resolve_local_reads` in `app/core/consensus.py`. Presence: `app/services/presence.py` (`coil_watch`) — GPIO/coil when learned; image-callback can mark occupied. Capture policy can require presence.

#### Duplicate suppression

Process-local `EventDeduper` (`app/services/dedup.py`) keyed by camera+image_id or camera+plate, ~2 s window. `create_entry` reuses any open session for the same plate. Not durable across process restart; not keyed by recognition `event_id` on the session row. Gate `command_uuid` is unique in SQLite.

#### Gate command path

`app/services/gates.py` `controller().open` (HVX GPIO / board / simulated). Audit: `GateCommandRecord` via `app/services/decisions.py`. Mode: COMMISSIONING default; SHADOW dry-runs automatic opens; physical requires `physical_control_verified`. Untouchable: `tools/hvx_sdk_host/`, `app/services/hvx_client.py`, `app/services/gates.py`, port-30000 NetSDK sequence.

#### Receipt / printer / QR

`app/services/receipts.py` + `app/infrastructure/hardware/printers.py`. One opaque `public_token` (`secrets.token_urlsafe(10)`). QR payload is `/p/{token}` (or `public_base_url`). Policies: `OFF`, `PRINT_OPTIONAL`, `PRINT_AND_OPEN` (default), `REQUIRE_TAKEN_BEFORE_OPEN`. Printer adapters: simulated, ESC/POS LAN, system/USB. No presenter/taken-sensor protocol yet — `take_receipt` is an API/sim call. Default PRINT_AND_OPEN pulses the gate without a taken sensor. Printer `PrintResult.ok` stays True on send failure (slip stored); gate can still open.

#### Vehicle passage / loop

Coil/GPIO presence watch exists. Session does **not** wait for a vehicle-passed event: OPEN command success (or simulation) moves ACTIVE/CLOSED. Phase 1 must document a `passage_sensing` capability/fallback.

#### Kiosk / cash

`app/services/kiosk_lookup.py` (plate or token). `mark_paid` / ledger `PaymentIntent` + `PaymentTransaction`. Cash works offline. Mobile providers exist but are out of scope until after Phase 6.

#### Topology

`Site → Zone → Gate → Lane → Camera` is data-driven (`app/services/topology.py`). Rock City 2-gate / 4-camera is `/cameras/seed-site` demo helper, not domain constants. Tariff numbers live in `fee_engine.CAR1_RULES` (configuration-shaped JSON on `tariffs.rules`); Phase 5 must keep them out of domain constants.

#### Hardware seams to preserve

- 32-bit `hvx_sdk_host`, native ALPR callbacks, snapshots
- HVX gate/GPIO path
- MediaMTX owned only by SmartParkMediaService
- SQLite live store
- DIRECT camera mode; EDGE_AGENT reserved
- Country-neutral plate default; TZ corrections only when site policy enables them

### Tests run (Phase 0)

```text
.venv/bin/python -m compileall -q app tools
.venv/bin/python -m pytest -q -p no:cacheprovider
```

### Test results

**421 passed**, 1 pre-existing Starlette/httpx deprecation warning, 3 subtests passed. `compileall` exit 0. No collection failures.

### Unresolved hardware verification

- Physical HVX login / native ALPR / GPIO not exercised on this Linux host
- Printer presenter/taken sensor not present
- Loop/photocell passage close not wired to session close
- DPAPI SecretStore not executed (Linux)
- Flutterwave/ClickPesa/Gemini live calls not in this baseline

### Known limitations (parking engine)

1. No explicit entry/exit state machine: `handle_plate_event` can print and OPEN in one call; invalid skip of RECEIPT_TAKEN is a policy flag, not a rejected transition.
2. Duplicate recognition is in-memory + "one open session per plate", not event-id durable idempotency.
3. Sessions lack `site_id` / lane ids; exit overwrites `gate_id` / `lane_direction`.
4. Gate OPEN is treated as passage; no VEHICLE_PASSED state.
5. Domain parking lives in `simulation.py` (also used live). `app/application/parking.py` is a re-export.
6. `EventDeduper` is process-global mutable state (prompt forbids that for parking *authority*; capture debounce can stay).
7. `public_token` is 10-byte urlsafe (~13 chars) — raise entropy in Phase 3; uniqueness not a DB constraint.
8. Default receipt policy opens the gate without taken confirmation.

### Phase 1 implementation plan (do this next; do not start Phase 2)

1. **Pure domain engine** in `app/domain/parking_engine.py` (no printer, no HVX, no FastAPI):
   - Fine-grained lifecycle states matching the prompt (entry: VEHICLE_DETECTED → … → ACTIVE; exit: VEHICLE_DETECTED → … → CLOSED | DENIED_PAYMENT_REQUIRED).
   - Map to existing stored `status` so current rows and APIs keep working (`WAITING_RECEIPT`/`ACTIVE`/`PAID`/`CLOSED`).
   - `apply_transition(session, event)` rejects illegal jumps (e.g. SESSION_CREATED → GATE_OPEN_REQUESTED when lane policy is RECEIPT_REQUIRED_BEFORE_OPEN).
2. **Session fields** (Alembic `0004`, add-only): `site_id` (default 1), `entry_lane_id`, `exit_lane_id`, `exit_camera_id`, `entry_event_id`, `exit_event_id`, `plate_raw`, `lifecycle`, timestamps listed above that have no equivalent. Unique `(site_id, entry_event_id)` where event_id is non-empty. Do not rename `plate` / `camera_id` / `gate_id`.
3. **Idempotency in the engine**: same `entry_event_id` returns the existing session; same receipt-taken / vehicle-passed / gate `command_uuid` is a no-op. Use DB constraints + lookups, not process-global maps.
4. **Concurrency**: one active session per `(site_id, plate)` via a partial unique idea implemented as a lookup+insert in a transaction (SQLite has no partial unique easily — enforce in engine + test two lanes racing). One session cannot be CLOSED by two exit events.
5. **Site-wide**: entry lane A, exit lane B on the same `site_id` is the happy path. One-gate and multi-gate fixtures in tests. No Rock City constants.
6. **Passage fallback policy** on the session/lane: `WAIT_FOR_PASSAGE` vs `OPEN_COMMAND_COUNTS_AS_PASSED` (default until hardware exists). Document in this file.
7. Tests in `tests/test_parking_engine.py` exactly as the prompt lists. Existing 421 tests must stay green; `simulation.py` remains the live orchestrator until Phase 4.

Do not touch printers, UI, MediaMTX, HVX host, or recognition internals in Phase 1.

---

## Phase 1 — Parking domain engine

### Implemented behavior

- Explicit lifecycle in `app/domain/parking_engine.py` with `InvalidTransition` for illegal jumps (including `SESSION_CREATED → GATE_OPEN_REQUESTED` when receipt must be taken).
- Persistence in `app/services/parking_sessions.py`: `start_entry`, `mark_receipt_taken`, `request_entry_open`, `mark_vehicle_passed`, `start_exit`, `complete_authorized_exit`. No HVX/printer imports.
- Alembic `0004`: `site_id`, lane/camera/event ids, `lifecycle`, receipt/payment timestamps, partial unique indexes for `(site_id, entry_event_id)` and one open plate per site.
- Stored `status` values unchanged so live `simulation.py` and reports keep working.
- Passage fallback `OPEN_COMMAND_COUNTS_AS_PASSED` (default) vs `WAIT_FOR_PASSAGE`.
- Site-wide sessions: enter lane A, exit lane B.

### Tests run

```text
.venv/bin/python -m compileall -q app tools
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_parking_engine.py
.venv/bin/python -m pytest -q -p no:cacheprovider
git diff --check
```

### Test results

**439 passed** (421 baseline + 18 parking-engine tests), 1 pre-existing Starlette/httpx warning.

### Unresolved hardware verification

Same as Phase 0. Passage sensors not wired; default policy counts OPEN as passed.

### Known limitations

- Live cameras still use `handle_plate_event` (Phase 4 will switch the orchestrator).
- `simulation.create_entry` does not yet write `entry_event_id` / `lifecycle`.
- Public token entropy still Phase 3.
- No printer/taken-sensor in this phase (by design).

Filled after commit.

---

## Phase 2 — Recognition good enough for a session

### Implemented behavior

- Parking consumes `NormalizedRecognitionEvent` (`app/domain/recognition.py`): `event_id`, `site_id`, `camera_id`, `lane_id`, `occurred_at`, `provider`, `plate_raw`, `plate_normalized`, `confidence`, `bbox`, `vehicle_detected`, `image_ref`, `plate_crop_ref`. Native ALPR and FastALPR map to the same contract (`provider` aliases `source`).
- `LaneRecognitionEngine` (`app/domain/recognition_engine.py`) wraps the existing `ConsensusTrack` + `FusionCoordinator`. No printers, HVX DLLs, or UI.
- Temporal consensus is configurable (`SMARTPARK_RECOGNITION_CONSENSUS_WINDOW_SECONDS`, default 2s). HIGH ≥ 0.92 / MEDIUM ≥ 0.75 / LOW below that. LOW never becomes a parking candidate. Tanzania OCR corrections stay opt-in (`plate_validation=TZ`).
- Modes: `NATIVE_ONLY`, `FASTALPR_ONLY`, `HYBRID`. HYBRID agreement → one event; disagreement → held, no session; a missing counterpart uses the available provider after wait.
- Presence-capable lanes ignore background plates until occupied. Stale frames older than 1000 ms are dropped (`LatestFrameBuffer` latest-wins). The recognition worker reads the same window/stale policy.
- `start_entry_from_recognition` is the only parking ingest for this contract. Live `handle_plate_event` is unchanged until Phase 4.
- Accuracy harness (`tools.evaluate_alpr`) now also reports `duplicate_event_rate` and `false_session_creation` when labels carry `visit_id` / `session_expected`.

### Tests run

```text
.venv/bin/python -m compileall -q app tools
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_parking_recognition.py tests/test_alpr_evaluation.py
.venv/bin/python -m pytest -q -p no:cacheprovider
git diff --check
```

### Test results

**454 passed** (439 Phase 1 + 14 parking-recognition + 1 evaluation metric test), 1 pre-existing Starlette/httpx warning. `compileall` exit 0.

### Unresolved hardware verification

Same as Phase 0/1. Native HVX + FastALPR agreement was simulated, not driven through a physical lane. Presence sensor still optional (`presence_capable`).

### Known limitations

- Live cameras still publish through `handle_plate_event` (Phase 4 wires `LaneRecognitionEngine` into the orchestrator).
- Receipt printing and gate OPEN are still out of this phase.
- Default consensus still needs two agreeing reads; a single HIGH frame does not skip the track (avoids one-OCR-frame sessions).
- Evaluation metrics for duplicate/false-session require labelled `visit_id` / `session_expected` fields; the smoke fixture does not include them.

### Phase 3 implementation plan (do this next; do not start Phase 4)

1. ReceiptPrinterAdapter protocol (print / status / presented / taken / recover) with capability flags. Simulated adapter for development; do not claim production taken-sensor if hardware lacks it.
2. One high-entropy public token on the session (raise entropy; unique DB constraint). Short human reference is separate and not the auth token. QR payload locally resolvable.
3. Print job tied to `session_id` + `print_job_id`; retries must not create a second session. Receipt-taken is lane policy `RECEIPT_REQUIRED_BEFORE_OPEN`, not a global constant.
4. Tests listed in the sequential prompt (token uniqueness, QR lookup, retry, duplicate taken, paper/offline, never-taken timeout, audited override). Do not send gate OPEN in this phase.

Commit: `d5efae7`.

---

## Phase 3 — Receipt and QR

### Implemented behavior

- `ReceiptPrinterAdapter` (`app/domain/receipt_engine.py`) with print / status / presented / taken / recover. Capabilities are declared, never assumed.
- Simulated kiosk adapter has `PAPER_STATUS`, `PRESENTER`, `TAKEN_SENSOR`, `CUTTER`. USB/LAN thermal wrap does **not** claim a taken sensor.
- High-entropy opaque `public_token` (`secrets.token_urlsafe(32)`), unique when non-empty. Short `human_reference` (`XXXX-XXXX`, no 0/O/1/I) is operator lookup only and is not the auth token.
- QR payload is `/s/{token}` (optional public base URL). Local lookup accepts `/s/` and existing `/p/` scanner strings. Token is not derived from plate or DB id.
- Print job is `session_id` + `print_job_id`. Retry reprints the same session; presented/taken duplicates are no-ops. Out of paper / offline → `ASSISTANCE_REQUIRED`. Never-taken timeout → assistance. Operator override is audited and does not pulse a gate.
- Lane policy remains `receipt_required_before_open` (`RECEIPT_REQUIRED_BEFORE_OPEN`). This phase does not send gate OPEN.
- Alembic `0005_receipt_qr_jobs`: print-job columns and unique token/reference indexes.
- Windows USB requirements now list `alembic`, `mako`, `markupsafe`, `typing_extensions`, `python-dotenv`, `greenlet` so `--no-deps` install gets the migration stack.

### Tests run

```text
.venv/bin/python -m compileall -q app tools
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_parking_receipts.py
.venv/bin/python -m pytest -q -p no:cacheprovider
git diff --check
```

### Test results

**467 passed** (454 Phase 2 + 12 parking-receipt tests + packaging), 1 pre-existing Starlette/httpx warning. `compileall` exit 0. USB kit rebuilt with Alembic/Mako/MarkupSafe/python-dotenv/greenlet wheels.

### Unresolved hardware verification

Same as Phase 0–2. Physical presenter / taken sensor not attached. Windows USB kit at `dist/SmartParkEdge-Install` now includes the Alembic wheel set for `--no-deps` install.

### Known limitations

- Live cameras still print through `issue_receipt` / `handle_plate_event` (Phase 4 wires print jobs into entry orchestration).
- Public HTTP page remains `/p/{token}`; the QR is `/s/{token}` and both parse locally.
- Hardware thermal adapters do not invent a taken sensor; taken confirmation is simulated or operator/override until hardware exists.

### Phase 4 implementation plan (do this next; do not start Phase 5)

Connect recognition + parking + printer + gate in one entry orchestrator. Presence → consensus → session → print → presented → taken → authorize → idempotent OPEN → vehicle passed → ACTIVE. Do not put the sequence in a FastAPI route or camera callback. Printer/taken failure must not silently open. Subscribers may skip receipt per lane policy.

Commit: `b1ce995`.

---

## Phase 4 — Entry orchestration

### Implemented behavior

- `EntryLaneController` (`app/application/entry_lane.py`) is the entry sequence: presence → recognition candidate → admission → session → print → taken → idempotent OPEN → vehicle passed → ACTIVE. FastAPI routes and camera callbacks only submit events; they do not own the sequence.
- Casual lanes with `receipt_required_before_open` wait for taken. Printer failure and gate-unavailable leave the session consistent and do not pulse. Duplicate ALPR reuses one session. Subscribers skip receipt when `subscriber_skip_receipt` is set. Vehicle-left before taken cancels (`ENTRY_CANCELLED`) and releases the open-plate lock.
- Live `handle_plate_event` still honors site `receipt_policy` (default PRINT_AND_OPEN) so existing kiosk/sim flows stay intact. The new controller is the RECEIPT_REQUIRED path and the Phase 4 test surface.
- SQLite datetime mix-up fixed: `lookup_entitlement` compares `valid_from` / `valid_until` via `as_utc()`. That was the `TypeError` on `POST /sim/capture`.

### Tests run

```text
.venv/bin/python -m compileall -q app tools
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_parking_entry.py
.venv/bin/python -m pytest -q -p no:cacheprovider
git diff --check
```

### Test results

**480 passed** (467 Phase 3 + 13 entry/datetime tests), 1 pre-existing Starlette/httpx warning. `compileall` exit 0.

### Unresolved hardware verification

Same as Phase 0–3. Full entry path is simulated. Not validated on a physical lane. HVX GPIO still only through `gates.controller`.

### Known limitations

- Default live policy remains PRINT_AND_OPEN until a lane is configured `REQUIRE_TAKEN_BEFORE_OPEN`.
- Operator/manual plate fallback UI is Phase 8.
- Physical taken-sensor still simulated.

### Phase 5 implementation plan (do this next; do not start Phase 6)

Pure tariff engine from configuration (not Rock City constants). Cash settlement on local SQLite with PaymentIntent/PaymentTransaction, Decimal/minor units, duplicate cash idempotency, `payment_exit_grace_until`. No public payment web app.

Commit: `84b7d7a`.

---

## Phase 5 — Tariff and local payment

### Implemented behavior

- `quote_stay` (`app/domain/tariff_engine.py`) prices a stay from tariff JSON only. Empty rules are rejected so 45-minute / TZS 1,000 values stay configuration (`fee_engine.CAR1_RULES` / site tariff row), not domain constants.
- Cash settlement remains `PaymentIntent` + `PaymentTransaction`. Ledger statuses include CREATED/PENDING/SUCCEEDED/FAILED/EXPIRED/REFUNDED/PARTIALLY_REFUNDED. Duplicate cash submit is idempotent (`session:{id}:settle`). Paid total is derived from SUCCEEDED rows.
- On full payment the session is `PAID`, `paid_at` is set, and `payment_exit_grace_until` is stored from `payment_exit_grace_seconds` (default 15 minutes). Cash does not call the network.

### Tests run

```text
.venv/bin/python -m compileall -q app tools
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_parking_tariff.py
.venv/bin/python -m pytest -q -p no:cacheprovider
git diff --check
```

### Test results

**489 passed**, 1 pre-existing Starlette/httpx warning.

### Unresolved hardware verification

Same as Phase 0–4. No live mobile-money provider calls in this phase (by design).

### Known limitations

- Amounts on the session row are still Numeric/float at the SQLAlchemy boundary; quotes use integer minor units.
- Day/night/holiday overlays exist in `fee_engine` but are not expanded in this phase.
- Public/mobile payment web app is still out of scope.

### Phase 6 implementation plan (do this next; do not start Phase 7)

ExitLaneController: plate (or QR fallback) → site-wide session → tariff → payment/grace → authorize or deny → idempotent OPEN → close. Unpaid stays closed. Lost ticket / QR fallback. Same site, different gates.

Commit: `4cb63fe`.


---

## Phase 6 — Exit orchestration

### Implementation status

**SOFTWARE IMPLEMENTED / HARDWARE VERIFICATION PENDING**

Implemented on branch `chatgpt/core-real-path-cleanup`:

- `ExitLaneController` is now the authoritative live EXIT path.
- Plate and receipt-QR fallback enter the same exit application service.
- Site-wide session resolution supports entry at one gate and exit at another.
- Exit pricing is refreshed from the session site's tariff.
- A fully paid session inside `payment_exit_grace_until` keeps its settled quote during the configured drive-to-exit window.
- Unpaid casual sessions remain closed to the barrier and return `DENIED_PAYMENT_REQUIRED`.
- Subscribers/access-plan vehicles can exit without a casual parking fee.
- Barrier failure keeps the parking session open.
- `WAIT_FOR_PASSAGE` no longer closes a session on the OPEN command; a passage event must call `vehicle_passed`.
- Entry and exit gate identity are stored separately (`entry_gate_id`, `exit_gate_id`).
- Exit gate commands have their own idempotency field (`exit_open_command_uuid`).
- Production database exit lookup uses `SELECT ... FOR UPDATE` semantics to serialize competing exit claims on PostgreSQL.
- HID keyboard-wedge and bounded-timeout serial QR scanner adapters exist.
- `/exit/qr-scan` is authenticated and routes the same receipt QR into `ExitLaneController`.
- Real ENTRY and EXIT camera events are forbidden from the legacy simulation engine.
- Simulation sessions are forced to dry-run gate I/O and cannot pulse a physical barrier.

### Automated tests added

`tests/test_parking_exit.py` covers:

- free-period exit
- unpaid denial
- payment followed by re-evaluation
- gate failure
- passage-sensor close
- same receipt QR fallback
- subscriber exit
- entry-gate / exit-gate audit identity

`tests/test_safety_regressions.py` covers fail-closed barrier/printer behavior and site-scoped entitlement lookup.

### CI

GitHub Actions is currently failing before runner steps start (the reported job has no steps/runner), so this branch must not be merged on CI evidence alone. Run the full suite locally on the deployment/dev machine before merge.

### Physical verification required before Phase 6 is GREEN

1. One real entry lane with printer + receipt taken sensor.
2. One real exit lane with plate recognition.
3. Unpaid vehicle must remain blocked.
4. Paid/free vehicle opens exactly once.
5. QR fallback opens the same session, not a parallel session.
6. Gate A entry -> Gate B exit.
7. If passage sensor is configured, session closes only after actual passage.
8. Barrier relay failure does not close the session.
9. Repeat for the other lanes.
10. 8-hour, then 24-72-hour soak.


---

## Phase 7 — Recognition commissioning

### Implementation status

**SOFTWARE IMPLEMENTED / FIELD CALIBRATION PENDING**

Added a technician-only recognition commissioning workspace and API:

- `GET /cameras/{id}/commissioning/recognition`
- `POST /cameras/{id}/commissioning/recognition/read`

The diagnostic path is intentionally side-effect free: it does not create parking
sessions, print receipts, alter payment state, or control barriers.

Per camera it reports:

- native-ALPR capability and recognition mode
- event-driven versus continuous-DETECT strategy
- native/local/fused plate readings
- latest plate crop and vehicle evidence
- plate pixel width and capture-quality band
- OCR latency
- live/detect FPS and frame age
- codec, transport, reconnects and dropped frames
- Recognition Worker ownership/heartbeat
- current and recommended DETECT stream role
- actionable commissioning warnings

The explicit software-read button reuses the latest stored plate crop when
available (OCR only, detector skipped), then falls back to the latest event
snapshot or live cache. This operation is diagnostic and does not persist a new
VehicleCapture.

Field acceptance remains required for day/night, glare, rain, motorcycle and
cross-gate conditions before recognition thresholds are treated as production
calibration.
