"""Independent, bounded display streams; no recognition ownership."""
import time
import httpx
from PySide6.QtCore import QThread, Signal
from .api import api, stream_http_error
from .frame_mailbox import DisplayMailbox


class MjpegStream(QThread):
    """Read /live.mjpeg and emit only the newest JPEG. Old frames in the pipe are dropped."""
    frame=Signal()
    failed=Signal(str)
    def __init__(self, camera_id):
        super().__init__()
        self.camera_id=camera_id
        self.mailbox=DisplayMailbox()
        self._stop=False
        self._client=None
    def stop(self):
        self._stop=True
        client=self._client
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
    def run(self):
        # On the lane PC, read QY/HVX frames straight from the local SDK host:
        # the Site Service relay drops frames whenever its event loop is busy
        # with a car (measured 8 fps with 0.4-0.7 s gaps vs 9.8 fps / 0.2 s
        # direct). Anything else, or any failure, uses the MJPEG relay.
        direct = getattr(self, "_run_from_local_host", None)
        try:
            if callable(direct) and direct():
                return
        except Exception:
            if self._stop:
                return            # any direct-path failure falls back to the relay
        client=httpx.Client(timeout=httpx.Timeout(connect=5.0, read=8.0, write=5.0, pool=5.0))
        self._client=client
        try:
            base_url = getattr(api, "local_base_url", "") or getattr(api, "base_url", "")
            with client.stream(
                "GET",
                f"{base_url}/cameras/{self.camera_id}/live.mjpeg",
                headers=api._headers(),
            ) as response:
                if response.status_code >= 400:
                    if not self._stop:
                        self.failed.emit(stream_http_error(response))
                    return
                buf=b""
                last_frame=time.monotonic()
                chunks=response.iter_bytes()
                while not self._stop:
                    try:
                        chunk=next(chunks)
                    except StopIteration:
                        break
                    except Exception as e:
                        if self._stop:
                            return
                        raise
                    buf += chunk
                    if len(buf) > 2_500_000:
                        start=buf.rfind(b"\xff\xd8")
                        buf = buf[start:] if start>=0 else buf[-120_000:]
                    latest, buf = pop_latest_mjpeg(buf)
                    if latest is not None:
                        last_frame=time.monotonic()
                        if self.mailbox.offer(latest):
                            self.frame.emit()
                    now=time.monotonic()
                    if now-last_frame > 8.0:
                        raise RuntimeError("No complete camera frame received; reconnecting.")
                if not self._stop:
                    self.failed.emit("Camera stream ended; reconnecting.")
        except Exception as e:
            if not self._stop:
                self.failed.emit(str(e))
        finally:
            self._client=None
            try:
                client.close()
            except Exception:
                pass


LOCAL_HOST_URL = "http://127.0.0.1:8765"


def _camera_ip(camera_id) -> str:
    try:
        row = api.get(f"/cameras/{camera_id}", timeout=5)
    except Exception:
        return ""
    return str((row or {}).get("ip_address") or "") if isinstance(row, dict) else ""


def local_host_handle(client: httpx.Client, ip: str) -> int | None:
    """This PC's SDK host handle for a camera IP, or None if not connected here."""
    if not ip:
        return None
    try:
        info = client.get(f"{LOCAL_HOST_URL}/info", timeout=1.5).json()
    except Exception:
        return None
    for row in (info or {}).get("connections") or []:
        if str(row.get("ip") or "") == ip and row.get("handle") is not None:
            return int(row["handle"])
    return None


def _mjpeg_stream_run_from_local_host(self) -> bool:
    """Long-poll the local host for each new frame. False means: use the relay."""
    ip = _camera_ip(self.camera_id)
    client = httpx.Client(timeout=httpx.Timeout(connect=1.0, read=3.0, write=2.0, pool=2.0), trust_env=False)
    self._client = client
    try:
        handle = local_host_handle(client, ip)
        if handle is None:
            return False
        seq, last_frame, misses = 0, time.monotonic(), 0
        while not self._stop:
            try:
                response = client.get(f"{LOCAL_HOST_URL}/live-jpeg/{handle}", params={"after": seq, "wait_ms": 1000})
            except Exception:
                if self._stop:
                    return True
                misses += 1
                handle = local_host_handle(client, ip) if misses >= 2 else handle
                if handle is None:
                    return False          # host gone or camera moved: fall back to the relay
                time.sleep(0.2)
                continue
            new_seq = int(response.headers.get("x-frame-seq") or 0)
            if response.status_code == 200 and response.content[:2] == b"\xff\xd8" and new_seq > seq:
                seq, last_frame, misses = new_seq, time.monotonic(), 0
                if self.mailbox.offer(response.content):
                    self.frame.emit()
            elif response.status_code == 404:
                handle = local_host_handle(client, ip)   # handles change after a host restart
                if handle is None:
                    return False
            if time.monotonic() - last_frame > 8.0:
                return False
        return True
    finally:
        self._client = None
        try:
            client.close()
        except Exception:
            pass


MjpegStream._run_from_local_host = _mjpeg_stream_run_from_local_host


def pop_latest_mjpeg(buf: bytes) -> tuple[bytes | None, bytes]:
    """Pull complete MJPEG parts from buf; keep only the newest JPEG."""
    latest = None
    boundary = b"--smartparkframe"
    while True:
        mark = buf.find(boundary)
        if mark < 0:
            jpeg, rest = _pop_raw_jpegs(buf)
            if jpeg:
                latest = jpeg
            return latest, rest
        header_end = buf.find(b"\r\n\r\n", mark)
        if header_end < 0:
            return latest, buf[mark:]
        headers = buf[mark:header_end]
        body = buf[header_end + 4:]
        length = None
        for line in headers.split(b"\r\n"):
            if line.lower().startswith(b"content-length:"):
                try:
                    length = int(line.split(b":", 1)[1].strip())
                except ValueError:
                    length = None
                break
        if length is None or length <= 0 or length > 2_500_000:
            jpeg, rest = _pop_raw_jpegs(body)
            if jpeg:
                latest = jpeg
            return latest, rest
        if len(body) < length:
            return latest, buf[mark:]
        latest = body[:length]
        buf = body[length:]
        if buf.startswith(b"\r\n"):
            buf = buf[2:]


def _pop_raw_jpegs(buf: bytes) -> tuple[bytes | None, bytes]:
    latest = None
    while True:
        start = buf.find(b"\xff\xd8")
        if start < 0:
            return latest, (buf[-1:] if buf.endswith(b"\xff") else b"")
        end = buf.find(b"\xff\xd9", start + 2)
        if end < 0:
            return latest, buf[start:]
        latest = buf[start:end + 2]
        buf = buf[end + 2:]
