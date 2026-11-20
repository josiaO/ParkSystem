"""Linked private vehicles: one active session per authorization group.

Acceptance tests 1-10 from ZIRP_LINKED_PRIVATE_VEHICLE&WINDOWS_PRODUCTION.md,
plus the database invariant and real-thread races. The PostgreSQL race test
runs only when ``ZIRP_TEST_POSTGRES_URL`` points at a disposable database,
e.g. ``postgresql+psycopg://zirp_test:...@127.0.0.1:5432/zirp_test``.
None of these tests touches a camera, a barrier or a payment provider: the
barrier opener is a recording fake and every gate result is declared simulated.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.application.entry_lane import EntryLaneController
from app.application.exit_lane import ExitLaneController
from app.db import Base
from app.domain import vehicle_groups as vg
from app.domain.parking_engine import CLOSED, EXIT_GATE_OPEN_REQUESTED, LanePolicy, PASSAGE_WAIT
from app.domain.recognition import CONF_HIGH, NormalizedRecognitionEvent
from app.models import (
    AccessDecision,
    AccessPlan,
    Camera,
    ExitConfirmation,
    Gate,
    Lane,
    ParkingSession,
    RegisteredVehicle,
    Role,
    Site,
    Tariff,
    User,
    UserRole,
    VehicleGroup,
    VehicleGroupOccupancy,
    VisitorPass,
)
from app.services import vehicle_groups as svc
from app.services.gates import GateCommandResult
from app.services.parking_sessions import start_entry, supervised_close

WAIT = LanePolicy(passage_sensing=PASSAGE_WAIT, subscriber_skip_receipt=True)
RULES = {
    "currency": "TZS", "day_start": "00:00:00", "day_end": "23:59:59",
    "free_day_seconds": 2700, "free_night_seconds": 2700, "day_block_seconds": 2700,
    "night_block_seconds": 2700, "day_block_fee": 1000, "night_block_fee": 1000,
    "daily_wrap_fee": 34000, "over_1000_subtract": 1000,
}

CAR_A = "T100AAA"
CAR_B = "T777XYZ"


class FakeOpener:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def __call__(self, db, gate, cameras, reason, session, side, command_uuid=""):
        self.calls.append((gate.id, session.id, side))
        return GateCommandResult(ok=True, simulated=True, message="OPEN", timestamp="t")


def _event(plate: str, event_id: str) -> NormalizedRecognitionEvent:
    return NormalizedRecognitionEvent(
        event_id=event_id, site_id=1, camera_id=100, lane_id=10,
        occurred_at="2026-11-20T08:00:00+00:00", provider="FASTALPR",
        plate_raw=plate, plate_normalized=plate, confidence=0.97, bbox=None,
        vehicle_detected=True, image_ref="", plate_crop_ref="", confidence_class=CONF_HIGH, accepted=True,
    )


def seed(db, *, private_release: str = vg.RELEASE_EXIT_LANE) -> None:
    db.add(Site(id=1, name="Site", currency="TZS"))
    db.flush()  # PostgreSQL enforces gates.site_id -> sites.id; SQLite does not
    db.add_all([Gate(id=1, name="Entry", site_id=1), Gate(id=2, name="Exit", site_id=1)])
    db.flush()
    db.add_all([
        Lane(id=10, gate_id=1, name="Entry", direction="ENTRY"),
        Lane(id=20, gate_id=2, name="Exit", direction="EXIT"),
    ])
    db.flush()
    db.add_all([
        Camera(id=100, name="Entry", ip_address="10.0.0.1", site_id=1, gate_id=1, lane_id=10, lane_direction="ENTRY"),
        Camera(id=200, name="Exit", ip_address="10.0.0.2", site_id=1, gate_id=2, lane_id=20, lane_direction="EXIT"),
    ])
    db.add(Tariff(site_id=1, name="Car1", car_type="Car1", currency="TZS", rules=RULES, active=True))
    plan = AccessPlan(id=1, site_id=1, name="Monthly Tenant", kind="MONTHLY", auto_open=True)
    db.add(plan)
    db.flush()
    owner = VehicleGroup(id=1, site_id=1, name="Obeid private cars", kind=vg.PRIVATE, owner_name="J. Obeid",
                         max_active_sessions=1, exit_release=private_release)
    fleet = VehicleGroup(id=2, site_id=1, name="ACME fleet", kind=vg.FLEET, company_name="ACME Logistics Ltd",
                         max_active_sessions=2, exit_release=vg.RELEASE_EXIT_LANE)
    db.add_all([owner, fleet])
    db.flush()
    db.add_all([
        RegisteredVehicle(id=1, site_id=1, plate=CAR_A, owner_name="J. Obeid", plan_id=1, group_id=1),
        RegisteredVehicle(id=2, site_id=1, plate=CAR_B, owner_name="J. Obeid", plan_id=1, group_id=1),
        RegisteredVehicle(id=3, site_id=1, plate="T301FLT", owner_name="ACME", plan_id=1, group_id=2),
        RegisteredVehicle(id=4, site_id=1, plate="T588KBW", owner_name="ACME", plan_id=1, group_id=2),
        RegisteredVehicle(id=5, site_id=1, plate="T937DMC", owner_name="ACME", plan_id=1, group_id=2),
        RegisteredVehicle(id=6, site_id=1, plate="T999SOLO", owner_name="Solo", plan_id=1),
    ])
    for role in ("Operator", "Supervisor"):
        db.add(Role(name=role, permissions_csv="exits.confirm" if role == "Operator" else "exits.confirm,exits.reconcile"))
    db.add_all([
        User(id=10, username="guard", full_name="Gate Guard", password_hash="x"),
        User(id=11, username="boss", full_name="Shift Supervisor", password_hash="x"),
    ])
    db.commit()


class LinkedVehicleTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        with self.Session() as db:
            seed(db)
        self.opener = FakeOpener()
        self.entry = EntryLaneController(opener=self.opener)
        self.exit = ExitLaneController(opener=self.opener)

    def tearDown(self):
        self.engine.dispose()

    # -- helpers ---------------------------------------------------------------
    def enter(self, db, plate: str, event_id: str) -> dict:
        out = asyncio.run(self.entry.submit(
            db, _event(plate, event_id), gate=db.get(Gate, 1), camera=db.get(Camera, 100), policy=WAIT,
        ))
        # WAIT_FOR_PASSAGE: the barrier command was accepted; passage comes later.
        out["admitted"] = bool(out.get("barrier_command_accepted"))
        return out

    def exit_lane(self, db, plate: str, event_id: str, *, sensor: bool = True) -> dict:
        out = asyncio.run(self.exit.submit_plate(
            db, plate=plate, event_id=event_id, site_id=1, gate=db.get(Gate, 2), camera=db.get(Camera, 200),
            lane_id=20, policy=WAIT,
        ))
        self.assertTrue(out["barrier_opened"], out)
        row = db.get(ParkingSession, out["session"]["id"])
        self.assertEqual(row.lifecycle, EXIT_GATE_OPEN_REQUESTED)
        if sensor:
            asyncio.run(self.exit.vehicle_passed(db, row, policy=WAIT))
        return out

    def held(self, db, group_id: int = 1) -> list[VehicleGroupOccupancy]:
        return svc.held_occupancies(db, group_id)

    # -- acceptance 1 & 2 ------------------------------------------------------
    def test_1_car_a_enters_car_b_rejected(self):
        with self.Session() as db:
            a = self.enter(db, CAR_A, "a-1")
            self.assertTrue(a["admitted"], a)
            self.assertEqual(a["entitlement"]["belongs_to"], "Private: J. Obeid")
            b = self.enter(db, CAR_B, "b-1")
            self.assertFalse(b["ok"])
            self.assertFalse(b["admitted"])
            self.assertEqual(b["reason"], "authorization_group_occupied")
            self.assertIn(CAR_A, b["message"])
            self.assertEqual(db.scalar(select(func.count()).select_from(ParkingSession)), 1)
            self.assertEqual(len(self.opener.calls), 1)
            refused = db.scalar(select(AccessDecision).where(AccessDecision.outcome == "GROUP_OCCUPIED"))
            self.assertEqual(refused.plate, CAR_B)

    def test_2_car_b_enters_car_a_rejected(self):
        with self.Session() as db:
            self.assertTrue(self.enter(db, CAR_B, "b-1")["admitted"])
            a = self.enter(db, CAR_A, "a-1")
            self.assertEqual(a["reason"], "authorization_group_occupied")
            self.assertIn(CAR_B, a["message"])

    # -- acceptance 3 & 4 ------------------------------------------------------
    def test_3_overnight_stay_still_blocks_next_day(self):
        with self.Session() as db:
            b = self.enter(db, CAR_B, "b-1")
            row = db.get(ParkingSession, b["session"]["id"])
            occ = self.held(db)[0]
            yesterday = datetime.now(timezone.utc) - timedelta(hours=15)
            row.entry_time = row.created_at = row.updated_at = yesterday
            occ.claimed_at = yesterday
            db.commit()
            from app.services.lane_sweeper import sweep_once  # time-outs must not free the group

            sweep_once(db, cfg={"passage_timeout_seconds": 60, "stranded_entry_minutes": 0})
            a = self.enter(db, CAR_A, "a-next-day")
            self.assertEqual(a["reason"], "authorization_group_occupied")
            self.assertEqual(len(self.held(db)), 1)

    def test_4_car_b_exits_then_car_a_allowed(self):
        with self.Session() as db:
            self.enter(db, CAR_B, "b-1")
            self.exit_lane(db, CAR_B, "b-exit")
            self.assertEqual(self.held(db), [])
            released = db.scalar(select(VehicleGroupOccupancy))
            self.assertEqual(released.release_evidence, vg.EV_PASSAGE_SENSOR)
            a = self.enter(db, CAR_A, "a-1")
            self.assertTrue(a["admitted"], a)

    # -- acceptance 5, 6, 7 ----------------------------------------------------
    def test_5_camera_missed_exit_manual_confirmation_closes_session(self):
        with self.Session() as db:
            b = self.enter(db, CAR_B, "b-1")
            found = svc.find_exit_candidates(db, CAR_B)
            self.assertEqual(found[0]["session_id"], b["session"]["id"])
            self.assertEqual(found[0]["belongs_to"], "Private: J. Obeid")
            self.assertTrue(found[0]["can_confirm"])
            with self.assertRaises(ValueError):  # reason is mandatory
                svc.confirm_manual_exit(db, session_id=b["session"]["id"], user=db.get(User, 10), reason="")
            out = svc.confirm_manual_exit(db, session_id=b["session"]["id"], user=db.get(User, 10),
                                          reason="Camera missed exit; guard saw car leave", identified_by="PLATE")
            self.assertEqual(out["confirmation"]["action"], "MANUAL_EXIT_CONFIRMED")
            self.assertEqual(out["confirmation"]["operator_name"], "Gate Guard")
            row = db.get(ParkingSession, b["session"]["id"])
            self.assertEqual(row.status, "CLOSED")
            self.assertEqual(row.lifecycle, CLOSED)
            self.assertEqual(self.held(db), [])
            self.assertTrue(self.enter(db, CAR_A, "a-1")["admitted"])

    def test_6_manual_boom_open_without_confirmation_keeps_group_locked(self):
        from app.services.manual_open import safe_record_manual_open

        with self.Session() as db:
            b = self.enter(db, CAR_B, "b-1")
            row = db.get(ParkingSession, b["session"]["id"])
            safe_record_manual_open(db, source="desk", gate=db.get(Gate, 2), side="EXIT", user=db.get(User, 10),
                                    reason="driver asked", command_ok=True, session=row, queue_alerts=False)
            db.refresh(row)
            self.assertNotEqual(row.status, "CLOSED")
            self.assertEqual(len(self.held(db)), 1)
            self.assertEqual(self.enter(db, CAR_A, "a-1")["reason"], "authorization_group_occupied")
            # The guard is unsure the car really left: the case goes to a supervisor.
            out = svc.confirm_manual_exit(db, session_id=row.id, user=db.get(User, 10), outcome="UNCERTAIN",
                                          reason="boom opened, no car seen on camera")
            self.assertEqual(out["confirmation"]["new_state"], vg.OCC_RECONCILIATION)
            with self.assertRaises(svc.NeedsSupervisor):
                svc.confirm_manual_exit(db, session_id=row.id, user=db.get(User, 10), reason="it left I think")
            self.assertEqual(self.enter(db, CAR_A, "a-2")["reason"], "authorization_group_occupied")

    def test_7_supervisor_reconciles_uncertain_exit_with_audit_trail(self):
        with self.Session() as db:
            b = self.enter(db, CAR_B, "b-1")
            sid = b["session"]["id"]
            svc.confirm_manual_exit(db, session_id=sid, user=db.get(User, 10), outcome="UNCERTAIN",
                                    reason="barrier was opened by hand")
            occ = self.held(db)[0]
            out = svc.reconcile(db, occupancy_id=occ.id, user=db.get(User, 11), decision="RELEASE",
                                reason="CCTV shows T777XYZ leaving at 07:42")
            self.assertEqual(out["occupancy"]["state"], vg.OCC_RELEASED)
            self.assertEqual(out["occupancy"]["release_evidence"], vg.EV_SUPERVISOR)
            self.assertEqual(db.get(ParkingSession, sid).status, "CLOSED")
            trail = db.scalars(select(ExitConfirmation).where(ExitConfirmation.session_id == sid)
                               .order_by(ExitConfirmation.id)).all()
            self.assertEqual([t.action for t in trail], ["MANUAL_EXIT_UNCERTAIN", "SUPERVISOR_RELEASED"])
            self.assertEqual(trail[1].operator_id, 11)
            self.assertIn("CCTV", trail[1].reason)
            self.assertTrue(self.enter(db, CAR_A, "a-1")["admitted"])

    def test_supervisor_keep_inside_keeps_lock(self):
        with self.Session() as db:
            b = self.enter(db, CAR_B, "b-1")
            svc.confirm_manual_exit(db, session_id=b["session"]["id"], user=db.get(User, 10), outcome="UNCERTAIN",
                                    reason="not sure")
            occ = self.held(db)[0]
            out = svc.reconcile(db, occupancy_id=occ.id, user=db.get(User, 11), decision="KEEP_INSIDE",
                                reason="car found in bay 12")
            self.assertEqual(out["occupancy"]["state"], vg.OCC_ACTIVE)
            self.assertEqual(self.enter(db, CAR_A, "a-1")["reason"], "authorization_group_occupied")

    # -- acceptance 8 ----------------------------------------------------------
    def test_8_database_refuses_two_live_slots(self):
        with self.Session() as db:
            db.add_all([
                VehicleGroupOccupancy(group_id=1, slot=1, state=vg.OCC_ACTIVE, plate=CAR_A),
                VehicleGroupOccupancy(group_id=1, slot=1, state=vg.OCC_ACTIVE, plate=CAR_B),
            ])
            with self.assertRaises(IntegrityError):
                db.commit()

    def test_8_interleaved_claims_second_fails(self):
        """Lane 1 claims inside an open transaction; lane 2's claim cannot also succeed."""
        with self.Session() as db:
            from app.services.access import lookup_entitlement

            ent_a = lookup_entitlement(db, CAR_A, site_id=1, strict=True)
            ent_b = lookup_entitlement(db, CAR_B, site_id=1, strict=True)
            start_entry(db, plate=CAR_A, event_id="race-a", site_id=1, gate_id=1, camera_id=100,
                        parker_kind=ent_a.kind, policy=WAIT, entitlement=ent_a)
            with self.assertRaises(vg.GroupOccupied):
                start_entry(db, plate=CAR_B, event_id="race-b", site_id=1, gate_id=1, camera_id=100,
                            parker_kind=ent_b.kind, policy=WAIT, entitlement=ent_b)
            self.assertEqual(db.scalar(select(func.count()).select_from(ParkingSession)), 1)

    # -- acceptance 9 ----------------------------------------------------------
    def test_9_company_fleet_follows_its_own_limit(self):
        with self.Session() as db:
            first = self.enter(db, "T301FLT", "f-1")
            self.assertTrue(first["admitted"])
            self.assertEqual(first["entitlement"]["belongs_to"], "Company: ACME Logistics Ltd")
            self.assertEqual(first["entitlement"]["company_name"], "ACME Logistics Ltd")
            self.assertTrue(self.enter(db, "T588KBW", "f-2")["admitted"])   # limit 2, not 1
            third = self.enter(db, "T937DMC", "f-3")
            self.assertEqual(third["reason"], "authorization_group_occupied")
            self.assertIn("Company: ACME Logistics Ltd", third["message"])
            # Fleet configured with no limit: never blocked.
            fleet = db.get(VehicleGroup, 2)
            fleet.max_active_sessions = 0
            db.commit()
            self.assertTrue(self.enter(db, "T937DMC", "f-4")["admitted"])

    def test_private_group_cannot_be_configured_above_one(self):
        self.assertEqual(vg.normalize_policy("PRIVATE", 5, None).max_active_sessions, 1)
        with self.Session() as db:
            group = db.get(VehicleGroup, 1)
            group.max_active_sessions = 3
            with self.assertRaises(IntegrityError):
                db.commit()

    # -- acceptance 10 ---------------------------------------------------------
    def test_10_unlinked_registered_and_casual_flows_unchanged(self):
        with self.Session() as db:
            solo = self.enter(db, "T999SOLO", "s-1")
            self.assertTrue(solo["admitted"])
            self.assertIsNone(solo["entitlement"]["group_id"])
            self.assertEqual(db.scalar(select(func.count()).select_from(VehicleGroupOccupancy)), 0)
            self.exit_lane(db, "T999SOLO", "s-exit")
            self.assertEqual(db.get(ParkingSession, solo["session"]["id"]).status, "CLOSED")
            casual = asyncio.run(self.entry.submit(
                db, _event("T555CAS", "c-1"), gate=db.get(Gate, 1), camera=db.get(Camera, 100),
                policy=LanePolicy(passage_sensing=PASSAGE_WAIT, receipt_required_before_open=False),
            ))
            self.assertTrue(casual["created_session"])
            self.assertEqual(casual["session"]["parker_kind"], "CASUAL")
            self.assertIsNone(casual["session"]["authorization_group_id"])

    # -- exit evidence policies ------------------------------------------------
    def test_exit_lane_without_sensor_releases_under_default_policy(self):
        with self.Session() as db:
            self.enter(db, CAR_B, "b-1")
            out = self.exit_lane(db, CAR_B, "b-exit", sensor=False)
            row = db.get(ParkingSession, out["session"]["id"])
            from app.services.lane_sweeper import sweep_once

            row.updated_at = datetime.now(timezone.utc) - timedelta(minutes=5)
            db.commit()
            sweep_once(db, cfg={"passage_timeout_seconds": 60, "stranded_entry_minutes": 0})
            self.assertEqual(self.held(db), [])
            self.assertTrue(self.enter(db, CAR_A, "a-1")["admitted"])

    def test_strict_policy_needs_sensor_or_guard(self):
        with self.Session() as db:
            group = db.get(VehicleGroup, 1)
            group.exit_release = vg.RELEASE_PASSAGE_CONFIRMED
            db.commit()
            self.enter(db, CAR_B, "b-1")
            out = self.exit_lane(db, CAR_B, "b-exit", sensor=False)
            row = db.get(ParkingSession, out["session"]["id"])
            from app.services.lane_sweeper import sweep_once

            row.updated_at = datetime.now(timezone.utc) - timedelta(minutes=5)
            db.commit()
            sweep_once(db, cfg={"passage_timeout_seconds": 60, "stranded_entry_minutes": 0})
            db.refresh(row)
            self.assertEqual(row.status, "CLOSED")            # the visit record is closed…
            held = self.held(db)
            self.assertEqual([o.state for o in held], [vg.OCC_EXIT_UNCONFIRMED])  # …the group is not
            self.assertEqual(self.enter(db, CAR_A, "a-1")["reason"], "authorization_group_occupied")
            pending = svc.pending_exits(db, include_active=False)
            self.assertEqual(pending[0]["plate"], CAR_B)
            svc.confirm_manual_exit(db, session_id=row.id, user=db.get(User, 10), reason="guard saw it leave")
            self.assertTrue(self.enter(db, CAR_A, "a-2")["admitted"])

    def test_same_car_back_at_entry_proves_unconfirmed_exit(self):
        with self.Session() as db:
            group = db.get(VehicleGroup, 1)
            group.exit_release = vg.RELEASE_PASSAGE_CONFIRMED
            db.commit()
            b = self.enter(db, CAR_B, "b-1")
            supervised_close(db, db.get(ParkingSession, b["session"]["id"]), reason="written off", user_id=11)
            self.assertEqual([o.state for o in self.held(db)], [vg.OCC_EXIT_UNCONFIRMED])
            again = self.enter(db, CAR_B, "b-2")
            self.assertTrue(again["admitted"], again)
            states = sorted(o.state for o in db.scalars(select(VehicleGroupOccupancy)).all())
            self.assertEqual(states, [vg.OCC_ACTIVE, vg.OCC_RELEASED])

    # -- visitors --------------------------------------------------------------
    def test_visitor_pass_admits_without_registration_and_is_single_use(self):
        with self.Session() as db:
            now = datetime.now(timezone.utc)
            db.add(VisitorPass(site_id=1, plate="T404VIS", visitor_name="Courier", host_group_id=2,
                               valid_from=now - timedelta(minutes=5), valid_until=now + timedelta(hours=4),
                               max_entries=1))
            db.commit()
            first = self.enter(db, "T404VIS", "v-1")
            self.assertTrue(first["admitted"], first)
            self.assertEqual(first["session"]["parker_kind"], "VISITOR")
            self.assertIn("ACME Logistics Ltd", first["entitlement"]["belongs_to"])
            self.assertEqual(db.scalar(select(RegisteredVehicle).where(RegisteredVehicle.plate == "T404VIS")), None)
            self.exit_lane(db, "T404VIS", "v-exit")
            second = asyncio.run(self.entry.submit(
                db, _event("T404VIS", "v-2"), gate=db.get(Gate, 1), camera=db.get(Camera, 100),
                policy=LanePolicy(passage_sensing=PASSAGE_WAIT, receipt_required_before_open=False),
            ))
            self.assertEqual(second["session"]["parker_kind"], "CASUAL")  # used pass: pays like anyone


class ApiTests(unittest.TestCase):
    """HTTP surface: permissions, company labels, manual exit and reconciliation."""

    def setUp(self):
        from app.api_main import app, ensure_roles
        from app.db import get_db
        from app.security import hash_password

        self.app = app
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)

        def override():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override
        with self.Session() as db:
            ensure_roles(db)
            for username, role in (("admin", "Admin"), ("guard", "Operator"), ("boss", "Supervisor")):
                user = User(username=username, full_name=username.title(), password_hash=hash_password("correct-horse"))
                db.add(user)
                db.flush()
                db.add(UserRole(user_id=user.id, role_id=db.scalar(select(Role.id).where(Role.name == role))))
            db.commit()
        self.client = TestClient(app)
        self.h = {name: {"Authorization": "Bearer " + self.client.post(
            "/auth/login", json={"username": name, "password": "correct-horse"}).json()["token"]}
            for name in ("admin", "guard", "boss")}

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()
        self.engine.dispose()

    def test_company_label_and_manual_exit_flow(self):
        c, h = self.client, self.h
        fleet = c.post("/vehicle-groups", headers=h["admin"], json={
            "name": "ACME fleet", "kind": "FLEET", "company_name": "ACME Logistics Ltd", "max_active_sessions": 3,
        })
        self.assertEqual(fleet.status_code, 200, fleet.text)
        self.assertEqual(fleet.json()["display_name"], "Company: ACME Logistics Ltd")
        private = c.post("/vehicle-groups", headers=h["admin"], json={
            "name": "Obeid cars", "kind": "PRIVATE", "owner_name": "J. Obeid", "max_active_sessions": 4,
        }).json()
        self.assertEqual(private["max_active_sessions"], 1)       # private is always one at a time
        car = c.post("/vehicles", headers=h["admin"], json={"plate": "T 301 FLT", "group_id": fleet.json()["id"]})
        self.assertEqual(car.status_code, 200, car.text)
        self.assertEqual(car.json()["belongs_to"], "Company: ACME Logistics Ltd")
        listed = c.get("/vehicles", headers=h["admin"]).json()
        self.assertEqual(listed[0]["company_name"], "ACME Logistics Ltd")
        c.post("/vehicles", headers=h["admin"], json={"plate": CAR_A, "group_id": private["id"]})
        c.post("/vehicles", headers=h["admin"], json={"plate": CAR_B, "group_id": private["id"]})
        self.assertEqual(c.post("/sessions", headers=h["admin"], json={"plate": CAR_B}).status_code, 200)
        blocked = c.post("/sessions", headers=h["admin"], json={"plate": CAR_A})
        self.assertEqual(blocked.status_code, 409, blocked.text)
        self.assertIn(CAR_B, blocked.json()["detail"])

        found = c.get("/exits/lookup", headers=h["guard"], params={"q": CAR_B})
        self.assertEqual(found.status_code, 200, found.text)
        sid = found.json()[0]["session_id"]
        uncertain = c.post("/exits/confirm", headers=h["guard"], json={
            "session_id": sid, "outcome": "UNCERTAIN", "reason": "boom opened by hand", "identified_by": "PLATE"})
        self.assertEqual(uncertain.status_code, 200, uncertain.text)
        occ_id = uncertain.json()["exit"]["occupancy"]["id"]
        denied = c.post("/exits/reconcile", headers=h["guard"], json={
            "occupancy_id": occ_id, "decision": "RELEASE", "reason": "trying"})
        self.assertEqual(denied.status_code, 403)
        blocked_confirm = c.post("/exits/confirm", headers=h["guard"], json={
            "session_id": sid, "outcome": "LEFT", "reason": "it left"})
        self.assertEqual(blocked_confirm.status_code, 409)
        ok = c.post("/exits/reconcile", headers=h["boss"], json={
            "occupancy_id": occ_id, "decision": "RELEASE", "reason": "CCTV confirms exit"})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(c.post("/sessions", headers=h["admin"], json={"plate": CAR_A}).status_code, 200)
        trail = c.get("/exits/confirmations", headers=h["guard"], params={"session_id": sid}).json()
        self.assertEqual([t["action"] for t in trail], ["SUPERVISOR_RELEASED", "MANUAL_EXIT_UNCERTAIN"])

    def test_visitor_pass_api(self):
        c, h = self.client, self.h
        made = c.post("/visitor-passes", headers=h["guard"], json={"plate": "T404VIS", "visitor_name": "Courier",
                                                                   "hours": 2, "max_entries": 1})
        self.assertEqual(made.status_code, 200, made.text)
        self.assertEqual(made.json()["state"], "VALID")
        looked = c.get("/vehicles/lookup/T404VIS", headers=h["admin"]).json()
        self.assertEqual(looked["kind"], "VISITOR")
        revoked = c.post(f"/visitor-passes/{made.json()['id']}/revoke", headers=h["guard"], json={"reason": "left"})
        self.assertEqual(revoked.json()["state"], "REVOKED")
        self.assertEqual(c.get("/vehicles/lookup/T404VIS", headers=h["admin"]).json()["kind"], "CASUAL")


def _race(session_factory, plates: list[str], round_no: int = 0) -> list[str]:
    """Each thread creates a visit for one linked plate at the same moment."""
    from app.services.access import lookup_entitlement

    barrier = threading.Barrier(len(plates))
    results: list[str] = []
    lock = threading.Lock()

    def worker(i: int, plate: str) -> None:
        db = session_factory()
        try:
            ent = lookup_entitlement(db, plate, site_id=1, strict=True)
            db.rollback()
            barrier.wait(timeout=10)
            try:
                _row, created = start_entry(db, plate=plate, event_id=f"race-{round_no}-{i}-{plate}", site_id=1, gate_id=1,
                                            camera_id=100, parker_kind=ent.kind, policy=WAIT, entitlement=ent)
                outcome = "created" if created else "duplicate"
            except vg.GroupOccupied:
                outcome = "occupied"
            except Exception as exc:  # a locked database counts as refused, never as admitted
                db.rollback()
                outcome = f"error:{type(exc).__name__}"
        finally:
            db.close()
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker, args=(i, p)) for i, p in enumerate(plates)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    return results


class ConcurrencySqliteTests(unittest.TestCase):
    def test_8_simultaneous_threads_one_winner_sqlite_file(self):
        folder = tempfile.mkdtemp()
        engine = create_engine(f"sqlite:///{os.path.join(folder, 'race.db')}", connect_args={"timeout": 15})
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        try:
            with factory() as db:
                seed(db)
            for round_no in range(5):
                results = _race(factory, [CAR_A, CAR_B], round_no)
                self.assertEqual(results.count("created"), 1, results)
                with factory() as db:
                    held = svc.held_occupancies(db, 1)
                    self.assertEqual(len(held), 1)
                    live = db.scalars(select(ParkingSession).where(ParkingSession.status != "CLOSED")).all()
                    self.assertEqual(len(live), 1)
                    svc.confirm_manual_exit(db, session_id=live[0].id, user=db.get(User, 10), reason="test reset")
        finally:
            engine.dispose()


@unittest.skipUnless(os.environ.get("ZIRP_TEST_POSTGRES_URL"), "set ZIRP_TEST_POSTGRES_URL to a disposable PostgreSQL database")
class ConcurrencyPostgresTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(os.environ["ZIRP_TEST_POSTGRES_URL"], pool_size=12, max_overflow=4)
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        with self.factory() as db:
            seed(db)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_8_simultaneous_lanes_one_winner_postgres(self):
        for round_no in range(10):
            results = _race(self.factory, [CAR_A, CAR_B, CAR_A, CAR_B], round_no)
            self.assertEqual(results.count("created"), 1, results)
            with self.factory() as db:
                live = db.scalars(select(ParkingSession).where(ParkingSession.status != "CLOSED")).all()
                self.assertEqual(len(live), 1)
                svc.confirm_manual_exit(db, session_id=live[0].id, user=db.get(User, 10), reason="reset")


if __name__ == "__main__":
    unittest.main()
