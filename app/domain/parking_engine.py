"""Deterministic parking session lifecycle. No printers, cameras, or GPIO.

Stored ``parking_sessions.status`` stays the operator-facing values already in
SQLite (WAITING_RECEIPT / ACTIVE / PAID / OPEN / CLOSED). Fine-grained
``lifecycle`` names are the auditable machine the prompt requires.

Illegal jumps raise ``InvalidTransition``. Repeating an event that already
applied is a no-op (idempotent), not an error.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.parking import (
    OPEN_STORED,
    STORED_ACTIVE,
    STORED_CLOSED,
    STORED_PAID,
    STORED_WAITING_RECEIPT,
)

# --- entry ---
VEHICLE_DETECTED = "VEHICLE_DETECTED"
IDENTITY_RESOLVED = "IDENTITY_RESOLVED"
SESSION_CREATED = "SESSION_CREATED"
RECEIPT_PRINTING = "RECEIPT_PRINTING"
RECEIPT_PRESENTED = "RECEIPT_PRESENTED"
RECEIPT_TAKEN = "RECEIPT_TAKEN"
ENTRY_AUTHORIZED = "ENTRY_AUTHORIZED"
GATE_OPEN_REQUESTED = "GATE_OPEN_REQUESTED"
VEHICLE_PASSED = "VEHICLE_PASSED"
ACTIVE = "ACTIVE"
ENTRY_CANCELLED = "ENTRY_CANCELLED"

# --- exit (prefixes distinguish from entry gate/passage) ---
EXIT_VEHICLE_DETECTED = "EXIT_VEHICLE_DETECTED"
SESSION_RESOLVED = "SESSION_RESOLVED"
TARIFF_CALCULATED = "TARIFF_CALCULATED"
AUTHORIZATION_DECISION = "AUTHORIZATION_DECISION"
AUTHORIZED = "AUTHORIZED"
DENIED_PAYMENT_REQUIRED = "DENIED_PAYMENT_REQUIRED"
EXIT_GATE_OPEN_REQUESTED = "EXIT_GATE_OPEN_REQUESTED"
EXIT_VEHICLE_PASSED = "EXIT_VEHICLE_PASSED"
CLOSED = "CLOSED"

ENTRY_ORDER = (
    VEHICLE_DETECTED,
    IDENTITY_RESOLVED,
    SESSION_CREATED,
    RECEIPT_PRINTING,
    RECEIPT_PRESENTED,
    RECEIPT_TAKEN,
    ENTRY_AUTHORIZED,
    GATE_OPEN_REQUESTED,
    VEHICLE_PASSED,
    ACTIVE,
)
EXIT_ORDER = (
    EXIT_VEHICLE_DETECTED,
    SESSION_RESOLVED,
    TARIFF_CALCULATED,
    AUTHORIZATION_DECISION,
    AUTHORIZED,
    EXIT_GATE_OPEN_REQUESTED,
    EXIT_VEHICLE_PASSED,
    CLOSED,
)

PASSAGE_WAIT = "WAIT_FOR_PASSAGE"
PASSAGE_OPEN_COUNTS = "OPEN_COMMAND_COUNTS_AS_PASSED"
PASSAGE_POLICIES = (PASSAGE_WAIT, PASSAGE_OPEN_COUNTS)

RECEIPT_STATES = {RECEIPT_PRINTING, RECEIPT_PRESENTED, RECEIPT_TAKEN}


class InvalidTransition(ValueError):
    """Lifecycle jump that the lane policy does not allow."""


@dataclass(frozen=True)
class LanePolicy:
    """Per-lane parking policy. Not Rock City constants.

    ``receipt_required_before_open`` is RECEIPT_REQUIRED_BEFORE_OPEN: the gate
    stays closed until the receipt is taken, unless this lane opts out.
    """

    receipt_required_before_open: bool = False
    passage_sensing: str = PASSAGE_OPEN_COUNTS
    subscriber_skip_receipt: bool = True

    def passage_fallback(self) -> bool:
        return self.passage_sensing != PASSAGE_WAIT


def _is_subscriber(kind: str | None) -> bool:
    return (kind or "CASUAL").upper() not in {"CASUAL", ""}


def _base_transitions() -> dict[str, frozenset[str]]:
    return {
        VEHICLE_DETECTED: frozenset({IDENTITY_RESOLVED}),
        IDENTITY_RESOLVED: frozenset({SESSION_CREATED}),
        SESSION_CREATED: frozenset({RECEIPT_PRINTING, ENTRY_AUTHORIZED, ENTRY_CANCELLED}),
        RECEIPT_PRINTING: frozenset({RECEIPT_PRESENTED, ENTRY_AUTHORIZED, ENTRY_CANCELLED}),
        RECEIPT_PRESENTED: frozenset({RECEIPT_TAKEN, ENTRY_AUTHORIZED, ENTRY_CANCELLED}),
        RECEIPT_TAKEN: frozenset({ENTRY_AUTHORIZED}),
        ENTRY_AUTHORIZED: frozenset({GATE_OPEN_REQUESTED}),
        GATE_OPEN_REQUESTED: frozenset({VEHICLE_PASSED}),
        VEHICLE_PASSED: frozenset({ACTIVE}),
        ACTIVE: frozenset({EXIT_VEHICLE_DETECTED}),
        ENTRY_CANCELLED: frozenset(),
        EXIT_VEHICLE_DETECTED: frozenset({SESSION_RESOLVED}),
        SESSION_RESOLVED: frozenset({TARIFF_CALCULATED}),
        TARIFF_CALCULATED: frozenset({AUTHORIZATION_DECISION}),
        AUTHORIZATION_DECISION: frozenset({AUTHORIZED, DENIED_PAYMENT_REQUIRED}),
        AUTHORIZED: frozenset({EXIT_GATE_OPEN_REQUESTED}),
        DENIED_PAYMENT_REQUIRED: frozenset({TARIFF_CALCULATED, AUTHORIZATION_DECISION}),
        EXIT_GATE_OPEN_REQUESTED: frozenset({EXIT_VEHICLE_PASSED}),
        EXIT_VEHICLE_PASSED: frozenset({CLOSED}),
        CLOSED: frozenset(),
    }


def allowed_targets(current: str, policy: LanePolicy, *, parker_kind: str = "CASUAL") -> set[str]:
    targets = set(_base_transitions().get(current, frozenset()))
    subscriber = _is_subscriber(parker_kind) and policy.subscriber_skip_receipt
    receipt_required = bool(policy.receipt_required_before_open) and not subscriber

    if current == SESSION_CREATED and not receipt_required:
        targets.add(ENTRY_AUTHORIZED)
    if current == IDENTITY_RESOLVED and subscriber:
        targets.add(SESSION_CREATED)

    if receipt_required and current in {SESSION_CREATED, RECEIPT_PRINTING, RECEIPT_PRESENTED}:
        targets.discard(ENTRY_AUTHORIZED)
        targets.discard(GATE_OPEN_REQUESTED)
    if receipt_required and current == SESSION_CREATED:
        targets.add(RECEIPT_PRINTING)
    if policy.passage_fallback():
        if current == GATE_OPEN_REQUESTED:
            targets.add(VEHICLE_PASSED)
            targets.add(ACTIVE)
        if current == EXIT_GATE_OPEN_REQUESTED:
            targets.add(EXIT_VEHICLE_PASSED)
            targets.add(CLOSED)

    return targets


def can_transition(current: str, target: str, policy: LanePolicy, *, parker_kind: str = "CASUAL") -> bool:
    if current == target:
        return True
    return target in allowed_targets(current, policy, parker_kind=parker_kind)


def stored_status_for(lifecycle: str, *, previous: str = STORED_ACTIVE, receipt_required: bool = False) -> str:
    if lifecycle in RECEIPT_STATES or lifecycle in {VEHICLE_DETECTED, IDENTITY_RESOLVED, SESSION_CREATED}:
        if receipt_required and lifecycle != RECEIPT_TAKEN:
            return STORED_WAITING_RECEIPT
        if lifecycle == RECEIPT_TAKEN:
            return STORED_ACTIVE
        return STORED_WAITING_RECEIPT if receipt_required else STORED_ACTIVE
    if lifecycle in {ENTRY_AUTHORIZED, GATE_OPEN_REQUESTED, VEHICLE_PASSED, ACTIVE}:
        return STORED_PAID if previous == STORED_PAID else STORED_ACTIVE
    if lifecycle == ENTRY_CANCELLED:
        return STORED_CLOSED
    if lifecycle == DENIED_PAYMENT_REQUIRED:
        return STORED_ACTIVE
    if lifecycle in {EXIT_VEHICLE_DETECTED, SESSION_RESOLVED, TARIFF_CALCULATED, AUTHORIZATION_DECISION, AUTHORIZED, EXIT_GATE_OPEN_REQUESTED, EXIT_VEHICLE_PASSED}:
        if lifecycle == CLOSED:
            return STORED_CLOSED
        return STORED_PAID if previous == STORED_PAID else STORED_ACTIVE
    if lifecycle == CLOSED:
        return STORED_CLOSED
    return previous or STORED_ACTIVE


def infer_lifecycle(status: str, *, side: str = "ENTRY") -> str:
    stored = (status or "").upper()
    if stored == STORED_CLOSED:
        return CLOSED
    if stored == STORED_WAITING_RECEIPT:
        return SESSION_CREATED
    if stored == STORED_PAID:
        return ACTIVE
    if (side or "").upper() == "EXIT":
        return EXIT_VEHICLE_DETECTED
    return ACTIVE if stored in OPEN_STORED else SESSION_CREATED


def apply_transition(
    current: str,
    target: str,
    policy: LanePolicy,
    *,
    parker_kind: str = "CASUAL",
) -> str:
    """Return *target* or raise. Same-state is idempotent."""
    current = current or VEHICLE_DETECTED
    if current == target:
        return current
    if not can_transition(current, target, policy, parker_kind=parker_kind):
        raise InvalidTransition(f"{current} -> {target} is not allowed")
    return target
