from __future__ import annotations

import asyncio

import httpx

from app.config import settings


class HVXHostUnavailable(RuntimeError):
    pass


_live_clients: dict[int, httpx.AsyncClient] = {}


def _shared_live_client(base_url: str) -> httpx.AsyncClient:
    """Reuse one HTTP client so live JPEG polling can keep up with moving video."""
    key = id(asyncio.get_running_loop())
    client = _live_clients.get(key)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(1.2, connect=0.5),
            limits=httpx.Limits(max_keepalive_connections=8, max_connections=16),
        )
        _live_clients[key] = client
    return client


class HVXHostClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.hvx_host_url).rstrip("/")

    async def info(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
                r = await client.get(f"{self.base_url}/info")
                r.raise_for_status()
                return r.json()
        except Exception as exc:
            raise HVXHostUnavailable(str(exc)) from exc

    async def connect(self, *, ip: str, port: int, username: str, password: str) -> dict:
        # ConnCameraEx (3s) then ConnCamera fallback (3s) plus StartVideo — HTTP must outlast that.
        http_timeout = max(settings.request_timeout_seconds, settings.hvx_connect_http_timeout_seconds, 20.0)
        try:
            async with httpx.AsyncClient(timeout=http_timeout) as client:
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
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            r = await client.get(f"{self.base_url}/state/{handle}")
            r.raise_for_status()
            return r.json()

    async def discover(self, wait_seconds: float = 2.0) -> dict:
        try:
            async with httpx.AsyncClient(timeout=max(settings.request_timeout_seconds, wait_seconds + 4.0)) as client:
                r = await client.post(f"{self.base_url}/discover", json={"wait_seconds": wait_seconds})
                r.raise_for_status()
                return r.json()
        except Exception as exc:
            raise HVXHostUnavailable(str(exc)) from exc

    async def disconnect(self, handle: int) -> dict:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            r = await client.post(f"{self.base_url}/disconnect/{handle}")
            r.raise_for_status()
            return r.json()

    async def last_captures(self) -> dict:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            r = await client.get(f"{self.base_url}/captures")
            r.raise_for_status()
            return r.json()

    async def snapshot_trigger(self, handle: int) -> dict:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            r = await client.post(f"{self.base_url}/snapshot-trigger/{int(handle)}")
            r.raise_for_status()
            return r.json()

    async def gpio_write(self, *, handle: int, index: int, value: int) -> dict:
        try:
            async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
                r = await client.post(f"{self.base_url}/gpio/write", json={
                    "handle": int(handle), "index": int(index), "value": int(value),
                })
                r.raise_for_status()
                return r.json()
        except Exception as exc:
            raise HVXHostUnavailable(str(exc)) from exc

    async def gate_setup(self, *, handle: int, state: int = 1, index: int = 0) -> dict:
        try:
            async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
                r = await client.post(f"{self.base_url}/gate-setup", json={
                    "handle": int(handle), "state": int(state), "index": int(index),
                })
                r.raise_for_status()
                return r.json()
        except Exception as exc:
            raise HVXHostUnavailable(str(exc)) from exc

    async def gpio_pulse(self, *, handle: int, index: int = 0, pulse_ms: int = 500) -> dict:
        try:
            async with httpx.AsyncClient(timeout=max(settings.request_timeout_seconds, 8.0)) as client:
                r = await client.post(f"{self.base_url}/gpio/pulse", json={
                    "handle": int(handle), "index": int(index), "pulse_ms": int(pulse_ms),
                })
                r.raise_for_status()
                return r.json()
        except httpx.HTTPStatusError as exc:
            try:
                detail = exc.response.json()
            except Exception:
                detail = exc.response.text
            raise HVXHostUnavailable(f"HVX GPIO error: {detail}") from exc
        except Exception as exc:
            raise HVXHostUnavailable(str(exc)) from exc

    async def event_jpeg(self, handle: int, image_id: int | None = None) -> bytes:
        suffix = f"?image_id={int(image_id)}" if image_id is not None else ""
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{self.base_url}/event-jpeg/{int(handle)}{suffix}")
            if r.status_code == 200 and r.content[:2] == b"\xff\xd8":
                return r.content
        return b""

    async def event_crop(self, handle: int, image_id: int | None = None) -> bytes:
        suffix = f"?image_id={int(image_id)}" if image_id is not None else ""
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{self.base_url}/event-crop/{int(handle)}{suffix}")
            if r.status_code == 200 and r.content[:2] == b"\xff\xd8":
                return r.content
        return b""

    async def drain_events(self, handle: int) -> list[dict] | None:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(f"{self.base_url}/events/{int(handle)}")
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
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(f"{self.base_url}/reports/{int(handle)}")
                if r.status_code != 200:
                    return []
                payload = r.json()
                rows = payload.get("reports") if isinstance(payload, dict) else None
                return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
        except Exception:
            return []

    async def read_gpio(self, handle: int, index: int = 1) -> dict:
        try:
            async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
                r = await client.get(f"{self.base_url}/gpio/{int(handle)}", params={"index": int(index)})
                if r.status_code != 200:
                    return {"ok": False, "handle": int(handle), "index": int(index)}
                return r.json()
        except Exception as exc:
            return {"ok": False, "handle": int(handle), "index": int(index), "error": str(exc)}

    async def scan_gpio(self, handle: int, indexes: list[int] | None = None) -> list[dict]:
        pins = indexes or [1, 2, 3, 4, 5, 6, 7]
        try:
            async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
                r = await client.get(
                    f"{self.base_url}/gpio-scan/{int(handle)}",
                    params={"indexes": ",".join(str(i) for i in pins)},
                )
                if r.status_code != 200:
                    return []
                payload = r.json()
                rows = payload.get("pins") if isinstance(payload, dict) else None
                return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
        except Exception:
            return []

    async def live_jpeg(self, handle: int) -> bytes:
        """Net_GetJpgBuffer live frame. Never the last car-event still."""
        try:
            client = _shared_live_client(self.base_url)
            r = await client.get(f"/live-jpeg/{int(handle)}")
            if r.status_code == 200 and r.content[:2] == b"\xff\xd8":
                return r.content
        except Exception:
            return b""
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
