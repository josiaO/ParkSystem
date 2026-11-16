"""End-to-end latency trace: one JSON line per stage, never blocking the caller.

Standard library only, Python 3.11 compatible: the 32-bit HVX host imports
this module too, so it must not pull in any app dependency.

Every record carries three clocks:

``perf_ns``
    ``time.perf_counter_ns()``. On Windows this is QueryPerformanceCounter
    and on Linux CLOCK_MONOTONIC; both are system-wide, so values from the
    HVX host, the Site Service and the Recognition Worker on one PC can be
    subtracted directly. This is the correlation clock.
``mono_ns``
    ``time.monotonic_ns()``. Kept for the existing lane timeline. On Windows
    with Python < 3.13 it has about 15.6 ms resolution, so do not use it for
    sub-frame comparisons.
``ts``
    Wall-clock epoch seconds, for lining up with other logs and phone video.

Each process writes its own file ``latency-trace-<proc>.jsonl`` (rotated by
size) so two processes never rotate the same file on Windows. The write is
done by a background thread from a bounded buffer: when the buffer is full a
record is dropped and counted, the caller is never delayed.

Environment:

``SMARTPARK_LATENCY_TRACE``           ``0`` disables tracing (default on).
``SMARTPARK_LATENCY_TRACE_DIR``       output directory.
``SMARTPARK_LATENCY_TRACE_FRAME_EVERY`` trace one frame in N per camera
                                      (default 15, about once a second).
``SMARTPARK_FRAME_AGE_LIMIT_MS``      stale limit for video frames (500).
``SMARTPARK_EVENT_AGE_LIMIT_MS``      stale limit for native events (2000).
"""

from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
import json
import os
from pathlib import Path
import threading
import time
import uuid

TRACE_ENV = "SMARTPARK_LATENCY_TRACE"
DIR_ENV = "SMARTPARK_LATENCY_TRACE_DIR"
FRAME_EVERY_ENV = "SMARTPARK_LATENCY_TRACE_FRAME_EVERY"
FRAME_AGE_LIMIT_ENV = "SMARTPARK_FRAME_AGE_LIMIT_MS"
EVENT_AGE_LIMIT_ENV = "SMARTPARK_EVENT_AGE_LIMIT_MS"

_trace_id: ContextVar[str] = ContextVar("latency_trace_id", default="")


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def frame_age_limit_ms() -> int:
    return _env_int(FRAME_AGE_LIMIT_ENV, 500, 1, 600_000)


def event_age_limit_ms() -> int:
    return _env_int(EVENT_AGE_LIMIT_ENV, 2000, 1, 600_000)


def enabled_by_env() -> bool:
    return str(os.environ.get(TRACE_ENV, "1")).strip().lower() not in {"0", "false", "no", "off"}


def default_directory() -> Path:
    configured = os.environ.get(DIR_ENV)
    if configured:
        return Path(configured)
    if os.name == "nt":
        return Path(os.environ.get("PROGRAMDATA") or Path.home()) / "SmartParkEdge" / "logs"
    return Path.cwd() / "logs"


def new_trace_id() -> str:
    return uuid.uuid4().hex


def current_trace_id() -> str:
    return _trace_id.get()


@contextmanager
def trace_context(trace_id: str | None = None):
    """Bind a trace id (for example a gate ``command_uuid``) to this task."""
    token = _trace_id.set(str(trace_id or new_trace_id()))
    try:
        yield _trace_id.get()
    finally:
        _trace_id.reset(token)


def percentile(samples, pct: float):
    values = sorted(float(v) for v in samples)
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 2)
    rank = (len(values) - 1) * (float(pct) / 100.0)
    low = int(rank)
    high = min(low + 1, len(values) - 1)
    value = values[low] + (values[high] - values[low]) * (rank - low)
    return round(value, 2)


class Histogram:
    """Bounded recent-sample window with count and max since start."""

    def __init__(self, size: int = 1024):
        self._samples: deque = deque(maxlen=size)
        self._lock = threading.Lock()
        self.count = 0
        self.max = 0.0

    def add(self, value: float) -> None:
        value = float(value)
        with self._lock:
            self._samples.append(value)
            self.count += 1
            if value > self.max:
                self.max = value

    def summary(self) -> dict:
        with self._lock:
            window = list(self._samples)
            count, peak = self.count, self.max
        return {
            "count": count,
            "window": len(window),
            "p50": percentile(window, 50),
            "p95": percentile(window, 95),
            "p99": percentile(window, 99),
            "max": round(peak, 2) if count else None,
        }


class MetricsRegistry:
    """Named histograms and counters, cheap enough for SDK callback threads."""

    def __init__(self, histogram_size: int = 1024):
        self._histograms: dict = {}
        self._counters: dict = {}
        self._gauges: dict = {}
        self._lock = threading.Lock()
        self._size = int(histogram_size)

    def observe(self, name: str, value: float) -> None:
        histogram = self._histograms.get(name)
        if histogram is None:
            with self._lock:
                histogram = self._histograms.setdefault(name, Histogram(self._size))
        histogram.add(value)

    def incr(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + int(amount)

    def gauge(self, name: str, value) -> None:
        with self._lock:
            self._gauges[name] = value

    def adjust(self, name: str, delta: int) -> int:
        with self._lock:
            value = int(self._gauges.get(name, 0) or 0) + int(delta)
            self._gauges[name] = value
            return value

    def snapshot(self) -> dict:
        with self._lock:
            histograms = dict(self._histograms)
            counters = dict(self._counters)
            gauges = dict(self._gauges)
        return {
            "histograms_ms": {name: histograms[name].summary() for name in sorted(histograms)},
            "counters": {name: counters[name] for name in sorted(counters)},
            "gauges": {name: gauges[name] for name in sorted(gauges)},
        }


class HeartbeatMonitor:
    """Measure how late a sleeping thread wakes up.

    A healthy process wakes within a millisecond or two of the requested
    interval. Lag here is time the interpreter could not schedule a Python
    thread: GIL held by a long C call, CPU starvation, or a paused process.
    """

    def __init__(self, metrics: MetricsRegistry, *, interval: float = 0.02, stall_ms: float = 100.0,
                 on_stall=None, name: str = "latency-heartbeat"):
        self.metrics = metrics
        self.interval = float(interval)
        self.stall_ms = float(stall_ms)
        self.on_stall = on_stall
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)

    def start(self) -> "HeartbeatMonitor":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            started = time.perf_counter_ns()
            time.sleep(self.interval)
            lag = (time.perf_counter_ns() - started) / 1_000_000.0 - self.interval * 1000.0
            lag = max(0.0, lag)
            self.metrics.observe("heartbeat_lag", lag)
            if lag >= self.stall_ms:
                self.metrics.incr("heartbeat_stalls")
                if self.on_stall is not None:
                    try:
                        self.on_stall(round(lag, 2))
                    except Exception:
                        pass


class TraceWriter:
    def __init__(
        self,
        proc: str,
        directory: Path | str | None = None,
        *,
        enabled: bool | None = None,
        max_bytes: int = 20_000_000,
        backups: int = 5,
        buffer_size: int = 20_000,
        flush_interval: float = 0.2,
    ):
        self.proc = str(proc)
        self.enabled = enabled_by_env() if enabled is None else bool(enabled)
        self.directory = Path(directory) if directory is not None else default_directory()
        self.path = self.directory / f"latency-trace-{self.proc}.jsonl"
        self.max_bytes = int(max_bytes)
        self.backups = int(backups)
        self.flush_interval = float(flush_interval)
        self.frame_every = _env_int(FRAME_EVERY_ENV, 15, 1, 100_000)
        self._buffer: deque = deque()
        self._buffer_size = int(buffer_size)
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._idle = threading.Event()
        self._idle.set()
        self._thread: threading.Thread | None = None
        self._closed = False
        self._frame_counters: dict = {}
        self.written = 0
        self.dropped = 0
        self.write_errors = 0
        self.last_error = ""

    # -- producer side -------------------------------------------------
    def emit(self, stage: str, **fields) -> dict | None:
        if not self.enabled or self._closed:
            return None
        record = {
            "ts": round(time.time(), 6),
            "perf_ns": time.perf_counter_ns(),
            "mono_ns": time.monotonic_ns(),
            "proc": self.proc,
            "pid": os.getpid(),
            "stage": str(stage),
        }
        if "trace" not in fields:
            trace = _trace_id.get()
            if trace:
                record["trace"] = trace
        for key, value in fields.items():
            if value is not None:
                record[key] = value
        with self._lock:
            if len(self._buffer) >= self._buffer_size:
                self.dropped += 1
                return None
            self._buffer.append(record)
            self._idle.clear()
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name=f"latency-trace-{self.proc}", daemon=True)
                self._thread.start()
        self._wake.set()
        return record

    def sample_frame(self, key) -> bool:
        """True for one frame in ``frame_every`` per key (camera/stage)."""
        if not self.enabled:
            return False
        with self._lock:
            count = self._frame_counters.get(key, 0)
            self._frame_counters[key] = count + 1
        return count % self.frame_every == 0

    # -- writer side ---------------------------------------------------
    def _run(self) -> None:
        while True:
            self._wake.wait(self.flush_interval)
            self._wake.clear()
            self._drain()
            if self._closed:
                self._drain()
                return

    def _drain(self) -> None:
        with self._lock:
            if not self._buffer:
                self._idle.set()
                return
            batch = list(self._buffer)
            self._buffer.clear()
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            text = "".join(json.dumps(row, ensure_ascii=False, default=str, separators=(",", ":")) + "\n" for row in batch)
            data = text.encode("utf-8")
            try:
                size = self.path.stat().st_size
            except OSError:
                size = 0
            if size and size + len(data) > self.max_bytes:
                self._rotate()
            with open(self.path, "ab") as handle:
                handle.write(data)
            self.written += len(batch)
        except Exception as exc:  # tracing must never take a process down
            self.write_errors += 1
            self.last_error = f"{type(exc).__name__}: {exc}"[:200]
        with self._lock:
            if not self._buffer:
                self._idle.set()

    def _rotate(self) -> None:
        for index in range(self.backups - 1, 0, -1):
            source = self.path.with_name(f"{self.path.name}.{index}")
            if source.exists():
                os.replace(source, self.path.with_name(f"{self.path.name}.{index + 1}"))
        if self.path.exists():
            os.replace(self.path, self.path.with_name(f"{self.path.name}.1"))

    def flush(self, timeout: float = 2.0) -> bool:
        if not self.enabled:
            return True
        self._wake.set()
        return self._idle.wait(timeout)

    def close(self) -> None:
        self.flush()
        self._closed = True
        self._wake.set()

    def stats(self) -> dict:
        with self._lock:
            pending = len(self._buffer)
        return {
            "enabled": self.enabled,
            "path": str(self.path),
            "written": self.written,
            "dropped": self.dropped,
            "pending": pending,
            "write_errors": self.write_errors,
            "last_error": self.last_error,
            "frame_every": self.frame_every,
        }


_tracer: TraceWriter | None = None
_tracer_lock = threading.Lock()


def configure(proc: str, directory: Path | str | None = None, **kwargs) -> TraceWriter:
    """Install the process tracer. Call once at process start."""
    global _tracer
    with _tracer_lock:
        if _tracer is not None:
            _tracer.close()
        _tracer = TraceWriter(proc, directory, **kwargs)
        return _tracer


def get_tracer() -> TraceWriter:
    """Return the process tracer, creating a default one named after the pid."""
    global _tracer
    with _tracer_lock:
        if _tracer is None:
            _tracer = TraceWriter(os.environ.get("SMARTPARK_LATENCY_TRACE_PROC") or f"proc{os.getpid()}")
        return _tracer


def emit(stage: str, **fields) -> dict | None:
    return get_tracer().emit(stage, **fields)


def age_ms_from_perf(perf_ns, now_ns: int | None = None):
    """Age of a ``perf_counter_ns`` stamp taken by any process on this PC."""
    try:
        stamp = int(perf_ns)
    except (TypeError, ValueError):
        return None
    if stamp <= 0:
        return None
    now = time.perf_counter_ns() if now_ns is None else int(now_ns)
    return round((now - stamp) / 1_000_000.0, 2)
