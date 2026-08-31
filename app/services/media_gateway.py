"""One upstream media producer per camera. Live view and FastALPR are consumers."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field, replace
from typing import Any

from app.config import settings
from app.domain.media import STREAM_STATES
from app.services.circuit import reconnect_for
from app.services.ffmpeg_profiles import (
    DEFAULT_PROFILE,
    fallback_profile,
    normalize_profile,
    normalize_transport,
    profile_args,
)
from app.services.frame_grab import ffmpeg_bin
from app.services.http_snapshot import grab_http_snapshot
from app.services.hvx_client import HVXHostClient
from app.services.latest_frame import FrameSample, LatestFrameBuffer
from app.services.rtsp_probe import redact_url, vendor_candidates
from app.services.stream_roles import (
    ROLE_DETECT,
    ROLE_LIVE,
    ROLE_MAIN,
    ROLE_SUB,
    hvx_profiles,
    profile_warnings,
    public_profiles,
    uri_for_role,
)

JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"


def take_latest_jpeg(buf: bytes) -> tuple[bytes, bytes]:
    """Return (latest complete JPEG, remainder). Drops stacked frames in the pipe."""
    latest = b""
    while True:
        start = buf.find(JPEG_SOI)
        if start < 0:
            return latest, (buf[-1:] if buf.endswith(b"\xff") else b"")
        end = buf.find(JPEG_EOI, start + 2)
        if end < 0:
            return latest, buf[start:]
        latest = buf[start:end + 2]
        buf = buf[end + 2:]


@dataclass(frozen=True)
class CameraLiveSpec:
    id: int
    ip: str
    username: str
    password: str
    rtsp_url: str
    sdk_handle: int | None
    ffmpeg_profile: str = DEFAULT_PROFILE
    transport: str = "TCP"
    need_detect: bool = False
    live_role: str = ROLE_LIVE
    stream_profiles: dict = field(default_factory=dict)


@dataclass
class StreamSession:
    spec: CameraLiveSpec
    state: str = "DISCONNECTED"
    live: LatestFrameBuffer = field(default_factory=lambda: LatestFrameBuffer("live", maxsize=1))
    detect: LatestFrameBuffer = field(default_factory=lambda: LatestFrameBuffer("detect", maxsize=1))
    producer: asyncio.Task | None = None
    viewers: int = 0
    detect_consumers: int = 0
    last_view_at: float = 0.0
    last_frame_received_at: float = 0.0
    last_keyframe_at: float = 0.0
    ffmpeg_pid: int | None = None
    child_pids: set[int] = field(default_factory=set)
    reconnects: int = 0
    decode_errors: int = 0
    frames_displayed: int = 0
    frames_sampled_ai: int = 0
    frames_dropped_ai: int = 0
    source: str = ""
    url: str = ""
    codec: str = ""
    width: int = 0
    height: int = 0
    fps: float = 0.0
    gop: int = 0
    transport: str = "TCP"
    ffmpeg_profile: str = DEFAULT_PROFILE
    using_fallback: bool = False
    last_error: str = ""
    ai_last_seq: int = 0
    ai_last_at: float = 0.0
    ai_infer_ms: float = 0.0
    ai_fps: float = 0.0
    _ai_fps_at: float = 0.0
    _ai_fps_n: int = 0
    _fps_at: float = 0.0
    _fps_n: int = 0
    live_fps: float = 0.0
    bitrate_bps: int = 0
    _bytes_window: int = 0
    _bytes_at: float = 0.0

    def wanted(self) -> bool:
        return self.viewers > 0 or self.detect_consumers > 0 or self.spec.need_detect


class LocalMediaGateway:
    """SmartPark media owner. Backends are HVX JPEG and FFmpeg RTSP, not go2rtc internals."""

    def __init__(self) -> None:
        self._sessions: dict[int, StreamSession] = {}
        self._idle_task: asyncio.Task | None = None
        self._watch_task: asyncio.Task | None = None

    def session(self, camera_id: int) -> StreamSession | None:
        return self._sessions.get(camera_id)

    def _session_for(self, spec: CameraLiveSpec) -> StreamSession:
        row = self._sessions.get(spec.id)
        if row is None:
            row = StreamSession(spec=spec)
            self._sessions[spec.id] = row
        else:
            row.spec = spec
        row.ffmpeg_profile = normalize_profile(spec.ffmpeg_profile)
        row.transport = normalize_transport(spec.transport)
        return row

    def start_watchers(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._idle_task is None or self._idle_task.done():
            self._idle_task = loop.create_task(self._idle_watch(), name="media-idle")
        if self._watch_task is None or self._watch_task.done():
            self._watch_task = loop.create_task(self._stale_watch(), name="media-stale")

    def stop_watchers(self) -> None:
        for task in (self._idle_task, self._watch_task):
            if task is not None:
                task.cancel()
        self._idle_task = None
        self._watch_task = None

    async def register_stream(self, camera_id: int, source: dict[str, Any]) -> dict[str, Any]:
        spec = source.get("spec")
        if not isinstance(spec, CameraLiveSpec):
            spec = CameraLiveSpec(
                id=int(camera_id),
                ip=str(source.get("ip") or ""),
                username=str(source.get("username") or ""),
                password=str(source.get("password") or ""),
                rtsp_url=str(source.get("rtsp_url") or source.get("uri") or ""),
                sdk_handle=source.get("sdk_handle"),
                ffmpeg_profile=str(source.get("ffmpeg_profile") or DEFAULT_PROFILE),
                transport=str(source.get("transport") or "TCP"),
                need_detect=bool(source.get("need_detect")),
                live_role=str(source.get("live_role") or ROLE_LIVE),
                stream_profiles=dict(source.get("stream_profiles") or {}),
            )
        row = self._session_for(spec)
        if source.get("need_detect"):
            row.detect_consumers = max(row.detect_consumers, 1)
            row.spec = replace(spec, need_detect=True)
        self.ensure_producer(row.spec)
        return await self.health(camera_id)

    async def unregister_stream(self, camera_id: int) -> None:
        self.stop_producer(camera_id, force=True)
        self._sessions.pop(camera_id, None)

    async def health(self, camera_id: int) -> dict[str, Any]:
        row = self._sessions.get(camera_id)
        if row is None:
            return {
                "camera_id": camera_id,
                "connection_state": "DISCONNECTED",
                "ok": False,
            }
        return self._health_row(row)

    async def get_live_endpoint(self, camera_id: int) -> dict[str, Any]:
        return {
            "camera_id": camera_id,
            "kind": "mjpeg",
            "path": f"/cameras/{camera_id}/live.mjpeg",
            "snapshot": f"/cameras/{camera_id}/snapshot.jpg",
        }

    async def get_detect_endpoint(self, camera_id: int) -> dict[str, Any]:
        sample = self.peek_detect(camera_id) or self.peek_live(camera_id)
        return {
            "camera_id": camera_id,
            "kind": "latest-frame",
            "seq": sample.seq if sample else 0,
            "age_ms": sample.age_ms() if sample else None,
        }

    async def snapshot(self, camera_id: int) -> bytes:
        sample = self.peek_live(camera_id) or self.peek_detect(camera_id)
        return sample.jpeg if sample else b""

    async def register_source(self, camera_id: int, source_config: dict[str, Any]) -> dict[str, Any]:
        return await self.register_stream(camera_id, source_config)

    async def unregister_source(self, camera_id: int) -> None:
        await self.unregister_stream(camera_id)

    async def get_snapshot(self, camera_id: int) -> bytes:
        return await self.snapshot(camera_id)

    async def metrics(self, camera_id: int) -> dict[str, Any]:
        return await self.health(camera_id)

    def peek_live(self, camera_id: int) -> FrameSample | None:
        row = self._sessions.get(camera_id)
        return row.live.latest() if row else None

    def peek_detect(self, camera_id: int) -> FrameSample | None:
        row = self._sessions.get(camera_id)
        return row.detect.latest() if row else None

    def note_displayed(self, camera_id: int) -> None:
        row = self._sessions.get(camera_id)
        if row is not None:
            row.frames_displayed += 1

    def note_ai_sample(self, camera_id: int, *, infer_ms: float = 0.0, dropped: bool = False) -> None:
        row = self._sessions.get(camera_id)
        if row is None:
            return
        now = time.monotonic()
        if dropped:
            row.frames_dropped_ai += 1
            return
        row.frames_sampled_ai += 1
        row.ai_infer_ms = float(infer_ms)
        row.ai_last_at = now
        sample = row.detect.latest() or row.live.latest()
        if sample:
            row.ai_last_seq = sample.seq
        if row._ai_fps_at <= 0:
            row._ai_fps_at = now
        row._ai_fps_n += 1
        elapsed = now - row._ai_fps_at
        if elapsed >= 1.0:
            row.ai_fps = round(row._ai_fps_n / elapsed, 1)
            row._ai_fps_at = now
            row._ai_fps_n = 0

    def acquire_live(self, spec: CameraLiveSpec) -> None:
        row = self._session_for(spec)
        row.viewers += 1
        row.last_view_at = time.monotonic()
        self.ensure_producer(spec)

    def release_live(self, camera_id: int) -> None:
        row = self._sessions.get(camera_id)
        if row is None:
            return
        row.viewers = max(0, row.viewers - 1)
        row.last_view_at = time.monotonic()

    def acquire_detect(self, spec: CameraLiveSpec) -> None:
        row = self._session_for(replace(spec, need_detect=True))
        row.detect_consumers = max(row.detect_consumers, 1)
        row.spec = replace(row.spec, need_detect=True)
        self.ensure_producer(row.spec)

    def release_detect(self, camera_id: int) -> None:
        row = self._sessions.get(camera_id)
        if row is None:
            return
        row.detect_consumers = 0
        row.spec = replace(row.spec, need_detect=False)

    def viewers_for(self, camera_id: int) -> int:
        row = self._sessions.get(camera_id)
        return int(row.viewers) if row else 0

    def pumping_spec(self, camera_id: int) -> CameraLiveSpec | None:
        row = self._sessions.get(camera_id)
        if row is None:
            return None
        if row.producer is not None and not row.producer.done():
            return row.spec
        return None

    def touch_live(self, spec: CameraLiveSpec) -> None:
        row = self._session_for(spec)
        row.last_view_at = time.monotonic()
        self.ensure_producer(spec)

    def ensure_producer(self, spec: CameraLiveSpec) -> None:
        self.start_watchers()
        row = self._session_for(spec)
        existing = row.producer
        if existing is not None and not existing.done() and row.spec == spec:
            return
        if existing is not None and not existing.done():
            existing.cancel()
        row.spec = spec
        try:
            row.producer = asyncio.get_running_loop().create_task(
                self._produce(row), name=f"media-{spec.id}",
            )
        except RuntimeError:
            row.producer = None

    def stop_producer(self, camera_id: int, *, force: bool = False) -> None:
        row = self._sessions.get(camera_id)
        if row is None:
            return
        if not force and row.wanted():
            return
        task = row.producer
        row.producer = None
        row.state = "DISCONNECTED"
        if task is not None:
            task.cancel()
        pids = list(row.child_pids)
        row.child_pids.clear()
        row.ffmpeg_pid = None
        for pid in pids:
            _kill_pid(pid)

    def stop_all(self) -> None:
        self.stop_watchers()
        for camera_id in list(self._sessions):
            self.stop_producer(camera_id, force=True)
        self._sessions.clear()

    def live_metrics(self) -> list[dict[str, Any]]:
        return [self._health_row(row) for _, row in sorted(self._sessions.items())]

    def child_pids(self) -> list[int]:
        pids: list[int] = []
        for row in self._sessions.values():
            pids.extend(sorted(row.child_pids))
        return pids

    def _health_row(self, row: StreamSession) -> dict[str, Any]:
        now = time.monotonic()
        live = row.live.latest()
        detect = row.detect.latest()
        pumping = row.producer is not None and not row.producer.done()
        age = round(now - row.last_frame_received_at, 3) if row.last_frame_received_at else None
        profiles = row.spec.stream_profiles or (hvx_profiles(row.spec.sdk_handle) if row.spec.sdk_handle is not None else {})
        warnings = profile_warnings(
            profiles,
            upstream_consumers=1 if pumping else 0,
            decoder_overloaded=row.live_fps > 0 and row.live_fps < 4 and pumping,
        )
        return {
            "camera_id": row.spec.id,
            "connection_state": row.state if pumping or row.state != "DISCONNECTED" else (
                "STREAMING" if pumping else ("cached" if live else "idle")
            ),
            "ok": pumping or bool(live),
            "viewers": row.viewers,
            "detect_consumers": row.detect_consumers,
            "pumping": pumping,
            "source": row.source or (live.source if live else ""),
            "fps": row.live_fps,
            "source_fps": row.live_fps,
            "live_fps": row.live_fps,
            "ai_processed_fps": row.ai_fps,
            "ai_samples_dropped": row.frames_dropped_ai,
            "ai_frame_age_ms": detect.age_ms(now) if detect else None,
            "live_frame_age_ms": live.age_ms(now) if live else None,
            "seq": live.seq if live else 0,
            "age_seconds": age,
            "queue_depth": row.live.depth(),
            "detect_queue_depth": row.detect.depth(),
            "rtsp": (row.url or "").startswith("rtsp://"),
            "sdk": row.source == "sdk" or row.spec.sdk_handle is not None,
            "codec": row.codec or ((profiles.get(ROLE_LIVE) or profiles.get(ROLE_SUB) or {}).get("codec") if isinstance(profiles, dict) else ""),
            "width": row.width,
            "height": row.height,
            "gop": row.gop,
            "transport": row.transport,
            "ffmpeg_profile": row.ffmpeg_profile,
            "using_fallback": row.using_fallback,
            "ffmpeg_pid": row.ffmpeg_pid,
            "child_pids": sorted(row.child_pids),
            "reconnects": row.reconnects,
            "decode_errors": row.decode_errors,
            "frames_received": row.live.received,
            "frames_decoded": row.live.received,
            "frames_displayed": row.frames_displayed,
            "frames_dropped_live": row.live.dropped,
            "frames_sampled_ai": row.frames_sampled_ai,
            "frames_dropped_ai": row.frames_dropped_ai,
            "last_keyframe_age": round(now - row.last_keyframe_at, 3) if row.last_keyframe_at else None,
            "last_frame_received_at": row.last_frame_received_at,
            "bitrate_bps": row.bitrate_bps,
            "ai_infer_ms": row.ai_infer_ms,
            "url_redacted": redact_url(row.url) if row.url else "",
            "stream_profiles": public_profiles(profiles),
            "warnings": warnings,
            "last_error": row.last_error,
        }

    def publish_detect(self, camera_id: int, jpeg: bytes, *, source: str = "", url: str = "") -> FrameSample | None:
        """Fill only the DETECT buffer (MediaMTX local RTSP consumer)."""
        if jpeg[:2] != JPEG_SOI:
            return None
        row = self._sessions.get(camera_id)
        if row is None:
            row = StreamSession(spec=CameraLiveSpec(
                id=camera_id, ip="", username="", password="", rtsp_url="", sdk_handle=None,
                need_detect=True,
            ))
            self._sessions[camera_id] = row
        now = time.monotonic()
        detect_row = (row.spec.stream_profiles or {}).get(ROLE_DETECT) or {}
        ai_fps = float(detect_row.get("ai_fps") or getattr(settings, "detect_fps", 5.0) or 5.0)
        interval = 1.0 / max(ai_fps, 1.0)
        latest_detect = row.detect.latest()
        if latest_detect is not None and (now - latest_detect.received_at) < interval:
            row.frames_dropped_ai += 1
            return latest_detect
        if latest_detect is not None and row.detect.depth() >= row.detect.maxsize:
            row.frames_dropped_ai += 1
        sample = row.detect.put(jpeg, source=source or "mediamtx", url=url)
        row.frames_sampled_ai += 1
        row.ai_last_at = now
        row.ai_last_seq = sample.seq
        return sample

    def publish(self, camera_id: int, jpeg: bytes, *, source: str = "", url: str = "", detect: bool = True) -> FrameSample | None:
        if jpeg[:2] != JPEG_SOI:
            return None
        row = self._sessions.get(camera_id)
        if row is None:
            row = StreamSession(spec=CameraLiveSpec(
                id=camera_id, ip="", username="", password="", rtsp_url="", sdk_handle=None,
            ))
            self._sessions[camera_id] = row
        now = time.monotonic()
        sample = row.live.put(jpeg, source=source, url=url)
        row.last_frame_received_at = now
        row.last_keyframe_at = now
        row.source = source or row.source
        row.url = url or row.url
        if row._fps_at <= 0:
            row._fps_at = now
        row._fps_n += 1
        row._bytes_window += len(jpeg)
        elapsed = now - row._fps_at
        if elapsed >= 1.0:
            row.live_fps = round(row._fps_n / elapsed, 1)
            row.bitrate_bps = int((row._bytes_window * 8) / elapsed)
            row._fps_at = now
            row._fps_n = 0
            row._bytes_window = 0
            row._bytes_at = now
        if detect:
            detect_row = (row.spec.stream_profiles or {}).get(ROLE_DETECT) or {}
            ai_fps = float(detect_row.get("ai_fps") or getattr(settings, "detect_fps", 5.0) or 5.0)
            interval = 1.0 / max(ai_fps, 1.0)
            latest_detect = row.detect.latest()
            if latest_detect is None or (now - latest_detect.received_at) >= interval:
                if latest_detect is not None and row.detect.depth() >= row.detect.maxsize:
                    row.frames_dropped_ai += 1
                row.detect.put(jpeg, source=source, url=url)
        from app.services.preview import remember_frame
        remember_frame(camera_id, jpeg, url=url, url_redacted=redact_url(url) if url else "", source=source)
        return sample

    async def _produce(self, row: StreamSession) -> None:
        spec = row.spec
        try:
            while row.wanted() or row.viewers > 0:
                row.state = "CONNECTING"
                ok = False
                try:
                    if spec.sdk_handle is not None:
                        ok = await self._sdk_frames(row)
                    else:
                        ok = await self._rtsp_frames(row)
                        if not ok:
                            ok = await self._http_stills(row)
                    if ok:
                        reconnect_for(spec.id).record_success()
                    else:
                        row.state = "DEGRADED"
                        row.decode_errors += 1
                        await self._backoff(row, "no frames")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    row.last_error = str(exc)[:300]
                    row.decode_errors += 1
                    row.state = "DEGRADED"
                    await self._backoff(row, str(exc))
                await asyncio.sleep(0.05)
        finally:
            if row.producer is asyncio.current_task():
                row.producer = None
            if not row.wanted():
                row.state = "DISCONNECTED"

    async def _backoff(self, row: StreamSession, error: str) -> None:
        row.state = "RECONNECTING"
        row.reconnects += 1
        await self._reap_children(row)
        wait = reconnect_for(row.spec.id).record_failure(error)
        await asyncio.sleep(min(wait, 8.0))

    async def _reap_children(self, row: StreamSession) -> None:
        pids = list(row.child_pids)
        row.child_pids.clear()
        row.ffmpeg_pid = None
        for pid in pids:
            _kill_pid(pid)
            try:
                await asyncio.wait_for(asyncio.to_thread(_wait_pid, pid), timeout=2.0)
            except Exception:
                _kill_pid(pid, force=True)

    async def _sdk_frames(self, row: StreamSession) -> bool:
        spec = row.spec
        if spec.sdk_handle is None:
            return False
        host = HVXHostClient()
        interval = float(getattr(settings, "live_sdk_interval_seconds", 0.04) or 0.04)
        got = False
        row.state = "STREAMING"
        row.source = "sdk"
        while row.wanted() or row.viewers > 0:
            started = time.monotonic()
            try:
                jpeg = await host.live_jpeg(int(spec.sdk_handle))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                row.last_error = str(exc)[:300]
                jpeg = b""
            if jpeg[:2] == JPEG_SOI:
                self.publish(
                    spec.id, jpeg,
                    source="sdk",
                    url=f"sdk://handle/{int(spec.sdk_handle)}",
                )
                got = True
                row.state = "STREAMING"
            elif got and (time.monotonic() - row.last_frame_received_at) > float(getattr(settings, "stale_stream_seconds", 2.5) or 2.5):
                row.state = "DEGRADED"
                return got
            delay = interval - (time.monotonic() - started)
            await asyncio.sleep(delay if delay > 0.002 else 0.002)
        return got

    async def _rtsp_frames(self, row: StreamSession) -> bool:
        spec = row.spec
        role = spec.live_role or ROLE_LIVE
        preferred = uri_for_role(spec.stream_profiles, role, spec.rtsp_url)
        if role == ROLE_MAIN:
            preferred = uri_for_role(spec.stream_profiles, ROLE_MAIN, preferred)
        urls = vendor_candidates(spec.ip, spec.username, spec.password, preferred or spec.rtsp_url)
        if preferred.startswith("rtsp://"):
            urls = [preferred] + [url for url in urls if url != preferred]
        profiles = [normalize_profile(spec.ffmpeg_profile)]
        fallback = fallback_profile(spec.ffmpeg_profile)
        if fallback not in profiles:
            profiles.append(fallback)
        transports = [normalize_transport(spec.transport)]
        if transports[0] == "AUTO":
            transports = ["TCP", "UDP"]
        for url in urls:
            for profile_name in profiles:
                for transport in transports:
                    stream = self.ffmpeg_jpeg_stream(
                        url,
                        profile=profile_name,
                        transport=transport,
                        scale=960 if role != ROLE_MAIN else None,
                        session=row,
                    )
                    try:
                        first = await asyncio.wait_for(stream.__anext__(), timeout=4.0)
                        row.ffmpeg_profile = profile_name
                        row.using_fallback = profile_name != normalize_profile(spec.ffmpeg_profile)
                        row.transport = transport
                        row.source = "rtsp"
                        row.url = url
                        row.state = "STREAMING"
                        self.publish(spec.id, first, source="rtsp", url=url)
                        async for jpeg in stream:
                            if not (row.wanted() or row.viewers > 0):
                                break
                            self.publish(spec.id, jpeg, source="rtsp", url=url)
                        return True
                    except asyncio.CancelledError:
                        await stream.aclose()
                        raise
                    except Exception as exc:
                        row.last_error = str(exc)[:300]
                        try:
                            await stream.aclose()
                        except Exception:
                            pass
        return False

    async def _http_stills(self, row: StreamSession) -> bool:
        spec = row.spec
        http = await grab_http_snapshot(spec.ip, spec.username, spec.password)
        if http.get("ok"):
            row.source = "http"
            row.url = str(http.get("url") or "")
            row.state = "STREAMING"
            self.publish(
                spec.id, http["jpeg"],
                source="http",
                url=str(http.get("url") or ""),
            )
            return True
        return False

    async def ffmpeg_jpeg_stream(
        self,
        url: str,
        *,
        profile: str = DEFAULT_PROFILE,
        transport: str = "TCP",
        scale: int | None = 960,
        session: StreamSession | None = None,
    ):
        """Keep one ffmpeg process open so live view is a real stream, not one still per spawn."""
        binary = ffmpeg_bin()
        if not binary:
            raise RuntimeError("ffmpeg is not installed")
        cmd = [
            binary,
            "-hide_banner", "-loglevel", "error",
            *profile_args(profile, transport=transport),
            "-i", url,
            "-an", "-vsync", "0", "-flush_packets", "1",
            "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "7",
        ]
        if scale:
            cmd.extend(["-vf", f"scale={int(scale)}:-2"])
        cmd.append("pipe:1")
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            limit=256 * 1024,
        )
        if session is not None and proc.pid:
            session.child_pids.add(proc.pid)
            session.ffmpeg_pid = proc.pid
        buf = b""
        try:
            while True:
                chunk = await asyncio.wait_for(proc.stdout.read(65536), timeout=8)
                if not chunk:
                    err = b""
                    if proc.stderr:
                        err = await proc.stderr.read()
                    raise RuntimeError((err.decode(errors="replace") or "ffmpeg live stream ended")[-300:])
                buf += chunk
                if len(buf) > 2_000_000:
                    start = buf.rfind(JPEG_SOI)
                    buf = buf[start:] if start >= 0 else buf[-200_000:]
                jpeg, buf = take_latest_jpeg(buf)
                if jpeg:
                    yield jpeg
        finally:
            await _terminate_proc(proc)
            if session is not None and proc.pid:
                session.child_pids.discard(proc.pid)
                if session.ffmpeg_pid == proc.pid:
                    session.ffmpeg_pid = None

    async def _idle_watch(self) -> None:
        idle = float(getattr(settings, "live_idle_seconds", 20.0) or 20.0)
        while True:
            await asyncio.sleep(1.0)
            now = time.monotonic()
            for camera_id, row in list(self._sessions.items()):
                if row.wanted():
                    continue
                last = row.last_view_at or 0.0
                if now - last >= idle:
                    self.stop_producer(camera_id, force=True)

    async def _stale_watch(self) -> None:
        stale = float(getattr(settings, "stale_stream_seconds", 2.5) or 2.5)
        while True:
            await asyncio.sleep(0.5)
            now = time.monotonic()
            for row in list(self._sessions.values()):
                if row.producer is None or row.producer.done():
                    continue
                if row.state not in {"STREAMING", "DEGRADED"}:
                    continue
                if not row.last_frame_received_at:
                    continue
                age = now - row.last_frame_received_at
                if age >= stale and row.state == "STREAMING":
                    row.state = "DEGRADED"
                if age >= stale * 2 and row.state == "DEGRADED":
                    task = row.producer
                    if task is not None and not task.done():
                        row.state = "RECONNECTING"
                        task.cancel()


def _kill_pid(pid: int, *, force: bool = False) -> None:
    if not pid:
        return
    try:
        import os
        import signal
        os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
    except Exception:
        pass


def _wait_pid(pid: int) -> None:
    if not pid:
        return
    try:
        import os
        os.waitpid(pid, 0)
    except Exception:
        pass


async def _terminate_proc(proc: asyncio.subprocess.Process, timeout: float = 2.0) -> None:
    if proc.returncode is not None:
        return
    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
    except Exception:
        proc.kill()
        try:
            await asyncio.wait_for(proc.wait(), timeout=1.0)
        except Exception:
            pass


gateway = LocalMediaGateway()
