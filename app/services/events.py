"""Publish domain events to the transactional outbox."""

from __future__ import annotations

from typing import Any

from app.services.queues import parking_outbox


def recognition_from_outbox(item: dict[str, Any]) -> dict[str, Any] | None:
    """Unwrap a PlateRecognized outbox row written by the recognition worker."""
    if str(item.get("kind") or "") != "PlateRecognized":
        return None
    wrapper = item.get("payload") or {}
    inner = wrapper.get("payload") if isinstance(wrapper, dict) else None
    if not isinstance(inner, dict):
        return None
    plate = str(inner.get("normalized_plate") or inner.get("plate_text_normalized") or "").strip()
    if not plate:
        return None
    return {
        **inner,
        "event_id": wrapper.get("event_id") or inner.get("event_id"),
        "plate": plate,
        "camera_id": inner.get("camera_id"),
        "source": str(inner.get("source") or inner.get("recognition_provider") or "FASTALPR"),
    }


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
