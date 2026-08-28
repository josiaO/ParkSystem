"""Session states. Stored values stay as they are; blueprint names are aliases."""

from __future__ import annotations

# Values written to parking_sessions.status today.
STORED_WAITING_RECEIPT = "WAITING_RECEIPT"
STORED_ACTIVE = "ACTIVE"
STORED_PAID = "PAID"
STORED_OPEN = "OPEN"
STORED_CLOSED = "CLOSED"

# Blueprint names → current stored values. Do not rewrite existing rows.
BLUEPRINT_TO_STORED = {
    "DETECTED": STORED_WAITING_RECEIPT,
    "ENTRY_AUTHORIZED": STORED_ACTIVE,
    "ACTIVE": STORED_ACTIVE,
    "PAYMENT_PENDING": STORED_ACTIVE,
    "PAID": STORED_PAID,
    "EXIT_AUTHORIZED": STORED_PAID,
    "CLOSED": STORED_CLOSED,
    "REVIEW_REQUIRED": STORED_WAITING_RECEIPT,
    "CANCELLED": STORED_CLOSED,
}

OPEN_STORED = {STORED_WAITING_RECEIPT, STORED_ACTIVE, STORED_PAID, STORED_OPEN}
