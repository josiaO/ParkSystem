from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from app.config import settings
from app.core import latency_trace


class HVXHostUnavailable(RuntimeError):
    pass


# Live frames (about 10 per second per camera) are fetched on these threads,
# not on the Site Service event loop. Parsing ~100 KB HTTP responses there,
# 40 times a second for four cameras, was the main source of event-loop
# stalls (median 0.3 s, up to 11 s) that delayed camera events, OCR and gate
# commands. Each camera keeps its own synchronous client, so one stalled
# camera cannot block or close another camera's connection.
_LIVE_WORKERS = 8
_live_executor: ThreadPoolExecutor | None = None
_live_executor_lock = threading.Lock()
_live_clients: dict[tuple[str, int], httpx.Client] = {}
_live_clients_lock = threading.Lock()
_poll_clients: dict[tuple[int, str], httpx.AsyncClient] = {}


def _live_pool() -> ThreadPoolExecutor:
    global _live_executor
    with _live_executor_lock:
        if _live_executor is None:
            _live_executor = ThreadPoolExecutor(max_workers=_LIVE_WORKERS, thread_name_prefix="hvx-live")
        return _live_executor


def _shared_poll_client(base_url: str) -> httpx.AsyncClient:
    key = (id(asyncio.get_running_loop()), base_url.rstrip("/"))
    client = _poll_clients.get(key)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=settings.request_timeout_seconds,
            limits=httpx.Limits(max_keepalive_connections=8, max_connections=16),
            trust_env=False,
        )
        _poll_clients[key] = client
    return client


class _TimedHostClient:
    """The shared host client with one call's timeout (no per-call client)."""

    def __init__(self, client: httpx.AsyncClient, timeout) -> None:
        self._client = client
        self._timeout = timeout

    async def get(self, url, **kwargs):
        kwargs.setdefault("timeout", self._timeout)
        return await self._client.get(url, **kwargs)

    async def post(self, url, **kwargs):
        kwargs.setdefault("timeout", self._timeout)
        return await self._client.post(url, **kwargs)


@contextlib.asynccontextmanager
async def _host_client(base_url: str, timeout):
    """Use instead of ``httpx.AsyncClient(...)`` per call.

    Building an AsyncClient creates an SSL context, which loads the Windows
    certificate store: 100-500 ms of CPU on the Site Service event loop for
    every snapshot trigger, GPIO write or capture read (seen as loop stalls).
    """
    yield _TimedHostClient(_shared_poll_client(base_url), timeout)


async def close_host_clients() -> None:
    loop_id = id(asyncio.get_running_loop())
    clients = [_poll_clients.pop(key) for key in list(_poll_clients) if key[0] == loop_id]
    await asyncio.gather(*(client.aclose() for client in clients), return_exceptions=True)
    with _live_clients_lock:
        live = [_live_clients.pop(key) for key in list(_live_clients)]
    for client in live:
        try:
            client.close()
        except Exception:
            pass


def _drop_live_client(base_url: str, handle: int) -> None:
    """Forget one camera's connection after a transport error; others are untouched."""
    with _live_clients_lock:
        client = _live_clients.pop((base_url.rstrip("/"), int(handle)), None)
    if client is not None:
        try:
            client.close()
        except Exception:
            pass


def _shared_live_client(base_url: str, handle: int) -> httpx.Client:
    """One synchronous client per camera, used only from the live-frame threads."""
    key = (base_url.rstrip("/"), int(handle))
    with _live_clients_lock:
        client = _live_clients.get(key)
        if client is None or client.is_closed:
            client = httpx.Client(
                base_url=base_url.rstrip("/"),
                timeout=httpx.Timeout(0.8, connect=0.4),
                limits=httpx.Limits(max_keepalive_connections=1, max_connections=2, keepalive_expiry=2.0),
                trust_env=False,
            )
            _live_clients[key] = client
        return client


def _fetch_live_frame(base_url: str, handle: int, params: dict) -> tuple[int, dict, bytes]:
    """Runs on a live-frame thread: one long-poll request, fully read."""
    response = _shared_live_client(base_url, handle).get(f"/live-jpeg/{int(handle)}", params=params, timeout=1.4)
    return response.status_code, dict(response.headers), response.content


def _trace_gpio_response(tracer, trace_id: str, handle: int, sent_ns: int, received_ns: int, payload) -> None:
    """Split the round trip into queue, SDK and hold using the host's stamps.

    All stamps are perf_counter_ns from processes on the same PC.
    """
    timing = (payload or {}).get("timing") or {} if isinstance(payload, dict) else {}
    host = (payload or {}).get("host_timing") or {} if isinstance(payload, dict) else {}

    def span(start, end):
        try:
            return round((int(end) - int(start)) / 1e6, 3) if start and end else None
        except (TypeError, ValueError):
            return None

    tracer.emit(
        "gate.http_received", trace=trace_id, camera=handle,
        ok=bool(payload.get("ok")) if isinstance(payload, dict) else False,
        round_trip_ms=span(sent_ns, received_ns),
        sent_to_host_received_ms=span(sent_ns, host.get("request_received_perf_ns")),
        host_queue_wait_ms=host.get("queue_wait_ms"),
        host_received_to_sdk_start_ms=span(host.get("request_received_perf_ns"), timing.get("sdk_start_perf_ns")),
        sent_to_relay_on_ms=span(sent_ns, timing.get("relay_on_perf_ns")),
        gate_setup_ms=timing.get("gate_setup_ms"), write_on_ms=timing.get("write_on_ms"),
        hold_ms=timing.get("hold_ms"), write_off_ms=timing.get("write_off_ms"),
        host_response_to_received_ms=span(host.get("response_ready_perf_ns"), received_ns),
        relay_on_perf_ns=timing.get("relay_on_perf_ns"),
    )


def _trace_live_frame(handle: int, headers, meta: dict, previous: int) -> None:
    tracer = latency_trace.get_tracer()
    captured = headers.get("x-frame-captured-perf-ns")
    age_ms = latency_trace.age_ms_from_perf(captured) if captured else None
    meta["frame_age_ms"] = age_ms
    if not tracer.sample_frame(("client.frame", int(handle))):
        return
    tracer.emit(
        "frame.received", camera=int(handle), seq=meta.get("frame_seq"), previous_seq=previous,
        age_ms=age_ms, host_age_at_serve_ms=headers.get("x-frame-age-ms"),
        request_ms=meta.get("duration_ms"), fresh=meta.get("fresh"),
        stale=bool(age_ms is not None and age_ms > latency_trace.frame_age_limit_ms()),
    )


class HVXHostClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.hvx_host_url).rstrip("/")
        self.last_live_seq: dict[int, int] = {}
        self.last_live_meta: dict[int, dict] = {}

    async def info(self) -> dict:
        try:
            r = await _shared_poll_client(self.base_url).get("/info", timeout=settings.request_timeout_seconds)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            raise HVXHostUnavailable(str(exc)) from exc

    async def connect(self, *, ip: str, port: int, username: str, password: str) -> dict:
        # ConnCameraEx (3s) then ConnCamera fallback (3s) plus StartVideo — HTTP must outlast that.
        http_timeout = max(settings.request_timeout_seconds, settings.hvx_connect_http_timeout_seconds, 20.0)
        try:
            async with _host_client(self.base_url, http_timeout) as client:
                r = await client.post(f"{self.base_url}/connect", json={
                    "ip": ip,
                    "port": port,
                    "timeout": 3,
                    "username": username,
                    "password": password,
                })
                r.raise_for_status()
                return r.json()
        except httpx.HTTPStatusError as exc:
            try:
                detail = exc.response.json()
            except Exception:
                detail = exc.response.text
            raise HVXHostUnavailable(f"HVX host error: {detail}") from exc
        except Exception as exc:
            raise HVXHostUnavailable(str(exc)) from exc

    async def state(self, handle: int) -> dict:
        client = _shared_poll_client(self.base_url)
        r = await client.get(f"/state/{handle}", timeout=settings.request_timeout_seconds)
        r.raise_for_status()
        return r.json()

    async def video_status(self, handle: int) -> dict:
        """Read video-only host diagnostics without refreshing recognition state."""
        try:
            client = _shared_poll_client(self.base_url)
            r = await client.get(f"/video-status/{int(handle)}", timeout=2.0)
            if r.status_code != 200:
                return {"ok": False, "status_code": r.status_code}
            payload = r.json()
            return payload if isinstance(payload, dict) else {"ok": False, "error": "invalid diagnostics"}
        except Exception as exc:
            return {"ok": False, "error": type(exc).__name__}

    async def discover(self, wait_seconds: float = 2.0) -> dict:
        try:
            async with _host_client(self.base_url, max(settings.request_timeout_seconds, wait_seconds + 4.0)) as client:
                r = await client.post(f"{self.base_url}/discover", json={"wait_seconds": wait_seconds})
                r.raise_for_status()
                return r.json()
        except Exception as exc:
            raise HVXHostUnavailable(str(exc)) from exc

    async def disconnect(self, handle: int, *, force: bool = False) -> dict:
        async with _host_client(self.base_url, settings.request_timeout_seconds) as client:
            r = await client.post(f"{self.base_url}/disconnect/{handle}", json={"force": bool(force)})
            r.raise_for_status()
            _drop_live_client(self.base_url, handle)
            return r.json()

    async def last_captures(self) -> dict:
        async with _host_client(self.base_url, settings.request_timeout_seconds) as client:
            r = await client.get(f"{self.base_url}/captures")
            r.raise_for_status()
            return r.json()

    async def snapshot_trigger(self, handle: int) -> dict:
        async with _host_client(self.base_url, settings.request_timeout_seconds) as client:
            r = await client.post(f"{self.base_url}/snapshot-trigger/{int(handle)}")
            r.raise_for_status()
            return r.json()

    async def gpio_write(self, *, handle: int, index: int, value: int) -> dict:
        try:
            async with _host_client(self.base_url, settings.request_timeout_seconds) as client:
                r = await client.post(f"{self.base_url}/gpio/write", json={
                    "handle": int(handle), "index": int(index), "value": int(value),
                })
                r.raise_for_status()
                return r.json()
        except Exception as exc:
            raise HVXHostUnavailable(str(exc)) from exc

    async def gate_setup(self, *, handle: int, state: int = 1, index: int = 0) -> dict:
        try:
            async with _host_client(self.base_url, settings.request_timeout_seconds) as client:
                r = await client.post(f"{self.base_url}/gate-setup", json={
                    "handle": int(handle), "state": int(state), "index": int(index),
                })
                r.raise_for_status()
                return r.json()
        except Exception as exc:
            raise HVXHostUnavailable(str(exc)) from exc

    async def gpio_pulse(self, *, handle: int, index: int = 0, pulse_ms: int = 500) -> dict:
        trace_id = latency_trace.current_trace_id() or latency_trace.new_trace_id()
        tracer = latency_trace.get_tracer()
        created_ns = time.perf_counter_ns()
        sent_ns = None
        try:
            # Shared keep-alive client: constructing one per pulse measured
            # 233-361 ms on the site PC before the relay command was sent.
            if True:
                client = _shared_poll_client(self.base_url)
                sent_ns = time.perf_counter_ns()
                tracer.emit(
                    "gate.http_sent", trace=trace_id, camera=int(handle), index=int(index),
                    pulse_ms=int(pulse_ms), client_create_ms=round((sent_ns - created_ns) / 1e6, 3),
                )
                r = await client.post("/gpio/pulse", json={
                    "handle": int(handle), "index": int(index), "pulse_ms": int(pulse_ms),
                    "trace_id": trace_id,
                }, headers={"X-Trace-Id": trace_id}, timeout=max(settings.request_timeout_seconds, 8.0))
                received_ns = time.perf_counter_ns()
                r.raise_for_status()
                payload = r.json()
                _trace_gpio_response(tracer, trace_id, int(handle), sent_ns, received_ns, payload)
                return payload
        except httpx.HTTPStatusError as exc:
            tracer.emit("gate.http_error", trace=trace_id, camera=int(handle),
                        status_code=exc.response.status_code,
                        elapsed_ms=round((time.perf_counter_ns() - (sent_ns or created_ns)) / 1e6, 3))
            try:
                detail = exc.response.json()
            except Exception:
                detail = exc.response.text
            raise HVXHostUnavailable(f"HVX GPIO error: {detail}") from exc
        except Exception as exc:
            tracer.emit("gate.http_error", trace=trace_id, camera=int(handle), error=type(exc).__name__,
                        elapsed_ms=round((time.perf_counter_ns() - (sent_ns or created_ns)) / 1e6, 3))
            raise HVXHostUnavailable(str(exc)) from exc

    async def event_jpeg(self, handle: int, image_id: int | None = None, *, capture_token: str | None = None) -> bytes:
        from urllib.parse import urlencode
        query = {"capture_token": capture_token} if capture_token else ({"image_id": int(image_id)} if image_id is not None else {})
        suffix = "?" + urlencode(query) if query else ""
        # Shared keep-alive client: building an AsyncClient per call (TLS
        # context + CA bundle on Windows) cost ~0.5 s per event image.
        r = await _shared_poll_client(self.base_url).get(f"/event-jpeg/{int(handle)}{suffix}", timeout=2.0)
        if r.status_code == 200 and r.content[:2] == b"\xff\xd8":
            return r.content
        return b""

    async def event_crop(self, handle: int, image_id: int | None = None, *, capture_token: str | None = None) -> bytes:
        from urllib.parse import urlencode
        query = {"capture_token": capture_token} if capture_token else ({"image_id": int(image_id)} if image_id is not None else {})
        suffix = "?" + urlencode(query) if query else ""
        r = await _shared_poll_client(self.base_url).get(f"/event-crop/{int(handle)}{suffix}", timeout=2.0)
        if r.status_code == 200 and r.content[:2] == b"\xff\xd8":
            return r.content
        return b""

    async def drain_events(self, handle: int) -> list[dict] | None:
        try:
            client = _shared_poll_client(self.base_url)
            r = await client.get(f"/events/{int(handle)}", timeout=2.0)
            if r.status_code == 404:
                return None
            if r.status_code == 200:
                payload = r.json()
                events = payload.get("events") if isinstance(payload, dict) else None
                if isinstance(events, list):
                    return [row for row in events if isinstance(row, dict)]
                return []
        except Exception:
            return None
        return None

    async def drain_reports(self, handle: int) -> list[dict]:
        try:
            client = _shared_poll_client(self.base_url)
            r = await client.get(f"/reports/{int(handle)}", timeout=2.0)
            if r.status_code != 200:
                return []
            payload = r.json()
            rows = payload.get("reports") if isinstance(payload, dict) else None
            return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
        except Exception:
            return []

    async def read_gpio(self, handle: int, index: int = 1) -> dict:
        try:
            async with _host_client(self.base_url, settings.request_timeout_seconds) as client:
                r = await client.get(f"{self.base_url}/gpio/{int(handle)}", params={"index": int(index)})
                if r.status_code != 200:
                    return {"ok": False, "handle": int(handle), "index": int(index)}
                return r.json()
        except Exception as exc:
            return {"ok": False, "handle": int(handle), "index": int(index), "error": str(exc)}

    async def scan_gpio(self, handle: int, indexes: list[int] | None = None) -> list[dict]:
        pins = indexes or [1, 2, 3, 4, 5, 6, 7]
        try:
            client = _shared_poll_client(self.base_url)
            r = await client.get(
                f"/gpio-scan/{int(handle)}",
                params={"indexes": ",".join(str(i) for i in pins)},
                timeout=settings.request_timeout_seconds,
            )
            if r.status_code != 200:
                return []
            payload = r.json()
            rows = payload.get("pins") if isinstance(payload, dict) else None
            return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
        except Exception:
            return []

    async def live_jpeg(self, handle: int) -> bytes:
        """Read the next latest-only OcxConfig frame, never a car-event still.

        The host waits for a source sequence newer than the previous response.
        This prevents the Windows HTTP bridge from returning the same cached
        frame so quickly that an MJPEG consumer displays a stale FIFO.
        """
        started = asyncio.get_running_loop().time()
        handle = int(handle)
        meta = {"status_code": None, "duration_ms": None, "fresh": False, "error": ""}
        try:
            previous = int(self.last_live_seq.get(handle, 0) or 0)
            # Always long-poll: on the first request the host waits for a
            # frame inside its live window instead of returning an old cache.
            params = {"after": previous, "wait_ms": 1000}
            status, raw_headers, content = await asyncio.get_running_loop().run_in_executor(
                _live_pool(), _fetch_live_frame, self.base_url, handle, params,
            )
            headers = httpx.Headers(raw_headers)
            meta["status_code"] = status
            try:
                self.last_live_seq[handle] = int(headers.get("x-frame-seq") or 0)
            except (TypeError, ValueError):
                self.last_live_seq[handle] = 0
            meta["frame_seq"] = self.last_live_seq.get(handle, 0)
            meta["wait"] = headers.get("x-frame-wait") or ""
            if status == 200 and content[:2] == b"\xff\xd8":
                meta["fresh"] = self.last_live_seq.get(handle, 0) > previous
                meta["duration_ms"] = round((asyncio.get_running_loop().time() - started) * 1000.0, 1)
                _trace_live_frame(handle, headers, meta, previous)
                return content
        except (httpx.TransportError, ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            _drop_live_client(self.base_url, handle)
            return b""
        except OSError as exc:
            if int(getattr(exc, "winerror", 0) or 0) == 10054:
                _drop_live_client(self.base_url, handle)
                meta["error"] = "connection_reset"
                return b""
            meta["error"] = type(exc).__name__
            return b""
        except Exception as exc:
            meta["error"] = type(exc).__name__
            return b""
        finally:
            meta["duration_ms"] = round((asyncio.get_running_loop().time() - started) * 1000.0, 1)
            self.last_live_meta[handle] = meta
        return b""

    async def capture_jpeg(self, handle: int, *, trigger: bool = False) -> bytes:
        jpeg = await self.live_jpeg(handle)
        if jpeg[:2] == b"\xff\xd8":
            return jpeg
        if not trigger:
            return b""
        try:
            await self.snapshot_trigger(handle)
        except Exception:
            return b""
        await asyncio.sleep(0.2)
        return await self.live_jpeg(handle)
