"""Live plate captures must create ParkingSessions even without a Gate."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import Base
from app.domain.site import DEFAULT_SITE_ID
from app.models import Camera, Site
from app.services.captures import persist_event
from app.services.simulation import _active_for_plate, create_entry, session_dict


class GatelessSessionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        with self.Session() as db:
            db.add(Site(id=DEFAULT_SITE_ID, name="Site", currency="TZS"))
            db.add(Camera(name="Entry cam", ip_address="10.0.0.9", lane_direction="ENTRY", adapter_id="dahua", site_id=DEFAULT_SITE_ID))
            db.commit()

    def tearDown(self):
        self.engine.dispose()

    def test_create_entry_without_gate(self):
        with self.Session() as db:
            cam = db.scalar(select(Camera))
            row = create_entry(db, plate="T165EED", gate=None, side="ENTRY", camera=cam, status="ACTIVE")
            self.assertEqual(row.plate, "T165EED")
            self.assertIsNone(row.gate_id)
            self.assertEqual(row.camera_id, cam.id)
            self.assertTrue(row.public_token)
            self.assertIsNotNone(_active_for_plate(db, "T165EED"))

    def test_handle_plate_event_without_gate(self):
        async def run():
            with self.Session() as db:
                cam = db.scalar(select(Camera))
                stored = persist_event(
                    db, cam, jpeg=b"\xff\xd8\xff\xd9", crop=b"",
                    capture={"image_id": 11, "plate": "T104EJW", "score": 90, "have_vehicle": True},
                )
                self.assertIsNotNone(stored)
                from app.application.live_parking import handle_live_entry
                result = await handle_live_entry(
                    db, camera=cam, capture=stored, gate=None, source="test",
                )
                self.assertTrue(result.get("ok"))
                session = result.get("session") or {}
                self.assertEqual(session.get("plate"), "T104EJW")
                self.assertIsNone(session.get("gate_id"))
                self.assertEqual(session.get("camera_id"), cam.id)
                self.assertIsNotNone(_active_for_plate(db, "T104EJW"))

        asyncio.run(run())

        asyncio.run(run())

    def test_session_dict_keeps_entry_photo_when_session_plate_was_corrected(self):
        import shutil
        import tempfile
        from unittest.mock import PropertyMock, patch
        from app.config import Settings

        media = Path(tempfile.mkdtemp(prefix="smartpark-media-"))
        try:
            with patch.object(Settings, "media_dir", new_callable=PropertyMock, return_value=media):
                with self.Session() as db:
                    cam = db.scalar(select(Camera))
                    persist_event(
                        db, cam, jpeg=b"\xff\xd8\xff\xd9", crop=b"\xff\xd8\xff\xdb\xff\xd9",
                        capture={"image_id": 3, "plate": "T285DQP", "score": 90, "have_vehicle": True},
                    )
                    row = create_entry(db, plate="T2850QP", gate=None, side="ENTRY", camera=cam, status="ACTIVE")
                    body = session_dict(row)
                    self.assertTrue(body.get("snapshot_url"))
                    self.assertTrue(body.get("crop_url"))
        finally:
            shutil.rmtree(media, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
