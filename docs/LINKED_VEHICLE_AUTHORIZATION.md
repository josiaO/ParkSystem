# Linked Private Vehicle Authorization — design, migration and test report

Status: implemented on branch `production-readiness` (uncommitted), 2026-11-20.
Scope: Part A of `ZIRP_LINKED_PRIVATE_VEHICLE&WINDOWS_PRODUCTION.md`.

## 1. Architecture findings (before the change)

| Area | What exists | Reused? |
|---|---|---|
| Registered vehicles | `registered_vehicles` (plate unique per site, `plan_id`, validity window); `access_plans` (MONTHLY/STAFF/VIP…). | Yes — a vehicle joins a group with one new column. |
| Entitlement lookup | `app/services/access.py::lookup_entitlement` (exact plate for barrier authority, fuzzy only for operator help). | Yes — extended with group and visitor fields. |
| Sessions | `parking_sessions` with `status` + fine-grained `lifecycle` (`app/domain/parking_engine.py`). Partial unique index `uq_parking_sessions_one_open_plate` already stops one plate having two open visits. | Yes — all closes go through `_commit_transition`, which became the single release hook. |
| Entry | Live cameras → `EntryLaneController.submit` → `parking_sessions.start_entry` (commits the session with `parking_entry_claims`). | Yes — the group slot is claimed inside `start_entry`'s transaction. |
| Exit | `ExitLaneController`; exit closes on a passage signal (`mark_vehicle_passed(EXIT)`), on `OPEN_COMMAND_COUNTS_AS_PASSED`, or by the lane sweeper after `passage_timeout_seconds`. | Yes — each path now states its *exit evidence*. |
| Manual barrier open | `app/services/manual_open.py` records manual openings and alerts; **it never changes a session**. | Unchanged; this is what keeps a group locked after a hand-opened boom. |
| Supervised close | `POST /sessions/{id}/exit` writes the visit off. | Extended: closing the record does not free a group unless `vehicle_left: true`. |
| Audit | `access_decisions`, `audit_logs`. | Yes, plus a new `exit_confirmations` trail. |
| Simulation endpoints | `/sim/entry`, `/sim/exit` use their own development-only flow. | **Not** group-aware (documented below). |

## 2. Database schema and migration plan

Migration `0021_linked_vehicle_groups` (additive, reversible).

New tables

* `vehicle_groups` — `name` (unique per site), `kind` PRIVATE|FLEET, `company_name`, `owner_name`, `contact_phone`, `max_active_sessions`, `exit_release` EXIT_LANE|PASSAGE_CONFIRMED, `enabled`.
  * `CHECK (kind <> 'PRIVATE' OR max_active_sessions = 1)` — a private group can never be configured for two cars.
* `vehicle_group_occupancies` — one row per visit holding a group slot: `group_id`, `slot`, `state`, `session_id`, `vehicle_id`, `plate`, `claimed_at`, `exit_reported_at`, `released_at`, `release_evidence`, `release_reason`, `released_by`.
  * **`uq_vehicle_group_occupancy_live_slot` UNIQUE (group_id, slot) WHERE released_at IS NULL** — the concurrency authority.
  * `uq_vehicle_group_occupancy_session` UNIQUE (session_id) — one slot per visit.
  * `CHECK ((state = 'RELEASED') = (released_at IS NOT NULL))`.
* `visitor_passes` — temporary authorization: `plate`, `visitor_name`, `host_group_id`, `host_name`, `valid_from/until`, `max_entries` (0 = any), `entries_used`, `revoked_at`.
* `exit_confirmations` — append-only audit of every manual confirmation, uncertainty, supervisor decision and automatic release/lock.

New nullable columns: `registered_vehicles.group_id`, `parking_sessions.authorization_group_id`, `parking_sessions.visitor_pass_id`. Existing rows stay NULL, so existing vehicles and visits behave exactly as before. PostgreSQL gets real foreign keys; SQLite keeps integer columns (it cannot `ALTER TABLE ADD CONSTRAINT`), as in migration 0006.

Rollout

1. Back up (`pg_dump`, the existing backup page) — the migration is additive but take one anyway.
2. Stop the Site Service, start it: `upgrade_to_head` runs 0021 automatically.
3. Create groups and assign vehicles (desktop **Vehicles → Linked cars & companies…**, or `POST /vehicle-groups`).
4. Rollback: `alembic downgrade 0020_clear_legacy_capture_zones` drops the new tables/columns. Vehicles and sessions are kept; group membership, visitor passes and the exit-confirmation audit are lost.

Verified: SQLite upgrade from an old revision → 0021, both constraints refuse violations, downgrade keeps vehicle rows, re-upgrade succeeds. **Not yet run against PostgreSQL** (see §6).

## 3. Authorization state-transition design

Rules: `app/domain/vehicle_groups.py` (pure). Database application: `app/services/vehicle_groups.py`.

Occupancy states: `ACTIVE` (inside) → `EXIT_UNCONFIRMED` (visit ended without accepted proof) → `RECONCILIATION` (guard unsure; supervisor decides) → `RELEASED`.

```
                 claim (same txn as session insert)
                              │
                              ▼
   ┌──────────────────────► ACTIVE ───────────── closed with accepted evidence ─────────┐
   │ supervisor              │   │                                                       │
   │ KEEP_INSIDE             │   └─ closed without accepted evidence ──► EXIT_UNCONFIRMED ─┤
   │                         │                                            │   │  │         │
   │                operator UNCERTAIN                     operator UNCERTAIN  │  │ same car│
   │                         ▼                                            ▼   │  │ at entry│
   └───────────────────── RECONCILIATION ◄────────────────────────────────────┘  │         │
                             │ supervisor RELEASE            operator CONFIRM ─────┘         │
                             ▼                                                               ▼
                          RELEASED ◄─────────────────────────────────────────────────── RELEASED
```

Exit evidence and whether it releases the slot:

| Evidence | Produced by | `EXIT_LANE` policy (default) | `PASSAGE_CONFIRMED` policy (strict) |
|---|---|---|---|
| `PASSAGE_SENSOR` | loop/beam → `ExitLaneController.vehicle_passed` | release | release |
| `EXIT_LANE` | exit camera/QR identified the car, exit authorized, barrier **accepted** the command; no passage signal (commissioning fallback or sweeper time-out) | release | **stay locked** |
| `OPERATOR_CONFIRMED` | guard confirms with photo + reason | release | release |
| `SUPERVISOR_RECONCILED` | supervisor | release | release |
| `SEEN_AT_ENTRY` | the same car is read at the entry while its slot is EXIT_UNCONFIRMED | release | release |
| `ENTRY_CANCELLED_NOT_OPENED` | entry attempt cancelled before any barrier command | release | release |
| `UNCONFIRMED` | write-off without "vehicle left", cancel after an open command | stay locked | stay locked |
| *manual boom opening* | `manual_open.py` | **no event at all** | **no event at all** |

The default (`EXIT_LANE`) was chosen because most sites have no passage loops; with it, a normal automated exit frees the group without a guard. A barrier command alone never does: it must follow an exit-lane identification of that very car. Sites that want proof of passage set the group to `PASSAGE_CONFIRMED`.

Concurrency: `claim_for_session` locks the group row `SELECT … FOR UPDATE` on PostgreSQL, re-reads live slots, inserts the occupancy and flushes inside the session's transaction. The partial unique index is the final authority on every database; a lost race raises `IntegrityError`, the session insert is rolled back and the claim is retried once more, which then raises `GroupOccupied`. Nothing is held in process memory.

Fleet policy: `FLEET` groups set `max_active_sessions` (0 = no limit, N = N slots) and their own `exit_release`. They never inherit the private one-at-a-time rule.

Company identification: every entitlement, vehicle list row, refusal message, exit lookup and occupancy carries `belongs_to` — `Company: ACME Logistics Ltd` or `Private: J. Obeid` — shown in the desktop Vehicles table ("Belongs to"), the vehicle dialog, the manual-exit dialog and the gate refusal message.

Visitors: `visitor_passes` give exact-plate, time-boxed, entry-counted authorization without a `registered_vehicles` row (`kind = VISITOR`, auto-open, free exit). Entry counting is an atomic conditional `UPDATE` in the session transaction. A used-up pass falls back to the normal casual flow.

## 4. Manual exit recovery workflow

1. Guard: **Sessions → Confirm vehicle left…** (or **Linked cars inside / exits waiting… → Confirm exit…**). Identify the visit by session number (`#123`), scanned receipt QR/link/reference, or plate (`GET /exits/lookup`).
2. The dialog shows the stored entry photograph, plate, entry time and stay, who the car belongs to, and the group slot state.
3. The guard chooses
   * **The vehicle has left** → `POST /exits/confirm {outcome: LEFT}`: the visit is closed (unpaid amount recorded), the slot is released with `OPERATOR_CONFIRMED`; or
   * **I am not sure** → `{outcome: UNCERTAIN}`: nothing is closed or released; the slot moves to `RECONCILIATION`.
   A reason (≥ 3 characters) is mandatory; the operator identity is the signed-in user.
4. Supervisor (`exits.reconcile`, new **Supervisor** role or Admin): **Reconcile (supervisor)…** → `POST /exits/reconcile` `RELEASE` (closes the visit if open, releases) or `KEEP_INSIDE` (slot back to ACTIVE, or kept EXIT_UNCONFIRMED when the visit is already closed). A guard cannot clear a case under reconciliation (HTTP 409).
5. Every step writes `exit_confirmations`, an `access_decisions` row and an `audit_logs` row.

Permissions added: `exits.confirm` (Operator, Supervisor, Developer), `exits.reconcile` (Supervisor, Developer), `visitors.manage` (Operator, Supervisor, Developer). Admin (`*`) has all.

## 5. Implementation and test report

Code

* `app/domain/vehicle_groups.py` — states, events, evidence, policies (pure).
* `app/models/vehicle_groups.py`, `app/migrations/alembic/versions/0021_linked_vehicle_groups.py`.
* `app/services/vehicle_groups.py` — claim, release, manual exit, reconciliation, visitor passes.
* Hooks: `parking_sessions.start_entry/_commit_transition/mark_vehicle_passed/complete_authorized_exit/supervised_close/manual_entry`, `lane_sweeper`, `access.lookup_entitlement`, `EntryLaneController` (refusal `authorization_group_occupied`).
* API: `app/api/vehicle_groups_routes.py` (`/vehicle-groups`, `/visitor-passes`, `/exits/*`); `group_id` on `/vehicles`.
* Desktop: `app/desktop/linked_vehicles.py`; Vehicles and Sessions pages.

Tests: `tests/test_linked_vehicle_groups.py`, `tests/test_linked_vehicles_desktop.py` — 23 passed, 1 skipped (PostgreSQL).

| # | Acceptance test | Test |
|---|---|---|
| 1 | A enters; B rejected | `test_1_car_a_enters_car_b_rejected` |
| 2 | B enters; A rejected | `test_2_car_b_enters_car_a_rejected` |
| 3 | B overnight; A rejected next day (sweeper does not free it) | `test_3_overnight_stay_still_blocks_next_day` |
| 4 | B exits; A allowed | `test_4_car_b_exits_then_car_a_allowed` |
| 5 | Camera misses exit; manual confirmation closes | `test_5_camera_missed_exit_manual_confirmation_closes_session` |
| 6 | Boom opened by hand, not confirmed; group locked | `test_6_manual_boom_open_without_confirmation_keeps_group_locked` |
| 7 | Supervisor reconciles with audit trail | `test_7_supervisor_reconciles_uncertain_exit_with_audit_trail` |
| 8 | Simultaneous requests cannot both succeed | `test_8_database_refuses_two_live_slots`, `test_8_interleaved_claims_second_fails`, `test_8_simultaneous_threads_one_winner_sqlite_file` (real threads, 5 rounds), `test_8_simultaneous_lanes_one_winner_postgres` (**skipped** — needs `ZIRP_TEST_POSTGRES_URL`) |
| 9 | Fleet follows its own policy | `test_9_company_fleet_follows_its_own_limit` |
| 10 | Existing flows unchanged | `test_10_unlinked_registered_and_casual_flows_unchanged` + full regression suite |

Extra: strict policy, same car back at entry, visitor single use, API permissions (guard gets 403 on reconcile), private limit cannot exceed 1, desktop dialogs (offscreen Qt).

Hardware: none of these tests drives a camera, barrier or payment provider (recording fake opener, results marked simulated). Needs real-hardware verification: passage-loop signal reaching `vehicle_passed`, exit camera read → barrier at a live lane, entry refusal shown on the LED/desk.

## 6. Unresolved risks (Part A)

1. **PostgreSQL race test not run here.** The `FOR UPDATE` + partial-unique-index path is written for PostgreSQL and the invariant is proven on SQLite. Run: `ZIRP_TEST_POSTGRES_URL=postgresql+psycopg://…/zirp_test pytest tests/test_linked_vehicle_groups.py` against a disposable database before production.
2. `/sim/entry` and `/sim/exit` (development-only) do not enforce groups.
3. Existing OCR de-duplication (`recent_similar_entry`, 3 s, similarity ≥ 0.85 on the same lane) treats two fleet cars with near-identical plates (T301FLT/T302FLT) arriving back-to-back as one car. Pre-existing behaviour; it affects fleets with sequential plates.
4. A grouped car whose exit is never seen keeps its group locked until a guard confirms — by design. Sites must staff the **exits waiting** list.
5. Deleting a group with history disables it instead (history references it).
6. The "same car back at entry" release applies only to `EXIT_UNCONFIRMED`, never to `RECONCILIATION` (a supervisor decides those).
