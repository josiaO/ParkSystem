"""Receipt identity, QR payload, and print-job state. No gates or OCR.

The parking session already exists before anything is printed. One opaque
public token is the QR identity. A short human reference is operator lookup
only and is never the authentication token.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable
from urllib.parse import unquote, urlparse
from uuid import uuid4

JOB_QUEUED = "QUEUED"
JOB_PRINTING = "PRINTING"
JOB_PRESENTED = "PRESENTED"
JOB_TAKEN = "TAKEN"
JOB_FAILED = "FAILED"
JOB_TIMED_OUT = "TIMED_OUT"
JOB_ASSISTANCE = "ASSISTANCE_REQUIRED"
JOB_OVERRIDE = "OPERATOR_OVERRIDE"

PRINT_JOB_STATES = (
    JOB_QUEUED, JOB_PRINTING, JOB_PRESENTED, JOB_TAKEN, JOB_FAILED,
    JOB_TIMED_OUT, JOB_ASSISTANCE, JOB_OVERRIDE,
)

CAP_PAPER_STATUS = "PAPER_STATUS"
CAP_PRESENTER = "PRESENTER"
CAP_TAKEN_SENSOR = "TAKEN_SENSOR"
CAP_CUTTER = "CUTTER"
CAP_RETRACT = "RETRACT"

# No 0/O/1/I so operators can read the short code aloud.
_HUMAN_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


class InvalidPrintJob(ValueError):
    """Illegal print-job jump or a retry that would create a second session."""


def new_public_token() -> str:
    """Cryptographically random opaque token. Not derived from plate or DB id."""
    return secrets.token_urlsafe(32)


def new_human_reference() -> str:
    """Short operator lookup such as 8Q7K-4M2P. Not the security token."""
    raw = "".join(secrets.choice(_HUMAN_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def new_print_job_id() -> str:
    return uuid4().hex


def normalize_human_reference(value: str | None) -> str:
    text = (value or "").strip().upper().replace(" ", "")
    if "-" not in text and len(text) == 8:
        text = f"{text[:4]}-{text[4:]}"
    allowed = set(_HUMAN_ALPHABET + "-")
    if not text or any(ch not in allowed for ch in text):
        return ""
    if len(text) != 9 or text[4] != "-":
        return ""
    return text


def session_qr_payload(token: str, *, base_url: str = "") -> str:
    """Locally parseable session QR. Token only — no plate, amount, or DB id."""
    token = (token or "").strip()
    if not token:
        return ""
    path = f"/s/{token}"
    base = (base_url or "").strip().rstrip("/")
    if base:
        return f"{base}{path}"
    return path


def extract_session_token(raw: str) -> str:
    """Pull the public token from a scanner string, `/s/` or `/p/` URL, or raw token."""
    text = (raw or "").strip().strip('"').strip("'")
    if not text:
        return ""
    if "://" in text or text.startswith("/"):
        parsed = urlparse(text if "://" in text else f"http://local{text}")
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        for marker in ("s", "p"):
            if marker in parts:
                idx = parts.index(marker)
                if idx + 1 < len(parts):
                    token = parts[idx + 1]
                    if token.lower() not in {
                        "qr.png", "status", "pay", "kiosk-pay", "snapshot.jpg", "crop.jpg",
                    }:
                        return token
        for bit in (parsed.query or "").split("&"):
            if bit.startswith("token="):
                return unquote(bit.split("=", 1)[1])
        return ""
    if "token=" in text:
        return unquote(text.split("token=", 1)[1].split("&", 1)[0].strip())
    if normalize_human_reference(text):
        return ""
    return text.split()[0]


def qr_exposes_secrets(payload: str, *, plate: str = "", session_id: int | None = None) -> bool:
    body = payload or ""
    if plate and plate.upper() in body.upper():
        return True
    if session_id is not None and str(session_id) in body.split("/"):
        return True
    return False


def free_period_line(rules: dict[str, Any] | None) -> str:
    """Tariff-configured free period. Empty rules → generic keep-receipt line."""
    rules = rules or {}
    seconds = int(rules.get("free_day_seconds") or rules.get("grace_seconds") or 0)
    if seconds <= 0:
        return "Keep this receipt. Charges follow the site tariff at the kiosk."
    minutes = max(1, seconds // 60)
    return f"Free period: first {minutes} minutes. Keep this receipt."


def _span(seconds: float) -> str:
    seconds = int(seconds)
    if seconds % 3600 == 0:
        hours = seconds // 3600
        return "hr" if hours == 1 else f"{hours}h"
    return f"{max(1, seconds // 60)}m"


TICKET_LANGUAGES = ("en", "sw", "both")

# key: (English, Swahili)
TICKET_TEXT = {
    "title": ("PARKING ENTRY TICKET", "TIKETI YA KUINGIA MAEGESHO"),
    "keep": ("KEEP THIS TICKET", "HIFADHI TIKETI HII"),
    "entry": ("Entry", "Kuingia"),
    "gate": ("Gate", "Geti"),
    "rate": ("Rate", "Ada"),
    "ref": ("Ref", "Kumb"),
    "how": ("HOW TO PAY", "JINSI YA KULIPA"),
    "pay": ("Scan the QR with your phone, or pay at the kiosk before you exit.",
            "Changanua QR kwa simu yako, au lipia kwenye kioski kabla ya kutoka."),
    "valid": ("Valid at any exit. If the camera cannot read your plate, scan the QR at the exit.",
              "Inatumika geti lolote la kutoka. Kamera isiposoma namba ya gari, changanua QR getini."),
    "plate_pending": ("Plate pending", "Namba haijasomwa"),
}


def ticket_language(value: str | None) -> str:
    value = str(value or "").strip().lower()
    return value if value in TICKET_LANGUAGES else "en"


def ticket_label(key: str, language: str) -> str:
    """Short label: one language, or both side by side ("Entry / Kuingia")."""
    en, sw = TICKET_TEXT[key]
    return {"en": en, "sw": sw}.get(ticket_language(language), f"{en} / {sw}")


def ticket_phrases(key: str, language: str) -> list[str]:
    """A sentence in the ticket language(s): one line each, English first."""
    en, sw = TICKET_TEXT[key]
    return {"en": [en], "sw": [sw]}.get(ticket_language(language), [en, sw])


def rate_line(rules: dict[str, Any] | None, language: str = "en") -> str:
    """Short tariff for the ticket, e.g. "45m free · TZS 1,000/hr" (sw: "dk 45 bure · TZS 1,000/saa")."""
    rules = rules or {}
    swahili = ticket_language(language) == "sw"
    parts = []
    free = int(rules.get("free_day_seconds") or rules.get("grace_seconds") or 0)
    if free > 0:
        parts.append(f"{_span_sw(free)} bure" if swahili else f"{_span(free)} free")
    try:
        fee, block = float(rules.get("day_block_fee") or 0), float(rules.get("day_block_seconds") or 0)
    except (TypeError, ValueError):
        fee, block = 0.0, 0.0
    if fee > 0 and block > 0:
        currency = str(rules.get("currency") or "TZS")
        unit = _span_sw(block, per=True) if swahili else _span(block)
        parts.append(f"{currency} {fee:,.0f}/{unit}")
    return " · ".join(parts)


def _span_sw(seconds: float, *, per: bool = False) -> str:
    seconds = int(seconds)
    if seconds % 3600 == 0:
        hours = seconds // 3600
        return "saa" if per and hours == 1 else f"saa {hours}"
    return f"dk {max(1, seconds // 60)}"


def plate_line(plate: str, *, plate_status: str = "") -> str:
    text = (plate or "").strip()
    status = (plate_status or "").upper()
    if not text or status in {"UNRESOLVED", "PENDING", "UNKNOWN"}:
        return "Plate pending"
    return text


def render_entry_receipt(
    *,
    site_name: str,
    plate: str,
    entry_time: str,
    entry_lane: str,
    human_reference: str,
    qr_payload: str,
    tariff_rules: dict[str, Any] | None = None,
    plate_status: str = "",
    language: str = "en",
) -> "ReceiptContent":
    language = ticket_language(language)
    shown_plate = plate_line(plate, plate_status=plate_status)
    if shown_plate == "Plate pending" and language == "sw":
        shown_plate = TICKET_TEXT["plate_pending"][1]
    free = free_period_line(tariff_rules)
    rate = rate_line(tariff_rules, language)
    lines = [
        site_name or "Parking Site",
        " · ".join(ticket_phrases("title", language)),
        " · ".join(ticket_phrases("keep", language)),
        "",
        shown_plate,
        "",
        f"{ticket_label('entry', language)}: {entry_time}",
        f"{ticket_label('gate', language)}: {entry_lane or '—'}",
        *([f"{ticket_label('rate', language)}: {rate}"] if rate else []),
        "",
        ticket_label("how", language),
        *ticket_phrases("pay", language),
        f"{ticket_label('ref', language)}: {human_reference}",
        "",
        *ticket_phrases("valid", language),
    ]
    return ReceiptContent(
        site_name=site_name or "SmartPark",
        plate=shown_plate,
        entry_time=entry_time,
        entry_lane=entry_lane or "",
        human_reference=human_reference,
        qr_payload=qr_payload,
        free_period=free,
        body_text="\n".join(lines) + "\n",
        lines=lines,
        rate=rate,
        language=language,
    )


@dataclass
class ReceiptContent:
    site_name: str
    plate: str
    entry_time: str
    entry_lane: str
    human_reference: str
    qr_payload: str
    free_period: str
    body_text: str
    lines: list[str] = field(default_factory=list)
    rate: str = ""
    language: str = "en"


@dataclass
class PrinterStatus:
    online: bool = True
    paper_ok: bool = True
    presented: bool = False
    taken: bool = False
    error: str = ""
    capabilities: frozenset[str] = field(default_factory=frozenset)

    def as_dict(self) -> dict[str, Any]:
        return {
            "online": self.online,
            "paper_ok": self.paper_ok,
            "presented": self.presented,
            "taken": self.taken,
            "error": self.error,
            "capabilities": sorted(self.capabilities),
        }


@dataclass
class PrintOutcome:
    ok: bool
    status: str
    error: str = ""
    path: str = ""
    simulated: bool = True
    adapter_id: str = ""


def allowed_job_targets(current: str) -> set[str]:
    current = current or JOB_QUEUED
    return {
        JOB_QUEUED: {JOB_PRINTING, JOB_FAILED},
        JOB_PRINTING: {JOB_PRESENTED, JOB_FAILED, JOB_ASSISTANCE},
        JOB_PRESENTED: {JOB_TAKEN, JOB_TIMED_OUT, JOB_ASSISTANCE, JOB_FAILED, JOB_PRINTING},
        JOB_FAILED: {JOB_QUEUED, JOB_PRINTING, JOB_ASSISTANCE},
        JOB_TIMED_OUT: {JOB_ASSISTANCE, JOB_OVERRIDE, JOB_PRINTING},
        JOB_ASSISTANCE: {JOB_OVERRIDE, JOB_PRINTING, JOB_QUEUED},
        JOB_OVERRIDE: {JOB_TAKEN, JOB_PRINTING},
        JOB_TAKEN: set(),
    }.get(current, set())


def apply_job_transition(current: str, target: str) -> str:
    current = current or JOB_QUEUED
    if current == target:
        return current
    if target not in allowed_job_targets(current):
        raise InvalidPrintJob(f"{current} -> {target} is not allowed")
    return target


@runtime_checkable
class ReceiptPrinterAdapter(Protocol):
    id: str
    capabilities: frozenset[str]

    async def print_entry_receipt(self, document: Any, *, job_id: str) -> PrintOutcome: ...

    async def get_status(self) -> PrinterStatus: ...

    async def wait_until_presented(self, *, timeout_seconds: float = 8.0) -> bool: ...

    async def wait_until_taken(self, *, timeout_seconds: float = 30.0) -> bool: ...

    async def cancel_or_recover(self) -> None: ...
