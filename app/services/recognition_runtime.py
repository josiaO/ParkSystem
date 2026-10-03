"""Per-camera latest-frame recognition runtime.

Site Service FastALPR and SmartParkRecognitionWorker share this mailbox so a
slow OCR call cannot build a frame backlog, starve another camera, or publish
an obsolete plate. Live video never waits on this module.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.services.latest_frame import FrameSample, LatestFrameBuffer

IDLE = "IDLE"
VEHICLE_PRESENT = "VEHICLE_PRESENT"
RECOGNIZING = "RECOGNIZING"
PLATE_CONFIRMED = "PLATE_CONFIRMED"
EVENT_PUBLISHED = "EVENT_PUBLISHED"
VEHICLE_DEPARTING = "VEHICLE_DEPARTING"

VISIT_STATES = (
    IDLE,
    VEHICLE_PRESENT,
    RECOGNIZING,
    PLATE_CONFIRMED,
    EVENT_PUBLISHED,
    VEHICLE_DEPARTING,
)


@dataclass(frozen=True)
class RecognitionTicket:
    """One in-flight (or pending) recognition request."""

    camera_id: int
    frame_seq: int
    generation: int
    captured_at: float
    recognition_started_at: float
    jpeg: bytes = b""
    source: str = ""
    visit_id: str = ""

    def frame_age_ms(self, now: float | None = None) -> float:
        stamp = self.captured_at or 0.0
        if stamp <= 0:
            return 0.0
        return round(((now if now is not None else time.monotonic()) - stamp) * 1000.0, 1)


@dataclass
class LaneVisit:
    """Presence-scoped visit. Plate text does not start or end a visit."""

    camera_id: int
    state: str = IDLE
    visit_id: str = ""
    published_plate: str = ""
    vehicle_present: bool = False
    last_presence_at: float = 0.0
    last_empty_at: float = 0.0
    last_native_event_at: float = 0.0
    published_events: int = 0
    duplicate_events_suppressed: int = 0

    def _begin(self, now: float) -> None:
        self.visit_id = uuid.uuid4().hex
        self.state = VEHICLE_PRESENT
        self.vehicle_present = True
        self.published_plate = ""
        self.last_presence_at = now
        self.last_empty_at = 0.0

    def reset(self, now: float | None = None) -> None:
        self.state = IDLE
        self.visit_id = ""
        self.published_plate = ""
        self.vehicle_present = False
        if now is not None:
            self.last_empty_at = now

    def observe(
        self,
        *,
        presence: bool,
        plate: str = "",
        now: float | None = None,
        native_event: bool = False,
        absence_seconds: float = 0.6,
    ) -> str:
        now = time.monotonic() if now is None else float(now)
        plate = str(plate or "").strip().upper()
        if native_event:
            self.last_native_event_at = now
            presence = True
        if presence:
            self.last_presence_at = now
            self.last_empty_at = 0.0
            if self.state in {IDLE, VEHICLE_DEPARTING} or not self.visit_id:
                self._begin(now)
            elif self.state == EVENT_PUBLISHED:
                self.vehicle_present = True
            else:
                self.vehicle_present = True
                if self.state == IDLE:
                    self._begin(now)
            if plate and self.state in {VEHICLE_PRESENT, RECOGNIZING}:
                self.state = PLATE_CONFIRMED
                self.published_plate = plate
            elif self.state == VEHICLE_PRESENT:
                self.state = RECOGNIZING
            return self.state
        if self.state == IDLE:
            return self.state
        if self.last_empty_at <= 0:
            self.last_empty_at = now
            self.state = VEHICLE_DEPARTING
            self.vehicle_present = False
            return self.state
        if (now - self.last_empty_at) >= float(absence_seconds):
            self.reset(now)
        else:
            self.state = VEHICLE_DEPARTING
            self.vehicle_present = False
        return self.state

    def mark_published(self, plate: str = "") -> bool:
        """Return True when this visit may create a parking event."""
        if self.state == EVENT_PUBLISHED:
            self.duplicate_events_suppressed += 1
            return False
        if plate:
            self.published_plate = str(plate).strip().upper()
        if not self.visit_id:
            self._begin(time.monotonic())
        self.state = EVENT_PUBLISHED
        self.vehicle_present = True
        self.published_events += 1
        return True


@dataclass
class CameraRecognitionLane:
    camera_id: int
    mailbox: LatestFrameBuffer = field(default_factory=lambda: LatestFrameBuffer("ai-mailbox", maxsize=1))
    visit: LaneVisit = field(init=False)
    generation: int = 1
    inflight: RecognitionTicket | None = None
    last_accepted_seq: int = 0
    last_accepted_generation: int = 0
    last_frame_at: float = 0.0
    last_frame_seq: int = 0
    last_recognition_started_at: float = 0.0
    last_recognition_completed_at: float = 0.0
    last_successful_read_at: float = 0.0
    last_plate: str = ""
    last_plate_at: float = 0.0
    dropped_ai_frames: int = 0
    stale_results_rejected: int = 0
    recognition_stalls: int = 0
    recognition_restarts: int = 0
    native_events_received: int = 0
    software_reads: int = 0
    published_events: int = 0
    duplicate_events_suppressed: int = 0
    sessions_created: int = 0
    last_infer_ms: float = 0.0
    infer_samples: list = field(default_factory=list)
    last_error: str = ""
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        self.visit = LaneVisit(camera_id=self.camera_id)

    def offer_frame(self, jpeg: bytes, *, source: str = "", source_ts: float | None = None) -> FrameSample | None:
        if not jpeg:
            return None
        sample = self.mailbox.put(jpeg, source=source, source_ts=source_ts)
        with self._lock:
            self.last_frame_at = time.monotonic()
            self.last_frame_seq = sample.seq
            self.dropped_ai_frames = int(self.mailbox.dropped)
        return sample

    def take_pending(self) -> FrameSample | None:
        sample = self.mailbox.take()
        if sample is None:
            return None
        with self._lock:
            while self.mailbox.depth() > 0:
                newer = self.mailbox.take()
                if newer is None:
                    break
                sample = newer
        return sample

    def begin(self, sample: FrameSample, *, now: float | None = None) -> RecognitionTicket:
        now = time.monotonic() if now is None else float(now)
        with self._lock:
            ticket = RecognitionTicket(
                camera_id=self.camera_id,
                frame_seq=int(sample.seq),
                generation=int(self.generation),
                captured_at=float(sample.received_at or now),
                recognition_started_at=now,
                jpeg=sample.jpeg,
                source=sample.source,
                visit_id=self.visit.visit_id,
            )
            self.inflight = ticket
            self.last_recognition_started_at = now
            if self.visit.state in {VEHICLE_PRESENT, IDLE}:
                self.visit.state = RECOGNIZING if self.visit.visit_id else self.visit.state
            return ticket

    def accept(
        self,
        ticket: RecognitionTicket,
        *,
        plate: str = "",
        now: float | None = None,
        stale_frame_ms: float = 1000.0,
    ) -> bool:
        """True when this result may update current plate / parking state."""
        now = time.monotonic() if now is None else float(now)
        plate = str(plate or "").strip().upper()
        with self._lock:
            if ticket.generation != self.generation:
                self.stale_results_rejected += 1
                if self.inflight is ticket:
                    self.inflight = None
                return False
            if ticket.frame_seq < self.last_accepted_seq and ticket.generation == self.last_accepted_generation:
                self.stale_results_rejected += 1
                if self.inflight is ticket:
                    self.inflight = None
                return False
            age = ticket.frame_age_ms(now)
            if age > float(stale_frame_ms) and not plate:
                self.stale_results_rejected += 1
            self.last_accepted_seq = max(self.last_accepted_seq, ticket.frame_seq)
            self.last_accepted_generation = ticket.generation
            self.last_recognition_completed_at = now
            self.last_infer_ms = round((now - ticket.recognition_started_at) * 1000.0, 1)
            self.infer_samples.append(self.last_infer_ms)
            if len(self.infer_samples) > 200:
                del self.infer_samples[: len(self.infer_samples) - 200]
            self.software_reads += 1
            if self.inflight is ticket or (self.inflight and self.inflight.frame_seq == ticket.frame_seq):
                self.inflight = None
            if plate:
                self.last_plate = plate
                self.last_plate_at = now
                self.last_successful_read_at = now
            return True

    def reject_inflight(self, ticket: RecognitionTicket | None = None) -> None:
        with self._lock:
            if ticket is None or self.inflight is ticket or (
                self.inflight and ticket and self.inflight.frame_seq == ticket.frame_seq
            ):
                self.inflight = None

    def recover(self) -> int:
        with self._lock:
            self.generation += 1
            self.inflight = None
            self.recognition_stalls += 1
            self.recognition_restarts += 1
            return self.generation

    def note_native_event(self) -> None:
        with self._lock:
            self.native_events_received += 1

    def note_session_created(self) -> None:
        with self._lock:
            self.sessions_created += 1

    def note_duplicate(self) -> None:
        with self._lock:
            self.duplicate_events_suppressed += 1
            self.visit.duplicate_events_suppressed += 1

    def note_published(self) -> None:
        with self._lock:
            self.published_events += 1

    def clear_current_plate(self) -> None:
        with self._lock:
            self.last_plate = ""
            self.last_plate_at = 0.0

    def inflight_age_s(self, now: float | None = None) -> float:
        with self._lock:
            if self.inflight is None:
                return 0.0
            started = self.inflight.recognition_started_at
        if started <= 0:
            return 0.0
        return max(0.0, (now if now is not None else time.monotonic()) - started)

    def is_stalled(self, stall_seconds: float, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else float(now)
        with self._lock:
            frames_fresh = self.last_frame_at > 0 and (now - self.last_frame_at) <= max(float(stall_seconds) * 2.0, 2.0)
            inflight = self.inflight
            started = self.last_recognition_started_at
            completed = self.last_recognition_completed_at
        if not frames_fresh:
            return False
        if inflight is not None:
            return inflight.frame_age_ms(now) / 1000.0 >= float(stall_seconds) or (
                inflight.recognition_started_at > 0 and (now - inflight.recognition_started_at) >= float(stall_seconds)
            )
        if started > 0 and started > completed and (now - started) >= float(stall_seconds):
            return True
        return False

    def snapshot(self, *, now: float | None = None, plate_fresh_seconds: float = 4.0) -> dict[str, Any]:
        now = time.monotonic() if now is None else float(now)
        with self._lock:
            inflight = self.inflight
            plate_age = (now - self.last_plate_at) * 1000.0 if self.last_plate and self.last_plate_at else None
            plate_current = ""
            if self.last_plate and self.last_plate_at and (now - self.last_plate_at) <= float(plate_fresh_seconds):
                if self.visit.vehicle_present or self.visit.state not in {IDLE, VEHICLE_DEPARTING}:
                    plate_current = self.last_plate
            pending = self.mailbox.snapshot()
            samples = list(self.infer_samples)
            state = self.visit.state
            if inflight is not None and state == IDLE:
                state = RECOGNIZING
            return {
                "camera_id": self.camera_id,
                "recognition_state": state,
                "recognition_generation": self.generation,
                "recognition_inflight": inflight is not None,
                "recognition_frame_seq": inflight.frame_seq if inflight else self.last_accepted_seq,
                "last_frame_at": self.last_frame_at,
                "frame_seq": self.last_frame_seq,
                "last_recognition_started_at": self.last_recognition_started_at,
                "last_recognition_completed_at": self.last_recognition_completed_at,
                "last_successful_read_at": self.last_successful_read_at,
                "last_plate": plate_current,
                "last_plate_age_ms": round(plate_age, 1) if plate_age is not None else None,
                "vehicle_present": bool(self.visit.vehicle_present),
                "visit_id": self.visit.visit_id,
                "dropped_ai_frames": int(self.mailbox.dropped or self.dropped_ai_frames),
                "stale_results_rejected": self.stale_results_rejected,
                "recognition_stalls": self.recognition_stalls,
                "recognition_restarts": self.recognition_restarts,
                "native_events_received": self.native_events_received,
                "software_reads": self.software_reads,
                "published_events": self.published_events or self.visit.published_events,
                "duplicate_events_suppressed": self.duplicate_events_suppressed or self.visit.duplicate_events_suppressed,
                "sessions_created": self.sessions_created,
                "pending_queue_depth": int(pending.get("depth") or 0),
                "inference_ms": self.last_infer_ms,
                "inference_ms_p50": _percentile(samples, 50),
                "inference_ms_p95": _percentile(samples, 95),
                "inference_ms_max": round(max(samples), 1) if samples else None,
                "last_error": self.last_error,
            }


class FairInferenceScheduler:
    """Global OCR cap with per-camera fairness.

    Each camera may hold at most one in-flight slot. A stalled camera is force-
    released so it cannot monopolize the process-wide limit.
    """

    def __init__(self, max_concurrency: int = 2) -> None:
        self.max_concurrency = max(1, int(max_concurrency or 1))
        self._held: dict[int, float] = {}
        self._lock = threading.Lock()
        self._zombies = 0

    def try_acquire(self, camera_id: int, *, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else float(now)
        camera_id = int(camera_id)
        with self._lock:
            if camera_id in self._held:
                return False
            if len(self._held) >= self.max_concurrency:
                return False
            self._held[camera_id] = now
            return True

    def release(self, camera_id: int) -> None:
        with self._lock:
            self._held.pop(int(camera_id), None)

    def force_release(self, camera_id: int) -> None:
        with self._lock:
            if int(camera_id) in self._held:
                self._held.pop(int(camera_id), None)
                self._zombies += 1

    def held(self) -> list[int]:
        with self._lock:
            return list(self._held)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "max_concurrency": self.max_concurrency,
                "inflight_cameras": list(self._held),
                "inflight": len(self._held),
                "zombies_released": self._zombies,
            }


class RecognitionRuntime:
    def __init__(self, max_concurrency: int | None = None) -> None:
        from app.config import settings

        cap = max_concurrency
        if cap is None:
            cap = int(getattr(settings, "recognition_max_concurrency", 4) or 4)
        self.scheduler = FairInferenceScheduler(cap)
        self._lanes: dict[int, CameraRecognitionLane] = {}
        self._lock = threading.Lock()

    def lane(self, camera_id: int) -> CameraRecognitionLane:
        camera_id = int(camera_id)
        with self._lock:
            row = self._lanes.get(camera_id)
            if row is None:
                row = CameraRecognitionLane(camera_id=camera_id)
                self._lanes[camera_id] = row
            return row

    def offer_frame(self, camera_id: int, jpeg: bytes, *, source: str = "") -> FrameSample | None:
        return self.lane(camera_id).offer_frame(jpeg, source=source)

    def begin_if_idle(self, camera_id: int, *, stale_frame_ms: float = 1000.0) -> RecognitionTicket | None:
        lane = self.lane(camera_id)
        if lane.inflight is not None:
            return None
        if not self.scheduler.try_acquire(camera_id):
            return None
        sample = lane.take_pending()
        if sample is None:
            self.scheduler.release(camera_id)
            return None
        if sample.age_ms() > float(stale_frame_ms):
            lane.dropped_ai_frames += 1
            self.scheduler.release(camera_id)
            return None
        return lane.begin(sample)

    def finish(self, ticket: RecognitionTicket, *, plate: str = "", stale_frame_ms: float = 1000.0) -> bool:
        lane = self.lane(ticket.camera_id)
        ok = lane.accept(ticket, plate=plate, stale_frame_ms=stale_frame_ms)
        self.scheduler.release(ticket.camera_id)
        return ok

    def recover(self, camera_id: int) -> int:
        lane = self.lane(camera_id)
        generation = lane.recover()
        self.scheduler.force_release(camera_id)
        return generation

    def watchdog_once(self, stall_seconds: float | None = None) -> list[int]:
        from app.config import settings

        stall = float(
            stall_seconds
            if stall_seconds is not None
            else getattr(settings, "recognition_worker_stall_seconds", 5.0)
        )
        recovered: list[int] = []
        with self._lock:
            ids = list(self._lanes)
        for camera_id in ids:
            if self.lane(camera_id).is_stalled(stall):
                self.recover(camera_id)
                recovered.append(camera_id)
        return recovered

    def snapshot(self, camera_id: int | None = None) -> dict[str, Any] | list[dict[str, Any]]:
        from app.config import settings

        fresh = float(getattr(settings, "live_plate_fresh_seconds", 4.0) or 4.0)
        if camera_id is not None:
            return self.lane(int(camera_id)).snapshot(plate_fresh_seconds=fresh)
        with self._lock:
            ids = sorted(self._lanes)
        return [self.lane(cid).snapshot(plate_fresh_seconds=fresh) for cid in ids]

    def reset(self) -> None:
        with self._lock:
            self._lanes.clear()
        self.scheduler = FairInferenceScheduler(self.scheduler.max_concurrency)


def _percentile(samples: list[float], pct: float) -> float | None:
    if not samples:
        return None
    ordered = sorted(float(item) for item in samples)
    if len(ordered) == 1:
        return round(ordered[0], 1)
    rank = (float(pct) / 100.0) * (len(ordered) - 1)
    low = int(rank)
    high = min(len(ordered) - 1, low + 1)
    frac = rank - low
    return round(ordered[low] * (1.0 - frac) + ordered[high] * frac, 1)


runtime = RecognitionRuntime()
