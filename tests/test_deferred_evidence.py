"""Evidence photos follow the decision instead of delaying it (step 3).

docs/ZIRP_HIGH_THROUGHPUT_ARCHITECTURE.md: the zone snapshot and plate crop
cost about 150 ms per car on SERVER01. A live capture row is committed with
reserved photo names (``evidence_state='PENDING'``) and the image work runs on
the evidence pool afterwards.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import PropertyMock, patch

import pytest
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import Base
from app.domain.site import DEFAULT_SITE_ID
from app.models import Camera, Site, VehicleCapture
from app.services import evidence
from app.services.captures import persist_event


def _jpeg(width=640, height=360) -> bytes:
    out = BytesIO()
    Image.new("RGB", (width, height), (90, 120, 150)).save(out, format="JPEG")
    return out.getvalue()


@pytest.fixture()
def env(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        db.add(Site(id=DEFAULT_SITE_ID, name="Site", currency="TZS"))
        db.add(Camera(id=3, name="Entry", ip_address="10.0.0.9", lane_direction="ENTRY", adapter_id="hvx",
                      site_id=DEFAULT_SITE_ID))
        db.commit()
    media = tmp_path / "media"
    media.mkdir()
    jobs: list[evidence.EvidenceJob] = []
    with patch.object(Settings, "media_dir", new_callable=PropertyMock, return_value=media), \
            patch.object(evidence, "submit", side_effect=jobs.append):
        yield factory, media, jobs
    engine.dispose()


def _capture(event_id="ev-1", plate="T123ABC"):
    return {"event_id": event_id, "plate": plate, "score": 0.97, "have_vehicle": True,
            "plate_box": {"x": 100, "y": 150, "w": 120, "h": 40}}


def test_capture_commits_before_any_image_work(env):
    factory, media, jobs = env
    with factory() as db, patch("app.services.captures.detection_zone_jpeg",
                                side_effect=AssertionError("image work on the decision path")):
        row = persist_event(db, db.get(Camera, 3), jpeg=_jpeg(), crop=b"", capture=_capture(),
                            defer_evidence=True)
    assert row is not None and row.plate == "T123ABC"
    assert row.evidence_state == "PENDING"
    assert row.snapshot_path.startswith("snapshots/") and row.crop_path.startswith("crops/")
    assert not (media / row.snapshot_path).exists()          # the decision did not wait for files
    assert len(jobs) == 1 and jobs[0].capture_id == row.id
    with factory() as other:                                  # committed, visible to the decision
        assert other.get(VehicleCapture, row.id).plate == "T123ABC"


def test_evidence_job_writes_the_reserved_files(env):
    factory, media, jobs = env
    with factory() as db:
        row = persist_event(db, db.get(Camera, 3), jpeg=_jpeg(), crop=b"", capture=_capture(),
                            defer_evidence=True)
    state = evidence.run_job(jobs[0], session_factory=factory)
    assert state == "STORED"
    with factory() as db:
        stored = db.get(VehicleCapture, row.id)
        assert stored.evidence_state == "STORED"
        assert (media / stored.snapshot_path).read_bytes()[:2] == b"\xff\xd8"
        if stored.crop_path:
            assert (media / stored.crop_path).is_file()
        assert stored.snapshot_path == row.snapshot_path       # the reserved name is the real name


def test_no_reference_is_left_to_a_photo_that_was_not_made(env):
    factory, media, jobs = env
    with factory() as db:
        row = persist_event(db, db.get(Camera, 3), jpeg=_jpeg(), crop=b"", capture=_capture(),
                            defer_evidence=True)
    job = jobs[0]
    job.make_crop = lambda: b""
    job.make_snapshot = lambda: (_ for _ in ()).throw(OSError("disk full"))
    assert evidence.run_job(job, session_factory=factory) == "MISSING"
    with factory() as db:
        stored = db.get(VehicleCapture, row.id)
        assert stored.evidence_state == "MISSING" and stored.snapshot_path == "" and stored.crop_path == ""


def test_pending_rows_of_a_dead_writer_become_missing(env):
    factory, media, jobs = env
    with factory() as db:
        row = persist_event(db, db.get(Camera, 3), jpeg=_jpeg(), crop=b"", capture=_capture(),
                            defer_evidence=True)
        assert evidence.mark_stale_pending(db) == 0           # still being written
        later = datetime.now(timezone.utc) + timedelta(minutes=15)
        assert evidence.mark_stale_pending(db, now=later) == 1
        db.refresh(row)
        assert row.evidence_state == "MISSING" and row.snapshot_path == ""


def test_other_callers_keep_writing_photos_with_the_row(env):
    factory, media, jobs = env
    with factory() as db:
        row = persist_event(db, db.get(Camera, 3), jpeg=_jpeg(), crop=b"", capture=_capture("ev-2"))
    assert row.evidence_state == ""
    assert (media / row.snapshot_path).is_file()
    assert jobs == []


def test_wait_for_follows_a_real_job(tmp_path):
    import time

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        db.add(VehicleCapture(id=7, camera_id=None, plate="T777AAA", evidence_state="PENDING",
                              snapshot_path="snapshots/t-car.jpg", crop_path=""))
        db.commit()
    data = _jpeg()

    def slow_snapshot():
        time.sleep(0.3)
        return data

    with patch.object(Settings, "media_dir", new_callable=PropertyMock, return_value=tmp_path):
        assert evidence.wait_for("snapshots/never-reserved.jpg", 2.0) is False
        job = evidence.EvidenceJob(capture_id=7, snapshot_ref="snapshots/t-car.jpg", crop_ref="",
                                   make_snapshot=slow_snapshot, make_crop=lambda: b"")
        future = evidence.submit(job, factory)
        assert (tmp_path / "snapshots" / "t-car.jpg").exists() is False
        assert evidence.wait_for("snapshots/t-car.jpg", 2.0) is True
        assert (tmp_path / "snapshots" / "t-car.jpg").read_bytes() == data
        assert future.result(2) == "STORED"
    with factory() as db:
        assert db.get(VehicleCapture, 7).evidence_state == "STORED"
    engine.dispose()


def test_duplicate_event_does_not_queue_a_second_job(env):
    factory, media, jobs = env
    with factory() as db:
        first = persist_event(db, db.get(Camera, 3), jpeg=_jpeg(), crop=b"", capture=_capture("ev-3"),
                              defer_evidence=True)
        again = persist_event(db, db.get(Camera, 3), jpeg=_jpeg(), crop=b"", capture=_capture("ev-3"),
                              defer_evidence=True)
    assert again.id == first.id
    assert len(jobs) == 1
    with factory() as db:
        assert len(db.scalars(select(VehicleCapture)).all()) == 1
