"""§9 optional AI review: disabled by default, bounded, never a gate/plate authority."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api_main import app, ensure_roles
from app.config import settings
from app.db import Base, get_db, set_session_factory
from app.domain.ai_review import (
    REASON_DISAGREEMENT,
    REASON_LOW_CONFIDENCE,
    IncidentSummaryRequest,
    VehicleReview,
    VehicleReviewRequest,
    judge,
)
from app.infrastructure import ai as ai_registry
from app.infrastructure.ai.gemini import GeminiAIReviewProvider
from app.models import Camera, Role, Site, User, UserRole, VehicleCapture
from app.security import hash_password
from app.services import ai_review
from app.services.circuit import CircuitBreaker

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"


def gemini_reply(payload: dict | str) -> dict:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return {"candidates": [{"content": {"parts": [{"text": text}]}}], "usageMetadata": {"totalTokenCount": 42}}


class FakeHTTP:
    def __init__(self, status=200, body=None, raise_exc=None):
        self.status, self.body, self.raise_exc = status, body, raise_exc
        self.calls: list[tuple[str, dict]] = []

    async def __call__(self, path, body):
        self.calls.append((path, body))
        if self.raise_exc:
            raise self.raise_exc
        return self.status, self.body


def _provider(http: FakeHTTP) -> GeminiAIReviewProvider:
    provider = GeminiAIReviewProvider(http=http)
    provider.breaker = CircuitBreaker(name="ai-gemini-test")
    return provider


def _request(**over) -> VehicleReviewRequest:
    base = dict(camera_id=1, capture_id=None, reason=REASON_LOW_CONFIDENCE, plate_candidates=["T123ABC"],
                crop_jpeg=JPEG, vehicle_jpeg=JPEG, synthetic=True)
    base.update(over)
    return VehicleReviewRequest(**base)


class JudgeTests(unittest.TestCase):
    def test_fusion_rule(self):
        r = judge(VehicleReview(readable=True, plate_candidate="t-123 abc"), ["T123ABC"])
        self.assertEqual((r.verdict, r.agrees_with, r.plate_candidate), ("supporting", "T123ABC", "T123ABC"))
        r = judge(VehicleReview(readable=True, plate_candidate="T123ABD"), ["T123ABC", "T128ABC"])
        self.assertEqual(r.verdict, "conflicting")
        r = judge(VehicleReview(readable=False, plate_candidate=""), ["T123ABC"])
        self.assertEqual(r.verdict, "unreadable")
        r = judge(VehicleReview(readable=True, plate_candidate="T123ABC", error="timeout"), ["T123ABC"])
        self.assertEqual(r.verdict, "unavailable")

    def test_review_reason(self):
        self.assertEqual(ai_review.review_reason({"plate": "T1", "confidence": 0.4}), REASON_LOW_CONFIDENCE)
        self.assertEqual(ai_review.review_reason({"plate": "T1", "confidence": 0.95}), "")
        self.assertEqual(ai_review.review_reason({"plate": "T1", "needs_review": True, "native_plate": "A", "local_plate": "B"}), REASON_DISAGREEMENT)
        self.assertEqual(ai_review.review_reason({"plate": "", "confidence": 0.1}), "")


class GeminiProviderTests(unittest.TestCase):
    def setUp(self):
        self._p = patch.multiple(settings, gemini_api_key="AIzaFakeKey000000000000000000000", ai_model="gemini-2.5-flash-lite",
                                 ai_send_vehicle_image=False)
        self._p.start()

    def tearDown(self):
        self._p.stop()

    def test_unconfigured_is_unavailable_without_network(self):
        with patch.object(settings, "gemini_api_key", ""):
            http = FakeHTTP()
            provider = _provider(http)
            review = asyncio.run(provider.review_vehicle_event(_request()))
            self.assertFalse(provider.health()["available"])
        self.assertEqual(review.verdict, "unavailable")
        self.assertIn("not configured", review.error)
        self.assertEqual(http.calls, [])

    def test_supporting_read_sends_only_crop_and_schema(self):
        http = FakeHTTP(body=gemini_reply({"readable": True, "plate_candidate": "T 123 ABC", "vehicle_type": "car", "vehicle_color": "white"}))
        provider = _provider(http)
        review = asyncio.run(provider.review_vehicle_event(_request()))
        self.assertEqual(review.verdict, "supporting")
        self.assertEqual(review.plate_candidate, "T123ABC")
        self.assertEqual(review.model, "gemini-2.5-flash-lite")
        path, body = http.calls[0]
        self.assertEqual(path, "models/gemini-2.5-flash-lite:generateContent")
        parts = body["contents"][0]["parts"]
        self.assertEqual(len(parts), 2)  # prompt + crop only; vehicle image not requested
        self.assertEqual(parts[1]["inline_data"]["mime_type"], "image/jpeg")
        self.assertEqual(body["generationConfig"]["responseMimeType"], "application/json")
        self.assertIn("plate_candidate", body["generationConfig"]["responseSchema"]["properties"])
        self.assertNotIn("confidence", json.dumps(body["generationConfig"]))  # schema never asks for a fake probability
        self.assertNotIn("AIzaFakeKey", json.dumps(body))

    def test_vehicle_image_only_when_requested(self):
        http = FakeHTTP(body=gemini_reply({"readable": True, "plate_candidate": "X"}))
        review = asyncio.run(_provider(http).review_vehicle_event(_request(want_vehicle_attributes=True)))
        self.assertEqual(len(http.calls[0][1]["contents"][0]["parts"]), 3)
        self.assertEqual(review.verdict, "conflicting")

    def test_unreadable_and_invalid_json(self):
        review = asyncio.run(_provider(FakeHTTP(body=gemini_reply({"readable": False, "plate_candidate": ""}))).review_vehicle_event(_request()))
        self.assertEqual(review.verdict, "unreadable")
        review = asyncio.run(_provider(FakeHTTP(body=gemini_reply("not json"))).review_vehicle_event(_request()))
        self.assertEqual(review.verdict, "unavailable")
        self.assertIn("invalid JSON", review.error)
        review = asyncio.run(_provider(FakeHTTP(body={"candidates": []})).review_vehicle_event(_request()))
        self.assertIn("no text", review.error)

    def test_quota_and_outage_trip_breaker_but_bad_request_does_not(self):
        provider = _provider(FakeHTTP(status=429, body={"error": {"message": "quota"}}))
        review = asyncio.run(provider.review_vehicle_event(_request()))
        self.assertEqual(review.verdict, "unavailable")
        self.assertEqual(provider.breaker.failures, 1)
        provider = _provider(FakeHTTP(raise_exc=TimeoutError()))
        asyncio.run(provider.review_vehicle_event(_request()))
        self.assertEqual(provider.breaker.failures, 1)
        provider = _provider(FakeHTTP(status=400, body={"error": {"message": "bad schema"}}))
        review = asyncio.run(provider.review_vehicle_event(_request()))
        self.assertIn("bad schema", review.error)
        self.assertEqual(provider.breaker.failures, 0)

    def test_open_breaker_skips_network(self):
        http = FakeHTTP(body=gemini_reply({"readable": True, "plate_candidate": "T123ABC"}))
        provider = _provider(http)
        for _ in range(provider.breaker.failure_threshold):
            provider.breaker.failure()
        review = asyncio.run(provider.review_vehicle_event(_request()))
        self.assertEqual(http.calls, [])
        self.assertIn("circuit open", review.error)

    def test_incident_summary(self):
        http = FakeHTTP(body=gemini_reply("Two reads of T123ABC at the entry within one minute."))
        summary = asyncio.run(_provider(http).summarize_incident(IncidentSummaryRequest(events=[{"plate": "T123ABC"}], question="what happened")))
        self.assertIn("T123ABC", summary.text)
        self.assertNotIn("responseSchema", http.calls[0][1]["generationConfig"])

    def test_no_image_never_calls(self):
        http = FakeHTTP(body=gemini_reply({"readable": True, "plate_candidate": "T123ABC"}))
        review = asyncio.run(_provider(http).review_vehicle_event(_request(crop_jpeg=b"", vehicle_jpeg=b"")))
        self.assertEqual(http.calls, [])
        self.assertEqual(review.error, "no image")


class StubProvider:
    provider_id = "stub"

    def __init__(self, plate="T123ABC", delay=0.0):
        self.plate, self.delay, self.calls = plate, delay, 0

    async def review_vehicle_event(self, request):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        return judge(VehicleReview(readable=True, plate_candidate=self.plate, provider="stub"), request.candidates())

    async def summarize_incident(self, request):
        self.calls += 1
        from app.domain.ai_review import IncidentSummary
        return IncidentSummary(text=f"{len(request.events)} events", provider="stub")

    def health(self):
        return {"provider_id": "stub", "available": True}


class ServiceLimitTests(unittest.TestCase):
    def setUp(self):
        ai_review.reset()
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        set_session_factory(self.Session)
        self.stub = StubProvider()
        self._prov = patch.object(ai_registry, "provider_for", lambda *_a, **_k: self.stub)
        self._prov.start()
        self._is_enabled = patch("app.services.modules.is_enabled", return_value=True)
        self._is_enabled.start()

    def tearDown(self):
        self._prov.stop()
        self._is_enabled.stop()
        set_session_factory(None)
        self.engine.dispose()
        ai_review.reset()

    def _capture(self, **over) -> dict:
        base = {"id": 1, "camera_id": 1, "plate": "T123ABC", "confidence": 0.4, "source": "simulation"}
        base.update(over)
        return base

    def test_disabled_by_default_never_schedules(self):
        self.assertFalse(settings.ai_enabled)
        async def go():
            return ai_review.schedule_capture_review(self._capture(), crop=JPEG, jpeg=JPEG)
        self.assertIsNone(asyncio.run(go()))
        self.assertEqual(ai_review.stats()["skipped_disabled"], 1)
        self.assertEqual(self.stub.calls, 0)

    def test_privacy_gate_blocks_real_imagery_until_accepted(self):
        with patch.multiple(settings, ai_enabled=True, ai_data_treatment_accepted=False):
            async def go():
                return ai_review.schedule_capture_review(self._capture(source="hybrid"), crop=JPEG, jpeg=JPEG)
            self.assertIsNone(asyncio.run(go()))
            self.assertEqual(ai_review.stats()["skipped_privacy"], 1)
            async def go_synthetic():
                task = ai_review.schedule_capture_review(self._capture(source="simulation"), crop=JPEG, jpeg=JPEG)
                return await task if task else None
            review = asyncio.run(go_synthetic())
            self.assertEqual(review.verdict, "supporting")
        with patch.multiple(settings, ai_enabled=True, ai_data_treatment_accepted=True, ai_min_interval_seconds=0.0):
            async def go_real():
                task = ai_review.schedule_capture_review(self._capture(source="hybrid"), crop=JPEG, jpeg=JPEG)
                return await task
            self.assertEqual(asyncio.run(go_real()).verdict, "supporting")

    def test_budget_interval_and_result_persistence(self):
        with self.Session() as db:
            db.add(Site(id=1, name="A"))
            db.add(Camera(id=1, name="Cam", ip_address="1.1.1.1"))
            db.add(VehicleCapture(id=1, camera_id=1, plate="T123ABC", confidence=0.4, source="simulation"))
            db.add(VehicleCapture(id=2, camera_id=1, plate="T123ABC", confidence=0.4, source="simulation"))
            db.commit()
        with patch.multiple(settings, ai_enabled=True, ai_daily_request_cap=1, ai_min_interval_seconds=0.0):
            ai_review.reset()
            async def go():
                first = ai_review.schedule_capture_review(self._capture(id=1), crop=JPEG, jpeg=JPEG)
                await first
                second = ai_review.schedule_capture_review(self._capture(id=2), crop=JPEG, jpeg=JPEG)
                return first.result(), second
            review, second = asyncio.run(go())
            self.assertEqual(review.verdict, "supporting")
            self.assertIsNone(second)
            self.assertEqual(ai_review.stats()["skipped_budget"], 1)
            self.assertEqual(self.stub.calls, 1)
        with self.Session() as db:
            row = db.get(VehicleCapture, 1)
            self.assertEqual(row.ai_review["verdict"], "supporting")
            self.assertEqual(row.plate, "T123ABC")  # never rewritten
            self.assertIsNone(db.get(VehicleCapture, 2).ai_review)
        with patch.multiple(settings, ai_enabled=True, ai_min_interval_seconds=60.0):
            ai_review.reset()
            async def go2():
                a = ai_review.schedule_capture_review(self._capture(id=1), crop=JPEG, jpeg=JPEG)
                b = ai_review.schedule_capture_review(self._capture(id=2), crop=JPEG, jpeg=JPEG)
                if a:
                    await a
                return a, b
            a, b = asyncio.run(go2())
            self.assertIsNotNone(a)
            self.assertIsNone(b)
            self.assertEqual(ai_review.stats()["skipped_interval"], 1)

    def test_timeout_yields_unavailable_and_conflict_never_edits_plate(self):
        self.stub.delay = 0.3
        with patch.multiple(settings, ai_enabled=True, ai_timeout_seconds=-0.95):
            review = asyncio.run(ai_review.run_review(_request(), persist=False))
        self.assertEqual((review.verdict, review.error), ("unavailable", "timeout"))
        self.stub.delay = 0.0
        self.stub.plate = "T999ZZZ"
        with patch.object(settings, "ai_enabled", True):
            review = asyncio.run(ai_review.run_review(_request(), persist=False))
        self.assertEqual(review.verdict, "conflicting")
        self.assertEqual(ai_review.stats()["conflicting"], 1)

    def test_health_reports_no_gate_authority(self):
        body = ai_review.health()
        self.assertFalse(body["enabled"])
        self.assertIs(body["gate_authority"], False)
        self.assertEqual(body["provider"]["provider_id"], "none")


class AIApiTests(unittest.TestCase):
    def setUp(self):
        ai_review.reset()
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

        def override_get_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        set_session_factory(self.Session)
        with self.Session() as db:
            ensure_roles(db)
            db.add(Site(id=1, name="A"))
            admin_role = db.scalar(select(Role).where(Role.name == "Admin"))
            user = User(username="admin", full_name="Test Admin", password_hash=hash_password("correct-horse"))
            db.add(user)
            db.flush()
            db.add(UserRole(user_id=user.id, role_id=admin_role.id))
            db.add(Camera(id=1, name="Cam", ip_address="1.1.1.1"))
            db.add(VehicleCapture(id=5, camera_id=1, plate="T123ABC", plate_raw="T123ABC", confidence=0.5, source="simulation"))
            db.commit()
        self.stub = StubProvider()
        self._prov = patch.object(ai_registry, "provider_for", lambda *_a, **_k: self.stub)
        self._prov.start()
        self.client = TestClient(app)
        token = self.client.post("/auth/login", json={"username": "admin", "password": "correct-horse"}).json()["token"]
        self.headers = {"Authorization": f"Bearer {token}"}

    def tearDown(self):
        self._prov.stop()
        self.client.close()
        set_session_factory(None)
        app.dependency_overrides.clear()
        self.engine.dispose()
        ai_review.reset()

    def test_disabled_endpoints(self):
        res = self.client.get("/ai/health", headers=self.headers)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertFalse(res.json()["enabled"])
        self.assertEqual(self.client.post("/ai/review/5", headers=self.headers).status_code, 409)
        self.assertEqual(self.client.post("/ai/incidents/summary", json={"plate": "T123ABC"}, headers=self.headers).status_code, 409)
        self.assertEqual(self.stub.calls, 0)

    def test_manual_review_and_summary_when_enabled(self):
        with patch.multiple(settings, ai_enabled=True, ai_data_treatment_accepted=False):
            res = self.client.post("/ai/review/5", headers=self.headers)
            self.assertEqual(res.status_code, 200, res.text)
            body = res.json()
            self.assertTrue(body["ok"])
            self.assertEqual(body["review"]["verdict"], "supporting")
            res = self.client.get("/captures", headers=self.headers)
            items = res.json()
            self.assertEqual(items[0]["ai_review"]["verdict"], "supporting")
            self.assertEqual(items[0]["plate"], "T123ABC")
            self.assertEqual(self.client.post("/ai/review/999", headers=self.headers).status_code, 404)
            res = self.client.post("/ai/incidents/summary", json={"plate": "T123ABC", "question": "why"}, headers=self.headers)
            self.assertEqual(res.status_code, 200, res.text)
            self.assertEqual(res.json()["text"], "1 events")
            self.assertEqual(self.client.get("/ai/reviews", headers=self.headers).json()["stats"]["supporting"], 1)

    def test_module_gating_hides_ai_routes(self):
        from app.services.modules import apply_profile
        with self.Session() as db:
            apply_profile(db, "LPR_ONLY")
        self.assertEqual(self.client.get("/ai/health", headers=self.headers).status_code, 200)
        with patch("app.services.modules.is_enabled", return_value=False):
            self.assertEqual(self.client.get("/ai/health", headers=self.headers).status_code, 404)


if __name__ == "__main__":
    unittest.main()
