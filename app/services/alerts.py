"""Alerts for manual barrier openings: routing, message text, durable delivery.

Recipients and thresholds are the ``alerts`` site setting (editable in the UI).
Provider credentials come from settings/env only. Every alert is an
``AlertDelivery`` row, so a down internet link or provider never loses one:
the delivery loop claims due rows, sends, and retries with back-off.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import re
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any, Callable

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.models import MANUAL_SOURCE_UNCOMMANDED, AlertDelivery, ManualOpenEvent, SiteSetting

log = logging.getLogger("smartpark")

SETTING_KEY = "alerts"
CHANNELS = ("sms", "email", "webhook")
PENDING, RETRY, SENDING, SENT, DEAD = "PENDING", "RETRY", "SENDING", "SENT", "DEAD"
CLAIM_TIMEOUT = timedelta(minutes=5)

DEFAULT_ALERT_SETTINGS: dict[str, Any] = {
    "enabled": True,
    "recipients": [],             # [{"channel": "sms"|"email"|"webhook", "to": "...", "name": "..."}]
    "notify_zero_fee": True,      # also alert when nothing was owed
    "notify_failed_commands": False,
    "boom_inputs": {},            # {"<camera_id>": {"index": 5, "active": 1}}
}

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------- settings

def alert_settings(db: Session) -> dict[str, Any]:
    row = db.get(SiteSetting, SETTING_KEY)
    merged = json.loads(json.dumps(DEFAULT_ALERT_SETTINGS))
    if row is not None and isinstance(row.value, dict):
        merged.update(row.value)
    return merged


def normalize_recipient(item: dict[str, Any]) -> dict[str, str]:
    channel = str(item.get("channel") or "").strip().lower()
    to = str(item.get("to") or "").strip()
    name = str(item.get("name") or "").strip()[:80]
    if channel not in CHANNELS:
        raise ValueError(f"Unknown alert channel {channel!r}; use one of {', '.join(CHANNELS)}")
    if channel == "sms":
        from app.infrastructure.payments.common import normalize_msisdn

        to = normalize_msisdn(to)
    elif channel == "email":
        if not _EMAIL.match(to):
            raise ValueError(f"Invalid e-mail address {to!r}")
    else:
        if not re.match(r"^https?://[^\s]+$", to):
            raise ValueError("Webhook recipient must be an http(s) URL")
    return {"channel": channel, "to": to[:300], "name": name}


def save_alert_settings(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    current = alert_settings(db)
    if "enabled" in payload:
        current["enabled"] = bool(payload["enabled"])
    for flag in ("notify_zero_fee", "notify_failed_commands"):
        if flag in payload:
            current[flag] = bool(payload[flag])
    if "recipients" in payload:
        seen: set[tuple[str, str]] = set()
        recipients = []
        for item in payload.get("recipients") or []:
            rec = normalize_recipient(item if isinstance(item, dict) else {})
            if (rec["channel"], rec["to"]) not in seen:
                seen.add((rec["channel"], rec["to"]))
                recipients.append(rec)
        current["recipients"] = recipients
    if "boom_inputs" in payload:
        inputs: dict[str, dict[str, int]] = {}
        for camera_id, value in (payload.get("boom_inputs") or {}).items():
            if value in (None, "", {}):
                continue
            index = int(value["index"])
            if not 1 <= index <= 16:
                raise ValueError("Boom input index must be 1-16")
            inputs[str(int(camera_id))] = {"index": index, "active": 1 if int(value.get("active", 1)) else 0}
        current["boom_inputs"] = inputs
    row = db.get(SiteSetting, SETTING_KEY)
    if row is None:
        db.add(SiteSetting(key=SETTING_KEY, value=current))
    else:
        row.value = current
    db.commit()
    from app.services import manual_open

    manual_open._boom_index_cache.clear()
    return alert_settings(db)


def boom_input_indexes(db: Session, camera_id: int) -> set[int]:
    entry = (alert_settings(db).get("boom_inputs") or {}).get(str(int(camera_id)))
    try:
        return {int(entry["index"])} if isinstance(entry, dict) else set()
    except (KeyError, TypeError, ValueError):
        return set()


# ----------------------------------------------------------------------- message

def _money(amount: float, currency: str) -> str:
    whole = abs(amount - round(amount)) < 0.005
    return f"{currency} {amount:,.0f}" if whole else f"{currency} {amount:,.2f}"


def _duration(seconds: int | None) -> str:
    if seconds is None or seconds < 0:
        return ""
    hours, rest = divmod(int(seconds), 3600)
    minutes = rest // 60
    if hours >= 24:
        days, hours = divmod(hours, 24)
        return f"{days}d {hours}h"
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes} min"


def _site_local(value: datetime | None, db: Session | None) -> str:
    if value is None:
        return ""
    try:
        from app.services.site_policy import as_site_local, site_policy

        return as_site_local(value, site_policy(db) if db is not None else None).strftime("%d %b %H:%M")
    except Exception:
        return _aware(value).strftime("%d %b %H:%M UTC")


def photo_url(db: Session | None, event: ManualOpenEvent) -> str:
    if not event.photo_ref:
        return ""
    from app.services.manual_open import signed_photo_path
    from app.services.receipts import resolve_public_base_url

    base = resolve_public_base_url(db) if db is not None else (settings.public_base_url or "")
    if not base:
        try:
            from app.deployment import server_base_url

            base = server_base_url()
        except Exception:
            base = ""
    return f"{base.rstrip('/')}{signed_photo_path(event)}" if base else signed_photo_path(event)


def format_alert(event: ManualOpenEvent, db: Session | None = None) -> dict[str, str]:
    """(subject, short text for SMS, long text for e-mail/webhook)."""
    when = _site_local(event.created_at, db)
    lane = event.lane_label or "a lane"
    if event.source == MANUAL_SOURCE_UNCOMMANDED:
        headline = f"Barrier at {lane} rose WITHOUT a Zirp command ({when})"
    elif not event.command_ok:
        headline = f"Manual open at {lane} was attempted but the barrier command FAILED ({when})"
    else:
        headline = f"Manual barrier open at {lane} ({when})"
    if event.plate:
        car = f"Car {event.plate}"
        if event.session_id:
            owed = float(event.amount_owed or 0)
            money = (f"owed {_money(owed, event.currency)}" if owed > 0 else "owed nothing")
            if float(event.amount_paid or 0) > 0:
                money += f" (paid {_money(float(event.amount_paid), event.currency)})"
            stay = _duration(event.duration_seconds)
            car += f" {money}" + (f", parked {stay}" if stay else "")
            if event.parker_kind and event.parker_kind.upper() not in {"CASUAL", ""}:
                car += f" [{event.parker_kind}]"
        else:
            car += ": no open parking visit found"
        if event.plate_seconds_before:
            car += f". Plate read {float(event.plate_seconds_before):.0f}s earlier"
    else:
        car = "Car NOT identified: no plate read on this lane just before opening"
    who = event.operator_name or ("nobody in Zirp" if event.source == MANUAL_SOURCE_UNCOMMANDED else "unknown user")
    reason = f' Reason: "{event.reason}".' if event.reason else ""
    link = photo_url(db, event)
    short = f"ZIRP: {headline}. {car}. By {who}.{reason}" + (f" Photo: {link}" if link else "")
    long = "\n".join(filter(None, [
        headline + ".",
        car + ".",
        f"Opened by: {who}",
        f"Reason: {event.reason}" if event.reason else "",
        f"Entry time: {_site_local(event.entry_time, db)}" if event.entry_time else "",
        f"Amount due: {_money(float(event.amount_due or 0), event.currency)}; paid: {_money(float(event.amount_paid or 0), event.currency)}" if event.session_id else "",
        f"Barrier command: {'accepted' if event.command_ok else 'FAILED'} {event.command_message[:200]}".strip(),
        f"Photo (link expires in {int(settings.alerts_photo_link_hours or 24)} h): {link}" if link else "",
        f"Zirp event #{event.id}",
    ]))
    owed_tag = f" — owed {_money(float(event.amount_owed or 0), event.currency)}" if float(event.amount_owed or 0) > 0 else ""
    subject = f"[Zirp] {('UNCOMMANDED ' if event.source == MANUAL_SOURCE_UNCOMMANDED else '')}manual open {lane} {event.plate or 'unidentified'}{owed_tag}"
    return {"subject": subject[:180], "short": short[:459], "long": long}


# ----------------------------------------------------------------------- queueing

def should_alert(event: ManualOpenEvent, cfg: dict[str, Any]) -> bool:
    if not cfg.get("enabled") or not cfg.get("recipients"):
        return False
    if event.source == MANUAL_SOURCE_UNCOMMANDED:
        return True
    if not event.command_ok:
        return bool(cfg.get("notify_failed_commands"))
    if not event.plate or float(event.amount_owed or 0) > 0:
        return True
    return bool(cfg.get("notify_zero_fee", True))


def queue_for_event(db: Session, event: ManualOpenEvent) -> list[AlertDelivery]:
    cfg = alert_settings(db)
    if not should_alert(event, cfg):
        event.alert_status = "NOT_SENT" if cfg.get("recipients") else "NO_RECIPIENTS"
        db.commit()
        return []
    rows = []
    now = _now()
    for recipient in cfg.get("recipients") or []:
        try:
            rec = normalize_recipient(recipient)
        except ValueError as exc:
            log.warning("skipping invalid alert recipient: %s", exc)
            continue
        row = AlertDelivery(event_id=event.id, channel=rec["channel"], recipient=rec["to"],
                            status=PENDING, next_attempt_at=now, created_at=now)
        db.add(row)
        rows.append(row)
    event.alert_status = "QUEUED" if rows else "NO_RECIPIENTS"
    db.commit()
    return rows


def refresh_event_status(db: Session, event_id: int) -> str:
    statuses = [s for (s,) in db.execute(select(AlertDelivery.status).where(AlertDelivery.event_id == event_id)).all()]
    event = db.get(ManualOpenEvent, event_id)
    if event is None or not statuses:
        return getattr(event, "alert_status", "") or ""
    if any(s in {PENDING, RETRY, SENDING} for s in statuses):
        status = "QUEUED"
    elif all(s == SENT for s in statuses):
        status = "SENT"
    elif any(s == SENT for s in statuses):
        status = "PARTIAL"
    else:
        status = "FAILED"
    event.alert_status = status
    db.commit()
    return status


# ----------------------------------------------------------------------- channels

class AlertSendError(RuntimeError):
    pass


def _photo_bytes(event: ManualOpenEvent) -> bytes:
    from app.services.manual_open import _read_media

    return _read_media(event.photo_ref) if event.photo_ref else b""


def send_sms(to: str, text: str) -> str:
    import httpx

    username = (settings.alerts_africastalking_username or "").strip()
    api_key = (settings.alerts_africastalking_api_key or "").strip()
    if not username or not api_key:
        raise AlertSendError("SMS provider not configured (SMARTPARK_ALERTS_AFRICASTALKING_USERNAME/_API_KEY)")
    data = {"username": username, "to": to, "message": text}
    if settings.alerts_africastalking_sender_id:
        data["from"] = settings.alerts_africastalking_sender_id
    response = httpx.post(
        settings.alerts_africastalking_base_url,
        data=data,
        headers={"apiKey": api_key, "Accept": "application/json"},
        timeout=float(settings.alerts_http_timeout_seconds or 8.0),
    )
    if response.status_code >= 400:
        raise AlertSendError(f"SMS HTTP {response.status_code}: {response.text[:200]}")
    try:
        recipients = (response.json().get("SMSMessageData") or {}).get("Recipients") or []
    except ValueError as exc:
        raise AlertSendError(f"SMS provider returned non-JSON: {response.text[:120]}") from exc
    if not recipients:
        raise AlertSendError(f"SMS not accepted: {response.text[:200]}")
    first = recipients[0]
    if int(first.get("statusCode") or 0) not in {100, 101, 102}:
        raise AlertSendError(f"SMS rejected: {first.get('status')}")
    return str(first.get("messageId") or "sent")


def send_email(to: str, subject: str, text: str, photo: bytes = b"") -> str:
    host = (settings.alerts_smtp_host or "").strip()
    sender = (settings.alerts_smtp_from or settings.alerts_smtp_username or "").strip()
    if not host or not sender:
        raise AlertSendError("E-mail not configured (SMARTPARK_ALERTS_SMTP_HOST/_FROM)")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = to
    message.set_content(text)
    if photo:
        message.add_attachment(photo, maintype="image", subtype="jpeg", filename="manual-open.jpg")
    timeout = float(settings.alerts_http_timeout_seconds or 8.0) * 2
    port = int(settings.alerts_smtp_port or 587)
    smtp_cls = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
    with smtp_cls(host, port, timeout=timeout) as client:
        if smtp_cls is smtplib.SMTP and settings.alerts_smtp_starttls:
            client.starttls()
        if settings.alerts_smtp_username:
            client.login(settings.alerts_smtp_username, settings.alerts_smtp_password or "")
        client.send_message(message)
    return "sent"


def send_webhook(url: str, payload: dict[str, Any]) -> str:
    import httpx

    body = json.dumps(payload, default=str, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "Zirp-Alerts/1"}
    secret = (settings.alerts_webhook_secret or "").strip()
    if secret:
        headers["X-Zirp-Signature"] = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    response = httpx.post(url, content=body, headers=headers, timeout=float(settings.alerts_http_timeout_seconds or 8.0))
    if response.status_code >= 400:
        raise AlertSendError(f"Webhook HTTP {response.status_code}")
    return str(response.status_code)


def send_one(db: Session, delivery: AlertDelivery, event: ManualOpenEvent) -> str:
    text = format_alert(event, db)
    if delivery.channel == "sms":
        return send_sms(delivery.recipient, text["short"])
    if delivery.channel == "email":
        return send_email(delivery.recipient, text["subject"], text["long"], _photo_bytes(event))
    if delivery.channel == "webhook":
        from app.services.manual_open import event_dict

        return send_webhook(delivery.recipient, {
            "type": "zirp.manual_open", "text": text["short"], "subject": text["subject"],
            "photo_url": photo_url(db, event), "event": event_dict(event, with_photo_link=False),
        })
    raise AlertSendError(f"Unknown channel {delivery.channel}")


# ----------------------------------------------------------------------- delivery

UNQUEUED_GRACE = timedelta(seconds=30)
UNQUEUED_LOOKBACK = timedelta(days=2)


def queue_unqueued_events(db: Session, *, now: datetime | None = None, limit: int = 50) -> int:
    """Queue alerts for manual-open events that were saved but never queued.

    ``record_manual_open`` commits the event first and queues alerts second so
    alerting never blocks the barrier. A crash, power cut or DB error between
    the two commits left ``alert_status='NONE'`` and the owner was never told.
    This sweep (run by the delivery loop) closes that gap. ``NONE`` is only the
    pre-queue state: ``queue_for_event`` always moves it to QUEUED, NOT_SENT or
    NO_RECIPIENTS, so an event is queued at most once.
    """
    now = now or _now()
    ids = db.scalars(
        select(ManualOpenEvent.id)
        .where(
            ManualOpenEvent.alert_status == "NONE",
            ManualOpenEvent.created_at < now - UNQUEUED_GRACE,
            ManualOpenEvent.created_at > now - UNQUEUED_LOOKBACK,
        )
        .order_by(ManualOpenEvent.id)
        .limit(limit)
    ).all()
    queued = 0
    for event_id in ids:
        # Claim the event so two Site Services sharing a database do not both queue it.
        claimed = db.execute(
            update(ManualOpenEvent)
            .where(ManualOpenEvent.id == event_id, ManualOpenEvent.alert_status == "NONE")
            .values(alert_status="QUEUEING")
        )
        db.commit()
        if claimed.rowcount != 1:
            continue
        event = db.get(ManualOpenEvent, event_id)
        try:
            queue_for_event(db, event)
            queued += 1
            log.warning("ALERT recovered unqueued manual-open event id=%s", event_id)
        except Exception as exc:
            db.rollback()
            db.execute(update(ManualOpenEvent).where(ManualOpenEvent.id == event_id).values(alert_status="NONE"))
            db.commit()
            log.error("ALERT re-queue failed for manual-open event id=%s: %s", event_id, exc)
    return queued


def _backoff_seconds(attempts: int) -> int:
    return int(min(3600, 15 * (2 ** max(0, attempts - 1))))


def claim_due(db: Session, *, now: datetime | None = None, limit: int = 20) -> list[int]:
    """Claim due rows atomically; safe if two Site Services share one database."""
    now = now or _now()
    candidates = db.scalars(
        select(AlertDelivery.id)
        .where(or_(
            (AlertDelivery.status.in_([PENDING, RETRY])) & (AlertDelivery.next_attempt_at <= now),
            (AlertDelivery.status == SENDING) & (AlertDelivery.claimed_at < now - CLAIM_TIMEOUT),
        ))
        .order_by(AlertDelivery.id)
        .limit(limit)
    ).all()
    claimed = []
    for delivery_id in candidates:
        result = db.execute(
            update(AlertDelivery)
            .where(
                AlertDelivery.id == delivery_id,
                or_(AlertDelivery.status.in_([PENDING, RETRY]),
                    (AlertDelivery.status == SENDING) & (AlertDelivery.claimed_at < now - CLAIM_TIMEOUT)),
            )
            .values(status=SENDING, claimed_at=now)
        )
        db.commit()
        if result.rowcount == 1:
            claimed.append(int(delivery_id))
    return claimed


def deliver_due_once(
    session_factory: Callable[[], Session] | None = None,
    *,
    sender: Callable[[Session, AlertDelivery, ManualOpenEvent], str] | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    from app.db import short_session

    factory = session_factory or short_session
    send = sender or send_one
    counts = {"sent": 0, "retry": 0, "dead": 0}
    with factory() as db:
        try:
            queue_unqueued_events(db, now=now)
        except Exception as exc:
            db.rollback()
            log.warning("ALERT unqueued-event sweep failed: %s", exc)
        claimed = claim_due(db, now=now)
        for delivery_id in claimed:
            delivery = db.get(AlertDelivery, delivery_id)
            event = db.get(ManualOpenEvent, delivery.event_id) if delivery is not None else None
            if delivery is None or event is None:
                continue
            try:
                send(db, delivery, event)
            except Exception as exc:
                db.rollback()
                delivery = db.get(AlertDelivery, delivery_id)
                delivery.attempts = int(delivery.attempts or 0) + 1
                delivery.last_error = f"{type(exc).__name__}: {exc}"[:500]
                if delivery.attempts >= int(settings.alerts_max_attempts or 8):
                    delivery.status = DEAD
                    counts["dead"] += 1
                    log.error("ALERT dead event=%s channel=%s after %s attempts: %s",
                              delivery.event_id, delivery.channel, delivery.attempts, delivery.last_error)
                else:
                    delivery.status = RETRY
                    delivery.next_attempt_at = (now or _now()) + timedelta(seconds=_backoff_seconds(delivery.attempts))
                    counts["retry"] += 1
                    log.warning("ALERT retry event=%s channel=%s attempt=%s: %s",
                                delivery.event_id, delivery.channel, delivery.attempts, delivery.last_error)
            else:
                delivery.status = SENT
                delivery.sent_at = now or _now()
                delivery.attempts = int(delivery.attempts or 0) + 1
                delivery.last_error = ""
                counts["sent"] += 1
                log.info("ALERT sent event=%s channel=%s", delivery.event_id, delivery.channel)
            db.commit()
            refresh_event_status(db, delivery.event_id)
    return counts


async def delivery_loop() -> None:
    """Background task (Site Server only): deliver queued alerts forever."""
    while True:
        try:
            await asyncio.to_thread(deliver_due_once)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("ALERT delivery pass failed: %s", exc)
        await asyncio.sleep(max(1.0, float(settings.alerts_poll_seconds or 5.0)))


def send_test(channel: str, to: str) -> dict[str, Any]:
    """Send a test message to one recipient right now (settings page)."""
    rec = normalize_recipient({"channel": channel, "to": to})
    text = "Zirp test alert: manual-open alerts are configured correctly for this recipient."
    try:
        if rec["channel"] == "sms":
            ref = send_sms(rec["to"], text)
        elif rec["channel"] == "email":
            ref = send_email(rec["to"], "[Zirp] Test alert", text)
        else:
            ref = send_webhook(rec["to"], {"type": "zirp.test", "text": text})
        return {"ok": True, "channel": rec["channel"], "result": ref}
    except Exception as exc:
        return {"ok": False, "channel": rec["channel"], "error": f"{type(exc).__name__}: {exc}"[:300]}


def provider_status() -> dict[str, bool]:
    return {
        "sms": bool(settings.alerts_africastalking_username and settings.alerts_africastalking_api_key),
        "email": bool(settings.alerts_smtp_host and (settings.alerts_smtp_from or settings.alerts_smtp_username)),
        "webhook": True,
        "webhook_signed": bool(settings.alerts_webhook_secret),
    }
