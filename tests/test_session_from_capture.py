"""Live plate captures must create ParkingSessions even without a Gate."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import Base
from app.models import Camera
from app.services.simulation import _active_for_plate, create_entry, handle_plate_event, session_dict


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
            db.add(Camera(name="Entry cam", ip_address="10.0.0.9", lane_direction="ENTRY", adapter_id="dahua"))
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
        async def fake_take(db, row, *, reason=""):
            return {"session": session_dict(row), "barrier": {"ok": False, "message": "No gate"}}

        async def run():
            with self.Session() as db:
                cam = db.scalar(select(Camera))
                with patch(
                    "app.services.simulation.issue_receipt",
                    new=AsyncMock(return_value={"receipt": "ok", "qr_url": "/p/x/qr.png", "print": {}}),
                ), patch(
                    "app.services.simulation.take_receipt",
                    new=AsyncMock(side_effect=fake_take),
                ):
                    result = await handle_plate_event(
                        db,
                        plate="T104EJW",
                        gate=None,
                        side="ENTRY",
                        simulated=False,
                        source="test",
                        camera=cam,
                    )
                self.assertTrue(result.get("ok"))
                session = result.get("session") or {}
                self.assertEqual(session.get("plate"), "T104EJW")
                self.assertIsNone(session.get("gate_id"))
                self.assertEqual(session.get("camera_id"), cam.id)
                self.assertIsNotNone(_active_for_plate(db, "T104EJW"))

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
