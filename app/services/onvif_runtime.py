"""Site Service supervisor for ONVIF Profile M event pollers.

One ``ONVIFEventPoller`` task per enabled ONVIF camera that (a) advertised a
licence-plate topic at discovery and (b) has ``onvif_profile.events_enabled``
set. Reconciled every few seconds from the database; cameras that are
disabled, re-typed or switched off stop within one reconcile period.

Captures are handed to ``persist`` (the Site Service's existing
``_persist_capture_event`` wrapper) — the same path HVX native reads use.
Evidence JPEGs come from the Media2/Media1 ``GetSnapshotUri`` result when the
device exposes one; a failed snapshot never blocks the plate read.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from sqlalchemy import select

from app.models import Camera
from app.services.onvif_events import ONVIFEventPoller, ONVIFPullPoint

PersistFn = Callable[[int, dict[str, Any], bytes], Awaitable[None]]

_pollers: dict[int, tuple[asyncio.Task, ONVIFEventPoller]] = {}
_persist: PersistFn | None = None
_snapshot_failures: dict[int, int] = {}


def set_persist(fn: PersistFn | None) -> None:
    global _persist
    _persist = fn


def wants_events(camera: Camera) -> bool:
    profile = dict(getattr(camera, "onvif_profile", None) or {})
    caps = dict(profile.get("capabilities") or {})
    return bool(
        camera.enabled
        and (camera.adapter_id or "hvx") == "onvif"
        and profile.get("events_enabled")
        and profile.get("events_url")
        and caps.get("plate_metadata")
    )


def stats_for(camera_id: int) -> dict[str, Any]:
    entry = _pollers.get(int(camera_id))
    if entry is None:
        return {"running": False}
    task, poller = entry
    return {"running": not task.done(), **poller.stats}


def stats() -> dict[str, Any]:
    return {
        "pollers": len(_pollers),
        "cameras": {cid: stats_for(cid) for cid in sorted(_pollers)},
    }


async def fetch_snapshot(uri: str, username: str, password: str, *, timeout: float = 4.0) -> bytes:
    """GET the ONVIF snapshot URI. Basic auth first, digest on 401."""
    if not uri:
        return b""
    import httpx

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        res = await client.get(uri, auth=(username, password) if username else None)
        if res.status_code == 401 and username:
            res = await client.get(uri, auth=httpx.DigestAuth(username, password))
        if res.status_code >= 400:
            return b""
        body = res.content or b""
        return body if body[:2] == b"\xff\xd8" else b""


def _handler(camera: Camera) -> Callable[[int, dict[str, Any]], Awaitable[None]]:
    profile = dict(camera.onvif_profile or {})
    snapshot_uri = str(profile.get("snapshot_uri") or "")
    username, password = camera.username or "", camera.password_secret or ""

    async def on_capture(camera_id: int, capture: dict[str, Any]) -> None:
        if _persist is None:
            return
        jpeg = b""
        if snapshot_uri and _snapshot_failures.get(camera_id, 0) < 5:
            try:
                jpeg = await fetch_snapshot(snapshot_uri, username, password)
                _snapshot_failures[camera_id] = 0 if jpeg else _snapshot_failures.get(camera_id, 0) + 1
            except Exception:
                _snapshot_failures[camera_id] = _snapshot_failures.get(camera_id, 0) + 1
        await _persist(camera_id, capture, jpeg)

    return on_capture


def _start(camera: Camera) -> None:
    profile = dict(camera.onvif_profile or {})
    caps = dict(profile.get("capabilities") or {})
    topics = list(caps.get("plate_topics") or [])
    pullpoint = ONVIFPullPoint(
        str(profile.get("events_url")),
        camera.username or "",
        camera.password_secret or "",
        topic_filter=topics[0] if len(topics) == 1 else "",
    )
    poller = ONVIFEventPoller(camera.id, pullpoint, _handler(camera))
    task = asyncio.create_task(poller.run(), name=f"onvif-events-{camera.id}")
    _pollers[camera.id] = (task, poller)


async def _stop(camera_id: int) -> None:
    entry = _pollers.pop(camera_id, None)
    if entry is None:
        return
    task, _poller = entry
    task.cancel()
    try:
        await asyncio.wait_for(task, timeout=3.0)
    except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
        pass


async def reconcile(db_factory) -> dict[str, int]:
    """Start/stop pollers to match the database. Cheap; call every few seconds."""
    with db_factory() as db:
        rows = list(db.scalars(select(Camera).where(Camera.adapter_id == "onvif")).all())
        wanted = {row.id: row for row in rows if wants_events(row)}
        # detach values we need after the session closes
        for row in wanted.values():
            db.expunge(row)
    started = stopped = 0
    for cid in list(_pollers):
        if cid not in wanted or _pollers[cid][0].done():
            await _stop(cid)
            stopped += 1
    for cid, row in wanted.items():
        if cid not in _pollers:
            _start(row)
            started += 1
    return {"started": started, "stopped": stopped, "running": len(_pollers)}


async def shutdown() -> None:
    for cid in list(_pollers):
        await _stop(cid)
    _snapshot_failures.clear()


def reset() -> None:
    """Tests only."""
    for cid, (task, _p) in list(_pollers.items()):
        task.cancel()
    _pollers.clear()
    _snapshot_failures.clear()
