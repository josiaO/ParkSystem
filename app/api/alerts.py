"""HTTP boundary for manual-open records and their alerts."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AlertDelivery, ManualOpenEvent, User
from app.security import require

from .module_routes import ModuleRoute


def _delivery_dict(row: AlertDelivery) -> dict:
    from app.infrastructure.payments.common import mask_msisdn

    to = row.recipient
    if row.channel == "sms":
        to = mask_msisdn(to)
    return {
        "id": row.id,
        "channel": row.channel,
        "to": to,
        "status": row.status,
        "attempts": row.attempts,
        "last_error": row.last_error,
        "sent_at": row.sent_at.isoformat() if row.sent_at else None,
    }


def register() -> APIRouter:
    router = APIRouter(route_class=ModuleRoute)

    @router.get("/manual-opens")
    def list_manual_opens(
        unacknowledged: bool = False,
        limit: int = Query(50, ge=1, le=500),
        db: Session = Depends(get_db),
        _: User = Depends(require("alerts.view")),
    ):
        from app.services.manual_open import event_dict

        query = select(ManualOpenEvent).order_by(ManualOpenEvent.id.desc()).limit(limit)
        if unacknowledged:
            query = query.where(ManualOpenEvent.acknowledged_at.is_(None))
        return [event_dict(row) for row in db.scalars(query).all()]

    @router.get("/manual-opens/{event_id}")
    def get_manual_open(event_id: int, db: Session = Depends(get_db), _: User = Depends(require("alerts.view"))):
        from app.services.manual_open import event_dict

        row = db.get(ManualOpenEvent, event_id)
        if row is None:
            raise HTTPException(404, "Manual open not found")
        deliveries = db.scalars(select(AlertDelivery).where(AlertDelivery.event_id == event_id)).all()
        return {**event_dict(row), "deliveries": [_delivery_dict(d) for d in deliveries]}

    @router.post("/manual-opens/{event_id}/acknowledge")
    def acknowledge_manual_open(
        event_id: int,
        payload: dict = Body(default_factory=dict),
        db: Session = Depends(get_db),
        user: User = Depends(require("alerts.acknowledge")),
    ):
        from app.services.audit import write_audit
        from app.services.manual_open import event_dict

        row = db.get(ManualOpenEvent, event_id)
        if row is None:
            raise HTTPException(404, "Manual open not found")
        if row.operator_id is not None and row.operator_id == user.id and "*" not in _perms(user):
            raise HTTPException(403, "The person who opened the barrier cannot acknowledge their own manual open.")
        if row.acknowledged_at is None:
            row.acknowledged_at = datetime.now(timezone.utc)
            row.acknowledged_by = user.id
            row.acknowledge_note = str((payload or {}).get("note") or "").strip()[:240]
            db.commit()
            write_audit(db, user, "manual_open.acknowledge", "manual_open", str(row.id),
                        f"{row.plate or 'unidentified'} {row.lane_label}: {row.acknowledge_note}"[:240])
            db.commit()
        return event_dict(row)

    @router.get("/manual-opens/{event_id}/photo.jpg", include_in_schema=False)
    def manual_open_photo(event_id: int, exp: int = 0, sig: str = "", db: Session = Depends(get_db)):
        """Signed, expiring link used in SMS/e-mail alerts (no login)."""
        from app.services.manual_open import _read_media, verify_photo_signature

        if not exp or not sig or not verify_photo_signature(event_id, exp, sig):
            raise HTTPException(403, "Link expired or invalid")
        row = db.get(ManualOpenEvent, event_id)
        data = _read_media(row.photo_ref) if row is not None and row.photo_ref else b""
        if not data:
            raise HTTPException(404, "Photo not found")
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})

    @router.get("/settings/alerts")
    def get_alert_settings(db: Session = Depends(get_db), _: User = Depends(require("settings.manage"))):
        from app.services.alerts import alert_settings, provider_status

        return {**alert_settings(db), "providers": provider_status()}

    @router.put("/settings/alerts")
    def put_alert_settings(
        payload: dict = Body(default_factory=dict),
        db: Session = Depends(get_db),
        user: User = Depends(require("settings.manage")),
    ):
        from app.services.alerts import provider_status, save_alert_settings
        from app.services.audit import write_audit

        try:
            saved = save_alert_settings(db, payload or {})
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        write_audit(db, user, "settings.alerts", "site_setting", "alerts",
                    f"{len(saved.get('recipients') or [])} recipients, enabled={saved.get('enabled')}")
        db.commit()
        return {**saved, "providers": provider_status()}

    @router.post("/settings/alerts/test")
    async def test_alert(payload: dict = Body(default_factory=dict), _: User = Depends(require("settings.manage"))):
        import asyncio

        from app.services.alerts import send_test

        try:
            return await asyncio.to_thread(send_test, str(payload.get("channel") or ""), str(payload.get("to") or ""))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    return router


def _perms(user: User) -> set[str]:
    from app.security import user_permissions

    return user_permissions(user)
