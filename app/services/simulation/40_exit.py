from __future__ import annotations

def quote_session(
    db: Session,
    row: ParkingSession,
    *,
    at: datetime | None = None,
    persist: bool = True,
) -> dict:
    at = at or datetime.now(timezone.utc)
    rules = normalize_tariff_rules(row.tariff_rules, car_type=row.car_type or "Car1") if row.tariff_rules else load_active_rules(
        db, row.car_type or "Car1", site_id=(row.site_id or DEFAULT_SITE_ID)
    )
    fee = calculate_car1_fee(row.entry_time, at, rules)
    row.amount_due = fee.due
    row.breakdown = list(fee.breakdown or [])
    row.currency = fee.currency
    if persist:
        db.commit()
    return fee.__dict__

def mark_paid(
    db: Session,
    row: ParkingSession,
    *,
    operator_id: int | None = None,
    method: str = "KIOSK_CASH",
) -> ParkingSession:
    quote_session(db, row)
    due = float(row.amount_due or 0)
    paid = float(row.amount_paid or 0)
    remaining = max(0.0, due - paid)
    if remaining <= 0.0001:
        raise ValueError("This vehicle does not have a fee to pay")
    recorded = record_succeeded_payment(
        db,
        row,
        amount=remaining,
        method=method,
        provider_id="kiosk_manual",
        operator_id=operator_id,
        idempotency_key=f"session:{row.id}:settle",
    )
    cfg = parking_settings(db)
    apply_from_ledger = recorded["session"]
    from app.infrastructure.payments.ledger import apply_session_payment_state
    apply_session_payment_state(
        db, apply_from_ledger, grace_seconds=int(cfg.get("payment_exit_grace_seconds") or 15 * 60),
    )
    db.commit()
    db.refresh(apply_from_ledger)
    return apply_from_ledger
