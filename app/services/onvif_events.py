"""ONVIF Profile M metadata/events → SmartPark recognition contract.

Devices that advertise licence-plate topics (see ``onvif_discover.plate_topics``)
deliver reads as WS-BaseNotification messages. We consume them through a
pull-point subscription (CreatePullPointSubscription → PullMessages → Renew),
which needs no inbound port on the Site Service.

Normalisation produces the same vendor-neutral *capture* dict that
``camera_lpr.native_from_sdk_capture`` already accepts for HVX callbacks, so
Profile M reads flow through the existing persist / session / gate / hybrid
path without a second pipeline.

Bounded by design: one in-flight PullMessages per camera, ≤ ``message_limit``
messages per pull, no queue. A dead camera backs off with the shared
``ReconnectPolicy``; the poller never raises into the Site Service loop.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import re
from typing import Any, Awaitable, Callable
import xml.etree.ElementTree as ET
import zlib

from app.services import onvif_discover as _od
from app.services.onvif_discover import NS_EVENTS, ONVIFError, _all, _find, _local, _text, _xml_escape


async def _post(*args, **kwargs):
    """Resolve at call time so the SOAP seam (and its test double) is shared."""
    return await _od._post(*args, **kwargs)

SOURCE = "onvif_profile_m"
PLATE_ITEM_RE = re.compile(r"^(licen[cs]e_?plate(_?(number|text))?|plate(_?(number|text))?|number_?plate|lpr|anpr|vehicle_?plate)$", re.I)
CONFIDENCE_ITEM_RE = re.compile(r"^(confidence|likelihood|score|probability)$", re.I)
COUNTRY_ITEM_RE = re.compile(r"^(country|region|issuing_?country)$", re.I)
_WSA = "http://www.w3.org/2005/08/addressing"


# ------------------------------------------------------------------ parsing --
def _items(el: ET.Element | None) -> dict[str, str]:
    if el is None:
        return {}
    out: dict[str, str] = {}
    for item in _all(el, "SimpleItem"):
        name = item.attrib.get("Name") or item.attrib.get("name") or ""
        if name:
            out[name] = str(item.attrib.get("Value") or item.attrib.get("value") or "")
    return out


def _normalize_confidence(value: str) -> float | None:
    try:
        num = float(str(value).strip().rstrip("%"))
    except (TypeError, ValueError):
        return None
    if num > 1.0:
        num = num / 100.0
    return max(0.0, min(1.0, num))


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_notification_messages(xml: str) -> list[dict[str, Any]]:
    """PullMessagesResponse (or a raw Notify) → list of normalised events.

    Each event: ``topic``, ``at`` (ISO or None), ``source`` items, ``data``
    items, ``plate_raw`` (empty when the message is not a plate read),
    ``confidence`` (0..1 or None), ``country``.
    """
    root = ET.fromstring(xml)
    events: list[dict[str, Any]] = []
    for message in _all(root, "NotificationMessage"):
        topic = _text(_find(message, "Topic"))
        body = _find(message, "Message")
        inner = None
        if body is not None:
            for child in body.iter():
                if _local(child.tag) == "Message" and child is not body:
                    inner = child
                    break
        target = inner if inner is not None else body
        utc = ""
        if target is not None:
            utc = target.attrib.get("UtcTime") or target.attrib.get("utctime") or ""
        source_items = _items(_find(target, "Source")) if target is not None else {}
        data_items = _items(_find(target, "Data")) if target is not None else {}
        plate_raw = ""
        confidence = None
        country = ""
        for name, value in data_items.items():
            key = name.replace(" ", "").replace("-", "_")
            if PLATE_ITEM_RE.match(key) and value:
                plate_raw = value.strip()
            elif CONFIDENCE_ITEM_RE.match(key):
                confidence = _normalize_confidence(value)
            elif COUNTRY_ITEM_RE.match(key):
                country = value.strip()
        events.append({
            "topic": topic,
            "at": _parse_time(utc).isoformat() if _parse_time(utc) else None,
            "source": source_items,
            "data": data_items,
            "plate_raw": plate_raw,
            "confidence": confidence,
            "country": country,
        })
    return events


def parse_subscription_reference(xml: str) -> tuple[str, str]:
    """CreatePullPointSubscriptionResponse → (address, termination_time)."""
    root = ET.fromstring(xml)
    ref = _find(root, "SubscriptionReference")
    address = _text(_find(ref, "Address")) if ref is not None else ""
    termination = _text(_find(root, "TerminationTime"))
    return address, termination


def event_image_id(event: dict[str, Any]) -> int:
    """Stable per-read id so the existing dedup (`camera_events.seen`) works."""
    key = f"{event.get('topic')}|{event.get('at')}|{event.get('plate_raw')}"
    return (zlib.crc32(key.encode("utf-8")) & 0x7FFFFFFF) or 1


def event_to_capture(event: dict[str, Any]) -> dict[str, Any] | None:
    """Recognition-contract capture for ``native_from_sdk_capture``; None when not a plate read."""
    plate = str(event.get("plate_raw") or "").strip()
    if not plate:
        return None
    confidence = event.get("confidence")
    return {
        "plate": plate,
        "confidence": float(confidence) if confidence is not None else None,
        "source": SOURCE,
        "have_vehicle": True,
        "image_id": event_image_id(event),
        "event_time": event.get("at"),
        "onvif_topic": event.get("topic") or "",
        "country_hint": event.get("country") or "",
        "snap_type": "onvif-metadata",
    }


def plate_captures(xml: str) -> list[dict[str, Any]]:
    """Convenience: PullMessagesResponse → capture dicts for plate reads only."""
    out = []
    for event in parse_notification_messages(xml):
        capture = event_to_capture(event)
        if capture:
            out.append(capture)
    return out


# ------------------------------------------------------------ pull point ----
class ONVIFPullPoint:
    """One pull-point subscription. Methods raise ONVIFError; caller backs off."""

    def __init__(self, events_url: str, username: str, password: str, *, timeout: float = 8.0,
                 topic_filter: str = "", initial_termination: str = "PT60S"):
        self.events_url = events_url
        self.username = username
        self.password = password
        self.timeout = float(timeout)
        self.topic_filter = topic_filter
        self.initial_termination = initial_termination
        self.address = ""
        self.termination = ""

    def _to_header(self) -> str:
        if not self.address:
            return ""
        return f'<wsa:To xmlns:wsa="{_WSA}">{_xml_escape(self.address)}</wsa:To>'

    async def subscribe(self) -> str:
        filt = ""
        if self.topic_filter:
            filt = (
                "<wsnt:Filter><wsnt:TopicExpression Dialect=\"http://www.onvif.org/ver10/tev/topicExpression/ConcreteSet\">"
                f"{_xml_escape(self.topic_filter)}</wsnt:TopicExpression></wsnt:Filter>"
            )
        body = (
            "<tev:CreatePullPointSubscription>"
            f"{filt}<tev:InitialTerminationTime>{self.initial_termination}</tev:InitialTerminationTime>"
            "</tev:CreatePullPointSubscription>"
        )
        try:
            xml = await _post(self.events_url, body, username=self.username, password=self.password,
                              action=f"{NS_EVENTS}/CreatePullPointSubscription", timeout=self.timeout)
        except Exception as exc:
            raise ONVIFError(f"CreatePullPointSubscription failed: {exc}") from exc
        address, termination = parse_subscription_reference(xml)
        if not address:
            raise ONVIFError("CreatePullPointSubscription returned no SubscriptionReference")
        self.address, self.termination = address, termination
        return address

    async def pull(self, *, wait: str = "PT5S", limit: int = 20) -> list[dict[str, Any]]:
        if not self.address:
            raise ONVIFError("not subscribed")
        body = f"<tev:PullMessages><tev:Timeout>{wait}</tev:Timeout><tev:MessageLimit>{int(limit)}</tev:MessageLimit></tev:PullMessages>"
        try:
            xml = await _post(self.address, body, username=self.username, password=self.password,
                              action=f"{NS_EVENTS}/PullMessages", timeout=self.timeout + 5.0,
                              header_extra=self._to_header())
        except Exception as exc:
            raise ONVIFError(f"PullMessages failed: {exc}") from exc
        return parse_notification_messages(xml)

    async def renew(self, termination: str = "PT60S") -> None:
        if not self.address:
            raise ONVIFError("not subscribed")
        body = f'<wsnt:Renew xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2"><wsnt:TerminationTime>{termination}</wsnt:TerminationTime></wsnt:Renew>'
        try:
            await _post(self.address, body, username=self.username, password=self.password,
                        action="http://docs.oasis-open.org/wsn/bw-2/SubscriptionManager/RenewRequest",
                        timeout=self.timeout, header_extra=self._to_header())
        except Exception as exc:
            raise ONVIFError(f"Renew failed: {exc}") from exc

    async def unsubscribe(self) -> None:
        if not self.address:
            return
        body = '<wsnt:Unsubscribe xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2"/>'
        try:
            await _post(self.address, body, username=self.username, password=self.password,
                        action="http://docs.oasis-open.org/wsn/bw-2/SubscriptionManager/UnsubscribeRequest",
                        timeout=self.timeout, header_extra=self._to_header())
        except Exception:
            pass
        self.address = ""


CaptureHandler = Callable[[int, dict[str, Any]], Awaitable[None]]


class ONVIFEventPoller:
    """Long-running poller for one camera. Latest reads only; no backlog."""

    def __init__(self, camera_id: int, pullpoint: ONVIFPullPoint, on_capture: CaptureHandler, *,
                 renew_every: float = 40.0, pull_wait: str = "PT5S", message_limit: int = 20):
        self.camera_id = int(camera_id)
        self.pullpoint = pullpoint
        self.on_capture = on_capture
        self.renew_every = float(renew_every)
        self.pull_wait = pull_wait
        self.message_limit = int(message_limit)
        self.stats: dict[str, Any] = {"pulls": 0, "messages": 0, "plates": 0, "errors": 0, "last_error": "",
                                      "subscribed": False, "last_plate_at": None}
        from app.services.circuit import ReconnectPolicy

        self.reconnect = ReconnectPolicy()

    async def run(self) -> None:
        loop = asyncio.get_event_loop()
        while True:
            if not self.reconnect.ready():
                await asyncio.sleep(0.5)
                continue
            try:
                await self.pullpoint.subscribe()
                self.stats["subscribed"] = True
                self.reconnect.record_success()
                last_renew = loop.time()
                while True:
                    events = await self.pullpoint.pull(wait=self.pull_wait, limit=self.message_limit)
                    self.stats["pulls"] += 1
                    self.stats["messages"] += len(events)
                    # Latest-wins per plate text inside one pull: never replay a burst.
                    latest: dict[str, dict[str, Any]] = {}
                    for event in events:
                        capture = event_to_capture(event)
                        if capture:
                            latest[capture["plate"]] = capture
                    for capture in latest.values():
                        self.stats["plates"] += 1
                        self.stats["last_plate_at"] = capture.get("event_time")
                        try:
                            await self.on_capture(self.camera_id, capture)
                        except asyncio.CancelledError:
                            raise
                        except Exception as exc:  # business handler must not kill the poller
                            self.stats["errors"] += 1
                            self.stats["last_error"] = f"handler: {exc}"[:200]
                    if loop.time() - last_renew >= self.renew_every:
                        await self.pullpoint.renew()
                        last_renew = loop.time()
            except asyncio.CancelledError:
                await self.pullpoint.unsubscribe()
                raise
            except ONVIFError as exc:
                self.stats["subscribed"] = False
                self.stats["errors"] += 1
                self.stats["last_error"] = str(exc)[:200]
                self.pullpoint.address = ""
                wait = self.reconnect.record_failure(str(exc))
                await asyncio.sleep(min(wait, 30.0))
            except Exception as exc:  # unexpected: back off, never crash Site Service
                self.stats["subscribed"] = False
                self.stats["errors"] += 1
                self.stats["last_error"] = f"{type(exc).__name__}: {exc}"[:200]
                self.pullpoint.address = ""
                wait = self.reconnect.record_failure(str(exc))
                await asyncio.sleep(min(wait, 30.0))
