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
    assert lines[0] == "Harbour Park" and lines[4] == "T482ABC"
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


def _doc(language: str) -> ReceiptDocument:
    return ReceiptDocument(
        site_name="Harbour Park", plate="T482ABC", entry_time="18 Nov 2026 14:38", entry_gate="1# Entry",
        public_reference="8Q7K-4M2P", public_url="", payment_instructions="", body_text="", qr_payload="",
        rate="45m free · TZS 1,000/hr", language=language,
    )


def test_ticket_language_choice():
    sw = escpos_bytes(_doc("sw"))
    assert b"TIKETI YA KUINGIA MAEGESHO" in sw and b"JINSI YA KULIPA" in sw and b"HOW TO PAY" not in sw
    assert _row("Kuingia", "18 Nov 2026 14:38") in sw
    en = escpos_bytes(_doc("en"))
    assert b"PARKING ENTRY TICKET" in en and b"KUINGIA" not in en


def test_bilingual_ticket_puts_both_languages_side_by_side():
    both = escpos_bytes(_doc("both"))
    assert _row("Entry / Kuingia", "18 Nov 2026 14:38") in both
    assert b"HOW TO PAY / JINSI YA KULIPA" in both and b"KEEP THIS TICKET / HIFADHI TIKETI HII" in both
    assert b"Scan the QR with your phone" in both and b"Changanua QR kwa simu yako" in both
    assert b"REF / KUMB 8Q7K-4M2P" in both
    for line in both.split(b"\n"):
        text = line.split(b"\x1ba")[-1]
        if not text.startswith((b"\x1b", b"\x1d")):
            assert len(text) <= TICKET_COLUMNS + 2, text


def test_swahili_text_and_rate():
    content = render_entry_receipt(
        site_name="Harbour Park", plate="T482ABC", entry_time="18 Nov 2026 14:38", entry_lane="1#",
        human_reference="8Q7K-4M2P", qr_payload="x", language="sw",
        tariff_rules={"free_day_seconds": 2700, "day_block_fee": 1000, "day_block_seconds": 3600},
    )
    assert "Ada: dk 45 bure · TZS 1,000/saa" in content.lines and "JINSI YA KULIPA" in content.lines
    assert rate_line({"free_day_seconds": 7200}, "sw") == "saa 2 bure"
