"""The entry ticket carries what the old gate ticket did, the Zirp way.

ParkWatch's ticket (Park.exe, the "Print..." handler at 0x4e53f0, printed via
the entry board) held: the operator lines [Card] Custom1..3 (website, e-mail),
the entry date-time, and a barcode plus text of a random ticket number that
was the only key to the visit. Zirp keys the visit on the plate, so its ticket
keeps plate/time/lane/QR and adds the operator lines and a CODE128 barcode of
the session reference, which the kiosk lookup accepts.
"""

from __future__ import annotations

from app.domain.receipt_engine import normalize_human_reference, render_entry_receipt, ticket_header_lines
from app.infrastructure.hardware.printers import ReceiptDocument, escpos_bytes, escpos_code128


def test_operator_header_lines_come_from_settings_text():
    assert ticket_header_lines("www.hubtrackiottech.com| info@hubtrackiottech.com ||") == [
        "www.hubtrackiottech.com", "info@hubtrackiottech.com"]
    assert ticket_header_lines("") == []
    assert len(ticket_header_lines("a|b|c|d")) == 3          # Custom1..3


def test_ticket_text_carries_header_and_entry_details():
    content = render_entry_receipt(
        site_name="Mlimani City", plate="T123ABC", entry_time="18 Nov 2026 14:05 EAT",
        entry_lane="1#", human_reference="8Q7K-4M2P", qr_payload="http://x/s/tok",
        header_lines=["www.hubtrackiottech.com", "info@hubtrackiottech.com"],
    )
    lines = content.lines
    assert lines.index("www.hubtrackiottech.com") == 2 and lines[4] == "PARKING ENTRY"
    assert "Plate: T123ABC" in lines and "Entry: 18 Nov 2026 14:05 EAT" in lines
    assert "Ref: 8Q7K-4M2P" in lines and content.header_lines[1] == "info@hubtrackiottech.com"


def test_escpos_ticket_prints_header_and_reference_barcode():
    document = ReceiptDocument(
        site_name="Mlimani City", plate="T123ABC", entry_time="14:05", entry_gate="1#",
        public_reference="8Q7K-4M2P", public_url="", payment_instructions="", body_text="",
        qr_payload="", header_lines=["www.hubtrackiottech.com"], barcode="8Q7K-4M2P",
    )
    data = escpos_bytes(document)
    assert b"www.hubtrackiottech.com\n" in data
    barcode = escpos_code128("8Q7K-4M2P")
    assert barcode in data
    assert b"\x1dk\x49\x0b{B8Q7K-4M2P" in barcode and b"\x1dH\x02" in barcode
    # What a scanner reads back is a valid kiosk reference.
    assert normalize_human_reference("8Q7K-4M2P") == "8Q7K-4M2P"


def test_no_barcode_when_disabled():
    document = ReceiptDocument(
        site_name="S", plate="P", entry_time="t", entry_gate="g", public_reference="8Q7K-4M2P",
        public_url="", payment_instructions="", body_text="", qr_payload="",
    )
    assert b"\x1dk" not in escpos_bytes(document)
    assert escpos_code128("") == b""
