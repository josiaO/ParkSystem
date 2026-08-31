"""Publish domain events to the transactional outbox."""

from __future__ import annotations

from typing import Any

from app.services.queues import parking_outbox


def publish(event: dict[str, Any], *, dedupe_key: str | None = None) -> dict[str, Any]:
    kind = str(event.get("kind") or "domain-event")
    payload = {
        "kind": kind,
        "event_id": event.get("event_id"),
        "occurred_at": event.get("occurred_at"),
        "site_id": event.get("site_id"),
        "dedupe_key": dedupe_key,
        "payload": event.get("payload") or {},
    }
    outbox_id = parking_outbox().enqueue(kind=kind, payload=payload)
    return {"queued": True, "outbox_id": outbox_id, "event": payload}
