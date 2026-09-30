# Core parking engine — build status

Sequential build per `prompts/SmartPark_Cursor_Core_Parking_Engine_Sequential_Prompt.md`.
Branch: `cursor/core-parking-engine-v1`, based on Codex HEAD `7de6c4f` (AI slice).

Do not start mobile/public payment web, cloud AI, watchlists, or multi-site cloud dashboards until Phase 6 is green.

| Phase | Status | Commit |
| --- | --- | --- |
| 0 Baseline and safety | PASS | `6a63eb0` |
| 1 Parking domain engine | PASS | (this commit) |
| 2 Recognition good enough for a session | not started | |
| 3 Receipt and QR | not started | |
| 4 Entry orchestration | not started | |
| 5 Tariff and local payment | not started | |
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

### Commit SHA

Filled after commit.

---

## Phase 2 —

(not started)
