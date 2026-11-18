"""Every camera event ends in a recorded outcome; unread images are kept, capped."""

from unittest.mock import patch

from app.services import event_outcomes as eo


def test_classify_covers_every_read_result():
    assert eo.classify(None) == "not_run"
    assert eo.classify({"ok": False, "error": "busy"}) == "not_run"
    assert eo.classify({"ok": True, "best": None, "detail": "no plate in the detection zone"}) == "no_plate_box"
    assert eo.classify({"ok": True, "best": None, "detail": "plate crop was not readable"}) == "unread"
    assert eo.classify({"ok": True, "best": {"plate": "T422BCR"}, "persist_skipped": "duplicate visit"}) == "rejected:duplicate visit"
    assert eo.classify({"ok": True, "best": {"plate": "T422BCR"}}) == "read"


def test_counts_and_kept_images_are_bounded(tmp_path):
    eo._counts.clear()
    jpeg = b"\xff\xd8" + b"x" * 32 + b"\xff\xd9"
    with patch.object(eo, "misses_dir", return_value=tmp_path), patch.object(eo, "KEEP_MISSES", 5):
        for _ in range(8):
            eo.note(3, "no_plate_box", jpeg=jpeg)
        eo.note(3, "read", jpeg=jpeg)                     # read events keep no image
        eo.note(3, "rejected:duplicate visit", jpeg=jpeg)
    assert eo.stats()["3"] == {"no_plate_box": 8, "read": 1, "rejected": 1}
    assert len(list(tmp_path.glob("*.jpg"))) == 5
