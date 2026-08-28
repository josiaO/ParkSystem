"""Live camera video. Persistent SDK JPEG or RTSP ffmpeg stream — not still snapshots."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from app.services.frame_grab import ffmpeg_bin, grab_camera_frame
from app.services.http_snapshot import grab_http_snapshot
from app.services.hvx_client import HVXHostClient
from app.services.rtsp_probe import redact_url, vendor_candidates

JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"
MJPEG_BOUNDARY = "smartparkframe"
MEDIA_KINDS = {"crops", "alpr", "annotated", "snapshots"}


@dataclass
class PreviewState:
    jpeg: bytes = b""
    url: str = ""
    url_redacted: str = ""
    captured_at: float = 0.0
    alpr: dict = field(default_factory=dict)
    seq: int = 0
    source: str = ""
    disk_at: float = 0.0
    fps: float = 0.0
    _fps_at: float = 0.0
    _fps_n: int = 0
    fingerprint: int = 0
    waiter: asyncio.Event | None = field(default=None, repr=False)


_state: dict[int, PreviewState] = {}


def get_state(camera_id: int) -> PreviewState:
    row = _state.get(camera_id)
    if row is None:
        row = PreviewState()
        _state[camera_id] = row
    return row


def _notify(row: PreviewState) -> None:
    waiter = row.waiter
    if waiter is None:
        try:
            waiter = asyncio.Event()
            row.waiter = waiter
        except RuntimeError:
            return
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
    get_state(camera_id).alpr = result


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
    grabbed = await grab_camera_frame(ip, username, password, explicit or cached)
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
    row = get_state(camera_id)
    from app.config import settings
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
        remember_frame(
            camera_id,
            grabbed["jpeg"],
            url=grabbed.get("url") or "",
            url_redacted=grabbed.get("url_redacted") or "",
            source=str(grabbed.get("source") or ""),
            persist=False,
        )
    return grabbed


async def mjpeg_from_cache(camera_id: int):
    last_seq = -1
    while True:
        row = get_state(camera_id)
        jpeg = row.jpeg
        if jpeg[:2] == JPEG_SOI and row.seq != last_seq:
            last_seq = row.seq
            header = (
                f"--{MJPEG_BOUNDARY}\r\n"
                f"Content-Type: image/jpeg\r\n"
                f"Content-Length: {len(jpeg)}\r\n\r\n"
            ).encode("ascii")
            yield header + jpeg + b"\r\n"
            if row.waiter is not None:
                row.waiter.clear()
            continue
        waiter = row.waiter
        if waiter is None:
            waiter = asyncio.Event()
            row.waiter = waiter
        try:
            await asyncio.wait_for(waiter.wait(), timeout=0.4)
        except asyncio.TimeoutError:
            pass


async def ffmpeg_jpeg_stream(url: str):
    """Keep one ffmpeg process open so live view is a real stream, not one still per spawn."""
    binary = ffmpeg_bin()
    if not binary:
        raise RuntimeError("ffmpeg is not installed")
    cmd = [
        binary,
        "-hide_banner", "-loglevel", "error",
        "-rtsp_transport", "tcp",
        "-fflags", "nobuffer",
        "-flags", "low_delay",
        "-i", url,
        "-an", "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "8",
        "-vf", "scale=960:-2",
        "pipe:1",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    buf = b""
    try:
        while True:
            chunk = await asyncio.wait_for(proc.stdout.read(32768), timeout=8)
            if not chunk:
                err = b""
                if proc.stderr:
                    err = await proc.stderr.read()
                raise RuntimeError((err.decode(errors="replace") or "ffmpeg live stream ended")[-300:])
            buf += chunk
            if len(buf) > 6_000_000:
                buf = buf[-400_000:]
            while True:
                start = buf.find(JPEG_SOI)
                end = buf.find(JPEG_EOI, start + 2) if start >= 0 else -1
                if start < 0 or end < 0:
                    if start > 0:
                        buf = buf[start:]
                    break
                jpeg = buf[start:end + 2]
                buf = buf[end + 2:]
                yield jpeg
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()


async def mjpeg_parts(url: str):
    async for jpeg in ffmpeg_jpeg_stream(url):
        header = (
            f"--{MJPEG_BOUNDARY}\r\n"
            f"Content-Type: image/jpeg\r\n"
            f"Content-Length: {len(jpeg)}\r\n\r\n"
        ).encode("ascii")
        yield header + jpeg + b"\r\n"


@dataclass(frozen=True)
class CameraLiveSpec:
    id: int
    ip: str
    username: str
    password: str
    rtsp_url: str
    sdk_handle: int | None


_pumps: dict[int, asyncio.Task] = {}
_pump_specs: dict[int, CameraLiveSpec] = {}
_viewers: dict[int, int] = {}
_last_view: dict[int, float] = {}
_idle_task: asyncio.Task | None = None


async def _sdk_frames(spec: CameraLiveSpec) -> bool:
    """Keep polling Net_GetJpgBuffer while SDK-connected. Empty gaps are normal between frames."""
    if spec.sdk_handle is None:
        return False
    got = False
    host = HVXHostClient()
    from app.config import settings
    interval = float(getattr(settings, "live_sdk_interval_seconds", 0.05) or 0.05)
    while spec.sdk_handle is not None:
        started = time.monotonic()
        try:
            jpeg = await host.live_jpeg(int(spec.sdk_handle))
        except asyncio.CancelledError:
            raise
        except Exception:
            jpeg = b""
        if jpeg[:2] == JPEG_SOI:
            remember_frame(
                spec.id, jpeg,
                url=f"sdk://handle/{int(spec.sdk_handle)}",
                url_redacted=f"sdk://handle/{int(spec.sdk_handle)}",
                source="sdk",
            )
            got = True
        delay = interval - (time.monotonic() - started)
        await asyncio.sleep(delay if delay > 0.005 else 0.005)
    return got


async def _rtsp_frames(spec: CameraLiveSpec) -> bool:
    urls = vendor_candidates(spec.ip, spec.username, spec.password, spec.rtsp_url)
    cached = get_state(spec.id).url
    if cached.startswith("rtsp://"):
        urls = [cached] + [url for url in urls if url != cached]
    for url in urls:
        stream = ffmpeg_jpeg_stream(url)
        try:
            first = await asyncio.wait_for(stream.__anext__(), timeout=4.0)
            redacted = redact_url(url)
            remember_frame(spec.id, first, url=url, url_redacted=redacted, source="rtsp")
            async for jpeg in stream:
                remember_frame(spec.id, jpeg, url=url, url_redacted=redacted, source="rtsp")
            return True
        except asyncio.CancelledError:
            await stream.aclose()
            raise
        except Exception:
            try:
                await stream.aclose()
            except Exception:
                pass
    return False


async def _http_stills(spec: CameraLiveSpec) -> bool:
    http = await grab_http_snapshot(spec.ip, spec.username, spec.password)
    if http.get("ok"):
        remember_frame(
            spec.id, http["jpeg"],
            url=http.get("url") or "",
            url_redacted=http.get("url_redacted") or "",
            source="http",
        )
        return True
    return False


def viewers_for(camera_id: int) -> int:
    return int(_viewers.get(camera_id) or 0)


def touch_live(spec: CameraLiveSpec) -> None:
    """Keep the shared pump alive while a snapshot/MJPEG client is watching."""
    _last_view[spec.id] = time.monotonic()
    start_live_pump(spec)


def acquire_live(spec: CameraLiveSpec) -> None:
    _viewers[spec.id] = viewers_for(spec.id) + 1
    touch_live(spec)


def release_live(camera_id: int) -> None:
    _viewers[camera_id] = max(0, viewers_for(camera_id) - 1)
    _last_view[camera_id] = time.monotonic()


def live_metrics() -> list[dict]:
    rows = []
    ids = set(_pumps) | set(_state) | set(_viewers)
    now = time.monotonic()
    for camera_id in sorted(ids):
        row = get_state(camera_id)
        pumping = camera_id in _pumps and not _pumps[camera_id].done()
        rows.append({
            "camera_id": camera_id,
            "connection_state": "streaming" if pumping else ("cached" if row.jpeg[:2] == JPEG_SOI else "idle"),
            "viewers": viewers_for(camera_id),
            "pumping": pumping,
            "source": row.source,
            "fps": row.fps,
            "seq": row.seq,
            "age_seconds": round(now - row.captured_at, 2) if row.captured_at else None,
            "queue_depth": 1 if row.jpeg[:2] == JPEG_SOI else 0,
            "rtsp": row.url.startswith("rtsp://"),
            "sdk": row.source == "sdk",
        })
    return rows


async def _idle_watch() -> None:
    from app.config import settings
    idle = float(getattr(settings, "live_idle_seconds", 8.0) or 8.0)
    while True:
        await asyncio.sleep(1.0)
        now = time.monotonic()
        for camera_id in list(_pumps):
            if viewers_for(camera_id) > 0:
                continue
            last = _last_view.get(camera_id) or 0.0
            if now - last >= idle:
                stop_live_pump(camera_id)


def start_idle_watch() -> None:
    global _idle_task
    if _idle_task is not None and not _idle_task.done():
        return
    try:
        _idle_task = asyncio.get_running_loop().create_task(_idle_watch(), name="live-idle")
    except RuntimeError:
        _idle_task = None


def stop_idle_watch() -> None:
    global _idle_task
    task = _idle_task
    _idle_task = None
    if task is not None:
        task.cancel()


def start_live_pump(spec: CameraLiveSpec) -> None:
    """Decode only while someone is watching. MJPEG readers share the latest JPEG."""
    start_idle_watch()
    existing = _pumps.get(spec.id)
    previous = _pump_specs.get(spec.id)
    if existing is not None and not existing.done() and previous == spec:
        return
    if existing is not None and not existing.done():
        existing.cancel()

    async def loop():
        try:
            while True:
                if spec.sdk_handle is not None:
                    await _sdk_frames(spec)
                    await asyncio.sleep(0.05)
                    continue
                streamed = await _rtsp_frames(spec)
                if not streamed:
                    await _http_stills(spec)
                    await asyncio.sleep(0.35)
                    continue
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            raise
        finally:
            if _pumps.get(spec.id) is asyncio.current_task():
                _pumps.pop(spec.id, None)
                _pump_specs.pop(spec.id, None)

    try:
        _pumps[spec.id] = asyncio.get_running_loop().create_task(loop(), name=f"live-{spec.id}")
        _pump_specs[spec.id] = spec
    except RuntimeError:
        pass


def stop_live_pump(camera_id: int) -> None:
    task = _pumps.pop(camera_id, None)
    _pump_specs.pop(camera_id, None)
    if task is not None:
        task.cancel()


def stop_live_pumps() -> None:
    stop_idle_watch()
    tasks = list(_pumps.values())
    _pumps.clear()
    _pump_specs.clear()
    _viewers.clear()
    for task in tasks:
        task.cancel()
