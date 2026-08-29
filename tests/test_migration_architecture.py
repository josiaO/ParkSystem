from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.core.plate import apply_site_plate, normalize_plate, validate_plate
from app.domain.devices import DEFAULT_CAMERA_ADAPTER
from app.domain.flags import DEFAULT_FLAGS, LIVE_VIEW_DIRECT_LEGACY
from app.infrastructure.hardware.cameras import camera_adapter_for
from app.infrastructure.hardware.gates import live_gate_adapter
from app.infrastructure.media import registry as media_registry
from app.infrastructure.recognition import list_recognition_providers, normalize_event, recognition_provider_for
from app.services.flags import flags
from app.services.lane_status import camera_operator_status
from app.services.media_gateway import LocalMediaGateway
from app.services.ocr_policy import fusion_mode
from app.services.site_policy import format_money, site_policy
from app.services import mediamtx


def _cam(**overrides):
    fields = {
        "id": 1,
        "name": "1# Entry",
        "ip_address": "192.168.1.144",
        "sdk_port": 30000,
        "username": "admin",
        "password_secret": "admin",
        "rtsp_url": "",
        "sdk_handle": 7,
        "adapter_id": "hvx",
        "connection_mode": "DIRECT",
        "enabled": True,
        "gate_id": 1,
        "lane_direction": "ENTRY",
        "status": "SDK_CONNECTED",
        "recognition_mode": "",
        "gate": type("Gate", (), {"name": "1#", "enabled": True, "mode": "COMMISSIONING"})(),
    }
    fields.update(overrides)
    return type("Camera", (), fields)()


class PlatePolicyTests(unittest.TestCase):
    def test_default_normalisation_is_country_neutral(self):
        self.assertEqual(normalize_plate("T 285 DQP"), "T285DQP")
        self.assertEqual(normalize_plate("abc-12"), "ABC12")
        none = validate_plate("ABC12", "NONE")
        self.assertTrue(none["ok"])
        tz = validate_plate("ABC12", "TZ")
        self.assertFalse(tz["ok"])
        self.assertTrue(validate_plate("T285DQP", "TZ")["ok"])
        applied = apply_site_plate("k  aa  123a", normalization="ALNUM_UPPER", validation="NONE")
        self.assertEqual(applied["normalized_plate"], "KAA123A")
        self.assertEqual(applied["validation_result"], "ACCEPTED")


class FlagAndSiteTests(unittest.TestCase):
    def test_defaults_keep_working_path_authoritative(self):
        cfg = flags()
        self.assertFalse(cfg["media_gateway_enabled"])
        self.assertFalse(cfg["fastalpr_new_pipeline_enabled"])
        self.assertFalse(cfg["webrtc_live_enabled"])
        self.assertTrue(cfg["native_alpr_enabled"])
        self.assertEqual(cfg["live_view_provider"], LIVE_VIEW_DIRECT_LEGACY)
        self.assertEqual(DEFAULT_FLAGS["live_view_provider"], LIVE_VIEW_DIRECT_LEGACY)

    def test_site_policy_currency_is_configurable(self):
        policy = site_policy()
        self.assertIn("timezone", policy)
        self.assertTrue(policy["currency"])
        self.assertIn(policy["language"], {"en", "sw", "ar", "fr", "pt"})
        label = format_money(1000, {"currency": "USD", "currency_precision": 2})
        self.assertIn("USD", label)


class RecognitionWrapTests(unittest.TestCase):
    def test_providers_are_registered(self):
        self.assertIn("hvx_native", list_recognition_providers())
        self.assertIn("fastalpr", list_recognition_providers())
        event = normalize_event(camera_id=1, plate="T 285 DQP", plate_raw="T 285 DQP", source="HVX_NATIVE", confidence=0.9)
        self.assertEqual(event["normalized_plate"], "T285DQP")
        self.assertEqual(event["source"], "HVX_NATIVE")
        self.assertTrue(event["event_id"])

    def test_native_provider_wraps_existing_mapping(self):
        provider = recognition_provider_for("hvx_native")
        result = asyncio.run(provider.process({
            "camera_id": 4,
            "capture": {"plate": "T 349 DLG", "score": 91},
        }))
        self.assertEqual(result["normalized_plate"], "T349DLG")
        self.assertEqual(result["source"], "HVX_NATIVE")
        self.assertGreater(result["confidence"], 0.8)

    def test_fusion_aliases(self):
        cam = _cam(recognition_mode="HYBRID")
        self.assertEqual(fusion_mode(cam), "HYBRID")
        self.assertEqual(fusion_mode(_cam(recognition_mode="FASTALPR_ONLY")), "LOCAL_ONLY")


class AdapterContractTests(unittest.TestCase):
    def test_hvx_still_default_and_can_disconnect(self):
        adapter = camera_adapter_for(_cam())
        self.assertEqual(adapter.id, DEFAULT_CAMERA_ADAPTER)
        with patch("app.infrastructure.hardware.cameras.hvx.HVXHostClient") as host:
            host.return_value.disconnect = AsyncMock(return_value={"ok": True})
            result = asyncio.run(adapter.disconnect(_cam()))
        self.assertTrue(result.get("ok") or result.get("disconnected"))

    def test_gate_adapter_has_close_and_state(self):
        adapter = live_gate_adapter()
        closed = asyncio.run(adapter.close(type("G", (), {"name": "1#"})(), [], "test"))
        self.assertTrue(hasattr(closed, "ok"))
        state = asyncio.run(adapter.get_state())
        self.assertIn("state", state)


class MediaGatewayWrapTests(unittest.TestCase):
    def test_local_gateway_implements_directive_methods(self):
        gw = LocalMediaGateway()
        health = asyncio.run(gw.register_source(9, {"ip": "127.0.0.1", "rtsp_url": ""}))
        self.assertEqual(health["camera_id"], 9)
        live = asyncio.run(gw.get_live_endpoint(9))
        self.assertIn("live.mjpeg", live["path"])
        metrics = asyncio.run(gw.metrics(9))
        self.assertIn("connection_state", metrics)
        asyncio.run(gw.unregister_source(9))

    def test_mediamtx_missing_binary_does_not_claim_ok(self):
        self.assertFalse(mediamtx.health()["ok"] or mediamtx.running())
        self.assertIn("optional", mediamtx.health()["note"].lower())

    def test_registry_live_endpoint_stays_direct_legacy(self):
        body = asyncio.run(media_registry.get_live_endpoint(1))
        self.assertEqual(body["provider"], "DIRECT_LEGACY")


class OperatorStatusTests(unittest.TestCase):
    def test_operator_copy_is_not_sdk_jargon(self):
        status = camera_operator_status(_cam())
        self.assertEqual(status["camera"], "Online")
        self.assertIn(status["live_video"], {"Online", "Offline", "Degraded"})
        self.assertEqual(status["plate_recognition"], "Ready")
        self.assertNotIn("NetSDK", status["camera"])
        self.assertNotIn("RTSP", status["barrier"])


    def test_required_docs_exist(self):
        root = __import__("pathlib").Path(__file__).resolve().parents[1] / "docs"
        for name in (
            "MEDIA-ARCHITECTURE.md", "CAMERA-ADAPTERS.md", "MEDIAMTX-INTEGRATION.md",
            "FASTALPR-PIPELINE.md", "NATIVE-ALPR.md", "CAMERA-ONBOARDING.md",
            "STREAM-PROFILES.md", "CAMERA-CAPABILITY-MATRIX.md", "ADDING-A-CAMERA-VENDOR.md",
            "ADDING-A-RECOGNITION-PROVIDER.md", "GATE-ADAPTERS.md", "MIGRATION-AND-ROLLBACK.md",
            "CAMERA-TROUBLESHOOTING.md",
        ):
            self.assertTrue((root / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
