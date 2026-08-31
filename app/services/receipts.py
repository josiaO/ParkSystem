"""Issue printer-ready receipts. Paper device is optional; the slip is always stored."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import settings
from app.infrastructure.hardware.printers import ReceiptDocument, printer_adapter, qr_png_bytes
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


def public_receipt_url(token: str, *, base_url: str | None = None) -> str:
    """Absolute URL encoded in receipt QR codes (phones must reach this host)."""
    token = (token or "").strip()
    path = f"/p/{token}" if token else ""
    base = (base_url or settings.public_base_url or "").strip().rstrip("/")
    if base:
        return f"{base}{path}"
    host = (settings.api_host or "127.0.0.1").strip()
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    port = int(settings.api_port or 8760)
    default_port = 443 if str(port) == "443" else (80 if str(port) == "80" else port)
    if (default_port == 443 and str(port) == "443") or (default_port == 80 and str(port) == "80"):
        return f"http://{host}{path}"
    return f"http://{host}:{port}{path}"


def resolve_public_base_url(db: Session | None = None) -> str:
    base = (settings.public_base_url or "").strip().rstrip("/")
    if base:
        return base
    if db is not None:
        from app.services.site_policy import site_policy
        policy = site_policy(db)
        base = str(policy.get("public_base_url") or "").strip().rstrip("/")
        if base:
            return base
    return ""


def _qr_png(payload: str) -> bytes:
    return qr_png_bytes(payload)


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
        "Scan the QR code to check parking time,",
        "amount and payment options.",
        "",
        "You can also pay at the kiosk.",
        "Lost paper is OK — the plate is the identity.",
    ]
    if public_url:
        lines.append(public_url)
    body = "\n".join(lines) + "\n"
    qr_target = public_url or token
    qr_png = _qr_png(qr_target)
    return ReceiptDocument(
        site_name=settings.site_name or settings.app_name,
        plate=row.plate,
        entry_time=when,
        entry_gate=gate_name,
        public_reference=token,
        public_url=public_url,
        payment_instructions="Scan the QR code for parking time, amount and payment options. You can also pay at the kiosk.",
        body_text=body,
        qr_payload=qr_target,
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
    public_url = public_receipt_url(token, base_url=resolve_public_base_url(db))
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
