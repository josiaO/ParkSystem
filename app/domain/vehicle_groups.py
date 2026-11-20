"""Linked-vehicle authorization groups: pure policy and state transitions.

A Vehicle Authorization Group links several registered vehicles that share
one parking entitlement. While a group member is inside, the group holds an
*occupancy slot*. A PRIVATE group has exactly one slot, so a second member is
refused until the first one has *confirmed* left. This is an active-occupancy
rule, not a calendar-day rule: a car that stays overnight still holds the slot
the next morning.

A FLEET (company) group has its own configurable limit (0 = no limit) and its
own exit-release policy; it never inherits the PRIVATE one-at-a-time rule.

The slot is released only on *exit evidence* the group's policy accepts. A
barrier-open command on its own is never evidence: manual boom openings do
not touch sessions or slots at all, and an operator must confirm the exit.

No database, camera or GPIO code here (see app/services/vehicle_groups.py).
"""

from __future__ import annotations

from dataclasses import dataclass

# --- group kinds ---
PRIVATE = "PRIVATE"
FLEET = "FLEET"
GROUP_KINDS = (PRIVATE, FLEET)

# --- occupancy states ---
OCC_ACTIVE = "ACTIVE"                      # member inside (or entering); slot held
OCC_EXIT_UNCONFIRMED = "EXIT_UNCONFIRMED"  # visit ended without accepted evidence; slot held
OCC_RECONCILIATION = "RECONCILIATION"      # operator could not confirm; supervisor decides; slot held
OCC_RELEASED = "RELEASED"                  # slot free
HELD_STATES = (OCC_ACTIVE, OCC_EXIT_UNCONFIRMED, OCC_RECONCILIATION)
OCCUPANCY_STATES = (*HELD_STATES, OCC_RELEASED)

# --- exit evidence ---
EV_PASSAGE_SENSOR = "PASSAGE_SENSOR"            # loop/beam confirmed the car passed the exit barrier
EV_EXIT_LANE = "EXIT_LANE"                      # exit camera/QR identified the car, exit was authorized
                                                # and the barrier accepted the command; no passage signal
EV_OPERATOR = "OPERATOR_CONFIRMED"              # guard confirmed the exit (photo + reason)
EV_SUPERVISOR = "SUPERVISOR_RECONCILED"         # supervisor released after review
EV_SEEN_AT_ENTRY = "SEEN_AT_ENTRY"              # the same car is back at the entry, so it had left
EV_ENTRY_NOT_OPENED = "ENTRY_CANCELLED_NOT_OPENED"  # entry attempt cancelled before any barrier command
EV_UNCONFIRMED = "UNCONFIRMED"                  # visit closed with no exit proof (written off, cancelled after open…)

# --- exit-release policies ---
RELEASE_EXIT_LANE = "EXIT_LANE"
RELEASE_PASSAGE_CONFIRMED = "PASSAGE_CONFIRMED"
RELEASE_POLICIES = (RELEASE_EXIT_LANE, RELEASE_PASSAGE_CONFIRMED)

_ALWAYS_ACCEPTED = frozenset({EV_PASSAGE_SENSOR, EV_OPERATOR, EV_SUPERVISOR, EV_SEEN_AT_ENTRY, EV_ENTRY_NOT_OPENED})
_ACCEPTED = {
    RELEASE_EXIT_LANE: _ALWAYS_ACCEPTED | {EV_EXIT_LANE},
    RELEASE_PASSAGE_CONFIRMED: _ALWAYS_ACCEPTED,
}

# --- occupancy events ---
E_CLOSED_CONFIRMED = "CLOSED_CONFIRMED"      # visit closed with accepted evidence
E_CLOSED_UNCONFIRMED = "CLOSED_UNCONFIRMED"  # visit closed without accepted evidence
E_OPERATOR_CONFIRM = "OPERATOR_CONFIRM"      # guard confirms the vehicle left
E_OPERATOR_UNCERTAIN = "OPERATOR_UNCERTAIN"  # guard cannot tell (boom opened, no photo match…)
E_SUPERVISOR_RELEASE = "SUPERVISOR_RELEASE"
E_SUPERVISOR_KEEP_INSIDE = "SUPERVISOR_KEEP_INSIDE"
E_SUPERVISOR_KEEP_LOCKED = "SUPERVISOR_KEEP_LOCKED"  # visit already closed; keep the slot until proof
E_SEEN_AT_ENTRY = "SEEN_AT_ENTRY"

_TRANSITIONS: dict[tuple[str, str], str] = {
    (OCC_ACTIVE, E_CLOSED_CONFIRMED): OCC_RELEASED,
    (OCC_ACTIVE, E_CLOSED_UNCONFIRMED): OCC_EXIT_UNCONFIRMED,
    (OCC_ACTIVE, E_OPERATOR_CONFIRM): OCC_RELEASED,
    (OCC_ACTIVE, E_OPERATOR_UNCERTAIN): OCC_RECONCILIATION,
    (OCC_ACTIVE, E_SUPERVISOR_RELEASE): OCC_RELEASED,
    (OCC_EXIT_UNCONFIRMED, E_OPERATOR_CONFIRM): OCC_RELEASED,
    (OCC_EXIT_UNCONFIRMED, E_OPERATOR_UNCERTAIN): OCC_RECONCILIATION,
    (OCC_EXIT_UNCONFIRMED, E_SUPERVISOR_RELEASE): OCC_RELEASED,
    (OCC_EXIT_UNCONFIRMED, E_SEEN_AT_ENTRY): OCC_RELEASED,
    (OCC_EXIT_UNCONFIRMED, E_CLOSED_CONFIRMED): OCC_RELEASED,
    (OCC_EXIT_UNCONFIRMED, E_CLOSED_UNCONFIRMED): OCC_EXIT_UNCONFIRMED,
    # An uncertain case belongs to a supervisor: an operator cannot clear it,
    # and closing the visit (e.g. a write-off) does not release it either.
    (OCC_RECONCILIATION, E_SUPERVISOR_RELEASE): OCC_RELEASED,
    (OCC_RECONCILIATION, E_SUPERVISOR_KEEP_INSIDE): OCC_ACTIVE,
    (OCC_RECONCILIATION, E_SUPERVISOR_KEEP_LOCKED): OCC_EXIT_UNCONFIRMED,
    (OCC_RECONCILIATION, E_CLOSED_CONFIRMED): OCC_RECONCILIATION,
    (OCC_RECONCILIATION, E_CLOSED_UNCONFIRMED): OCC_RECONCILIATION,
    (OCC_EXIT_UNCONFIRMED, E_SUPERVISOR_KEEP_INSIDE): OCC_ACTIVE,
    (OCC_EXIT_UNCONFIRMED, E_SUPERVISOR_KEEP_LOCKED): OCC_EXIT_UNCONFIRMED,
}


class InvalidOccupancyTransition(ValueError):
    """The occupancy cannot take this event from its current state."""


class GroupOccupied(Exception):
    """Every slot of the vehicle's authorization group is held by another member."""

    def __init__(self, group: dict, holders: list[dict]):
        self.group = group
        self.holders = holders
        names = ", ".join(str(h.get("plate") or "?") for h in holders) or "another vehicle"
        super().__init__(f"{group.get('display_name') or group.get('name') or 'Group'}: {names} is still inside")


class VisitorPassExhausted(Exception):
    """A visitor pass was used up between lookup and session creation."""


def next_state(state: str, event: str) -> str:
    try:
        return _TRANSITIONS[(state, event)]
    except KeyError:
        raise InvalidOccupancyTransition(f"{state} -> {event} is not allowed") from None


def releases(policy: str, evidence: str) -> bool:
    """Does this exit evidence free the slot under the group's policy?"""
    return evidence in _ACCEPTED.get(policy or RELEASE_EXIT_LANE, _ACCEPTED[RELEASE_EXIT_LANE])


@dataclass(frozen=True)
class GroupPolicy:
    kind: str = PRIVATE
    max_active_sessions: int = 1   # 0 = no limit (FLEET only)
    exit_release: str = RELEASE_EXIT_LANE

    @property
    def enforced(self) -> bool:
        return self.max_active_sessions > 0


def normalize_policy(kind: str | None, max_active: int | None, exit_release: str | None) -> GroupPolicy:
    """Validate a group's configuration. PRIVATE is always exactly one at a time."""
    kind = (kind or PRIVATE).strip().upper()
    if kind not in GROUP_KINDS:
        raise ValueError(f"Group type must be one of {', '.join(GROUP_KINDS)}")
    release = (exit_release or RELEASE_EXIT_LANE).strip().upper()
    if release not in RELEASE_POLICIES:
        raise ValueError(f"Exit release must be one of {', '.join(RELEASE_POLICIES)}")
    if kind == PRIVATE:
        return GroupPolicy(kind=PRIVATE, max_active_sessions=1, exit_release=release)
    limit = 0 if max_active is None else int(max_active)
    if limit < 0 or limit > 500:
        raise ValueError("Fleet limit must be between 0 (no limit) and 500")
    return GroupPolicy(kind=FLEET, max_active_sessions=limit, exit_release=release)


def display_name(kind: str, name: str, company_name: str = "", owner_name: str = "") -> str:
    """One line an operator reads at the gate: who this car belongs to."""
    if (kind or "").upper() == FLEET:
        return f"Company: {company_name or name}"
    return f"Private: {owner_name or name}"
