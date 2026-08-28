# ADR-007 — Receipt is not primary identity

## Status

Accepted.

## Decision

Printing is configurable (`OFF`, `PRINT_OPTIONAL`, `PRINT_AND_OPEN`, `REQUIRE_TAKEN_BEFORE_OPEN`). Subscribers/VIP default to no receipt. Lost paper is not fatal.

## Consequences

- QR on the slip points at `/p/{opaque-token}` for status and future pay
- `REQUIRE_TAKEN_BEFORE_OPEN` remains available for sites that want a physical take-sensor
- Do not add a mandatory second identity object “to replace the RFID card”
