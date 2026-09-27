"""Printable parking, money, and plate-accuracy reports for a date range."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    GateCommandRecord,
    ParkingSession,
    PaymentTransaction,
    RegisteredVehicle,
    User,
    VehicleCapture,
)
from app.services.kiosk_lookup import format_stay
from app.services.simulation import OPEN_STATUSES


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def default_range(now: datetime | None = None) -> tuple[datetime, datetime]:
    end = _aware(now or datetime.now(timezone.utc))
    start = end.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, end


def parse_range(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    default_start, default_end = default_range()
    start_at = _aware(start) if start else default_start
    end_at = _aware(end) if end else default_end
    if end_at < start_at:
        start_at, end_at = end_at, start_at
    # A date-only end lands at midnight; include that whole day.
    if end and end.hour == 0 and end.minute == 0 and end.second == 0 and end.microsecond == 0:
        end_at = end_at + timedelta(days=1)
    return start_at, end_at


def _money(amount: float, currency: str) -> str:
    return f"{currency} {amount:,.0f}"


def report_summary(db: Session, start: datetime | None = None, end: datetime | None = None) -> dict:
    start_at, end_at = parse_range(start, end)
    currency = "TZS"
    sample = db.scalar(select(ParkingSession.currency).where(ParkingSession.currency != "").limit(1))
    if sample:
        currency = sample

    entries = db.scalar(
        select(func.count(ParkingSession.id)).where(
            ParkingSession.entry_time >= start_at,
            ParkingSession.entry_time < end_at,
        )
    ) or 0
    exits = db.scalar(
        select(func.count(ParkingSession.id)).where(
            ParkingSession.exit_time >= start_at,
            ParkingSession.exit_time < end_at,
        )
    ) or 0
    still_inside = db.scalar(
        select(func.count(ParkingSession.id)).where(ParkingSession.status.in_(tuple(OPEN_STATUSES)))
    ) or 0
    unpaid = db.scalar(
        select(func.count(ParkingSession.id)).where(
            ParkingSession.status.in_(tuple(OPEN_STATUSES)),
            ParkingSession.parker_kind == "CASUAL",
            ParkingSession.amount_due > ParkingSession.amount_paid,
        )
    ) or 0

    paid_rows = db.execute(
        select(PaymentTransaction.method, func.count(PaymentTransaction.id), func.coalesce(func.sum(PaymentTransaction.amount), 0))
        .where(
            PaymentTransaction.status == "SUCCEEDED",
            PaymentTransaction.confirmed_at >= start_at,
            PaymentTransaction.confirmed_at < end_at,
        )
        .group_by(PaymentTransaction.method)
    ).all()
    by_method = []
    collected = 0.0
    for method, count, amount in paid_rows:
        value = float(amount or 0)
        collected += value
        by_method.append({
            "method": method or "UNKNOWN",
            "count": int(count or 0),
            "amount": value,
            "label": _money(value, currency),
        })

    payments = [
        {
            "when": row.confirmed_at.isoformat() if row.confirmed_at else "",
            "session_id": row.session_id,
            "method": row.method,
            "amount": float(row.amount or 0),
            "currency": row.currency or currency,
            "status": row.status,
        }
        for row in db.scalars(
            select(PaymentTransaction)
            .where(
                PaymentTransaction.confirmed_at >= start_at,
                PaymentTransaction.confirmed_at < end_at,
            )
            .order_by(PaymentTransaction.id.desc())
            .limit(500)
        ).all()
    ]

    stays = []
    for row in db.scalars(
        select(ParkingSession).where(
            ParkingSession.exit_time >= start_at,
            ParkingSession.exit_time < end_at,
            ParkingSession.entry_time.is_not(None),
        )
    ).all():
        start = row.entry_time
        finish = row.exit_time
        if start is None or finish is None:
            continue
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if finish.tzinfo is None:
            finish = finish.replace(tzinfo=timezone.utc)
        stays.append(max(0, int((finish - start).total_seconds())))
    average_stay = int(sum(stays) / len(stays)) if stays else 0
    free_exits = db.scalar(
        select(func.count(ParkingSession.id)).where(
            ParkingSession.exit_time >= start_at,
            ParkingSession.exit_time < end_at,
            ParkingSession.amount_due <= 0,
            ParkingSession.parker_kind == "CASUAL",
        )
    ) or 0

    users = {row.id: row.username for row in db.scalars(select(User)).all()}
    operator_totals: dict[str, dict] = defaultdict(lambda: {"count": 0, "amount": 0.0})
    day_totals: dict[str, dict] = defaultdict(lambda: {"count": 0, "amount": 0.0})
    for row in db.scalars(
        select(PaymentTransaction).where(
            PaymentTransaction.status == "SUCCEEDED",
            PaymentTransaction.confirmed_at >= start_at,
            PaymentTransaction.confirmed_at < end_at,
        )
    ).all():
        name = users.get(row.operator_id) or "No operator (phone or system)"
        operator_totals[name]["count"] += 1
        operator_totals[name]["amount"] += float(row.amount or 0)
        if row.confirmed_at:
            stamp = row.confirmed_at.astimezone(timezone.utc).date().isoformat()
            day_totals[stamp]["count"] += 1
            day_totals[stamp]["amount"] += float(row.amount or 0)

    outstanding_rows = []
    for row in db.scalars(
        select(ParkingSession)
        .where(ParkingSession.status.in_(tuple(OPEN_STATUSES)))
        .order_by(ParkingSession.entry_time)
    ).all():
        due = float(row.amount_due or 0)
        paid = float(row.amount_paid or 0)
        remaining = max(0.0, due - paid)
        if row.parker_kind != "CASUAL" and remaining <= 0:
            continue
        start = row.entry_time
        if start and start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        seconds = int((datetime.now(timezone.utc) - start).total_seconds()) if start else 0
        outstanding_rows.append({
            "plate": row.plate,
            "kind": row.parker_kind or "CASUAL",
            "since": row.entry_time.isoformat() if row.entry_time else "",
            "stay": format_stay(seconds),
            "due": due,
            "paid": paid,
            "remaining": remaining,
            "note": "Fee still open" if remaining > 0 else "Inside — fee not closed yet",
        })

    accuracy = _accuracy(db, start_at, end_at)
    exceptions = _exceptions(db, start_at, end_at)
    seasons = _seasons(db)

    sections = [
        {
            "title": "Visits",
            "rows": [
                {"label": "Cars entered", "value": str(int(entries))},
                {"label": "Cars exited", "value": str(int(exits))},
                {"label": "Still inside now", "value": str(int(still_inside))},
                {"label": "Casual visits still unpaid", "value": str(int(unpaid))},
                {"label": "Average stay of cars that left", "value": format_stay(average_stay) if stays else "—"},
                {"label": "Casual exits with no fee", "value": str(int(free_exits))},
            ],
        },
        {
            "title": "Money collected",
            "rows": [{"label": "Total", "value": _money(collected, currency)}] + [
                {"label": item["method"].replace("_", " ").title(), "value": f"{item['count']} payments · {item['label']}"}
                for item in by_method
            ],
        },
        {
            "title": "Plate reading",
            "rows": accuracy["summary_rows"],
        },
    ]
    reports = [
        _sheet("overview", "Overview", [], [], sections),
        _sheet("payments", "Payments", [
            {"key": "when", "label": "When"},
            {"key": "session_id", "label": "Session"},
            {"key": "method", "label": "Method"},
            {"key": "amount", "label": "Amount"},
            {"key": "currency", "label": "Currency"},
            {"key": "status", "label": "Status"},
        ], payments),
        _sheet("outstanding", "Cars still inside or owing", [
            {"key": "plate", "label": "Plate"},
            {"key": "kind", "label": "Kind"},
            {"key": "since", "label": "Entered"},
            {"key": "stay", "label": "Time inside"},
            {"key": "due", "label": "Due"},
            {"key": "paid", "label": "Paid"},
            {"key": "remaining", "label": "Still to pay"},
            {"key": "note", "label": "Note"},
        ], outstanding_rows),
        _sheet("daily", "Takings by day", [
            {"key": "day", "label": "Day"},
            {"key": "count", "label": "Payments"},
            {"key": "amount", "label": "Amount"},
        ], [
            {"day": day, "count": bucket["count"], "amount": round(bucket["amount"], 2)}
            for day, bucket in sorted(day_totals.items())
        ]),
        _sheet("operators", "Cash by operator", [
            {"key": "operator", "label": "Operator"},
            {"key": "count", "label": "Payments"},
            {"key": "amount", "label": "Amount"},
        ], [
            {"operator": name, "count": bucket["count"], "amount": round(bucket["amount"], 2)}
            for name, bucket in sorted(operator_totals.items())
        ]),
        _sheet("accuracy", "Plate reading accuracy", [
            {"key": "label", "label": "Measure"},
            {"key": "value", "label": "Value"},
        ], [{"label": row["label"], "value": row["value"]} for row in accuracy["summary_rows"]]),
        _sheet("exceptions", "Manual actions and plate corrections", [
            {"key": "when", "label": "When"},
            {"key": "action", "label": "Action"},
            {"key": "detail", "label": "Detail"},
        ], exceptions),
        _sheet("seasons", "Season and registered plates", [
            {"key": "plate", "label": "Plate"},
            {"key": "owner", "label": "Owner"},
            {"key": "plan", "label": "Plan"},
            {"key": "valid_from", "label": "Starts"},
            {"key": "valid_until", "label": "Ends"},
            {"key": "state", "label": "State"},
        ], seasons),
    ]
    return {
        "ok": True,
        "currency": currency,
        "start": start_at.isoformat(),
        "end": end_at.isoformat(),
        "entries": int(entries),
        "exits": int(exits),
        "still_inside": int(still_inside),
        "unpaid_casual": int(unpaid),
        "average_stay_seconds": average_stay,
        "collected": collected,
        "collected_label": _money(collected, currency),
        "by_method": by_method,
        "payments": payments,
        "sections": sections,
        "reports": reports,
        "accuracy": accuracy["rates"],
    }


def _sheet(report_id: str, title: str, columns: list[dict], rows: list[dict], sections: list | None = None) -> dict:
    return {
        "id": report_id,
        "title": title,
        "columns": columns,
        "rows": rows,
        "sections": sections or [],
    }


def _accuracy(db: Session, start_at: datetime, end_at: datetime) -> dict:
    reads = 0
    both = 0
    agreed = 0
    disagreed = 0
    corrected = 0
    held = 0
    for row in db.scalars(
        select(VehicleCapture).where(
            VehicleCapture.created_at >= start_at,
            VehicleCapture.created_at < end_at,
        )
    ).all():
        reads += 1
        box = row.bbox if isinstance(row.bbox, dict) else {}
        fusion = box.get("fusion") if isinstance(box.get("fusion"), dict) else {}
        native = str(fusion.get("native_plate") or box.get("native_plate") or "").strip().upper()
        local = str(fusion.get("local_plate") or box.get("local_plate") or "").strip().upper()
        if box.get("operator_plate"):
            corrected += 1
        if box.get("needs_review") or box.get("pending_confirmation"):
            held += 1
        if native and local:
            both += 1
            if native == local:
                agreed += 1
            else:
                disagreed += 1
        elif fusion.get("disagreed"):
            disagreed += 1
    agreement = f"{round(100 * agreed / both)}% of {both}" if both else "No paired reads in this period"
    correction = f"{corrected} of {reads}" if reads else "No reads in this period"
    rows = [
        {"label": "Camera reads stored", "value": str(reads)},
        {"label": "Native and local agreed", "value": agreement},
        {"label": "Reads that disagreed", "value": str(disagreed)},
        {"label": "Operator corrections", "value": correction},
        {"label": "Still waiting for a person to confirm", "value": str(held)},
    ]
    return {
        "summary_rows": rows,
        "rates": {
            "reads": reads,
            "paired": both,
            "agreed": agreed,
            "disagreed": disagreed,
            "corrected": corrected,
            "held": held,
        },
    }


def _exceptions(db: Session, start_at: datetime, end_at: datetime) -> list[dict]:
    rows = []
    for row in db.scalars(
        select(AuditLog)
        .where(
            AuditLog.created_at >= start_at,
            AuditLog.created_at < end_at,
            AuditLog.action.in_(("plate.correct", "barrier.open", "payments.create")),
        )
        .order_by(AuditLog.id.desc())
        .limit(300)
    ).all():
        rows.append({
            "when": row.created_at.isoformat() if row.created_at else "",
            "action": row.action,
            "detail": row.detail or row.target_id or "",
        })
    for row in db.scalars(
        select(GateCommandRecord)
        .where(
            GateCommandRecord.created_at >= start_at,
            GateCommandRecord.created_at < end_at,
            GateCommandRecord.automatic.is_(False),
        )
        .order_by(GateCommandRecord.id.desc())
        .limit(200)
    ).all():
        rows.append({
            "when": row.created_at.isoformat() if row.created_at else "",
            "action": "manual barrier",
            "detail": row.reason or row.message or "",
        })
    rows.sort(key=lambda item: item["when"], reverse=True)
    return rows[:300]


def _seasons(db: Session) -> list[dict]:
    now = datetime.now(timezone.utc)
    soon = now + timedelta(days=14)
    listed = []
    for row in db.scalars(select(RegisteredVehicle).order_by(RegisteredVehicle.plate)).all():
        until = row.valid_until
        if until and until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        if until is None:
            state = "No end date"
        elif until < now:
            state = "Expired"
        elif until <= soon:
            state = "Ends within 14 days"
        else:
            state = "Active"
        listed.append({
            "plate": row.plate,
            "owner": row.owner_name or "",
            "plan": row.plan.name if row.plan else "",
            "valid_from": row.valid_from.date().isoformat() if row.valid_from else "",
            "valid_until": until.date().isoformat() if until else "",
            "state": state,
        })
    return listed


def report_by_id(summary: dict, kind: str) -> dict:
    wanted = (kind or "payments").strip().lower()
    for report in summary.get("reports") or []:
        if report.get("id") == wanted:
            return report
    raise KeyError(wanted)


def table_csv(report: dict) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    if report.get("sections") and not report.get("columns"):
        writer.writerow(["section", "label", "value"])
        for section in report["sections"]:
            for row in section.get("rows") or []:
                writer.writerow([section.get("title") or "", row.get("label") or "", row.get("value") or ""])
        return buffer.getvalue()
    columns = report.get("columns") or []
    writer.writerow([column["label"] for column in columns])
    for row in report.get("rows") or []:
        writer.writerow([row.get(column["key"], "") for column in columns])
    return buffer.getvalue()


def report_csv(summary: dict) -> str:
    return table_csv(report_by_id(summary, "payments"))
