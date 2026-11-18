"""80 mm entry ticket: big plate, entry facts, a short rate, the pay QR and the reference."""

from __future__ import annotations

from app.domain.receipt_engine import rate_line, render_entry_receipt
from app.infrastructure.hardware.printers import TICKET_COLUMNS, ReceiptDocument, _row, escpos_bytes


def test_rate_line_is_short():
    rules = {"free_day_seconds": 2700, "day_block_fee": 1000, "day_block_seconds": 3600, "currency": "TZS"}
    assert rate_line(rules) == "45m free · TZS 1,000/hr"
    assert rate_line({"day_block_fee": 500, "day_block_seconds": 1800}) == "TZS 500/30m"
    assert rate_line({}) == ""


def test_ticket_text_order():
    content = render_entry_receipt(
        site_name="Harbour Park", plate="T482ABC", entry_time="18 Nov 2026 14:38", entry_lane="1# Entry",
        human_reference="8Q7K-4M2P", qr_payload="http://x/s/tok",
        tariff_rules={"free_day_seconds": 2700, "day_block_fee": 1000, "day_block_seconds": 3600},
    )
    lines = content.lines
    assert lines[0] == "Harbour Park" and lines[3] == "T482ABC"
    assert lines.index("Entry: 18 Nov 2026 14:38") < lines.index("Gate: 1# Entry") < lines.index("Rate: 45m free · TZS 1,000/hr")
    assert "HOW TO PAY" in lines and "Ref: 8Q7K-4M2P" in lines
    assert content.rate == "45m free · TZS 1,000/hr"


def test_thermal_ticket_layout():
    document = ReceiptDocument(
        site_name="Harbour Park", plate="T482ABC", entry_time="18 Nov 2026 14:38", entry_gate="1# Entry",
        public_reference="8Q7K-4M2P", public_url="", payment_instructions="", body_text="", qr_payload="",
        rate="45m free · TZS 1,000/hr",
    )
    data = escpos_bytes(document)
    assert b"\x1d!\x11T 482 ABC\n" in data                       # double-size, spaced plate
    assert _row("Entry", "18 Nov 2026 14:38") in data
    assert b"45m free - TZS 1,000/hr\n" in data                   # ASCII separator on paper
    assert b"REF 8Q7K-4M2P" in data and data.endswith(b"\x1dV\x00")
    assert len(_row("Gate", "1# Entry")) == TICKET_COLUMNS + 1
