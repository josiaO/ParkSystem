"""Live camera video. UI consumes the media gateway; FastALPR does not."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from app.config import settings
from app.services.frame_grab import grab_camera_frame
from app.services.http_snapshot import grab_http_snapshot
from app.services.hvx_client import HVXHostClient
from app.services.media_gateway import CameraLiveSpec, gateway, take_latest_jpeg
from app.services.rtsp_probe import redact_url

JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"
MJPEG_BOUNDARY = "smartparkframe"
MEDIA_KINDS = {"crops", "alpr", "annotated", "snapshots", "receipts"}

# Re-export for callers/tests that import from preview.
__all__ = [
    "CameraLiveSpec",
    "JPEG_EOI",
    "JPEG_SOI",
    "MEDIA_KINDS",
    "MJPEG_BOUNDARY",
    "PreviewState",
    "acquire_detect",
    "acquire_live",
    "ensure_mjpeg_source",
    "ffmpeg_jpeg_stream",
    "fresh_alpr",
    "fresh_last_car",
    "get_state",
    "live_metrics",
    "live_is_current",
    "media_path",
    "mjpeg_from_cache",
    "mjpeg_parts",
    "pumping_spec",
    "release_detect",
    "release_live",
    "remember_alpr",
    "remember_frame",
    "remember_last_car",
    "resolve_playable",
    "sdk_jpeg",
    "snapshot_for_camera",
    "start_idle_watch",
    "start_live_pump",
    "stop_idle_watch",
    "stop_live_pump",
    "stop_live_pumps",
    "take_latest_jpeg",
    "touch_live",
    "viewers_for",
    "watch_live",
]


@dataclass
class PreviewState:
    jpeg: bytes = b""
    url: str = ""
    url_redacted: str = ""
    captured_at: float = 0.0
    alpr: dict = field(default_factory=dict)
    alpr_at: float = 0.0
    last_car: dict = field(default_factory=dict)
    last_car_at: float = 0.0
    plate_box: dict = field(default_factory=dict)
    plate_box_at: float = 0.0
    viewer_transport: str = ""
    viewer_transport_at: float = 0.0
    seq: int = 0
    source: str = ""
    disk_at: float = 0.0
    fps: float = 0.0
    _fps_at: float = 0.0
    _fps_n: int = 0
    fingerprint: int = 0
    waiters: set[asyncio.Event] = field(default_factory=set, repr=False)


_state: dict[int, PreviewState] = {}
_viewers: dict[int, int] = {}
_last_view: dict[int, float] = {}
_snapshot_locks: dict[int, asyncio.Lock] = {}


def get_state(camera_id: int) -> PreviewState:
    row = _state.get(camera_id)
    if row is None:
        row = PreviewState()
        _state[camera_id] = row
    return row


def live_is_current(camera_id: int) -> bool:
    row = get_state(camera_id)
    session = gateway.session(camera_id)
    # A response containing the same cached JPEG is not a fresh video frame.
    # Prefer the gateway's unique-frame timestamp so SDK polling cannot keep a
    # frozen picture looking healthy forever.
    if session is not None and hasattr(session, "last_fresh_frame_at"):
        fresh_at = float(getattr(session, "last_fresh_frame_at") or 0.0)
    else:
        # Compatibility for lightweight callers/tests that provide the old
        # session shape. Real StreamSession objects always have the fresh
        # timestamp above, even when it is zero.
        fresh_at = float(getattr(session, "last_received_at", 0.0) or row.captured_at)
    return bool(row.jpeg[:2] == JPEG_SOI and fresh_at and time.monotonic() - fresh_at <= settings.stale_stream_seconds)


def _notify(row: PreviewState) -> None:
    for waiter in list(row.waiters):
        waiter.set()


def remember_frame(
    camera_id: int,
    jpeg: bytes,
    *,
    url: str = "",
    url_redacted: str = "",
    source: str = "",
    persist: bool = False,
) -> None:
    if jpeg[:2] != JPEG_SOI:
        return
    row = get_state(camera_id)
    fingerprint = hash(jpeg)
    changed = fingerprint != row.fingerprint
    row.jpeg = jpeg
    row.captured_at = time.monotonic()
    row.fingerprint = fingerprint
    if changed:
        row.seq += 1
        now = time.monotonic()
        if row._fps_at <= 0:
            row._fps_at = now
        row._fps_n += 1
        elapsed = now - row._fps_at
        if elapsed >= 1.0:
            row.fps = round(row._fps_n / elapsed, 1)
            row._fps_at = now
            row._fps_n = 0
    if source:
        row.source = source
    if url:
        row.url = url
    if url_redacted:
        row.url_redacted = url_redacted
    if changed:
        _notify(row)
        from app.services.queues import VIDEO_FRAMES
        VIDEO_FRAMES.put((camera_id, row.seq))
    if persist:
        from app.config import settings
        dest = settings.media_dir / "snapshots" / f"camera-{camera_id}.jpg"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(jpeg)
        row.disk_at = time.monotonic()


def remember_alpr(camera_id: int, result: dict) -> None:
    row = get_state(camera_id)
    row.alpr = result or {}
    row.alpr_at = time.monotonic() if result else 0.0


def fresh_alpr(camera_id: int, *, max_age_seconds: float | None = None) -> dict | None:
    row = get_state(camera_id)
    if not row.alpr or row.alpr_at <= 0:
        return None
    from app.config import settings
    max_age = float(
        max_age_seconds
        if max_age_seconds is not None
        else getattr(settings, "live_plate_fresh_seconds", 4.0)
    )
    if time.monotonic() - row.alpr_at > max_age:
        row.alpr = {}
        row.alpr_at = 0.0
        return None
    return row.alpr


def remember_plate_box(camera_id: int, overlay: dict | None) -> None:
    """Keep the camera plate rectangle for the current visit."""
    row = get_state(camera_id)
    if overlay:
        row.plate_box = dict(overlay)
        row.plate_box_at = time.monotonic()
    else:
        row.plate_box = {}
        row.plate_box_at = 0.0


def held_plate_box(camera_id: int, *, max_age_seconds: float = 180.0) -> dict | None:
    """Last camera plate box, until the lane goes idle or this cap elapses."""
    row = get_state(camera_id)
    if not row.plate_box or row.plate_box_at <= 0:
        return None
    if time.monotonic() - row.plate_box_at > max_age_seconds:
        row.plate_box = {}
        row.plate_box_at = 0.0
        return None
    return dict(row.plate_box)


def remember_last_car(camera_id: int, payload: dict | None) -> None:
    row = get_state(camera_id)
    if payload:
        row.last_car = payload
        row.last_car_at = time.monotonic()
    else:
        row.last_car = {}
        row.last_car_at = 0.0


def fresh_last_car(camera_id: int, *, max_age_seconds: float | None = None) -> dict | None:
    """Return the latest vehicle only while it is recent enough for live UI.

    Historical captures remain in the database/detections page. The live lane
    must clear an old plate after the vehicle has left instead of presenting it
    as if it still belongs to the next car.
    """
    row = get_state(camera_id)
    if not row.last_car or row.last_car_at <= 0:
        return None
    from app.config import settings
    max_age = float(
        max_age_seconds
        if max_age_seconds is not None
        else getattr(settings, "live_plate_fresh_seconds", 4.0)
    )
    if time.monotonic() - row.last_car_at > max_age:
        row.last_car = {}
        row.last_car_at = 0.0
        return None
    return row.last_car


def remember_viewer_transport(camera_id: int, transport: str) -> None:
    row = get_state(camera_id)
    row.viewer_transport = str(transport or "").upper()
    row.viewer_transport_at = time.monotonic() if transport else 0.0


def viewer_live_provider(camera_id: int) -> str:
    row = get_state(camera_id)
    if not row.viewer_transport or row.viewer_transport_at <= 0:
        return ""
    if time.monotonic() - row.viewer_transport_at > 30.0:
        return ""
    return row.viewer_transport


def media_path(kind: str, name: str):
    from app.config import settings
    if kind not in MEDIA_KINDS or not name or "/" in name or "\\" in name or ".." in name:
        return None
    path = (settings.media_dir / kind / name).resolve()
    root = settings.media_dir.resolve()
    if path != root and root not in path.parents:
        return None
    return path if path.is_file() else None


async def sdk_jpeg(sdk_handle: int | None, *, trigger: bool = False) -> dict:
    if sdk_handle is None:
        return {"ok": False, "error": "no SDK handle"}
    try:
        jpeg = await HVXHostClient().live_jpeg(int(sdk_handle))
        if jpeg[:2] != JPEG_SOI and trigger:
            jpeg = await HVXHostClient().capture_jpeg(int(sdk_handle), trigger=True)
    except Exception as exc:
        return {"ok": False, "error": f"SDK JPEG: {exc}", "source": "sdk"}
    if jpeg[:2] == JPEG_SOI:
        return {
            "ok": True,
            "jpeg": jpeg,
            "bytes": len(jpeg),
            "url": f"sdk://handle/{int(sdk_handle)}",
            "url_redacted": f"sdk://handle/{int(sdk_handle)}",
            "source": "sdk",
        }
    return {
        "ok": False,
        "error": "SDK connected, waiting for live video (Net_StartVideo / Net_GetJpgBuffer)",
        "source": "sdk",
    }


async def resolve_playable(ip: str, username: str, password: str, explicit: str = "", cached: str = "", sdk_handle: int | None = None) -> dict:
    sdk = {"ok": False, "error": ""}
    if sdk_handle is not None:
        sdk = await sdk_jpeg(sdk_handle)
        if sdk.get("ok"):
            return sdk
    http = await grab_http_snapshot(ip, username, password)
    if http.get("ok"):
        return http
    grabbed = await grab_camera_frame(
        ip,
        username,
        password,
        explicit or cached,
        prefer_qy=sdk_handle is not None,
    )
    if grabbed.get("ok"):
        grabbed["source"] = grabbed.get("source") or "rtsp"
        return grabbed
    return {
        "ok": False,
        "error": sdk.get("error") or http.get("error") or grabbed.get("error") or "No live JPEG",
        "sdk": {k: v for k, v in sdk.items() if k != "jpeg"},
        "http": {k: v for k, v in http.items() if k != "jpeg"},
        "rtsp": {k: v for k, v in grabbed.items() if k != "jpeg"},
        "source": "none",
    }


async def snapshot_for_camera(
    camera_id: int,
    ip: str,
    username: str,
    password: str,
    explicit: str = "",
    sdk_handle: int | None = None,
) -> dict:
    lock = _snapshot_locks.setdefault(int(camera_id), asyncio.Lock())
    async with lock:
        return await _snapshot_for_camera_unlocked(
            camera_id, ip, username, password, explicit, sdk_handle=sdk_handle,
        )


def _fresh_gateway_sample(camera_id: int):
    session = gateway.session(int(camera_id))
    sample = gateway.peek_live(int(camera_id))
    if sample is None or sample.jpeg[:2] != JPEG_SOI:
        return None
    fresh_at = (
        float(getattr(session, "last_fresh_frame_at", 0.0) or 0.0)
        if session is not None else 0.0
    ) or sample.received_at
    stale = float(getattr(settings, "stale_stream_seconds", 2.5) or 2.5)
    if fresh_at <= 0 or time.monotonic() - fresh_at > stale:
        return None
    return sample


async def _wait_for_fresh_gateway_sample(camera_id: int, *, timeout: float = 1.25):
    deadline = time.monotonic() + max(0.1, float(timeout))
    while time.monotonic() < deadline:
        sample = _fresh_gateway_sample(camera_id)
        if sample is not None:
            return sample
        await asyncio.sleep(0.05)
    return _fresh_gateway_sample(camera_id)


async def _snapshot_for_camera_unlocked(
    camera_id: int,
    ip: str,
    username: str,
    password: str,
    explicit: str = "",
    sdk_handle: int | None = None,
) -> dict:
    from app.infrastructure.media.registry import mediamtx_live_active
    from app.services import mediamtx

    if mediamtx_live_active(camera_id):
        local = mediamtx.live_endpoint(camera_id).get("rtsp") or ""
        sample = await _wait_for_fresh_gateway_sample(camera_id)
        if sample is not None:
            return {
                "ok": True,
                "jpeg": sample.jpeg,
                "url": sample.url or local,
                "url_redacted": redact_url(sample.url or local),
                "cached": True,
                "source": sample.source or "mediamtx",
            }
        # Never spawn a second FFmpeg RTSP reader while the live MediaMTX
        # consumer is active. That competing decoder is what makes snapshots
        # cause the live stream to stack, stall, or jump after recovery.
        return {
            "ok": False,
            "error": "Live stream is stale; snapshot was not taken to protect video",
            "source": "mediamtx",
            "url": local,
        }
    cached = await gateway.snapshot(camera_id)
    if cached[:2] == JPEG_SOI and live_is_current(camera_id):
        row = get_state(camera_id)
        return {
            "ok": True,
            "jpeg": cached,
            "url": row.url,
            "url_redacted": row.url_redacted,
            "cached": True,
            "source": row.source or "gateway",
        }
    session = gateway.session(int(camera_id))
    row = get_state(camera_id)
    producer_active = bool(
        session is not None
        and session.producer is not None
        and not (
            callable(getattr(session.producer, "done", None))
            and session.producer.done()
        )
    )
    if producer_active or (session is not None and session.detect_consumers > 0):
        sample = await _wait_for_fresh_gateway_sample(camera_id)
        if sample is not None:
            return {
                "ok": True,
                "jpeg": sample.jpeg,
                "url": sample.url,
                "url_redacted": redact_url(sample.url),
                "cached": True,
                "source": sample.source or "gateway",
            }
        # The HVX host already owns the SDK decoder. Reading its latest JPEG
        # is safe and does not create a second camera/FFmpeg connection. This
        # keeps SDK snapshots usable while the shared producer warms up.
        active_sdk_handle = sdk_handle if sdk_handle is not None else getattr(getattr(session, "spec", None), "sdk_handle", None)
        if active_sdk_handle is not None:
            grabbed = await resolve_playable(ip, username, password, explicit, row.url, sdk_handle=active_sdk_handle)
            if grabbed.get("ok"):
                gateway.publish(
                    camera_id,
                    grabbed["jpeg"],
                    source=str(grabbed.get("source") or "sdk"),
                    url=str(grabbed.get("url") or f"sdk://handle/{int(active_sdk_handle)}"),
                    detect=False,
                )
            return grabbed
        return {
            "ok": False,
            "error": "Live stream is stale; snapshot was not taken to protect video",
            "source": session.source or "gateway",
        }
    row = get_state(camera_id)
    ttl = float(getattr(settings, "snapshot_cache_seconds", 0.4) or 0.4)
    if row.jpeg[:2] == JPEG_SOI and (time.monotonic() - row.captured_at) < ttl:
        return {
            "ok": True,
            "jpeg": row.jpeg,
            "url": row.url,
            "url_redacted": row.url_redacted,
            "cached": True,
            "source": row.source or "cache",
        }
    grabbed = await resolve_playable(ip, username, password, explicit, row.url, sdk_handle=sdk_handle)
    if grabbed.get("ok"):
        gateway.publish(
            camera_id,
            grabbed["jpeg"],
            source=str(grabbed.get("source") or ""),
            url=str(grabbed.get("url") or ""),
            detect=False,
        )
    return grabbed


async def mjpeg_from_cache(camera_id: int):
    """Send the newest JPEG only. Never replay a backlog of frames."""
    last_seq = -1
    event = asyncio.Event()
    row = get_state(camera_id)
    row.waiters.add(event)
    try:
        while True:
            row = get_state(camera_id)
            jpeg = row.jpeg
            if jpeg[:2] == JPEG_SOI and row.seq != last_seq:
                last_seq = row.seq
                gateway.note_displayed(camera_id)
                header = (
                    f"--{MJPEG_BOUNDARY}\r\n"
                    f"Content-Type: image/jpeg\r\n"
                    f"Content-Length: {len(jpeg)}\r\n\r\n"
                ).encode("ascii")
                yield header + jpeg + b"\r\n"
                event.clear()
                continue
            try:
                await asyncio.wait_for(event.wait(), timeout=0.05)
            except asyncio.TimeoutError:
                # Do not leave an operator on an apparently live but stale
                # picture. Ask only this camera's producer to recover, then
                # close the response cleanly so the browser's existing retry
                # path can reconnect. Raising here used to turn an ordinary
                # stream recovery into an unhandled Starlette exception and
                # an invisible 500 in the operator UI.
                if last_seq >= 0 and not live_is_current(camera_id):
                    gateway.restart_decoder(camera_id)
                    return
            finally:
                event.clear()
    finally:
        row.waiters.discard(event)


async def ffmpeg_jpeg_stream(url: str):
    async for jpeg in gateway.ffmpeg_jpeg_stream(url):
        yield jpeg


async def mjpeg_parts(url: str):
    async for jpeg in ffmpeg_jpeg_stream(url):
        header = (
            f"--{MJPEG_BOUNDARY}\r\n"
            f"Content-Type: image/jpeg\r\n"
            f"Content-Length: {len(jpeg)}\r\n\r\n"
        ).encode("ascii")
        yield header + jpeg + b"\r\n"


def viewers_for(camera_id: int) -> int:
    return int(_viewers.get(camera_id) or 0)


def pumping_spec(camera_id: int) -> CameraLiveSpec | None:
    return gateway.pumping_spec(camera_id)


def touch_live(spec: CameraLiveSpec) -> None:
    """Keep the shared pump alive while a snapshot/MJPEG client is watching."""
    _last_view[spec.id] = time.monotonic()
    start_live_pump(spec)


def watch_live(spec: CameraLiveSpec) -> None:
    """Register an operator viewer without necessarily decoding JPEGs server-side.

    Browser WebRTC reads MediaMTX directly. Starting an FFmpeg->MJPEG decoder
    for that same viewer wastes CPU and can starve ALPR. Legacy/direct viewers
    still need the existing producer.
    """
    _viewers[spec.id] = viewers_for(spec.id) + 1
    _last_view[spec.id] = time.monotonic()
    from app.infrastructure.media.registry import mediamtx_live_active
    from app.services.flags import flags
    if mediamtx_live_active(spec.id) and bool(flags().get("webrtc_live_enabled")):
        return
    if mediamtx_live_active(spec.id):
        from app.services.mediamtx_live import ensure_live_consumer
        ensure_live_consumer(spec)
        return
    touch_live(spec)


def acquire_live(spec: CameraLiveSpec) -> None:
    """Acquire a JPEG/MJPEG viewer; unlike WebRTC this needs a local decoder."""
    _viewers[spec.id] = viewers_for(spec.id) + 1
    _last_view[spec.id] = time.monotonic()
    ensure_mjpeg_source(spec)


def ensure_mjpeg_source(spec: CameraLiveSpec) -> None:
    """Fill the JPEG cache that desktop /live.mjpeg reads.

    MediaMTX still owns browser WebRTC. HVX/QY desktop panes use the SDK
    live_jpeg pump (ParkWatch picture path) so we do not add a second FFmpeg
    JPEG decoder on top of MediaMTX ingest. Generic IP cameras keep the
    MediaMTX JPEG consumer. If that consumer produces no frame, callers can
    invoke this again after a short wait; ``gateway.ensure_producer`` is the
    last-resort SDK/RTSP pump.
    """
    _last_view[spec.id] = time.monotonic()
    if spec.sdk_handle is not None:
        start_idle_watch()
        row = gateway._session_for(spec)
        row.viewers = max(row.viewers, viewers_for(spec.id))
        row.last_view_at = time.monotonic()
        gateway.ensure_producer(spec)
        return
    row = gateway.session(spec.id)
    if row is not None and row.producer is not None and not row.producer.done():
        row.viewers = viewers_for(spec.id)
        row.last_view_at = time.monotonic()
        return
    from app.infrastructure.media.registry import mediamtx_live_active
    if mediamtx_live_active(spec.id):
        from app.services.mediamtx_live import ensure_live_consumer
        ensure_live_consumer(spec)
        return
    touch_live(spec)


def release_live(camera_id: int) -> None:
    """Stop showing this camera. Recognition on a connected camera keeps running."""
    _viewers[camera_id] = max(0, viewers_for(camera_id) - 1)
    _last_view[camera_id] = time.monotonic()
    row = gateway.session(camera_id)
    if row is not None:
        row.viewers = viewers_for(camera_id)
        row.last_view_at = time.monotonic()


def acquire_detect(spec: CameraLiveSpec) -> None:
    from app.infrastructure.media.registry import mediamtx_detect_active
    if mediamtx_detect_active(spec.id):
        # Drop a direct fallback lease before handing DETECT to MediaMTX.
        gateway.release_detect(spec.id)
        from app.services.mediamtx_detect import ensure_detect_consumer
        ensure_detect_consumer(spec)
        return
    gateway.acquire_detect(spec)


def release_detect(camera_id: int) -> None:
    gateway.release_detect(camera_id)


def live_metrics() -> list[dict]:
    gateway_rows = {int(row["camera_id"]): row for row in gateway.live_metrics()}
    ids = set(gateway_rows) | set(_state) | set(_viewers)
    now = time.monotonic()
    rows = []
    for camera_id in sorted(ids):
        preview = get_state(camera_id)
        media = dict(gateway_rows.get(camera_id) or {})
        pumping = bool(media.get("pumping"))
        state = media.get("connection_state") or (
            "STREAMING" if pumping else ("cached" if preview.jpeg[:2] == JPEG_SOI else "idle")
        )
        age = media.get("age_seconds")
        if age is None and preview.captured_at:
            age = round(now - preview.captured_at, 2)
        rows.append({
            "camera_id": camera_id,
            "connection_state": state,
            "viewers": viewers_for(camera_id),
            "pumping": pumping,
            "source": media.get("source") or preview.source,
            "fps": media.get("fps") or preview.fps,
            "seq": media.get("seq") or preview.seq,
            "age_seconds": age,
            "queue_depth": media.get("queue_depth") if "queue_depth" in media else (1 if preview.jpeg[:2] == JPEG_SOI else 0),
            "rtsp": bool(media.get("rtsp") if "rtsp" in media else preview.url.startswith("rtsp://")),
            "sdk": bool(media.get("sdk") if "sdk" in media else preview.source == "sdk"),
            "live_frame_age_ms": media.get("live_frame_age_ms"),
            "ai_frame_age_ms": media.get("ai_frame_age_ms"),
            "detect_frame_age_ms": media.get("detect_frame_age_ms"),
            "source_fps": media.get("source_fps") or 0,
            "frozen": bool(media.get("frozen")),
            "duplicate_frames": media.get("duplicate_frames") or 0,
            "frames_changed": media.get("frames_changed") or 0,
            "decoder_restarts": media.get("decoder_restarts") or 0,
            "ai_processed_fps": media.get("ai_processed_fps") or 0,
            "ai_samples_dropped": media.get("ai_samples_dropped") or 0,
            "codec": media.get("codec") or "",
            "transport": media.get("transport") or "",
            "ffmpeg_profile": media.get("ffmpeg_profile") or "",
            "gop": media.get("gop") or 0,
            "reconnects": media.get("reconnects") or 0,
            "frames_received": media.get("frames_received") or preview.seq,
            "frames_dropped_live": media.get("frames_dropped_live") or 0,
            "frames_sampled_ai": media.get("frames_sampled_ai") or 0,
            "frames_dropped_ai": media.get("frames_dropped_ai") or 0,
            "child_pids": media.get("child_pids") or [],
            "warnings": media.get("warnings") or [],
            "stream_profiles": media.get("stream_profiles") or {},
        })
    return rows


def start_idle_watch() -> None:
    gateway.start_watchers()


def stop_idle_watch() -> None:
    gateway.stop_watchers()


def start_live_pump(spec: CameraLiveSpec) -> None:
    """One gateway producer. MJPEG readers and FastALPR share the latest JPEG."""
    from app.infrastructure.media.registry import mediamtx_live_active
    if mediamtx_live_active(spec.id):
        from app.services.mediamtx_live import ensure_live_consumer
        ensure_live_consumer(spec)
        return
    start_idle_watch()
    row = gateway._session_for(spec)
    row.viewers = max(row.viewers, viewers_for(spec.id))
    row.last_view_at = time.monotonic()
    if spec.need_detect:
        row.detect_consumers = max(row.detect_consumers, 1)
    gateway.ensure_producer(spec)


def stop_live_pump(camera_id: int) -> None:
    gateway.stop_producer(camera_id, force=True)


def stop_live_pumps() -> None:
    from app.services.mediamtx_detect import stop_all as stop_mediamtx_detect
    from app.services.mediamtx_live import stop_all as stop_mediamtx_live
    stop_mediamtx_live()
    stop_mediamtx_detect()
    gateway.stop_all()
    _viewers.clear()
