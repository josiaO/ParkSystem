"""ONVIF Media2 / Profile M: capability-driven discovery and plate-event normalisation.

A fake SOAP device answers the same operations a real camera would; nothing
here talks to hardware. Real-camera verification remains HARDWARE-REQUIRED.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services import onvif_discover as od
from app.services import onvif_events as oe
from app.services import onvif_runtime
from app.services.onvif_profile import apply_discovery, set_events_enabled
from app.services.stream_roles import public_profiles

USER, PW = "admin", "s3cret"


def soap(body: str) -> str:
    return f'<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Body>{body}</s:Body></s:Envelope>'


SERVICES = soap(f"""<tds:GetServicesResponse xmlns:tds="{od.NS_DEVICE}">
  <tds:Service><tds:Namespace>{od.NS_DEVICE}</tds:Namespace><tds:XAddr>http://10.0.0.9/onvif/device_service</tds:XAddr></tds:Service>
  <tds:Service><tds:Namespace>{od.NS_MEDIA1}</tds:Namespace><tds:XAddr>http://10.0.0.9/onvif/media</tds:XAddr></tds:Service>
  <tds:Service><tds:Namespace>{od.NS_MEDIA2}</tds:Namespace><tds:XAddr>http://10.0.0.9/onvif/media2</tds:XAddr></tds:Service>
  <tds:Service><tds:Namespace>{od.NS_EVENTS}</tds:Namespace><tds:XAddr>http://10.0.0.9/onvif/events</tds:XAddr></tds:Service>
  <tds:Service><tds:Namespace>{od.NS_ANALYTICS}</tds:Namespace><tds:XAddr>http://10.0.0.9/onvif/analytics</tds:XAddr></tds:Service>
</tds:GetServicesResponse>""")

PROFILES2 = soap(f"""<tr2:GetProfilesResponse xmlns:tr2="{od.NS_MEDIA2}" xmlns:tt="{od.NS_SCHEMA}">
  <tr2:Profiles token="P1" fixed="true"><tr2:Name>MainStream</tr2:Name>
    <tr2:Configurations><tr2:VideoEncoder token="VE1"><tt:Encoding>H265</tt:Encoding>
      <tt:Resolution><tt:Width>2560</tt:Width><tt:Height>1440</tt:Height></tt:Resolution>
      <tt:RateControl><tt:FrameRateLimit>25.0</tt:FrameRateLimit><tt:BitrateLimit>4096</tt:BitrateLimit></tt:RateControl>
      <tt:GovLength>50</tt:GovLength></tr2:VideoEncoder>
      <tr2:Metadata token="MD1"><tt:Analytics>true</tt:Analytics></tr2:Metadata>
    </tr2:Configurations></tr2:Profiles>
  <tr2:Profiles token="P2"><tr2:Name>SubStream</tr2:Name>
    <tr2:Configurations><tr2:VideoEncoder token="VE2"><tt:Encoding>H264</tt:Encoding>
      <tt:Resolution><tt:Width>1280</tt:Width><tt:Height>720</tt:Height></tt:Resolution>
      <tt:RateControl><tt:FrameRateLimit>15</tt:FrameRateLimit></tt:RateControl></tr2:VideoEncoder>
    </tr2:Configurations></tr2:Profiles>
</tr2:GetProfilesResponse>""")

EVENT_PROPS = soap(f"""<tev:GetEventPropertiesResponse xmlns:tev="{od.NS_EVENTS}" xmlns:wstop="http://docs.oasis-open.org/wsn/t-1" xmlns:tns1="http://www.onvif.org/ver10/topics" xmlns:tt="{od.NS_SCHEMA}">
  <wstop:TopicSet>
    <tns1:Device><Trigger><DigitalInput wstop:topic="true"/></Trigger></tns1:Device>
    <tns1:RuleEngine><LicensePlateDetector><LicensePlate wstop:topic="true"><tt:MessageDescription/></LicensePlate></LicensePlateDetector>
      <CellMotionDetector><Motion wstop:topic="true"/></CellMotionDetector></tns1:RuleEngine>
  </wstop:TopicSet>
</tev:GetEventPropertiesResponse>""")

EVENT_PROPS_NO_LPR = soap(f"""<tev:GetEventPropertiesResponse xmlns:tev="{od.NS_EVENTS}" xmlns:wstop="http://docs.oasis-open.org/wsn/t-1" xmlns:tns1="http://www.onvif.org/ver10/topics">
  <wstop:TopicSet><tns1:RuleEngine><CellMotionDetector><Motion wstop:topic="true"/></CellMotionDetector></tns1:RuleEngine></wstop:TopicSet>
</tev:GetEventPropertiesResponse>""")

PULL = soap(f"""<tev:PullMessagesResponse xmlns:tev="{od.NS_EVENTS}" xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2" xmlns:tt="{od.NS_SCHEMA}">
  <tev:CurrentTime>2026-09-30T10:00:05Z</tev:CurrentTime><tev:TerminationTime>2026-09-30T10:01:00Z</tev:TerminationTime>
  <wsnt:NotificationMessage>
    <wsnt:Topic Dialect="...">tns1:RuleEngine/LicensePlateDetector/LicensePlate</wsnt:Topic>
    <wsnt:Message><tt:Message UtcTime="2026-09-30T10:00:04Z" PropertyOperation="Initialized">
      <tt:Source><tt:SimpleItem Name="VideoSourceConfigurationToken" Value="VS1"/></tt:Source>
      <tt:Data><tt:SimpleItem Name="LicensePlate" Value="T 123 ABC"/><tt:SimpleItem Name="Confidence" Value="87"/>
               <tt:SimpleItem Name="Country" Value="TZ"/></tt:Data>
    </tt:Message></wsnt:Message>
  </wsnt:NotificationMessage>
  <wsnt:NotificationMessage>
    <wsnt:Topic Dialect="...">tns1:RuleEngine/CellMotionDetector/Motion</wsnt:Topic>
    <wsnt:Message><tt:Message UtcTime="2026-09-30T10:00:04Z"><tt:Data><tt:SimpleItem Name="IsMotion" Value="true"/></tt:Data></tt:Message></wsnt:Message>
  </wsnt:NotificationMessage>
  <wsnt:NotificationMessage>
    <wsnt:Topic Dialect="...">tns1:RuleEngine/LicensePlateDetector/LicensePlate</wsnt:Topic>
    <wsnt:Message><tt:Message UtcTime="2026-09-30T10:00:05Z">
      <tt:Data><tt:SimpleItem Name="PlateNumber" Value="KBZ 456 Q"/><tt:SimpleItem Name="Likelihood" Value="0.61"/></tt:Data>
    </tt:Message></wsnt:Message>
  </wsnt:NotificationMessage>
</tev:PullMessagesResponse>""")

SUBSCRIBE = soap(f"""<tev:CreatePullPointSubscriptionResponse xmlns:tev="{od.NS_EVENTS}" xmlns:wsa="http://www.w3.org/2005/08/addressing">
  <tev:SubscriptionReference><wsa:Address>http://10.0.0.9/onvif/Subscription?Idx=7</wsa:Address></tev:SubscriptionReference>
  <wsnt:CurrentTime xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2">2026-09-30T10:00:00Z</wsnt:CurrentTime>
  <wsnt:TerminationTime xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2">2026-09-30T10:01:00Z</wsnt:TerminationTime>
</tev:CreatePullPointSubscriptionResponse>""")


def uri_response(uri: str) -> str:
    return soap(f'<tr2:GetStreamUriResponse xmlns:tr2="{od.NS_MEDIA2}"><tr2:Uri>{uri}</tr2:Uri></tr2:GetStreamUriResponse>')


class FakeDevice:
    """Answers SOAP by action name. Records calls for assertions."""

    def __init__(self, *, media2: bool = True, lpr: bool = True):
        self.calls: list[tuple[str, str]] = []
        self.media2 = media2
        self.lpr = lpr
        self.envelopes: list[str] = []

    async def post(self, url, body, *, username, password, action, timeout=3.0, header_extra=""):
        self.calls.append((action.rsplit("/", 1)[-1], url))
        self.envelopes.append(od._envelope(body, action=action, username=username, password=password, header_extra=header_extra))
        op = action.rsplit("/", 1)[-1]
        if op == "GetServices":
            if self.media2:
                return SERVICES
            return SERVICES.replace(f"<tds:Service><tds:Namespace>{od.NS_MEDIA2}</tds:Namespace><tds:XAddr>http://10.0.0.9/onvif/media2</tds:XAddr></tds:Service>", "")
        if op == "GetProfiles" and od.NS_MEDIA2 in action:
            return PROFILES2
        if op == "GetProfiles":
            return soap(f'<trt:GetProfilesResponse xmlns:trt="{od.NS_MEDIA1}"><trt:Profiles token="P1"><Name>Main</Name>'
                        '<VideoEncoderConfiguration><Encoding>H264</Encoding><Width>1920</Width><Height>1080</Height>'
                        '<FrameRateLimit>20</FrameRateLimit></VideoEncoderConfiguration></trt:Profiles></trt:GetProfilesResponse>')
        if op == "GetStreamUri":
            token = "P2" if "<tr2:ProfileToken>P2<" in body or "<trt:ProfileToken>P2<" in body else "P1"
            return uri_response(f"rtsp://10.0.0.9:554/onvif/{token.lower()}")
        if op == "GetSnapshotUri":
            token = "P2" if "P2<" in body else "P1"
            return uri_response(f"http://10.0.0.9/onvif/snapshot/{token.lower()}.jpg")
        if op == "GetEventProperties":
            return EVENT_PROPS if self.lpr else EVENT_PROPS_NO_LPR
        if op == "CreatePullPointSubscription":
            return SUBSCRIBE
        if op == "PullMessages":
            return PULL
        if op in {"RenewRequest", "UnsubscribeRequest"}:
            return soap("<ok/>")
        raise RuntimeError(f"unexpected {op}")


class ParserTests(unittest.TestCase):
    def test_services_and_capability_summary(self):
        services = od.parse_services(SERVICES)
        self.assertEqual(services[od.NS_MEDIA2], "http://10.0.0.9/onvif/media2")
        topics = od.parse_event_topics(EVENT_PROPS)
        self.assertIn("RuleEngine/LicensePlateDetector/LicensePlate", topics)
        self.assertIn("RuleEngine/CellMotionDetector/Motion", topics)
        caps = od.summarize_capabilities(services, topics)
        self.assertTrue(caps["media2"] and caps["events"] and caps["analytics"] and caps["profile_m"])
        self.assertTrue(caps["plate_metadata"])
        self.assertEqual(caps["plate_topics"], ["RuleEngine/LicensePlateDetector/LicensePlate"])
        self.assertEqual(od.capability_flags(caps),
                         ["ONVIF", "ONVIF_MEDIA2", "ONVIF_EVENTS", "ONVIF_PROFILE_M", "ONVIF_PLATE_METADATA"])

    def test_profile_m_without_plate_topics_is_not_lpr(self):
        services = od.parse_services(SERVICES)
        caps = od.summarize_capabilities(services, od.parse_event_topics(EVENT_PROPS_NO_LPR))
        self.assertTrue(caps["profile_m"])
        self.assertFalse(caps["plate_metadata"])
        self.assertNotIn("ONVIF_PLATE_METADATA", od.capability_flags(caps))

    def test_media2_profiles_parse_encoder_and_metadata(self):
        rows = od.parse_profiles_media2(PROFILES2)
        self.assertEqual([r["token"] for r in rows], ["P1", "P2"])
        main = rows[0]
        self.assertEqual((main["codec"], main["width"], main["height"], main["fps"], main["gop"]), ("h265", 2560, 1440, 25.0, 50))
        self.assertTrue(main["has_metadata"])
        self.assertFalse(rows[1]["has_metadata"])
        self.assertEqual(rows[1]["media_version"], 2)

    def test_ws_security_header_present_and_password_not_in_clear(self):
        env = od._envelope("<x/>", action="a", username="admin", password="s3cret")
        self.assertIn("wsse:UsernameToken", env)
        self.assertIn("PasswordDigest", env)
        self.assertNotIn("s3cret", env)
        self.assertNotIn("wsse:Security", od._envelope("<x/>", action="a"))

    def test_notification_messages_normalise_plate_reads_only(self):
        events = oe.parse_notification_messages(PULL)
        self.assertEqual(len(events), 3)
        first, motion, second = events
        self.assertEqual(first["plate_raw"], "T 123 ABC")
        self.assertAlmostEqual(first["confidence"], 0.87)
        self.assertEqual(first["country"], "TZ")
        self.assertEqual(first["at"], "2026-09-30T10:00:04+00:00")
        self.assertEqual(motion["plate_raw"], "")
        self.assertIsNone(oe.event_to_capture(motion))
        self.assertEqual(second["plate_raw"], "KBZ 456 Q")
        self.assertAlmostEqual(second["confidence"], 0.61)
        captures = oe.plate_captures(PULL)
        self.assertEqual([c["plate"] for c in captures], ["T 123 ABC", "KBZ 456 Q"])
        self.assertEqual(captures[0]["source"], oe.SOURCE)
        self.assertTrue(captures[0]["have_vehicle"])
        self.assertNotEqual(captures[0]["image_id"], captures[1]["image_id"])
        self.assertEqual(captures[0]["image_id"], oe.plate_captures(PULL)[0]["image_id"], "image id must be stable")

    def test_capture_feeds_existing_recognition_contract(self):
        from app.services.camera_lpr import native_from_sdk_capture

        native = native_from_sdk_capture(oe.plate_captures(PULL)[0])
        self.assertEqual(native["plate"], "T123ABC")
        self.assertEqual(native["plate_raw"], "T 123 ABC")
        self.assertEqual(native["source"], oe.SOURCE)
        self.assertGreater(native["confidence"], 0)
        self.assertTrue(native["have_vehicle"])

    def test_subscription_reference(self):
        address, termination = oe.parse_subscription_reference(SUBSCRIBE)
        self.assertEqual(address, "http://10.0.0.9/onvif/Subscription?Idx=7")
        self.assertEqual(termination, "2026-09-30T10:01:00Z")


class DiscoveryTests(unittest.TestCase):
    def _discover(self, device: FakeDevice):
        with patch.object(od, "_post", device.post):
            return asyncio.run(od.discover_onvif("10.0.0.9", USER, PW, timeout=0.5))

    def test_media2_preferred_with_stream_and_snapshot_uris(self):
        device = FakeDevice()
        found = self._discover(device)
        self.assertTrue(found["ok"])
        self.assertEqual(found["media_version"], 2)
        self.assertEqual(found["media_url"], "http://10.0.0.9/onvif/media2")
        ops = [op for op, _ in device.calls]
        self.assertIn("GetServices", ops)
        self.assertIn("GetStreamUri", ops)
        self.assertIn("GetSnapshotUri", ops)
        self.assertIn("GetEventProperties", ops)
        media2_calls = [url for op, url in device.calls if op in {"GetProfiles", "GetStreamUri", "GetSnapshotUri"}]
        self.assertTrue(all(url.endswith("/media2") for url in media2_calls), media2_calls)
        p1 = found["profiles"][0]
        self.assertEqual(p1["uri"], "rtsp://admin:s3cret@10.0.0.9:554/onvif/p1")
        self.assertNotIn("s3cret", p1["uri_redacted"])
        self.assertIn("10.0.0.9:554/onvif/p1", p1["uri_redacted"])
        self.assertEqual(p1["snapshot_uri"], "http://admin:s3cret@10.0.0.9/onvif/snapshot/p1.jpg")
        self.assertNotIn("s3cret", p1["snapshot_uri_redacted"])
        self.assertEqual(found["capabilities"]["plate_topics"], ["RuleEngine/LicensePlateDetector/LicensePlate"])
        self.assertEqual(found["events_url"], "http://10.0.0.9/onvif/events")
        self.assertEqual(found["services"]["media2"], "http://10.0.0.9/onvif/media2")

    def test_media1_fallback_when_media2_absent(self):
        device = FakeDevice(media2=False)
        found = self._discover(device)
        self.assertTrue(found["ok"])
        self.assertEqual(found["media_version"], 1)
        self.assertEqual(found["media_url"], "http://10.0.0.9/onvif/media")
        self.assertFalse(found["capabilities"]["media2"])
        self.assertFalse(found["capabilities"]["profile_m"])
        self.assertEqual(found["profiles"][0]["uri"], "rtsp://admin:s3cret@10.0.0.9:554/onvif/p1")

    def test_unreachable_device_is_not_onvif(self):
        async def boom(*a, **k):
            raise RuntimeError("connect timeout")

        with patch.object(od, "_post", boom):
            found = asyncio.run(od.discover_onvif("10.0.0.99", USER, PW, timeout=0.2))
        self.assertFalse(found["ok"])
        self.assertFalse(found["onvif"])
        self.assertIn("timeout", found["error"])

    def test_stream_discovery_uses_onvif_uris_not_vendor_guesses(self):
        from app.services.stream_discover import discover_camera_streams

        device = FakeDevice()
        with patch.object(od, "_post", device.post), patch("app.services.stream_discover.probe") as probe:
            found = asyncio.run(discover_camera_streams("10.0.0.9", USER, PW, "", timeout=0.5))
        self.assertEqual(found["source"], "onvif")
        probe.assert_not_called()
        self.assertEqual(found["stream_profiles"]["MAIN"]["uri"], "rtsp://admin:s3cret@10.0.0.9:554/onvif/p1")
        self.assertEqual(found["stream_profiles"]["SUB"]["uri"], "rtsp://admin:s3cret@10.0.0.9:554/onvif/p2")
        public = public_profiles(found["stream_profiles"])
        for row in public.values():
            self.assertNotIn("uri", row)
            self.assertNotIn("snapshot_uri", row)
            self.assertNotIn("s3cret", str(row))


class _Cam:
    def __init__(self, **kw):
        self.id = kw.get("id", 5)
        self.enabled = kw.get("enabled", True)
        self.adapter_id = kw.get("adapter_id", "onvif")
        self.username = USER
        self.password_secret = PW
        self.media_capabilities = kw.get("media_capabilities", ["RTSP"])
        self.onvif_profile = kw.get("onvif_profile", {})


class ProfilePersistenceTests(unittest.TestCase):
    def test_apply_discovery_sets_flags_and_default_events_toggle(self):
        device = FakeDevice()
        with patch.object(od, "_post", device.post):
            found = asyncio.run(od.discover_onvif("10.0.0.9", USER, PW, timeout=0.5))
        cam = _Cam()
        profile = apply_discovery(cam, found)
        self.assertTrue(profile["events_enabled"])
        self.assertEqual(profile["events_url"], "http://10.0.0.9/onvif/events")
        self.assertEqual(cam.media_capabilities, ["RTSP", "ONVIF", "ONVIF_MEDIA2", "ONVIF_EVENTS", "ONVIF_PROFILE_M", "ONVIF_PLATE_METADATA"])
        self.assertTrue(onvif_runtime.wants_events(cam))
        # operator turns it off; a re-discovery keeps it off
        set_events_enabled(cam, False)
        self.assertFalse(onvif_runtime.wants_events(cam))
        apply_discovery(cam, found)
        self.assertFalse(cam.onvif_profile["events_enabled"])

    def test_no_plate_topics_means_no_events_even_if_asked(self):
        device = FakeDevice(lpr=False)
        with patch.object(od, "_post", device.post):
            found = asyncio.run(od.discover_onvif("10.0.0.9", USER, PW, timeout=0.5))
        cam = _Cam()
        apply_discovery(cam, found)
        self.assertFalse(cam.onvif_profile["events_enabled"])
        with self.assertRaises(ValueError):
            set_events_enabled(cam, True)
        self.assertFalse(onvif_runtime.wants_events(cam))

    def test_hvx_cameras_never_get_onvif_pollers(self):
        cam = _Cam(adapter_id="hvx", onvif_profile={"events_enabled": True, "events_url": "http://x",
                                                    "capabilities": {"plate_metadata": True}})
        self.assertFalse(onvif_runtime.wants_events(cam))


class PollerTests(unittest.TestCase):
    def setUp(self):
        onvif_runtime.reset()

    def test_poller_subscribes_pulls_and_delivers_latest_plate_per_text(self):
        device = FakeDevice()
        got: list[tuple[int, dict]] = []

        async def on_capture(camera_id, capture):
            got.append((camera_id, capture))
            if len(got) >= 2:
                raise asyncio.CancelledError()

        async def run():
            with patch.object(od, "_post", device.post):
                pp = oe.ONVIFPullPoint("http://10.0.0.9/onvif/events", USER, PW, timeout=0.5)
                poller = oe.ONVIFEventPoller(7, pp, on_capture, pull_wait="PT1S")
                task = asyncio.create_task(poller.run())
                try:
                    await asyncio.wait_for(task, timeout=3.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                return poller

        poller = asyncio.run(run())
        self.assertEqual([c["plate"] for _, c in got[:2]], ["T 123 ABC", "KBZ 456 Q"])
        self.assertTrue(all(cid == 7 for cid, _ in got))
        ops = [op for op, _ in device.calls]
        self.assertEqual(ops[0], "CreatePullPointSubscription")
        self.assertIn("PullMessages", ops)
        self.assertIn("UnsubscribeRequest", ops, "cancel must unsubscribe")
        self.assertGreaterEqual(poller.stats["plates"], 2)
        # PullMessages is addressed to the subscription manager, not the events service
        pull_urls = [url for op, url in device.calls if op == "PullMessages"]
        self.assertTrue(all("Subscription?Idx=7" in u for u in pull_urls))

    def test_poller_backs_off_on_subscribe_failure_without_raising(self):
        async def failing(*a, **k):
            raise RuntimeError("HTTP 401")

        async def run():
            with patch.object(od, "_post", failing):
                pp = oe.ONVIFPullPoint("http://10.0.0.9/onvif/events", USER, PW, timeout=0.2)
                poller = oe.ONVIFEventPoller(7, pp, lambda cid, c: asyncio.sleep(0))
                task = asyncio.create_task(poller.run())
                await asyncio.sleep(0.3)
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                return poller

        poller = asyncio.run(run())
        self.assertGreaterEqual(poller.stats["errors"], 1)
        self.assertIn("CreatePullPointSubscription failed", poller.stats["last_error"])
        self.assertFalse(poller.stats["subscribed"])
        self.assertGreater(poller.reconnect.attempts, 0)

    def test_reconcile_starts_and_stops_pollers_from_db(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from app.db import Base
        from app.models import Camera

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(engine)
        profile = {"events_enabled": True, "events_url": "http://10.0.0.9/onvif/events",
                   "capabilities": {"plate_metadata": True, "plate_topics": ["RuleEngine/LicensePlateDetector/LicensePlate"]}}
        with Session() as db:
            db.add(Camera(name="ONVIF LPR", ip_address="10.0.0.9", adapter_id="onvif", onvif_profile=profile))
            db.add(Camera(name="HVX", ip_address="10.0.0.10", adapter_id="hvx", onvif_profile=profile))
            db.add(Camera(name="ONVIF plain", ip_address="10.0.0.11", adapter_id="onvif", onvif_profile={}))
            db.commit()

        async def failing(*a, **k):
            await asyncio.sleep(10)

        async def run():
            with patch.object(od, "_post", failing):
                first = await onvif_runtime.reconcile(Session)
                running = dict(onvif_runtime.stats()["cameras"])
                with Session() as db:
                    cam = db.query(Camera).filter_by(name="ONVIF LPR").one()
                    cam.enabled = False
                    db.commit()
                second = await onvif_runtime.reconcile(Session)
                await onvif_runtime.shutdown()
                return first, running, second

        first, running, second = asyncio.run(run())
        self.assertEqual(first, {"started": 1, "stopped": 0, "running": 1})
        self.assertEqual(len(running), 1)
        self.assertTrue(next(iter(running.values()))["running"])
        self.assertEqual(second["stopped"], 1)
        self.assertEqual(second["running"], 0)
        engine.dispose()


class ApiTests(unittest.TestCase):
    """Discovery route persists capabilities; Profile M reads land as captures."""

    def setUp(self):
        import shutil
        import tempfile
        from unittest.mock import PropertyMock

        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from app.api_main import app, ensure_roles
        from app.config import Settings
        from app.db import Base, get_db, set_session_factory
        from app.models import Role, User, UserRole
        from app.security import hash_password

        onvif_runtime.reset()
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        self.media = Path(tempfile.mkdtemp(prefix="smartpark-onvif-"))
        self._media_patch = patch.object(Settings, "media_dir", new_callable=PropertyMock, return_value=self.media)
        self._media_patch.start()
        self._rm = shutil.rmtree

        def override_get_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        set_session_factory(self.Session)
        self._set_session_factory = set_session_factory
        with self.Session() as db:
            ensure_roles(db)
            from app.services.modules import apply_profile
            apply_profile(db, "PARKING_PRO")
            admin_role = db.scalar(select(Role).where(Role.name == "Admin"))
            user = User(username="admin", full_name="Test Admin", password_hash=hash_password("correct-horse"))
            db.add(user)
            db.flush()
            db.add(UserRole(user_id=user.id, role_id=admin_role.id))
            db.commit()
        self.app = app
        self.client = TestClient(app)
        token = self.client.post("/auth/login", json={"username": "admin", "password": "correct-horse"}).json()["token"]
        self.headers = {"Authorization": f"Bearer {token}"}
        cam = self.client.post("/cameras", headers=self.headers, json={
            "name": "Gate ONVIF", "ip_address": "10.0.0.9", "adapter_id": "onvif", "username": USER, "password": PW,
            "lane_direction": "ENTRY",
        })
        self.assertEqual(cam.status_code, 200, cam.text)
        self.camera_id = cam.json()["id"]

    def tearDown(self):
        self.client.close()
        self._set_session_factory(None)
        self._media_patch.stop()
        self._rm(self.media, ignore_errors=True)
        self.app.dependency_overrides.clear()
        onvif_runtime.reset()
        self.engine.dispose()

    def test_discover_route_persists_capabilities_without_leaking_credentials(self):
        device = FakeDevice()
        with patch.object(od, "_post", device.post):
            res = self.client.post(f"/cameras/{self.camera_id}/onvif/discover", headers=self.headers)
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["source"], "onvif")
        self.assertNotIn(PW, res.text)
        cam = body["camera"]
        self.assertIn("ONVIF_MEDIA2", cam["media_capabilities"])
        self.assertIn("ONVIF_PLATE_METADATA", cam["media_capabilities"])
        self.assertTrue(cam["onvif"]["profile_m"])
        self.assertTrue(cam["onvif"]["events_enabled"])
        self.assertEqual(cam["onvif"]["media_version"], 2)
        self.assertIn("10.0.0.9/onvif/snapshot/p1.jpg", cam["onvif"]["snapshot_uri"])
        self.assertEqual(cam["stream_profiles"]["MAIN"]["codec"], "h265")
        # toggle off / on
        off = self.client.patch(f"/cameras/{self.camera_id}/onvif/events", headers=self.headers, json={"enabled": False})
        self.assertEqual(off.status_code, 200)
        self.assertFalse(off.json()["onvif"]["events_enabled"])
        on = self.client.patch(f"/cameras/{self.camera_id}/onvif/events", headers=self.headers, json={"enabled": True})
        self.assertTrue(on.json()["onvif"]["events_enabled"])

    def test_events_toggle_refused_when_camera_lacks_plate_topics(self):
        device = FakeDevice(lpr=False)
        with patch.object(od, "_post", device.post):
            self.client.post(f"/cameras/{self.camera_id}/onvif/discover", headers=self.headers)
        res = self.client.patch(f"/cameras/{self.camera_id}/onvif/events", headers=self.headers, json={"enabled": True})
        self.assertEqual(res.status_code, 409)

    def test_diagnostic_pull_returns_normalised_events(self):
        device = FakeDevice()
        with patch.object(od, "_post", device.post):
            self.client.post(f"/cameras/{self.camera_id}/onvif/discover", headers=self.headers)
            res = self.client.post(f"/cameras/{self.camera_id}/onvif/events/pull", headers=self.headers)
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["messages"], 3)
        plates = [e["capture"]["plate"] for e in body["events"] if e["capture"]]
        self.assertEqual(plates, ["T 123 ABC", "KBZ 456 Q"])
        self.assertIn("UnsubscribeRequest", [op for op, _ in device.calls])

    def test_profile_m_read_becomes_a_vehicle_capture_once(self):
        from app.api_main import _onvif_capture
        from app.models import VehicleCapture

        capture = oe.plate_captures(PULL)[0]
        asyncio.run(_onvif_capture(self.camera_id, capture, b""))
        asyncio.run(_onvif_capture(self.camera_id, dict(capture), b""))  # duplicate event id
        with self.Session() as db:
            rows = db.query(VehicleCapture).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].plate, "T123ABC")
        self.assertEqual(rows[0].camera_id, self.camera_id)
        captures = self.client.get("/captures", headers=self.headers, params={"camera_id": self.camera_id})
        self.assertEqual(captures.status_code, 200)
        self.assertNotIn(PW, captures.text)


if __name__ == "__main__":
    unittest.main()
