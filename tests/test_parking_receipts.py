"""Phase 3: one session QR, print jobs, no gate OPEN."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import sys
from unittest.mock import PropertyMock, patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.db import Base
from app.domain.parking_engine import GATE_OPEN_REQUESTED, LanePolicy, RECEIPT_TAKEN
from app.domain.receipt_engine import (
    CAP_PRESENTER,
    CAP_TAKEN_SENSOR,
    JOB_ASSISTANCE,
    JOB_OVERRIDE,
    JOB_PRESENTED,
    JOB_TAKEN,
    extract_session_token,
    new_human_reference,
    new_public_token,
    qr_exposes_secrets,
    render_entry_receipt,
    session_qr_payload,
)
from app.infrastructure.hardware.receipt_printers import HardwareReceiptPrinter, SimulatedKioskPrinter
from app.models import AuditLog, ParkingSession, Receipt, Site
from app.services import parking_sessions as sessions
from app.services.kiosk_lookup import find_session
from app.services.receipt_jobs import (
    expire_if_not_taken,
    mark_receipt_presented,
    mark_receipt_taken,
    operator_override,
    print_entry_receipt,
)


def _engine():
    return create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)


class TokenAndQrUnitTests(unittest.TestCase):
    def test_session_token_uniqueness_and_entropy(self):
        tokens = {new_public_token() for _ in range(40)}
        self.assertEqual(len(tokens), 40)
        for token in tokens:
            self.assertGreaterEqual(len(token), 32)
            self.assertNotIn("/", token)
            self.assertNotIn(" ", token)

    def test_human_reference_is_not_the_auth_token(self):
        ref = new_human_reference()
        self.assertRegex(ref, r"^[2-9A-HJ-NP-Z]{4}-[2-9A-HJ-NP-Z]{4}$")
        self.assertEqual(extract_session_token(ref), "")
        token = new_public_token()
        self.assertNotEqual(token, ref)
        self.assertGreater(len(token), len(ref))

    def test_qr_payload_is_local_session_path(self):
        token = "AbCdEfGh1234567890-_xyz"
        self.assertEqual(session_qr_payload(token), f"/s/{token}")
        self.assertEqual(
            session_qr_payload(token, base_url="https://pay.smartpark.example"),
            f"https://pay.smartpark.example/s/{token}",
        )
        self.assertEqual(extract_session_token(f"/s/{token}"), token)
        self.assertEqual(extract_session_token(f"/p/{token}"), token)
        self.assertEqual(extract_session_token(f"https://site.local/s/{token}"), token)
        self.assertEqual(extract_session_token(f"http://192.168.1.10:8760/p/{token}/qr.png"), token)

    def test_qr_does_not_expose_db_id_or_plate(self):
        token = new_public_token()
        payload = session_qr_payload(token, base_url="https://pay.example")
        self.assertFalse(qr_exposes_secrets(payload, plate="T123ABC", session_id=99))
        self.assertTrue(qr_exposes_secrets("/s/99", plate="T123ABC", session_id=99))
        self.assertTrue(qr_exposes_secrets("/s/T123ABC", plate="T123ABC", session_id=1))

    def test_receipt_rendering(self):
        pending = render_entry_receipt(
            site_name="Harbour Park",
            plate="",
            entry_time="01 Sep 2026 08:00",
            entry_lane="North Entry",
            human_reference="8Q7K-4M2P",
            qr_payload="/s/opaque-token",
            plate_status="UNRESOLVED",
        )
        self.assertEqual(pending.lines[0], "SmartPark")
        self.assertIn("Plate pending", pending.body_text)
        self.assertIn("North Entry", pending.body_text)
        self.assertIn("8Q7K-4M2P", pending.body_text)
        self.assertNotIn("45 minute", pending.body_text.lower())
        self.assertEqual(pending.qr_payload, "/s/opaque-token")
        configured = render_entry_receipt(
            site_name="Harbour Park",
            plate="T123ABC",
            entry_time="01 Sep 2026 08:00",
            entry_lane="North Entry",
            human_reference="8Q7K-4M2P",
            qr_payload="/s/opaque-token",
            tariff_rules={"free_day_seconds": 2700},
        )
        self.assertIn("T123ABC", configured.body_text)
        self.assertIn("first 45 minutes", configured.free_period)
        self.assertEqual(configured.lines.count("SmartPark"), 1)


class HardwareCapabilityTests(unittest.TestCase):
    def test_usb_thermal_does_not_claim_taken_sensor(self):
        hardware = HardwareReceiptPrinter("system")
        self.assertNotIn(CAP_TAKEN_SENSOR, hardware.capabilities)
        self.assertNotIn(CAP_PRESENTER, hardware.capabilities)
        sim = SimulatedKioskPrinter()
        self.assertIn(CAP_TAKEN_SENSOR, sim.capabilities)


class ParkingReceiptPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = _engine()
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        with self.Session() as db:
            db.add(Site(id=1, name="Site"))
            db.commit()
        self.media = Path(tempfile.mkdtemp(prefix="smartpark-receipt-"))
        self._media = patch.object(Settings, "media_dir", new_callable=PropertyMock, return_value=self.media)
        self._media.start()
        self.policy = LanePolicy(receipt_required_before_open=True)

    def tearDown(self):
        self._media.stop()
        shutil.rmtree(self.media, ignore_errors=True)
        self.engine.dispose()

    def _session(self, db, plate: str, event_id: str) -> ParkingSession:
        row, created = sessions.start_entry(
            db, plate=plate, event_id=event_id, lane_id=None, camera_id=None, gate_id=None, policy=self.policy,
        )
        self.assertTrue(created)
        return row

    def test_stored_tokens_are_unique(self):
        with self.Session() as db:
            a = self._session(db, "T111AAA", "evt-a")
            b = self._session(db, "T222BBB", "evt-b")
            self.assertNotEqual(a.public_token, b.public_token)
            self.assertNotEqual(a.human_reference, b.human_reference)
            self.assertGreaterEqual(len(a.public_token), 32)
            b.public_token = a.public_token
            with self.assertRaises(IntegrityError):
                db.commit()

    def test_qr_resolves_local_session(self):
        with self.Session() as db:
            row = self._session(db, "T333CCC", "evt-c")
            token = row.public_token
            ref = row.human_reference
            self.assertEqual(find_session(db, f"/s/{token}").id, row.id)
            self.assertEqual(find_session(db, f"https://pay.smartpark.example/s/{token}").id, row.id)
            self.assertEqual(find_session(db, f"/p/{token}").id, row.id)
            self.assertEqual(find_session(db, ref).id, row.id)
            self.assertIsNone(find_session(db, "/s/no-such-token"))

    def test_print_retry_keeps_same_session(self):
        async def _run():
            with self.Session() as db:
                row = self._session(db, "T444DDD", "evt-d")
                printer = SimulatedKioskPrinter()
                first = await print_entry_receipt(db, row, printer=printer, policy=self.policy)
                session_id = first["session_id"]
                job_id = first["print_job_id"]
                self.assertFalse(first["created_session"])
                self.assertEqual(first["status"], JOB_PRESENTED)
                db.refresh(row)
                self.assertEqual(row.open_command_uuid, "")
                self.assertNotEqual(row.lifecycle, GATE_OPEN_REQUESTED)
                second = await print_entry_receipt(db, row, printer=printer, policy=self.policy)
                db.refresh(row)
                self.assertEqual(second["session_id"], session_id)
                self.assertEqual(second["print_job_id"], job_id)
                self.assertEqual(row.print_retry_count, 1)
                self.assertEqual(db.scalar(select(func.count()).select_from(ParkingSession)), 1)
                self.assertEqual(
                    db.scalar(select(func.count()).select_from(Receipt).where(Receipt.session_id == row.id)),
                    1,
                )
                payload = second["qr_payload"]
                self.assertIn("/s/", payload)
                self.assertFalse(qr_exposes_secrets(payload, plate=row.plate, session_id=row.id))
                self.assertNotIn(row.plate, payload)
                self.assertEqual(payload.count("/s/"), 1)

        asyncio.run(_run())

    def test_duplicate_printer_and_taken_events_are_safe(self):
        async def _run():
            with self.Session() as db:
                row = self._session(db, "T555EEE", "evt-e")
                printer = SimulatedKioskPrinter()
                await print_entry_receipt(db, row, printer=printer, policy=self.policy)
                await mark_receipt_presented(db, row, policy=self.policy)
                await mark_receipt_presented(db, row, policy=self.policy)
                db.refresh(row)
                self.assertEqual(row.print_job_status, JOB_PRESENTED)
                updated = await mark_receipt_taken(db, row, printer=printer, policy=self.policy)
                taken_at = updated.receipt_taken_at
                again = await mark_receipt_taken(db, row, printer=printer, policy=self.policy)
                self.assertEqual(again.receipt_taken_at, taken_at)
                self.assertEqual(again.print_job_status, JOB_TAKEN)
                self.assertEqual(again.lifecycle, RECEIPT_TAKEN)
                self.assertEqual(again.open_command_uuid, "")
                self.assertNotEqual(again.lifecycle, GATE_OPEN_REQUESTED)

        asyncio.run(_run())

    def test_printer_out_of_paper_and_offline(self):
        async def _run():
            with self.Session() as db:
                paper = self._session(db, "T666FFF", "evt-f")
                printer = SimulatedKioskPrinter()
                printer.paper_ok = False
                out = await print_entry_receipt(db, paper, printer=printer, policy=self.policy)
                self.assertTrue(out["assistance_required"])
                self.assertEqual(out["status"], JOB_ASSISTANCE)
                self.assertEqual(out["created_session"], False)
                db.refresh(paper)
                self.assertEqual(paper.print_job_status, JOB_ASSISTANCE)
                self.assertEqual(paper.open_command_uuid, "")
                self.assertEqual(paper.id, out["session_id"])

                offline = self._session(db, "T777GGG", "evt-g")
                dead = SimulatedKioskPrinter()
                dead.online = False
                fail = await print_entry_receipt(db, offline, printer=dead, policy=self.policy)
                self.assertTrue(fail["assistance_required"])
                db.refresh(offline)
                self.assertEqual(offline.print_job_status, JOB_ASSISTANCE)
                self.assertEqual(offline.open_command_uuid, "")
                self.assertEqual(db.scalar(select(func.count()).select_from(ParkingSession)), 2)

        asyncio.run(_run())

    def test_receipt_never_taken_timeout(self):
        async def _run():
            with self.Session() as db:
                row = self._session(db, "T888HHH", "evt-h")
                await print_entry_receipt(db, row, printer=SimulatedKioskPrinter(), policy=self.policy)
                db.refresh(row)
                row.receipt_printed_at = datetime.now(timezone.utc) - timedelta(seconds=120)
                db.commit()
                expire_if_not_taken(db, row, now=datetime.now(timezone.utc), timeout_seconds=90)
                db.refresh(row)
                self.assertEqual(row.print_job_status, JOB_ASSISTANCE)
                self.assertIn("never taken", row.printer_error)
                self.assertEqual(row.open_command_uuid, "")

        asyncio.run(_run())

    def test_operator_override_is_audited_and_does_not_open(self):
        async def _run():
            with self.Session() as db:
                row = self._session(db, "T999JJJ", "evt-j")
                printer = SimulatedKioskPrinter()
                printer.paper_ok = False
                await print_entry_receipt(db, row, printer=printer, policy=self.policy)
                operator_override(db, row, reason="presenter jam")
                db.refresh(row)
                self.assertEqual(row.print_job_status, JOB_OVERRIDE)
                self.assertEqual(row.open_command_uuid, "")
                log = db.scalar(select(AuditLog).where(AuditLog.action == "RECEIPT_OPERATOR_OVERRIDE"))
                self.assertIsNotNone(log)
                self.assertEqual(log.target_id, str(row.id))
                self.assertIn("presenter jam", log.detail)
                self.assertNotEqual(row.lifecycle, GATE_OPEN_REQUESTED)

        asyncio.run(_run())
