from __future__ import annotations

"""One upstream media producer per camera. Live view and FastALPR are consumers."""

import asyncio

import logging

import time

from collections import deque

from dataclasses import dataclass, field, replace

from typing import Any

from app.config import settings

from app.domain.cameras import CameraStreamStatus

from app.infrastructure.hardware.cameras import adapter_requires_native_stream

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

from app.services.ffmpeg_recovery import drain_stderr

from app.services.http_snapshot import grab_http_snapshot

from app.services.hvx_client import HVXHostClient

from app.services.latest_frame import FrameSample, LatestFrameBuffer

from app.services.rtsp_probe import redact_url, vendor_candidates

from app.services.stream_roles import (
    ROLE_DETECT,
    ROLE_EVIDENCE,
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

# Optional observers keep the camera engine independent from display and
# recognition modules.  The gateway owns transport, buffering, and recovery;
# consumers may subscribe without becoming an import-time dependency of it.
_frame_observers: list = []
_generation_observers: list = []


def register_frame_observer(observer) -> None:
    if callable(observer) and observer not in _frame_observers:
        _frame_observers.append(observer)


def register_generation_observer(observer) -> None:
    if callable(observer) and observer not in _generation_observers:
        _generation_observers.append(observer)


def _notify_frame_observers(*args, **kwargs) -> None:
    for observer in tuple(_frame_observers):
        try:
            observer(*args, **kwargs)
        except Exception:
            log.debug("media frame observer failed", exc_info=True)


def _notify_generation_observers(camera_id: int, generation: int) -> None:
    for observer in tuple(_generation_observers):
        try:
            observer(camera_id, generation=generation)
        except Exception:
            log.debug("media generation observer failed camera=%s", camera_id, exc_info=True)

log = logging.getLogger("smartpark")

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

def live_scale_filter(scale: int) -> str:
    """Fit inside the requested width. A smaller substream is not enlarged."""
    width = max(160, min(int(scale), 1920))
    return f"scale={width}:-2:force_original_aspect_ratio=decrease"

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
    adapter_id: str = "hvx"
    recognition_mode: str = ""

@dataclass
class StreamSession:
    spec: CameraLiveSpec
    state: str = "DISCONNECTED"
    live: LatestFrameBuffer = field(default_factory=lambda: LatestFrameBuffer("live", maxsize=1))
    detect: LatestFrameBuffer = field(default_factory=lambda: LatestFrameBuffer("detect", maxsize=1))
    producer: asyncio.Task | None = None
    producer_spec: CameraLiveSpec | None = None
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
    # Arrivals include repeated JPEGs. Freshness moves only when the picture changes.
    frames_arrived: int = 0
    frames_changed: int = 0
    duplicate_frames: int = 0
    decoder_restarts: int = 0
    last_received_at: float = 0.0
    last_fresh_frame_at: float = 0.0
    frozen: bool = False
    source_fps: float = 0.0
    source_frame_seq: int = 0
    frame_intervals: deque = field(default_factory=lambda: deque(maxlen=256))
    _restart_not_before: float = 0.0
    # Compatibility field retained for older runtime payloads. SDK cameras do
    # not switch to RTSP after OcxConfig goes silent: that would create a
    # competing reader and defeat the vendor's bounded drop-on-full queue.
    native_fallback_until: float = 0.0
    _src_at: float = 0.0
    _src_n: int = 0
    _chg_n: int = 0
    # SDK bridge diagnostics. These are deliberately per camera so a stalled
    # QY lane cannot hide behind a healthy sibling lane.
    sdk_diagnostics: dict[str, Any] = field(default_factory=dict)
    request_duration_ms: float | None = None
    request_status: int | None = None
    request_error: str = ""
    last_source_progress_at: float = 0.0
    recovery_reason: str = ""
    # A reconnect starts a new media generation. Consumers can use this to
    # reject frames that were produced by a cancelled/old decoder task.
    generation: int = 1
    # Wall-clock and monotonic timing are kept separately: wall-clock values
    # are useful in support payloads, while monotonic values are safe for
    # freshness and timeout decisions.
    startup_started_at: float = 0.0
    stream_startup_ms: float | None = None
    connected_at: float = 0.0
    last_reconnected_at: float = 0.0
    last_reconnect_reason: str = ""
    last_successful_frame_at: float = 0.0

    def wanted(self) -> bool:
        return self.viewers > 0 or self.detect_consumers > 0 or self.spec.need_detect

CameraMediaSession = StreamSession

def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 1)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return round(ordered[index], 1)

def _effective_ocr_owner(mode: str) -> str:
    """Describe the configured plate owner without starting a second reader."""
    canonical = str(mode or "").strip().upper()
    if canonical in {"NATIVE_ONLY"}:
        return "native_camera"
    if canonical in {"HYBRID", "NATIVE_WITH_LOCAL_VERIFY"}:
        return "native_camera+fastalpr_worker"
    return "fastalpr_worker"

def _classify_sdk_stall(row: StreamSession, now: float) -> str | None:
    """Separate demand, bridge, and native decoder symptoms for diagnostics."""
    if row.spec.sdk_handle is None and row.source != "sdk":
        return None
    diag = row.sdk_diagnostics
    if not diag:
        return "not_observed"
    demand_age = diag.get("consumer_demand_age_ms")
    pump = diag.get("pump_liveness")
    callback_age = diag.get("callback_age_ms")
    jpeg_age = diag.get("jpeg_age_ms")
    if isinstance(demand_age, (int, float)) and demand_age > 5000:
        return "consumer_inactive"
    if pump is False:
        return "pump_dead"
    if isinstance(callback_age, (int, float)) and callback_age > 5000:
        return "native_decoder_stall"
    if isinstance(jpeg_age, (int, float)) and jpeg_age > 5000:
        return "bridge_or_encode_stall"
    if row.request_duration_ms is not None and row.request_duration_ms > 1000:
        return "bridge_request_stall"
    if row.last_error:
        return "bridge_error"
    return None

def _kill_pid(pid: int, *, force: bool = False) -> None:
    if not pid:
        return
    try:
        import os
        import signal
        # Windows has no SIGKILL; os.kill(SIGTERM) already calls TerminateProcess.
        sig = signal.SIGTERM
        if force and os.name != "nt":
            sig = getattr(signal, "SIGKILL", signal.SIGTERM)
        os.kill(pid, sig)
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
