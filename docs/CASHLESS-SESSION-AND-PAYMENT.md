# Cashless entry — session matching and payment sync

## Status

Design for review. Not implemented. Fail-state choices in §3 and §5 of `prompts/CURSOR-PROMPT-CASHLESS.md` are open questions at the end of this document.

## Purpose

Make the entry plate and the exit plate the only link for a casual visit, without a second identity object and without a second payment path.

## What already exists (do not replace)

| Need in the brief | Already in the product |
|---|---|
| First-class session with its own id | `parking_sessions.id`, site-wide, not keyed only by plate string |
| Opaque session handle for QR | `public_token` — not the plate, not the integer id (ADR-001) |
| Live fee at pay time | `quote_session` → `calculate_car1_fee` |
| One ledger for cash and mobile | `record_succeeded_payment` (ADR-004) |
| Kiosk cash with no internet | `mark_paid` / `KIOSK_CASH` |
| 45 min day grace, 1,000 TZS block | Car1 rules: `free_day_seconds=2700`, `day_block_seconds=2700`, `day_block_fee=1000` |
| OCR lookalikes 0/O, 1/I, 8/B, 5/S | `app/core/plate.py` (`confusion_variants`, `plate_similarity`) |
| Exact open-session lookup | `_active_for_plate` — exact string only, newest row |
| Take-before-open policy | `REQUIRE_TAKEN_BEFORE_OPEN` (optional; default is `PRINT_AND_OPEN`, ADR-007) |
| Override audit | `write_audit` → `audit_logs` |
| Entry / exit photos | `vehicle_captures.snapshot_path` / `crop_path` |
| Cross-gate exit on one server | Sessions are site-wide; 1#→2# is already valid |

`vehicle_color` and `vehicle_type` exist on the recognition event contract and are unset today. They are optional tie-breakers later, not required for v1 of the matcher.

## What this must NOT do

- Add an RFID stand-in, a second session table, or a second payment ledger (ADR-001, ADR-004, ADR-007).
- Put a fixed amount, the plate, or `parking_sessions.id` in the QR (ADR-001).
- Mark a visit paid from a phone page, a screenshot, or a webhook that has not been verified and written by `record_succeeded_payment`.
- Change the default receipt policy away from `PRINT_AND_OPEN` until that ADR conflict is accepted.
- Split the site into lane-controller processes until the Rock City Mall network question is answered. `EDGE_AGENT` stays reserved; `DIRECT` stays the live camera mode.
- Relocate or rewrite `tools/hvx_sdk_host/`, `app/services/hvx_client.py`, `app/services/gates.py`, or the port-30000 sequence.
- Hard-code Rock City Mall gate count, distance, grace, or tariff.

## ADR conflicts (stop until answered)

1. **ADR-007.** Default casual entry is print-then-open. A printer failure is time-limited and the boom still opens. The brief’s entry interlock holds the boom until a take-sensor fires. That policy already exists as `REQUIRE_TAKEN_BEFORE_OPEN`. Making it the site default overrides ADR-007.
2. **ADR-007.** “Do not add a mandatory second identity object to replace the RFID card.” The session row and `public_token` already are the identity. This design does not add another one.
3. **Site topology docs and the working-engine rule.** One Site Server owns all lanes over `DIRECT`. A per-structure lane controller is the reserved `EDGE_AGENT` idea. Do not build it on assumption.

---

## 2. Session identity and exit matching

### Identity

A casual stay remains one `ParkingSession` row:

- Surrogate id: `parking_sessions.id` (what the ledger and QR token point at).
- Natural description: `(site, entry gate_id, normalized plate, entry_time)`.
- Public handle: `public_token` (QR and `/p/{token}`).

Exit matching searches **open** rows (`WAITING_RECEIPT`, `ACTIVE`, `PAID`, `OPEN`). It does not require `exit_plate == session.plate`.

`_active_for_plate` stays the exact-match fast path. A new matcher runs when that path misses, and also when an exact match is not unique enough (two open rows that both score as plausible).

### Score

For one exit read against one open session, after `normalize_plate`:

| Signal | Score contribution | Notes |
|---|---|---|
| Identical normalized plate | 1.00 | Fast path |
| Exit text is a `confusion_variants` spelling of the session plate (max 2 substitutions, pairs O/0, I/1, B/8, S/5) | 0.96 | Reuse `app/core/plate.py`. This is the “bad exit-frame OCR” case |
| Otherwise `plate_similarity` (normalized Levenshtein) | that value, 0–1 | Same function registered-plate fuzzy match uses |
| Entry gate equals this exit’s structure | +0.02, capped at 1 | Weak prior only. Cross-gate stays legal |
| `vehicle_color` / `vehicle_type` both present and equal | +0.02, capped at 1 | Ignored while those fields are empty |
| `vehicle_color` / `vehicle_type` both present and different | −0.05 | Cannot by itself reject a 1.00 plate |
| Entry time is after the exit read | reject | Not a candidate |

No color or type is required to auto-match.

### Decision

Configurable in `site_settings` (proposed starting numbers, not yet applied):

| Key | Proposed | Meaning |
|---|---|---|
| `match_auto_floor` | 0.92 | Best candidate must reach this to open with no person |
| `match_plausible_floor` | 0.80 | Anything at or above this is “could be this car” |
| `match_margin` | 0.08 | Best must lead the next candidate by this much |

Rules, in order:

1. **No candidate** at or above `match_plausible_floor` → hold. Outcome `EXIT_MATCH_NO_SESSION`. QR scan or attendant.
2. **Two or more** candidates at or above `match_plausible_floor` → hold, even if one is exact. Outcome `EXIT_MATCH_AMBIGUOUS`. Never auto-pick.
3. **One** candidate, score ≥ `match_auto_floor`, and (no second candidate or gap ≥ `match_margin`) → bind that session and continue to payment check. Outcome `EXIT_MATCH_AUTO`. If the bound plate differs from the raw exit read, store both on the decision `extra`.
4. **One** plausible candidate under the auto floor → hold. Outcome `EXIT_MATCH_LOW_CONFIDENCE`. Attendant sees entry snapshot beside exit snapshot.

Worked cases the tests will lock:

| Open sessions | Exit read | Result |
|---|---|---|
| `T285DQP` only | `T285DQP` | Auto |
| `T285DQP` only | `T28SDQP` (S/5 confusion) | Auto via confusion variant (0.96 ≥ 0.92), one candidate |
| `T285DQP` and `T285DOP` | `T285DQP` | Ambiguous if both score ≥ 0.80 (one exact, one one-edit). Hold |
| `T285DQP` only | `T111AAA` | No session. Hold |
| `T285DQP` and `T999XYZ` | `T285DOP` | Auto only if the far plate scores under 0.80 and `T285DQP` clears 0.92 |

Every hold is an `access_decisions` row with that outcome, the exit plate, the candidate ids and scores, and `barrier_opened=false`. That table is the count of how often OCR is holding cars.

QR scan at exit (`public_token`) skips this matcher for that visit. Plate match is not consulted again.

Registered / subscriber exits stay on `lookup_entitlement` (exact, confusion-against-known, then fuzzy ≥ 0.85). This matcher is for open casual sessions.

### Where it lives

New function next to the plate helpers, called from `handle_exit` before the fee quote. It does not open the barrier. `handle_exit` still decides paid / grace / hold, and the gate adapter still pulses.

---

## 4. Payment: QR reference, one ledger, sync

### QR

The slip and the phone page keep encoding `/p/{public_token}` (absolute when `SMARTPARK_PUBLIC_BASE_URL` is set). The token is a session reference. The amount is not in the code.

Whoever scans it calls the fee engine for that session at that moment (`quote_session`). Kiosk and phone show duration, entry photo, and the live amount. Payment is refused when the quoted due is already covered (`mark_paid` already raises in that case).

### One write path

| Payer | How it becomes money | Ledger |
|---|---|---|
| Cash at kiosk | Operator confirms on the site PC. No internet | `record_succeeded_payment`, method `KIOSK_CASH`, key `session:{id}:settle` |
| Mobile money | Provider webhook hits a **cloud relay**, not the site PC. Relay verifies the provider signature, then the site copies a verified record down and calls the same function | `record_succeeded_payment`, method from the provider, idempotency key = provider transaction id |

A browser “success” page does not write the ledger (ADR-004).

Cash never waits on the relay. If the site has no route to the internet, kiosk settle still works.

### Relay and the not-yet-synced case

The driver’s phone cannot reach the site PC. The relay is the only public payment endpoint.

```text
Phone pays provider
  → provider webhook → cloud relay (verify signature)
  → relay stores {public_token, amount, currency, provider_txn_id, paid_at}
  → relay returns the phone a signed paid-proof (HMAC over those fields)
  → site pulls pending proofs (poll) or receives them on the LAN path the relay can reach (push)
  → site calls record_succeeded_payment
  → duplicate webhook or duplicate poll hits the same idempotency key and does not double-charge
```

The site stores the HMAC secret. Verification of a paid-proof does not need the internet.

**Proposed exit behavior when the boom is reached before the poll has landed** (numbers not applied until confirmed):

1. Quote locally. If grace or the local ledger already covers the fee, open. No network call.
2. If the visit is unpaid, hold the barrier.
3. For up to **20 seconds**, poll the relay three times. If a verified record arrives, write the ledger and open.
4. If the poll fails or returns nothing, the exit QR scanner accepts either:
   - the entry slip (`public_token`) — re-quote and send the driver to the kiosk if still unpaid; or
   - the phone’s **signed paid-proof** — verify HMAC on the site PC, check amount and token against the live quote, then `record_succeeded_payment` with the provider transaction id.
5. A photo of a payment app, an SMS, or an unsigned page does not open the gate. Attendant override is a separate audited action (`write_audit`, action `exit.payment_override`, target the session id, detail = who, when, why, and the unmatched provider reference if any).

If the relay is unreachable and the phone has no signed proof, the car stays held. Cash at the kiosk is the offline way out. The site does not invent a `SUCCEEDED` row.

Grace and the 1,000 TZS / 45 min block stay Car1 configuration (`free_day_seconds`, `day_block_seconds`, `day_block_fee`). Night rules stay as stored (35 min free, 1,000 TZS block) until someone edits the tariff. This design does not add a second calculator. The existing `over_1000_subtract` step stays; changing it would change what drivers pay today.

---

## 3. Entry interlock (not built — choices open)

When, and only when, the site policy is `REQUIRE_TAKEN_BEFORE_OPEN`, the lane runs:

`PLATE_CONFIRMED → RECEIPT_PRINTING → AWAITING_TICKET_TAKEN → TAKEN | TIMEOUT → GATE_OPEN`

Today `take_receipt` sets `ACTIVE` and then pulses. The brief requires the take-sensor latch and the open relay to sit in the **gate adapter**, so application code cannot pulse a casual entry on that lane unless the adapter has seen the sensor for that session. That is a wrap around `app/services/gates.py`, not a rewrite. The sensor itself is not wired yet (known gap).

Manual override uses `write_audit` with the signed-in user, action `entry.interlock_override`, target session id, and a mandatory reason. Override is the only path that may open without the sensor, and only after that audit row is committed.

Default site policy stays `PRINT_AND_OPEN` until the ADR-007 question below is answered. Failure behavior inside the interlock is not chosen in this document.

---

## 5. Two gates (not built — network open)

Documented Rock City shape: one Site Server, four HVX cameras (1# entry/exit, 2# entry/exit), sessions shared, a second PC may be an operator client. Distance between structures is not in the software.

If both structures are on one switched LAN or fiber that this server can reach, no lane-controller process is required. Cross-gate matching is the matcher above plus the existing site-wide session list.

If they are not on one LAN, the brief’s lane-controller model needs a new ADR. Until then, a disconnected lane must not fail closed for cars that entered and exit on that same lane, and it must not silently open a cross-gate exit it cannot check. That behavior is specified only after the network answer.

Gate count, tariff, and grace stay in `sites` / `gates` / `tariffs` / `site_settings`.

---

## 6 and 7

Exit order after a bound session: quote fee → grace (due 0) opens → local or synced `SUCCEEDED` covering due opens → otherwise hold for kiosk or QR. Low-confidence and ambiguous matches never reach the boom; they go to the attendant pair of photos or the exit scanner.

Attendant UI (manual match, interlock override, open sessions per gate) waits until this document is accepted and §2–§4 are in code.

## Tests to add after acceptance

- Two similar open plates, exit read equal to one of them → `EXIT_MATCH_AMBIGUOUS`, barrier stays shut.
- One open plate, exit read is a single confusion-pair miss (`T285DQP` / `T28SDQP`) → `EXIT_MATCH_AUTO`.
- Sensor timeout under the interlock policy does whatever this review chooses — asserted, not implied.
- Mobile `SUCCEEDED` absent locally, signed paid-proof present → one ledger row, then open. A second webhook with the same provider transaction id does not insert another row.
- Relay down, no proof → barrier stays shut, kiosk cash still writes the ledger.

## Open questions

1. Change the casual default from `PRINT_AND_OPEN` to `REQUIRE_TAKEN_BEFORE_OPEN`? That overrides ADR-007.
2. Printer offline, out of paper, or jam at `PLATE_CONFIRMED`: hold and alert, or keep today’s “log and still open”?
3. Take-sensor never fires: hold until an audited override, or auto-open after a timeout?
4. Sensor fires but the printer did not finish (torn ticket): ignore the sensor and hold, or treat the sensor as taken?
5. Are the two Rock City structures (~400 m apart) on one LAN/fiber the Site Server can use to reach all four cameras? If not, confirm the lane-controller split before any of that is built.
6. Confirm the matcher floors (0.92 auto, 0.80 plausible, 0.08 margin) and the 20-second / 3-poll sync hold.
7. Confirm that an unsigned phone screen never opens the gate, and that a relay-signed paid-proof may.
