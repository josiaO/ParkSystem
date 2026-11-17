"""Tanzanian fixed-slot correction: T + 3 digits + 3 letters. Cases are real
FastALPR reads from SITE-PC01 (2026-11-17)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.core.plate import apply_site_plate
from app.core.plate_policy import correct_tz_standard_plate, plate_policy_for

CORRECTED = {
    "7619BAZ": "T619BAZ",   # leading T read as 7
    "1302BLB": "T302BLB",   # ... as 1
    "I833DOY": "T833DOY",   # ... as I
    "TS94ESV": "T594ESV",   # S in a digit slot
    "TO88EKB": "T088EKB",   # O in a digit slot
    "TB12EGG": "T812EGG",   # B in a digit slot
    "TZ66EOD": "T266EOD",   # Z in a digit slot
    "T872EH2": "T872EHZ",   # 2 in a letter slot
    "TL23E5A": "T123ESA",   # L in a digit slot, 5 in a letter slot
}
UNCHANGED = [
    "T460EBS",               # already standard
    "SM15711", "SM14505", "STN5611", "STK1234", "SU1234", "DFPB0610", "DFPA2609",
    "DFA6205", "SNK7151C", "CD12345", "PT1234", "MC123ABC", "JWTZ123",   # special formats
    "T8790DKV", "T282DC", "44116", "MX3880",                              # other lengths
    "15111DD", "T2711DG", "T4205BK",   # would land outside the issued series (I, S)
    "7S5IBO2",                         # more than two changes
]


@pytest.mark.parametrize("read,expected", sorted(CORRECTED.items()))
def test_misread_standard_plates_are_fitted_to_their_slots(read, expected):
    result = plate_policy_for("TZ").correct(read)
    assert result["plate"] == expected and result["corrected"] is True
    assert result["reason"].startswith("tz-slots")


@pytest.mark.parametrize("read", UNCHANGED)
def test_special_and_unfixable_plates_are_never_rewritten(read):
    assert plate_policy_for("TZ").correct(read)["plate"] == read
    assert correct_tz_standard_plate(read) == (read, [])


def test_registered_plates_win_and_neutral_sites_are_untouched():
    kept = plate_policy_for("TZ").correct("TS94ESV", known_plates=["TS94ESV"])   # registered as read
    assert kept["plate"] == "TS94ESV" and kept["reason"] == "exact-known"
    assert plate_policy_for("NONE").correct("7619BAZ")["plate"] == "7619BAZ"
    applied = apply_site_plate("7619BAZ", validation="TZ")
    assert applied["normalized_plate"] == "T619BAZ" and applied["validation_ok"] and not applied["hold_for_operator"]


def test_site_service_saves_the_corrected_plate_and_keeps_the_raw_read():
    from app import api_main as api
    from app.models import Camera

    camera = Camera(id=906, name="Entry", ip_address="10.0.0.8", stream_profiles={})
    read = {"ok": True, "best": {"plate": "7619BAZ", "plate_raw": "7619BAZ", "confidence": 0.97,
                                  "bbox": {"x1": 10, "y1": 10, "x2": 90, "y2": 40}}}
    jpeg = b"\xff\xd8" + b"0" * 64 + b"\xff\xd9"

    async def run():
        with patch("app.services.media_gateway.gateway.peek_detect", return_value=None), \
             patch("app.services.alpr.recognize_arrival_bytes", return_value=read), \
             patch("app.api_main.site_policy", return_value={"plate_validation": "TZ"}), \
             patch("app.api_main.should_persist_vehicle_capture", return_value=(True, "")), \
             patch("app.api_main._persist_capture_event", new=AsyncMock()) as persist:
            out = await api._run_local_alpr_locked(None, camera, jpeg, ticket=None)
        assert out["best"]["plate"] == "T619BAZ" and out["best"]["plate_raw"] == "7619BAZ"
        capture = persist.await_args.args[2]
        assert capture["plate"] == "T619BAZ" and capture["plate_raw"] == "7619BAZ"

    asyncio.run(run())
