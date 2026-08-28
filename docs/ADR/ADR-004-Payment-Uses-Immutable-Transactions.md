# ADR-004 — Payment uses immutable transactions

## Status

Accepted.

## Decision

Kiosk and future mobile money share `PaymentIntent` + `PaymentTransaction`. Session `amount_paid` is derived from SUCCEEDED rows (minus refunds when those exist). A browser page must not be the source of truth for PAID.

## Consequences

- `mark_paid` / `POST /sessions/{id}/pay` writes a ledger row then updates the session
- Duplicate callbacks use `idempotency_key`
- Simulated and kiosk-manual providers exist before a live Tanzania aggregator is chosen
