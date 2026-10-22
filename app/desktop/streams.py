"""Independent, bounded display streams; no recognition ownership."""
import time
import httpx
from PySide6.QtCore import QThread, Signal
from .api import api, BASE, stream_http_error
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
        client=httpx.Client(timeout=httpx.Timeout(connect=5.0, read=8.0, write=5.0, pool=5.0))
        self._client=client
        try:
            with client.stream(
                "GET",
                f"{BASE}/cameras/{self.camera_id}/live.mjpeg",
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
