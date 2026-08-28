# ADR-001 — Plate is primary identity

## Status

Accepted.

## Decision

A parking session is identified by a normalized license plate (plus site). Receipts, QR tokens, and any future cards are convenience handles. A driver who loses paper can still be found by plate at a kiosk, on `/p/{token}` if they have the link, or by the exit camera.

## Consequences

- Casual entry does not require RFID
- Default receipt policy is `PRINT_AND_OPEN`, not paper-taken-before-open
- Public tokens must not equal the plate or the integer session id
