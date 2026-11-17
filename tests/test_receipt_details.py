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


def test_cleanup_never_removes_a_photo_a_visit_still_uses(tmp_path):
    """A car parked longer than media_retention_days keeps its entry photo.

    Only files no capture points to are pruned after the retention period.
    """
    import os
    import time
    from unittest.mock import patch

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db import Base
    from app.models import VehicleCapture
    from app.services.captures import prune_unreferenced_media

    (tmp_path / "snapshots").mkdir()
    old = time.time() - 40 * 86400
    for name in ("parked.jpg", "orphan.jpg", "fresh-orphan.jpg"):
        path = tmp_path / "snapshots" / name
        path.write_bytes(b"\xff\xd8\xff\xd9")
        if name != "fresh-orphan.jpg":
            os.utime(path, (old, old))
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db, patch("app.config.Settings.media_dir", new=property(lambda self: tmp_path)):
        db.add(VehicleCapture(camera_id=1, plate="T422BCR", snapshot_path="snapshots/parked.jpg"))
        db.commit()
        result = prune_unreferenced_media(db, retention_days=14)
    assert result["removed"] == 1
    assert (tmp_path / "snapshots" / "parked.jpg").exists()          # 40 days old, still referenced: kept
    assert not (tmp_path / "snapshots" / "orphan.jpg").exists()      # old and unreferenced: removed
    assert (tmp_path / "snapshots" / "fresh-orphan.jpg").exists()    # unreferenced but recent: kept
