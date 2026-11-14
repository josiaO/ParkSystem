"""Pipeline watchdog (Phase 3.3): more than "the process is alive".

Every ``pipeline_watchdog_seconds`` the Site Service checks, for this
installation only:

* the database answers a trivial query;
* the HVX SDK host (camera SDK and the GPIO barrier controller for HVX lanes)
  answers ``/info``;
* every enabled camera produced a fresh frame:
  - HVX/QY cameras: the SDK video callback age from the host;
  - generic RTSP cameras: the MediaMTX path is ready and its byte counter is
    still moving.

On a failure it restarts only the affected part and writes a ``watchdog.*``
audit event:

* a frozen HVX camera: its SDK session is force-disconnected; the existing HVX
  watch loop reconnects that one camera (at most once per cooldown);
* the HVX host not answering twice in a row: if it runs as the Windows service
  ``SmartParkHvxHost`` that service is restarted, otherwise only an event is
  written (a logon task cannot be restarted from Session 0);
* a stalled generic camera or a failing database: event and health alarm only.
  MediaMTX (owned by the Media Service) re-pulls its RTSP sources by itself,
  and the database cannot be restarted from here.

It never touches a barrier.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

log = logging.getLogger("smartpark")


@dataclass
class WatchdogDeps:
    """Side effects, injectable for tests."""

    check_database: Callable[[], float]
    list_cameras: Callable[[], list[dict]]
    hvx_info: Callable[[], Awaitable[dict]]
    hvx_video_status: Callable[[int], Awaitable[dict]]
    hvx_disconnect: Callable[[int], Awaitable[Any]]
    mediamtx_camera: Callable[[int], dict]
    restart_hvx_service: Callable[[], bool]
    record_event: Callable[[str, str, str], None]


@dataclass
class PipelineWatchdog:
    frame_stale_seconds: float = 10.0
    restart_cooldown_seconds: float = 120.0
    hvx_failures_before_restart: int = 2
    clock: Callable[[], float] = time.monotonic
    _last_bytes: dict[int, int] = field(default_factory=dict)
    _last_restart: dict[str, float] = field(default_factory=dict)
    _hvx_failures: int = 0
    last_report: dict = field(default_factory=dict)

    def _cooled(self, key: str) -> bool:
        now = self.clock()
        if now - self._last_restart.get(key, float("-inf")) < self.restart_cooldown_seconds:
            return False
        self._last_restart[key] = now
        return True

    async def run_once(self, deps: WatchdogDeps) -> dict:
        problems: list[dict] = []
        actions: list[str] = []

        # Database ---------------------------------------------------------
        try:
            db_ms = round(deps.check_database() * 1000, 1)
            database = {"ok": True, "query_ms": db_ms}
        except Exception as exc:
            database = {"ok": False, "error": str(exc)[:200]}
            problems.append({"component": "database", "detail": database["error"]})
            deps.record_event("watchdog.database", "database", database["error"])

        cameras = deps.list_cameras() if database["ok"] else []
        uses_hvx = any(cam.get("sdk") for cam in cameras)

        # HVX host / gate controller ----------------------------------------
        hvx: dict[str, Any] = {"required": uses_hvx}
        if uses_hvx:
            info = {}
            try:
                info = await deps.hvx_info()
            except Exception as exc:
                info = {"error": str(exc)[:200]}
            hvx_ok = bool(info.get("available"))
            hvx["ok"] = hvx_ok
            if hvx_ok:
                self._hvx_failures = 0
            else:
                self._hvx_failures += 1
                detail = str(info.get("startup_error") or info.get("error") or "no answer")[:200]
                problems.append({"component": "hvx_host", "detail": detail})
                if self._hvx_failures >= self.hvx_failures_before_restart and self._cooled("hvx_host"):
                    restarted = deps.restart_hvx_service()
                    action = "hvx_host service restarted" if restarted else "hvx_host not restartable (logon task); event only"
                    actions.append(action)
                    deps.record_event("watchdog.hvx_host", "hvx_host", f"{detail}; {action}")

        # Fresh frames ------------------------------------------------------
        frames: list[dict] = []
        for cam in cameras:
            cid = int(cam["id"])
            row: dict[str, Any] = {"camera_id": cid, "name": cam.get("name") or str(cid)}
            if cam.get("sdk"):
                if not hvx.get("ok"):
                    row.update(ok=False, reason="hvx host down")
                else:
                    status = await deps.hvx_video_status(int(cam["sdk_handle"]))
                    age_ms = status.get("callback_age_ms")
                    row["frame_age_ms"] = age_ms
                    fresh = age_ms is not None and float(age_ms) <= self.frame_stale_seconds * 1000
                    row["ok"] = fresh
                    if not fresh:
                        row["reason"] = "no SDK video callback" if age_ms is None else "SDK video frozen"
                        if self._cooled(f"camera:{cid}"):
                            try:
                                await deps.hvx_disconnect(int(cam["sdk_handle"]))
                                row["action"] = "sdk session reset; HVX watch loop reconnects"
                            except Exception as exc:
                                row["action"] = f"sdk reset failed: {str(exc)[:120]}"
                            actions.append(f"camera {cid}: {row['action']}")
                            deps.record_event("watchdog.camera", str(cid), f"{row['reason']}; {row['action']}")
            else:
                media = deps.mediamtx_camera(cid)
                live = ((media.get("roles") or {}).get("LIVE") or {}) if isinstance(media, dict) else {}
                received = live.get("bytes_received")
                previous = self._last_bytes.get(cid)
                if received is not None:
                    self._last_bytes[cid] = int(received)
                moving = received is not None and (previous is None or int(received) > previous)
                row["ok"] = bool(live.get("ready")) and moving
                row["bytes_received"] = received
                if not row["ok"]:
                    row["reason"] = "MediaMTX path not ready" if not live.get("ready") else "no new video bytes"
                    if self._cooled(f"camera:{cid}"):
                        deps.record_event("watchdog.camera", str(cid), f"{row['reason']}; MediaMTX retries the source")
            frames.append(row)
            if not row.get("ok"):
                problems.append({"component": f"camera:{cid}", "detail": row.get("reason", "")})

        report = {
            "ok": not problems,
            "checked_at": time.time(),
            "database": database,
            "hvx_host": hvx,
            "cameras": frames,
            "problems": problems,
            "actions": actions,
        }
        self.last_report = report
        return report


# Real dependencies ------------------------------------------------------------

def _check_database() -> float:
    from sqlalchemy import text

    from app.db import short_session

    started = time.perf_counter()
    with short_session() as db:
        db.execute(text("SELECT 1")).scalar()
    return time.perf_counter() - started


def _list_cameras() -> list[dict]:
    from sqlalchemy import select

    from app.db import short_session
    from app.models import Camera
    from app.services.node_scope import camera_active_on_this_installation

    rows = []
    with short_session() as db:
        for cam in db.scalars(select(Camera).where(Camera.enabled == True)).all():  # noqa: E712
            if not camera_active_on_this_installation(cam, db=db):
                continue
            sdk = cam.sdk_handle is not None and str(cam.adapter_id or "hvx").lower() in {"hvx", "qy", "native"}
            rows.append({"id": cam.id, "name": cam.name, "sdk": sdk, "sdk_handle": cam.sdk_handle})
    return rows


def _restart_hvx_service() -> bool:
    if os.name != "nt":
        return False
    try:
        query = subprocess.run(["sc.exe", "query", "SmartParkHvxHost"], capture_output=True, text=True, timeout=5)
        if query.returncode != 0:
            return False
        subprocess.run(["sc.exe", "stop", "SmartParkHvxHost"], capture_output=True, timeout=20)
        time.sleep(3)
        started = subprocess.run(["sc.exe", "start", "SmartParkHvxHost"], capture_output=True, timeout=20)
        return started.returncode in (0, 1056)
    except (OSError, subprocess.TimeoutExpired):
        return False


def _record_event(action: str, target: str, detail: str) -> None:
    from app.db import short_session
    from app.models import AuditLog
    from app.services.health import note_worker_failure

    log.warning("watchdog %s target=%s %s", action, target, detail)
    note_worker_failure("watchdog", f"{action} {target}: {detail}"[:300])
    try:
        with short_session() as db:
            db.add(AuditLog(user_id=None, action=action, target_type="watchdog", target_id=str(target)[:80], detail=detail[:2000]))
            db.commit()
    except Exception:
        log.exception("watchdog could not write its audit event")


def default_deps() -> WatchdogDeps:
    from app.services.hvx_client import HVXHostClient
    from app.services.mediamtx_telemetry import camera_telemetry

    client = HVXHostClient()

    async def disconnect(handle: int):
        return await client.disconnect(handle, force=True)

    return WatchdogDeps(
        check_database=_check_database,
        list_cameras=_list_cameras,
        hvx_info=client.info,
        hvx_video_status=client.video_status,
        hvx_disconnect=disconnect,
        mediamtx_camera=camera_telemetry,
        restart_hvx_service=_restart_hvx_service,
        record_event=_record_event,
    )


_watchdog: PipelineWatchdog | None = None


def watchdog() -> PipelineWatchdog:
    global _watchdog
    if _watchdog is None:
        from app.config import settings

        _watchdog = PipelineWatchdog(frame_stale_seconds=float(getattr(settings, "watchdog_frame_stale_seconds", 10.0)))
    return _watchdog


def snapshot() -> dict:
    return dict(watchdog().last_report or {"ok": None, "note": "watchdog has not run yet"})


async def loop(interval_seconds: float) -> None:
    deps = default_deps()
    # Let cameras connect after a boot before judging them.
    await asyncio.sleep(max(5.0, interval_seconds))
    while True:
        try:
            await watchdog().run_once(deps)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("pipeline watchdog iteration failed")
        await asyncio.sleep(interval_seconds)
