"""Print jobs for an existing parking session. Does not open gates.

Retries keep the same session_id and print_job_id. Duplicate presented/taken
events are no-ops. Printer failure and never-taken timeout raise assistance
required; an operator override is audited and does not pulse a barrier.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.domain.parking_engine import LanePolicy, RECEIPT_PRESENTED, RECEIPT_PRINTING, RECEIPT_TAKEN
from app.domain.receipt_engine import (
    JOB_ASSISTANCE,
    JOB_FAILED,
    JOB_OVERRIDE,
    JOB_PRESENTED,
    JOB_PRINTING,
    JOB_QUEUED,
    JOB_TAKEN,
    JOB_TIMED_OUT,
    InvalidPrintJob,
    apply_job_transition,
    new_print_job_id,
    render_entry_receipt,
    session_qr_payload,
)
from app.infrastructure.hardware.printers import ReceiptDocument, qr_png_bytes
from app.infrastructure.hardware.receipt_printers import receipt_printer_for
from app.models import AuditLog, Gate, Lane, ParkingSession, Receipt, utcnow
from app.services.parking_sessions import advance
from app.services.receipts import resolve_public_base_url


TAKEN_TIMEOUT_SECONDS = 90.0


def _job_state(row: ParkingSession) -> str:
    return (row.print_job_status or JOB_QUEUED) or JOB_QUEUED


def _set_job(row: ParkingSession, target: str) -> None:
    row.print_job_status = apply_job_transition(_job_state(row), target)
    row.updated_at = utcnow()


def _lane_name(db: Session, row: ParkingSession) -> str:
    if row.entry_lane_id:
        lane = db.get(Lane, row.entry_lane_id)
        if lane is not None:
            return lane.name
    if row.gate_id:
        gate = db.get(Gate, row.gate_id)
        if gate is not None:
            return gate.name
    return row.lane_direction or ""


def _document_for(db: Session, row: ParkingSession) -> ReceiptDocument:
    when = (row.entry_time or utcnow()).strftime("%d %b %Y %H:%M")
    token = row.public_token or ""
    qr_payload = session_qr_payload(token, base_url=resolve_public_base_url(db))
    content = render_entry_receipt(
        site_name=settings.site_name or settings.app_name,
        plate=row.plate,
        entry_time=when,
        entry_lane=_lane_name(db, row),
        human_reference=row.human_reference or "",
        qr_payload=qr_payload,
        tariff_rules=row.tariff_rules if isinstance(row.tariff_rules, dict) else None,
        plate_status=row.plate_status,
    )
    qr_png = qr_png_bytes(content.qr_payload)
    return ReceiptDocument(
        site_name=content.site_name,
        plate=content.plate,
        entry_time=content.entry_time,
        entry_gate=content.entry_lane,
        public_reference=content.human_reference,
        public_url=content.qr_payload,
        payment_instructions=content.free_period,
        body_text=content.body_text,
        qr_payload=content.qr_payload,
        qr_png=qr_png,
        lines=content.lines,
    )


def _record_receipt(db: Session, row: ParkingSession, document: ReceiptDocument, outcome, *, job_id: str) -> Receipt:
    existing = db.scalar(select(Receipt).where(Receipt.print_job_id == job_id)) if job_id else None
    if existing is not None:
        existing.status = outcome.status
        existing.printer_error = outcome.error
        existing.printer_adapter = outcome.adapter_id or existing.printer_adapter
        existing.retry_count = int(row.print_retry_count or 0)
        existing.body_text = document.body_text
        existing.qr_payload = document.qr_payload
        existing.payload = {**(existing.payload or {}), "path": outcome.path, "simulated": outcome.simulated}
        return existing
    record = Receipt(
        session_id=row.id,
        plate=row.plate,
        public_token=row.public_token or "",
        body_text=document.body_text,
        qr_payload=document.qr_payload,
        printer_adapter=outcome.adapter_id or "simulated_kiosk",
        status=outcome.status,
        print_job_id=job_id,
        retry_count=int(row.print_retry_count or 0),
        printer_error=outcome.error,
        payload={"path": outcome.path, "simulated": outcome.simulated, "human_reference": row.human_reference},
    )
    db.add(record)
    return record


async def print_entry_receipt(
    db: Session,
    row: ParkingSession,
    *,
    printer=None,
    policy: LanePolicy | None = None,
) -> dict[str, Any]:
    """Print for an existing session. Never creates a second session."""
    policy = policy or LanePolicy(receipt_required_before_open=True)
    printer = printer or receipt_printer_for()
    if _job_state(row) == JOB_TAKEN:
        return {"session_id": row.id, "print_job_id": row.print_job_id, "status": JOB_TAKEN, "created_session": False}
    first = not row.print_job_id
    if first:
        row.print_job_id = new_print_job_id()
        row.print_retry_count = 0
        row.print_job_status = JOB_QUEUED
    else:
        row.print_retry_count = int(row.print_retry_count or 0) + 1
    if _job_state(row) == JOB_FAILED:
        _set_job(row, JOB_QUEUED)
    if _job_state(row) != JOB_PRINTING:
        _set_job(row, JOB_PRINTING)
    row.receipt_status = "PRINTING"
    if first and policy.receipt_required_before_open:
        current = row.lifecycle or ""
        if current in {"SESSION_CREATED", ""}:
            try:
                advance(db, row, RECEIPT_PRINTING, policy=policy)
            except Exception:
                pass
    document = _document_for(db, row)
    outcome = await printer.print_entry_receipt(document, job_id=row.print_job_id)
    _record_receipt(db, row, document, outcome, job_id=row.print_job_id)
    if not outcome.ok:
        row.printer_error = outcome.error
        _set_job(row, JOB_FAILED)
        _set_job(row, JOB_ASSISTANCE)
        row.receipt_status = "FAILED"
        db.commit()
        db.refresh(row)
        return {
            "session_id": row.id,
            "print_job_id": row.print_job_id,
            "status": JOB_ASSISTANCE,
            "error": outcome.error,
            "created_session": False,
            "assistance_required": True,
        }
    row.printer_error = ""
    _set_job(row, JOB_PRESENTED)
    row.receipt_status = "PRINTED"
    row.receipt_printed_at = row.receipt_printed_at or utcnow()
    try:
        advance(db, row, RECEIPT_PRESENTED, policy=policy)
    except Exception:
        row.lifecycle = RECEIPT_PRESENTED
    db.commit()
    db.refresh(row)
    return {
        "session_id": row.id,
        "print_job_id": row.print_job_id,
        "status": JOB_PRESENTED,
        "qr_payload": document.qr_payload,
        "human_reference": row.human_reference,
        "created_session": False,
        "assistance_required": False,
        "path": outcome.path,
    }


async def mark_receipt_presented(db: Session, row: ParkingSession, *, policy: LanePolicy | None = None) -> ParkingSession:
    if _job_state(row) == JOB_PRESENTED:
        return row
    _set_job(row, JOB_PRESENTED)
    row.receipt_status = "PRINTED"
    row.receipt_printed_at = row.receipt_printed_at or utcnow()
    try:
        advance(db, row, RECEIPT_PRESENTED, policy=policy or LanePolicy(receipt_required_before_open=True))
    except Exception:
        pass
    db.commit()
    db.refresh(row)
    return row


async def mark_receipt_taken(
    db: Session,
    row: ParkingSession,
    *,
    printer=None,
    policy: LanePolicy | None = None,
) -> ParkingSession:
    if _job_state(row) == JOB_TAKEN:
        return row
    if printer is not None and hasattr(printer, "simulate_taken"):
        printer.simulate_taken()
        requires_sensor = bool((policy or LanePolicy(receipt_required_before_open=True)).receipt_required_before_open)
        if requires_sensor:
            try:
                await printer.wait_until_taken(timeout_seconds=0.1)
            except TimeoutError as exc:
                raise InvalidPrintJob(str(exc)) from exc
    _set_job(row, JOB_TAKEN)
    row.receipt_status = "TAKEN"
    row.receipt_taken_at = row.receipt_taken_at or utcnow()
    from app.services.parking_sessions import mark_receipt_taken as persist_taken
    persist_taken(db, row, policy=policy or LanePolicy(receipt_required_before_open=True))
    db.commit()
    db.refresh(row)
    return row


def expire_if_not_taken(
    db: Session,
    row: ParkingSession,
    *,
    now: datetime | None = None,
    timeout_seconds: float = TAKEN_TIMEOUT_SECONDS,
) -> ParkingSession:
    if _job_state(row) in {JOB_TAKEN, JOB_OVERRIDE}:
        return row
    if _job_state(row) != JOB_PRESENTED:
        return row
    now = now or datetime.now(timezone.utc)
    presented = row.receipt_printed_at
    if presented is None:
        return row
    if presented.tzinfo is None:
        presented = presented.replace(tzinfo=timezone.utc)
    if now - presented < timedelta(seconds=float(timeout_seconds)):
        return row
    _set_job(row, JOB_TIMED_OUT)
    _set_job(row, JOB_ASSISTANCE)
    row.printer_error = "receipt never taken"
    db.commit()
    db.refresh(row)
    return row


def operator_override(
    db: Session,
    row: ParkingSession,
    *,
    reason: str,
    user_id: int | None = None,
) -> ParkingSession:
    """Audited exception. Does not open the gate."""
    if _job_state(row) != JOB_OVERRIDE:
        if _job_state(row) in {JOB_PRESENTED, JOB_FAILED, JOB_TIMED_OUT}:
            try:
                _set_job(row, JOB_ASSISTANCE)
            except InvalidPrintJob:
                pass
        if _job_state(row) != JOB_OVERRIDE:
            _set_job(row, JOB_OVERRIDE)
    row.receipt_status = "OVERRIDE"
    db.add(AuditLog(
        user_id=user_id,
        action="RECEIPT_OPERATOR_OVERRIDE",
        target_type="parking_session",
        target_id=str(row.id),
        detail=(reason or "operator override")[:240],
    ))
    db.commit()
    db.refresh(row)
    return row
