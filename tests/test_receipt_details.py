"""Driver receipt details: reference, free period, chargeable time, rate."""

from types import SimpleNamespace

from app.services.session_presentation import tariff_summary

RULES = {"currency": "TZS", "day_block_fee": 1000, "day_block_seconds": 2700,
         "night_block_fee": 1000, "night_block_seconds": 2100}


def test_summary_comes_from_the_stored_quote_and_tariff():
    row = SimpleNamespace(breakdown=["duration:5400s", "free:2700s", "day:2700s/1blk=1000"],
                          tariff_rules=RULES, currency="TZS")
    assert tariff_summary(row) == {
        "free_label": "45 min",
        "chargeable_label": "45 min",
        "rate_label": "TZS 1,000 per 45 min (night TZS 1,000 per 35 min)",
    }


def test_same_day_and_night_rate_is_shown_once_and_missing_data_is_blank():
    same = {**RULES, "night_block_seconds": 2700}
    row = SimpleNamespace(breakdown=["duration:7200s", "free:2700s"], tariff_rules=same, currency="TZS")
    assert tariff_summary(row)["rate_label"] == "TZS 1,000 per 45 min"
    assert tariff_summary(row)["chargeable_label"] == "1 h 15 min"
    empty = SimpleNamespace(breakdown=None, tariff_rules=None, currency="TZS")
    assert tariff_summary(empty) == {"free_label": "", "chargeable_label": "", "rate_label": ""}


def test_pruned_photos_are_not_offered(tmp_path):
    """Media older than media_retention_days is deleted; the receipt must not link to it."""
    from unittest.mock import patch

    from app.services import kiosk_lookup

    (tmp_path / "snapshots").mkdir()
    (tmp_path / "snapshots" / "kept.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    with patch("app.config.Settings.media_dir", new=property(lambda self: tmp_path)):
        assert kiosk_lookup._media_exists("snapshots/kept.jpg") is True
        assert kiosk_lookup._media_exists("snapshots/pruned.jpg") is False
        assert kiosk_lookup._media_exists("") is False
        assert kiosk_lookup._media_exists("snapshots/../../etc/passwd") is False
