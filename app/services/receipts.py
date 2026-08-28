"""Issue printer-ready receipts. Paper device is optional; the slip is always stored."""

from __future__ import annotations

from io import BytesIO

from sqlalchemy.orm import Session

from app.config import settings
from app.infrastructure.hardware.printers import ReceiptDocument, printer_adapter
from app.models import Gate, ParkingSession, Receipt, utcnow


RECEIPT_POLICIES = (
    "OFF",
    "PRINT_OPTIONAL",
    "PRINT_AND_OPEN",
    "REQUIRE_TAKEN_BEFORE_OPEN",
)


def resolve_receipt_policy(cfg: dict) -> str:
    policy = str(cfg.get("receipt_policy") or "").strip().upper()
    if policy in RECEIPT_POLICIES:
        return policy
    if cfg.get("receipt_required_before_open") is True:
        return "REQUIRE_TAKEN_BEFORE_OPEN"
    return "PRINT_AND_OPEN"


def policy_requires_taken(policy: str) -> bool:
    return policy == "REQUIRE_TAKEN_BEFORE_OPEN"


def policy_should_print(policy: str) -> bool:
    return policy != "OFF"


def _qr_png(payload: str) -> bytes:
    if not payload:
        return b""
    try:
        import qrcode
    except Exception:
        return b""
    image = qrcode.make(payload)
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def build_document(row: ParkingSession, *, gate: Gate | None, public_url: str) -> ReceiptDocument:
    when = (row.entry_time or utcnow()).strftime("%d %b %Y %H:%M")
    gate_name = gate.name if gate else (row.lane_direction or "")
    token = row.public_token or ""
    site = settings.site_name or settings.app_name
    lines = [
        site,
        "PARKING ENTRY",
        "",
        f"Plate: {row.plate}",
        f"Entry: {when}",
        f"Gate: {gate_name}",
        f"Reference: {token}",
        "",
        "Scan the QR to check parking time,",
        "amount and payment options.",
        "",
        "You can also pay at the kiosk.",
        "Lost paper is OK — the plate is the identity.",
        public_url,
    ]
    body = "\n".join(lines) + "\n"
    qr_png = _qr_png(public_url or token)
    return ReceiptDocument(
        site_name=settings.site_name or settings.app_name,
        plate=row.plate,
        entry_time=when,
        entry_gate=gate_name,
        public_reference=token,
        public_url=public_url,
        payment_instructions="Scan to check parking time, amount and payment options. You can also pay at the kiosk.",
        body_text=body,
        qr_payload=public_url or token,
        qr_png=qr_png,
        lines=lines,
    )


def receipt_dict(row: Receipt) -> dict:
    return {
        "id": row.id,
        "session_id": row.session_id,
        "plate": row.plate,
        "public_token": row.public_token,
        "body_text": row.body_text,
        "qr_payload": row.qr_payload,
        "qr_url": f"/p/{row.public_token}/qr.png" if row.public_token else None,
        "printer_adapter": row.printer_adapter,
        "status": row.status,
        "payload": row.payload or {},
        "slip_path": (row.payload or {}).get("path") or "",
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def issue_receipt(
    db: Session,
    row: ParkingSession,
    *,
    gate: Gate | None,
    adapter_id: str | None = None,
    printer_name: str | None = None,
) -> dict:
    token = row.public_token or ""
    public_url = f"/p/{token}" if token else ""
    document = build_document(row, gate=gate, public_url=public_url)
    adapter = printer_adapter(adapter_id, printer_name=printer_name)
    try:
        printed = await adapter.print_receipt(document)
    except Exception as exc:
        from app.infrastructure.hardware.printers import PrintResult, store_slip_files
        path = store_slip_files(document)
        printed = PrintResult(
            ok=True, adapter_id=getattr(adapter, "id", "simulated"), status="READY",
            message=f"Receipt stored at {path} ({exc})", simulated=True, path=path,
        )
    qr_path = ""
    if document.qr_png:
        folder = settings.media_dir / "receipts"
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / f"{token or row.plate}.png"
        dest.write_bytes(document.qr_png)
        qr_path = str(dest)
    record = Receipt(
        session_id=row.id,
        plate=row.plate,
        public_token=token,
        body_text=document.body_text,
        qr_payload=document.qr_payload,
        qr_path=qr_path,
        printer_adapter=printed.adapter_id,
        status=printed.status,
        payload={
            "site_name": document.site_name,
            "entry_time": document.entry_time,
            "entry_gate": document.entry_gate,
            "public_url": document.public_url,
            "message": printed.message,
            "simulated": printed.simulated,
            "path": printed.path,
        },
    )
    db.add(record)
    if printed.ok and row.receipt_status in {"", "NONE"}:
        row.receipt_status = "PRINTED"
    db.commit()
    db.refresh(record)
    return {
        "receipt": document.body_text,
        "receipt_record": receipt_dict(record),
        "print": printed.__dict__,
        "qr_payload": document.qr_payload,
        "qr_url": f"/p/{token}/qr.png" if token else None,
    }
