from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import platform
import socket
import struct
import sys
import threading
import time
from urllib.parse import parse_qs, urlparse

# The install root (repo root, or the kit payload) holds app/core/latency_trace.py,
# which is standard-library only and shared with the 64-bit app.
_INSTALL_ROOT = str(Path(__file__).resolve().parents[2])
if _INSTALL_ROOT not in sys.path:
    sys.path.append(_INSTALL_ROOT)

from hvx_sdk import HVXSDK, HVXSDKError, describe_rc, HOST_METRICS, _latency, _trace, _trace_sample

HOST="127.0.0.1"
PORT=int(os.environ.get("SMARTPARK_HVX_PORT", "8765"))


def _int_or(value, default: int) -> int:
    """Convert JSON numbers while treating an explicit null as omitted."""
    return int(default if value is None else value)


def _env_bounded(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


class BoundedHTTPServer(HTTPServer):
    """Serve SDK requests without creating an unbounded thread per socket.

    The old ``ThreadingHTTPServer`` allocated a native thread for every
    polling connection.  A stuck SDK GPIO call therefore consumed another
    thread on every dashboard poll until Windows returned ``can't start new
    thread``.  That took the camera/control plane down even though the camera
    sessions themselves were still connected.

    Keep a small fixed worker pool and a bounded admission semaphore.  A
    saturated host rejects excess requests instead of accumulating work that
    can never be serviced.  The SDK callbacks and camera decoder remain
    independent of this HTTP pool.
    """

    request_queue_size = 64

    def __init__(self, server_address, handler_class, *, max_workers: int | None = None, max_pending: int | None = None):
        # Each watched camera holds one live-video long-poll (<=1.5 s) while
        # event drains, event photos, GPIO and coil polls also need workers.
        # Eight workers saturated with three or four cameras and rejected the
        # plate-event drains that recognition depends on.
        if max_workers is None:
            max_workers = _env_bounded("SMARTPARK_HVX_HTTP_WORKERS", 24, 4, 64)
        if max_pending is None:
            max_pending = _env_bounded("SMARTPARK_HVX_HTTP_PENDING", 48, 8, 256)
        super().__init__(server_address, handler_class)
        self.daemon_threads = True
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="hvx-http")
        self._request_slots = threading.BoundedSemaphore(max_workers + max_pending)

        self.max_workers = int(max_workers)
        self.max_pending = int(max_pending)
        HOST_METRICS.gauge("http.max_workers", self.max_workers)
        HOST_METRICS.gauge("http.max_pending", self.max_pending)

    def process_request(self, request, client_address):
        accepted_ns = time.perf_counter_ns()
        HOST_METRICS.incr("http.connections_accepted")
        if not self._request_slots.acquire(blocking=False):
            # Do not hand a request to an unbounded queue.  The client will
            # retry through the normal HTTP client backoff path.
            HOST_METRICS.incr("http.connections_rejected")
            _trace("host.http.rejected", reason="request slots exhausted")
            try:
                request.close()
            except OSError:
                pass
            return
        HOST_METRICS.adjust("http.connections_queued", 1)
        try:
            self._executor.submit(self._process_request, request, client_address, accepted_ns)
        except RuntimeError:
            HOST_METRICS.adjust("http.connections_queued", -1)
            self._request_slots.release()
            try:
                request.close()
            except OSError:
                pass

    def _process_request(self, request, client_address, accepted_ns=None):
        # A worker owns this connection until the client closes it or the
        # keep-alive socket idles out. Time spent waiting for a worker is the
        # queue wait that a boom command would see on a fresh connection.
        queue_wait_ms = round((time.perf_counter_ns() - accepted_ns) / 1_000_000.0, 3) if accepted_ns else None
        HOST_METRICS.adjust("http.connections_queued", -1)
        busy = HOST_METRICS.adjust("http.workers_busy", 1)
        if queue_wait_ms is not None:
            HOST_METRICS.observe("http.connection_queue_wait", queue_wait_ms)
        _connection_state.queue_wait_ms = queue_wait_ms
        _connection_state.workers_busy_at_start = busy
        _connection_state.requests = 0
        started_ns = time.perf_counter_ns()
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            HOST_METRICS.observe("http.connection_held", (time.perf_counter_ns() - started_ns) / 1_000_000.0)
            HOST_METRICS.adjust("http.workers_busy", -1)
            self.shutdown_request(request)
            self._request_slots.release()

    def server_close(self):
        super().server_close()
        self._executor.shutdown(wait=False, cancel_futures=True)


_connection_state = threading.local()


def _endpoint_key(method: str, path: str) -> str:
    parts = [part for part in str(path or "").split("/") if part]
    if not parts:
        return f"{method} /"
    if parts[0] == "gpio" and len(parts) > 1 and parts[1] in {"pulse", "write"}:
        return f"{method} /gpio/{parts[1]}"
    return f"{method} /{parts[0]}"


# Endpoints that control hardware or report health are traced on every call;
# frame and event polls are sampled so tracing cannot load the host.
_ALWAYS_TRACED = {"POST /gpio/pulse", "POST /gpio/write", "POST /gate-setup", "GET /gpio", "GET /metrics"}


def _is_peer_disconnect(exc: BaseException) -> bool:
    """Return true for a client closing an HTTP keep-alive socket normally."""
    if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
        return True
    if isinstance(exc, OSError) and int(getattr(exc, "winerror", 0) or 0) == 10054:
        return True
    text = str(exc).lower()
    return "10054" in text or "forcibly closed" in text or "connection reset" in text


def resolve_vendor_dir() -> Path:
    env = os.environ.get("SMARTPARK_HVX_VENDOR_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve().parent
    ocx = here.parent.parent / "OcxConfig"
    local = here / "vendor"
    installed = here.parent.parent / "vendor"
    supplied = here.parent.parent / "Current_ParkSystem_configs" / "Camera_config" / "OcxConfig"
    for candidate in (installed, ocx, local, supplied):
        if (candidate / "NetSDK.dll").exists():
            return candidate
    return ocx if ocx.exists() else local


VENDOR = resolve_vendor_dir()

FAKE_SDK_FLAG = "--fake-sdk"


def fake_sdk_requested(argv=None) -> bool:
    argv = sys.argv if argv is None else argv
    return FAKE_SDK_FLAG in argv or os.environ.get("SMARTPARK_HVX_FAKE_SDK") == "1"


def create_sdk(*, fake: bool = False):
    """Real NetSDK, or the deterministic fake from tests/fakes (developer machines only)."""
    if fake:
        fakes = Path(_INSTALL_ROOT) / "tests" / "fakes"
        if not (fakes / "fake_hvx_sdk.py").is_file():
            raise HVXSDKError("--fake-sdk needs tests/fakes/fake_hvx_sdk.py (developer checkout only)")
        if str(fakes) not in sys.path:
            sys.path.insert(0, str(fakes))
        import fake_hvx_sdk
        return fake_hvx_sdk.make_sdk(HVXSDK, VENDOR)
    return HVXSDK(VENDOR)


HOST_LOG_DIRECTORY = Path(os.environ.get("PROGRAMDATA") or Path.home()) / "SmartParkEdge" / "logs"

# Records emitted while the SDK connects (before start_instrumentation) must
# land in the host's own trace file, next to hvx-host.log.
os.environ.setdefault("SMARTPARK_LATENCY_TRACE_PROC", "hvx-host")
if __name__ == "__main__" and _latency is not None:
    _latency.configure("hvx-host", None if os.environ.get(_latency.DIR_ENV) else HOST_LOG_DIRECTORY)

sdk=None
startup_error=""
try:
    sdk=create_sdk(fake=fake_sdk_requested())
except Exception as exc:
    startup_error=str(exc)


def metrics_payload() -> dict:
    payload = HOST_METRICS.snapshot()
    payload["clock"] = "perf_counter_ns"
    payload["now_perf_ns"] = time.perf_counter_ns()
    payload["fake_sdk"] = bool(getattr(sdk, "fake_sdk", False))
    payload["trace"] = _latency.get_tracer().stats() if _latency is not None else {"enabled": False}
    if sdk is not None:
        cameras = {}
        try:
            for row in sdk.connection_sessions():
                handle = int(row.get("handle"))
                video = row.get("video") or {}
                cameras[str(handle)] = {
                    "ip": row.get("ip"),
                    "capture_mode": video.get("capture_mode"),
                    "frame_delivery": video.get("frame_delivery"),
                    "draw_data_primary": video.get("draw_data_primary"),
                    "frame_age_ms": video.get("frame_age_ms"),
                    "callback_fps": video.get("callback_fps"),
                    "jpeg_production_fps": video.get("jpeg_production_fps"),
                    "event_queue_depth": len(getattr(sdk, "_pending_events", {}).get(handle) or ()),
                }
        except Exception as exc:
            cameras = {"error": str(exc)}
        payload["cameras"] = cameras
    return payload


def reply(handler, status, payload):
    body=json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type","application/json")
    handler.send_header("Content-Length",str(len(body)))
    handler.send_header("Connection", "keep-alive")
    handler.end_headers(); handler.wfile.write(body)


def reply_jpeg(handler, jpeg: bytes, status=200, headers=None):
    handler.send_response(status)
    handler.send_header("Content-Type", "image/jpeg")
    handler.send_header("Content-Length", str(len(jpeg)))
    for name, value in (headers or {}).items():
        handler.send_header(str(name), str(value))
    handler.send_header("Connection", "keep-alive")
    handler.end_headers()
    handler.wfile.write(jpeg)


def reply_empty(handler, status=204, headers=None):
    handler.send_response(status)
    for name, value in (headers or {}).items():
        handler.send_header(str(name), str(value))
    handler.send_header("Content-Length", "0")
    handler.send_header("Connection", "keep-alive")
    handler.end_headers()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version="SmartParkHVXHost/0.1"
    # Idle keep-alive connections hold one bounded worker until this expires.
    keepalive_timeout = 10.0
    def setup(self):
        super().setup()
        # A keep-alive socket must not reserve one of the bounded workers
        # forever when an httpx client disappears without a clean FIN.
        self.request.settimeout(self.keepalive_timeout)
    def handle_one_request(self):
        # Browsers and the desktop client can close a keep-alive /info or JPEG
        # request while the host is writing its response.  socketserver prints
        # a traceback for that expected RST, which obscures actual SDK errors.
        try:
            return super().handle_one_request()
        except (TimeoutError, socket.timeout):
            self.close_connection = True
            return
        except OSError as exc:
            if _is_peer_disconnect(exc):
                self.close_connection = True
                return
            raise
    def log_message(self, fmt, *args):
        # Live JPEG is polled many times a second. Writing each one to a
        # captured stdout pipe blocks the response until that pipe drains.
        path = urlparse(self.path).path if getattr(self, "path", "") else ""
        if path.startswith("/live-jpeg/") or path.startswith("/capture-jpeg/"):
            return
        try:
            sys.stdout.write("[hvx-host] " + (fmt % args) + "\n")
        except Exception:
            return
    def log_error(self, fmt, *args):
        # BaseHTTPRequestHandler logs request failures through this method in
        # some Python versions, before the outer server loop sees them.
        text = fmt % args if args else str(fmt)
        if _is_peer_disconnect(OSError(text)):
            return
        super().log_error(fmt, *args)
    def _timed(self, method: str, dispatch):
        started_ns = time.perf_counter_ns()
        path = urlparse(self.path).path
        endpoint = _endpoint_key(method, path)
        self._request_started_ns = started_ns
        self._endpoint = endpoint
        first = getattr(_connection_state, "requests", 0) == 0
        _connection_state.requests = getattr(_connection_state, "requests", 0) + 1
        queue_wait_ms = getattr(_connection_state, "queue_wait_ms", None) if first else 0.0
        self._queue_wait_ms = queue_wait_ms
        try:
            return dispatch()
        finally:
            handler_ms = round((time.perf_counter_ns() - started_ns) / 1_000_000.0, 3)
            HOST_METRICS.observe(f"http.handler.{endpoint}", handler_ms)
            HOST_METRICS.incr(f"http.requests.{endpoint}")
            if endpoint in _ALWAYS_TRACED or _trace_sample(("http", endpoint)):
                _trace(
                    "host.http.request", trace=self.headers.get("X-Trace-Id") or None,
                    endpoint=endpoint, handler_ms=handler_ms, queue_wait_ms=queue_wait_ms,
                    first_on_connection=first,
                    workers_busy=getattr(_connection_state, "workers_busy_at_start", None),
                )
    def do_GET(self):
        return self._timed("GET", self._do_GET)
    def do_POST(self):
        return self._timed("POST", self._do_POST)
    def _do_GET(self):
        parsed=urlparse(self.path)
        path=parsed.path
        query=parse_qs(parsed.query)
        if path == "/info":
            required = ["NetSDK.dll", "CommModule.dll", "PlaySdk.dll", "Log.dll", "RtspRecvSdk.dll", "DecodeSdk.dll"]
            files = {name: (VENDOR / name).exists() for name in required}
            api_required = ["Net_Init", "Net_StartVideo", "Net_AddPlayWindow", "Net_SetDrawDataOut", "Net_GetJpgBuffer", "Net_FreeBuffer"]
            api_available = {name: bool(sdk and hasattr(sdk.dll, name)) for name in api_required}
            return reply(self, 200, {
                "available": sdk is not None,
                "connections": sdk.connection_sessions() if sdk else [],
                "startup_error": startup_error,
                "python_bits": struct.calcsize("P") * 8,
                "platform": platform.platform(),
                "vendor_dir": str(VENDOR),
                "dll": "NetSDK.dll",
                "stream_backend": "ocxconfig_netsdk",
                "stream_delivery": [
                    "Net_AddPlayWindow",
                    "Net_SetDrawDataOut (primary decoded-frame callback)",
                    "Net_GetJpgBuffer (compatibility fallback)",
                ],
                "latest_frame_policy": "bounded_latest_frame_drop_old",
                "native_requirements": {
                    "python_bits": 32,
                    "vendor_files": files,
                    "api": api_available,
                    "primary_delivery": "Net_StartVideo -> Net_AddPlayWindow -> Net_SetDrawDataOut -> bounded latest JPEG",
                    "fallback_delivery": "Net_GetJpgBuffer or PlaySdk HWND capture",
                },
                "files": files,
                "missing": [name for name, present in files.items() if not present],
                "sdk_control_port_default": 30000,
                "timeout_unit": "seconds",
                "connect_sequence": [
                    "Net_Init",
                    "Net_AddCamera",
                    "Net_RegReportMessEx",
                    "Net_ConnCameraEx then Net_ConnCamera fallback",
                    "Net_QueryConnState",
                    "Net_FuntionListRsp then capability-selected stream type",
                    "Net_RegOffLineClient",
                    "Net_StartVideo -> Net_ShowPlateRegion -> Net_AddPlayWindow -> Net_SetDrawDataOut (primary)",
                    "Net_RegImageRecvEx2 then Net_RegImageRecvEx",
                ],
            })
        if path == "/metrics":
            return reply(self, 200, metrics_payload())
        if path == "/captures":
            if not sdk: return reply(self,503,{"error":startup_error})
            try:
                return reply(self,200,{"captures": sdk.last_captures()})
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        if path.startswith("/events/"):
            if not sdk: return reply(self,503,{"error":startup_error})
            try:
                handle=int(path.rsplit("/",1)[-1])
                return reply(self,200,{"events": sdk.drain_events(handle)})
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        if path.startswith("/reports/"):
            if not sdk: return reply(self,503,{"error":startup_error})
            try:
                handle=int(path.rsplit("/",1)[-1])
                return reply(self,200,{"reports": sdk.drain_reports(handle)})
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        if path.startswith("/gpio-scan/"):
            if not sdk: return reply(self,503,{"error":startup_error})
            try:
                handle=int(path.rsplit("/",1)[-1])
                raw=(query.get("indexes") or ["1,2,3,4,5,6,7"])[0]
                indexes=[int(part) for part in str(raw).split(",") if part.strip().isdigit()]
                return reply(self,200,{"pins": sdk.gpio_states(handle, indexes or [1,2,3,4,5,6,7])})
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        if path.startswith("/gpio/"):
            if not sdk: return reply(self,503,{"error":startup_error})
            try:
                parts=[p for p in path.split("/") if p]
                handle=int(parts[1])
                index=int(query.get("index",[parts[2] if len(parts)>2 else 1])[0])
                return reply(self,200,sdk.read_gpio(handle, index))
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        if path.startswith("/event-jpeg/"):
            if not sdk: return reply(self,503,{"error":startup_error})
            try:
                handle=int(path.rsplit("/",1)[-1])
                image_id=query.get("image_id") or query.get("id")
                jpeg=sdk.event_jpeg_for(handle, int(image_id[0]) if image_id else None, capture_token=(query.get("capture_token") or [None])[0])
                if not jpeg:
                    return reply(self,404,{"error":"no car snapshot yet"})
                return reply_jpeg(self, jpeg)
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        if path.startswith("/event-crop/"):
            if not sdk: return reply(self,503,{"error":startup_error})
            try:
                handle=int(path.rsplit("/",1)[-1])
                image_id=query.get("image_id") or query.get("id")
                jpeg=sdk.event_crop_for(handle, int(image_id[0]) if image_id else None, capture_token=(query.get("capture_token") or [None])[0])
                if not jpeg:
                    return reply(self,404,{"error":"no plate crop yet"})
                return reply_jpeg(self, jpeg)
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        if path.startswith("/live-jpeg/") or path.startswith("/capture-jpeg/"):
            if not sdk: return reply(self,503,{"error":startup_error})
            try:
                handle=int(path.rsplit("/",1)[-1])
                after = _int_or((query.get("after") or [0])[0], 0)
                wait_ms = _int_or((query.get("wait_ms") or [0])[0], 0)
                jpeg, seq = sdk.live_frame_for(handle, after_seq=after, wait_ms=wait_ms)
                if not jpeg:
                    HOST_METRICS.incr(f"frames.served_empty.{handle}")
                    return reply_empty(self, 204, headers={
                        "X-Frame-Seq": seq,
                        "X-Frame-Wait": "timeout" if after else "empty",
                    })
                headers = {"X-Frame-Seq": seq}
                captured = sdk.live_frame_captured_perf_ns(handle, seq) if hasattr(sdk, "live_frame_captured_perf_ns") else None
                if captured:
                    now_ns = time.perf_counter_ns()
                    age_ms = round((now_ns - captured) / 1_000_000.0, 2)
                    headers["X-Frame-Captured-Perf-Ns"] = captured
                    headers["X-Frame-Age-Ms"] = age_ms
                    HOST_METRICS.observe("frame.age_at_serve", age_ms)
                    if _trace_sample(("served", handle)):
                        _trace("host.frame.served", camera=handle, seq=seq, age_ms=age_ms, after=after,
                               wait_ms=wait_ms, captured_perf_ns=captured,
                               long_poll_ms=round((now_ns - self._request_started_ns) / 1_000_000.0, 2))
                HOST_METRICS.incr(f"frames.served.{handle}")
                return reply_jpeg(self, jpeg, headers=headers)
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        if path.startswith("/video-status/"):
            if not sdk: return reply(self,503,{"error":startup_error})
            try:
                handle=int(path.rsplit("/",1)[-1])
                return reply(self,200,sdk.video_status(handle))
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        if path.startswith("/state/"):
            if not sdk: return reply(self,503,{"error":startup_error})
            try:
                handle=int(path.rsplit("/",1)[-1]); state=sdk.state(handle)
                payload = {"handle": handle}
                if isinstance(state, dict):
                    payload.update(state)
                else:
                    payload["state"] = state
                return reply(self,200,payload)
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        return reply(self,404,{"error":"not found"})
    def _do_POST(self):
        path=urlparse(self.path).path
        length=int(self.headers.get("Content-Length","0") or 0)
        try: data=json.loads(self.rfile.read(length) or b"{}")
        except Exception: return reply(self,400,{"error":"invalid JSON"})
        if not sdk: return reply(self,503,{"error":startup_error})
        if path == "/discover":
            if not sdk: return reply(self,503,{"error":startup_error})
            try:
                wait=float(data.get("wait_seconds",2))
                return reply(self,200,sdk.discover(wait))
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        if path == "/connect":
            try:
                result=sdk.add_and_connect(
                    str(data["ip"]),
                    _int_or(data.get("port", 30000), 30000),
                    _int_or(data.get("timeout", 3), 3),
                    str(data.get("username", "") or ""),
                    str(data.get("password", "") or ""),
                )
                return reply(self,200,result)
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        if path.startswith("/disconnect/"):
            try:
                handle=int(path.rsplit("/",1)[-1]); rc=sdk.disconnect(handle, force=bool(data.get("force")))
                return reply(self,200,{"ok":rc==0,"rc":rc})
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        if path.startswith("/snapshot-trigger/"):
            try:
                handle=int(path.rsplit("/",1)[-1]); rc=sdk.snapshot_trigger(handle)
                return reply(self,200,{
                    "ok": rc==0,
                    "rc": rc,
                    "jpeg_bytes": len(sdk.jpeg_for(handle)),
                    "note": "Net_ImageSnap queued. JPEG arrives on the image callback.",
                })
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        if path == "/gpio/write":
            try:
                handle=int(data["handle"]); index=_int_or(data.get("index",0), 0); value=_int_or(data.get("value",1), 1)
                rc=sdk.write_gpio(handle, index, value)
                return reply(self,200,{"ok":rc==0,"rc":rc,"rc_name":describe_rc(rc),"handle":handle,"index":index,"value":value})
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        if path == "/gpio/pulse":
            try:
                handle=int(data["handle"]); index=_int_or(data.get("index",0), 0); pulse_ms=_int_or(data.get("pulse_ms",500), 500)
                trace_id = str(self.headers.get("X-Trace-Id") or data.get("trace_id") or "")
                received_ns = getattr(self, "_request_started_ns", None) or time.perf_counter_ns()
                _trace("host.gpio.request_received", trace=trace_id or None, camera=handle, index=index,
                       queue_wait_ms=getattr(self, "_queue_wait_ms", None),
                       workers_busy=getattr(_connection_state, "workers_busy_at_start", None))
                try:
                    result = sdk.gpio_pulse(handle, index, pulse_ms, trace_id=trace_id)
                except TypeError as exc:
                    if "trace_id" not in str(exc):
                        raise
                    result = sdk.gpio_pulse(handle, index, pulse_ms)
                result["host_timing"] = {
                    "request_received_perf_ns": received_ns,
                    "queue_wait_ms": getattr(self, "_queue_wait_ms", None),
                    "response_ready_perf_ns": time.perf_counter_ns(),
                }
                return reply(self,200,result)
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        if path == "/gate-setup":
            try:
                handle=int(data["handle"]); state=_int_or(data.get("state",1), 1); index=_int_or(data.get("index",0), 0)
                rc=sdk.gate_setup(handle, state, index)
                return reply(self,200,{"ok":rc==0,"rc":rc,"rc_name":describe_rc(rc),"handle":handle,"state":state,"index":index})
            except Exception as exc: return reply(self,500,{"error":str(exc)})
        return reply(self,404,{"error":"not found"})


_heartbeat = None


def start_instrumentation():
    """Start the scheduling-lag heartbeat (the trace file is opened at import)."""
    global _heartbeat
    if _latency is None or _heartbeat is not None:
        return
    _heartbeat = _latency.HeartbeatMonitor(
        HOST_METRICS, on_stall=lambda lag: _trace("host.heartbeat.stall", lag_ms=lag),
        name="hvx-heartbeat",
    ).start()


if __name__ == "__main__":
    log_directory = HOST_LOG_DIRECTORY
    log_directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(log_directory / "hvx-host.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    host_log = logging.getLogger("smartpark.hvx")
    host_log.setLevel(logging.INFO)
    host_log.addHandler(handler)
    host_log.info("SDK host starting: bits=%s vendor=%s available=%s error=%s fake=%s", struct.calcsize('P')*8, VENDOR, sdk is not None, startup_error, bool(getattr(sdk, "fake_sdk", False)))
    start_instrumentation()
    print(f"SmartPark HVX SDK Host — http://{HOST}:{PORT}")
    print(f"Python bitness: {struct.calcsize('P')*8}")
    if startup_error: print("SDK unavailable:",startup_error)
    server=BoundedHTTPServer((HOST,PORT),Handler)
    try: server.serve_forever()
    finally:
        if sdk: sdk.close()
