from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import asyncio
import logging
import time

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .db import Base, engine, ensure_schema, get_db, short_session, SessionLocal
from .domain.site import DEFAULT_SITE_ID
from .models import AccessPlan, AccessDecision, Camera, CameraStatus, Gate, GateMode, ParkingSession, PaymentTransaction, Receipt, RegisteredVehicle, Role, Tariff, User, VehicleCapture
from .schemas import (
    CameraCreate, CameraImport, CameraOnboardProbe, CameraOnboardTest, CameraUpdate, FeeQuoteRequest, FusionRequest, GateCreate, GateUpdate, LedWrite,
    LoginRequest, LoginResponse, ManualGateCommand, MigrationFlagsUpdate, ModelPackRequest, ParkingSettingsUpdate, PaymentConfirm, PublicPaymentIntentRequest, PlateCorrection, PlateEngineCorrection, SessionCreate, SimEntryRequest, SimExitRequest,
    SitePolicyUpdate, StreamProfilesUpdate, UserCreate, UserUpdate, AccessPlanCreate, AccessPlanUpdate, VehicleCreate, VehicleUpdate,
    VehicleBulkCreate, VehicleBulkDelete, TariffEditorUpdate, BackupSettingsUpdate,
    ModuleProfileApply, ModuleEnablement, ZoneCreate, LaneCreate, OnboardingStep, AIIncidentSummaryRequest,
)
from .security import authenticate_user, create_session, current_user, oauth2_scheme, require, require_any, require_media, revoke_session, user_permissions
from .core.fusion import resolve_readings
from .infrastructure.recognition.engines import active_engine, list_engines, recognize_frame
from .infrastructure.recognition.engines.training import apply_model_pack, record_correction, training_status
from .services.alpr import status as alpr_status
from .services.redaction import redact_text

log = logging.getLogger("smartpark")
from .services.audit import write_audit
from .services.bootstrap import ensure_bootstrap_admin, setup_status
from .services.captures import capture_dict, latest_for_camera, list_captures, persist_event, should_persist_vehicle_capture
from .services.fee_engine import calculate_car1_fee, ensure_car1_tariff, load_active_rules
from .services.gates import controller
from .services.led_udp import send_led_text
from .services.hvx_client import HVXHostClient, HVXHostUnavailable
from .services.hvx_vendor import vendor_inventory
from .services.camera_lpr import choose_overlay_box, local_from_fastalpr, native_from_sdk_capture
from .services.ocr_policy import fusion_mode, should_run_local
from .services.presence import coil_watch
from .services.site_policy import site_policy
from .services.preview import (
    MJPEG_BOUNDARY, CameraLiveSpec, acquire_detect, acquire_live, get_state, media_path, mjpeg_from_cache, mjpeg_parts,
    pumping_spec, release_detect, release_live, remember_alpr, remember_frame, remember_last_car, snapshot_for_camera, start_idle_watch,
    start_live_pump, stop_live_pump, stop_live_pumps, touch_live, viewers_for,
)
from .services.http_snapshot import grab_http_snapshot
from .services.ipcam_discover import generic_discovery_row, scan_lan_devices
from .services.rtsp_probe import probe, vendor_candidates
from .services.site_cameras import (
    KNOWN_SITE_CAMERAS, KNOWN_SITE_GATES, camera_spec_for_ip, discovery_row,
    probe_ips, side_label, site_camera_defaults, tcp_open,
)
from .services.simulation import (
    handle_exit, handle_plate_event, mark_paid, parking_settings,
    save_parking_settings, session_dict as sim_session_dict, take_receipt,
)
from .services.users import create_user, delete_user, load_user, load_users, update_user, user_dict
from .services.access import ensure_access_plans, lookup_entitlement, plan_dict, vehicle_dict
from .services.receipts import RECEIPT_POLICIES, issue_receipt, receipt_dict
from .core.plate import normalize_plate
from .infrastructure.hardware.printers import list_system_printers, printer_adapter
from .infrastructure.hardware.cameras import adapter_has_native_plates, camera_adapter_for
from .infrastructure.hardware.edge import edge_agent_status
from .infrastructure.hardware.registry import camera_adapter_id, camera_connection_mode, devices_as_dicts
from .infrastructure.payments.ledger import list_transactions, transaction_dict

WEB_DIR = Path(__file__).resolve().parent / "web"


DEFAULT_ROLES = {
    "Admin": "*",
    "Operator": ",".join([
        "dashboard.view", "cameras.view", "cameras.connect", "gates.view",
        "gates.open", "gates.open_simulated", "fees.view",
        "subscribers.view", "sessions.view", "payments.view", "payments.create",
        "settings.view",
    ]),
    "Developer": ",".join([
        "dashboard.view", "cameras.view", "cameras.connect", "gates.view",
        "gates.open", "hardware.view", "fees.view", "simulation.run",
        "subscribers.view", "subscribers.manage", "sessions.view",
        "payments.view", "payments.create", "settings.view", "settings.manage",
        "users.view",
    ]),
    "Kiosk Operator": ",".join([
        "kiosk.use", "sessions.view", "payments.view", "payments.create",
        "dashboard.view",
    ]),
}


def ensure_roles(db: Session):
    for name, permissions in DEFAULT_ROLES.items():
        role = db.scalar(select(Role).where(Role.name == name))
        if not role:
            db.add(Role(name=name, permissions_csv=permissions, system_role=True))
        elif role.system_role:
            role.permissions_csv = permissions
    db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .services.logging_setup import configure_logging
    from .services.runtime import install_asyncio_exception_filter, mark_core_ready, set_process_name, set_startup_state

    configure_logging("site-service")
    set_process_name("SmartParkSiteService")
    set_startup_state("STARTING")
    install_asyncio_exception_filter()
    ensure_schema()
    with SessionLocal() as db:
        ensure_roles(db)
        ensure_bootstrap_admin(db)
        ensure_car1_tariff(db)
        ensure_access_plans(db)
        from .services.modules import ensure_modules_initialized
        from .services.topology import ensure_default_site, sync_gate_lanes_from_cameras

        ensure_modules_initialized(db)
        ensure_default_site(db)
        sync_gate_lanes_from_cameras(db)
        from .services.secrets_migration import migrate_plaintext_secrets

        try:
            migrate_plaintext_secrets(db)
        except Exception as exc:  # a secret-store problem must not stop parking
            log.warning("secrets migration skipped: %s", exc)
    mark_core_ready()
    start_idle_watch()
    # MediaMTX has one owner: SmartParkMediaService.  The Site Service only
    # consumes its local control/stream endpoints and must not spawn a competing
    # sidecar process.
    from .services import hybrid_fusion
    hybrid_fusion.set_persist(_persist_capture_event)
    ingest = asyncio.create_task(_camera_event_loop(), name="camera-events")
    outbox = asyncio.create_task(_outbox_loop(), name="parking-outbox")
    hvx_watch = asyncio.create_task(_hvx_watch_loop(), name="hvx-watch")
    fusion_flush = asyncio.create_task(_fusion_flush_loop(), name="hybrid-fusion-flush")
    payments_reconcile = asyncio.create_task(_payments_reconcile_loop(), name="payments-reconcile")
    from .services import onvif_runtime
    onvif_runtime.set_persist(_onvif_capture)
    onvif_events = asyncio.create_task(_onvif_events_loop(), name="onvif-events")
    try:
        yield
    finally:
        for task in (ingest, outbox, hvx_watch, fusion_flush, payments_reconcile, onvif_events):
            task.cancel()
        await asyncio.gather(ingest, outbox, hvx_watch, fusion_flush, payments_reconcile, onvif_events, return_exceptions=True)
        await onvif_runtime.shutdown()
        stop_live_pumps()
        # Do not stop MediaMTX here; SmartParkMediaService owns that process.
        set_startup_state("OFFLINE")


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
from .api.module_routes import ModuleRoute
from .services.public_ingress import PublicIngressGuard
app.router.route_class = ModuleRoute
# Requests arriving via the public payments tunnel may only reach /p/*,
# /api/public/* and /api/webhooks/*. No-op when no ingress host is configured.
app.add_middleware(PublicIngressGuard)


@app.exception_handler(HTTPException)
async def _redacted_http_exception(request: Request, exc: HTTPException):
    """Error bodies never carry RTSP passwords, provider keys or webhook hashes."""
    from .services.redaction import redact_obj

    return JSONResponse({"detail": redact_obj(exc.detail)}, status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(Exception)
async def _redacted_unhandled_exception(request: Request, exc: Exception):
    """Unhandled errors log the redacted traceback and return a redacted message."""
    from .services.redaction import redact_text

    log.error("unhandled error on %s %s: %s", request.method, request.url.path, redact_text(repr(exc)), exc_info=exc)
    return JSONResponse({"detail": redact_text(f"{type(exc).__name__}: {exc}")[:400]}, status_code=500)


def _login_response(db: Session, username: str, password: str) -> LoginResponse:
    from .services.modules import ensure_modules_initialized, load_config, navigation_items

    user = authenticate_user(db, username, password)
    token = create_session(db, user)
    ensure_modules_initialized(db)
    perms = user_permissions(user)
    cfg = load_config(db)
    return LoginResponse(
        token=token,
        access_token=token,
        token_type="bearer",
        username=user.username,
        permissions=sorted(perms),
        navigation=navigation_items(db, perms),
        modules={
            "profile": cfg.get("profile"),
            "enabled": cfg.get("enabled"),
            "onboarding_completed": cfg.get("onboarding_completed"),
        },
    )


@app.get("/", include_in_schema=False)
def web_app():
    index = WEB_DIR / "index.html"
    if not index.exists():
        raise HTTPException(404, "Web UI not found")
    # Avoid stale browser cache after UI token/shell updates.
    return FileResponse(
        index,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/health")
def health():
    from .services.health import live
    return live()


@app.get("/health/live")
def health_live():
    from .services.health import live
    return live()


@app.get("/health/ready")
def health_ready():
    from .services.health import ready
    body = ready()
    if not body.get("ok"):
        return JSONResponse(body, status_code=503)
    return body


@app.get("/health/details")
def health_details(_: User = Depends(require("hardware.view"))):
    from .services.health import details
    return details()


@app.get("/health/diagnostics")
def health_diagnostics(db: Session = Depends(get_db), _: User = Depends(require("hardware.view"))):
    """Support bundle: health, schema, secrets backend, cameras. Always redacted."""
    from .services.diagnostics import bundle
    return bundle(db)


@app.get("/auth/setup")
def auth_setup(db: Session = Depends(get_db)):
    return setup_status(db)


@app.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    return _login_response(db, payload.username, payload.password)


@app.post("/auth/token", response_model=LoginResponse)
def login_token(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    return _login_response(db, form.username, form.password)


@app.post("/auth/logout")
def logout(token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if token:
        revoke_session(db, token)
    return {"ok": True}


@app.get("/auth/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    from .services.modules import ensure_modules_initialized, load_config, navigation_items
    from .security import user_permissions

    ensure_modules_initialized(db)
    perms = user_permissions(user)
    cfg = load_config(db)
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "permissions": sorted(perms),
        "modules": {
            "profile": cfg.get("profile"),
            "enabled": cfg.get("enabled"),
            "onboarding_completed": cfg.get("onboarding_completed"),
        },
        "navigation": navigation_items(db, perms),
    }


@app.get("/modules")
def modules_list(db: Session = Depends(get_db), _: User = Depends(require("settings.view"))):
    from .services.modules import list_modules, load_config

    return {"modules": list_modules(db), "config": load_config(db)}


@app.get("/modules/profiles")
def modules_profiles(_: User = Depends(require("settings.view"))):
    from .services.modules import list_profiles

    return {"profiles": list_profiles()}


@app.get("/modules/navigation")
def modules_navigation(user: User = Depends(current_user), db: Session = Depends(get_db)):
    from .services.modules import navigation_items
    from .security import user_permissions

    return {"navigation": navigation_items(db, user_permissions(user))}


@app.get("/modules/health")
def modules_health(db: Session = Depends(get_db), _: User = Depends(require("dashboard.view"))):
    from .services.modules import module_health

    return module_health(db)


@app.put("/modules/profile")
def modules_apply_profile(
    payload: ModuleProfileApply,
    db: Session = Depends(get_db),
    _: User = Depends(require("settings.manage")),
):
    from .services.modules import apply_profile

    try:
        return apply_profile(db, payload.profile)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/modules/enabled")
def modules_set_enabled(
    payload: ModuleEnablement,
    db: Session = Depends(get_db),
    _: User = Depends(require("settings.manage")),
):
    from .services.modules import set_enabled

    try:
        return set_enabled(db, payload.enabled, profile=payload.profile)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/topology")
def topology_get(db: Session = Depends(get_db), _: User = Depends(require("settings.view"))):
    from .services.topology import site_topology

    return site_topology(db)


@app.post("/topology/zones")
def topology_create_zone(
    payload: ZoneCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require("settings.manage")),
):
    from .services.topology import create_zone, zone_dict

    row = create_zone(db, site_id=payload.site_id, name=payload.name)
    return zone_dict(row)


@app.post("/topology/lanes")
def topology_create_lane(
    payload: LaneCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require("settings.manage")),
):
    from .services.topology import create_lane, lane_dict

    row = create_lane(
        db,
        name=payload.name,
        gate_id=payload.gate_id,
        zone_id=payload.zone_id,
        direction=payload.direction,
        bidirectional=payload.bidirectional,
    )
    return lane_dict(row)


@app.get("/onboarding/status")
def onboarding_status_route(db: Session = Depends(get_db), _: User = Depends(require("settings.view"))):
    from .services.modules import onboarding_status

    return onboarding_status(db)


@app.post("/onboarding/step")
def onboarding_step_route(
    payload: OnboardingStep,
    db: Session = Depends(get_db),
    _: User = Depends(require("settings.manage")),
):
    from .services.modules import save_onboarding_step

    try:
        return save_onboarding_step(db, payload.step, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/cameras")
def list_cameras(db: Session = Depends(get_db), _: User = Depends(require("cameras.view"))):
    rows = db.scalars(select(Camera).order_by(Camera.id)).all()
    return [camera_dict(c) for c in rows]


@app.get("/cameras/discover")
async def discover_cameras(
    scan_lan: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require("cameras.view")),
):
    return await _discover_cameras(db, scan_lan=scan_lan)


@app.post("/cameras/seed-site")
def seed_site_cameras(db: Session = Depends(get_db), user: User = Depends(require("cameras.manage"))):
    created, skipped, gates = _import_site_layout(db, user)
    return {
        "created": [camera_dict(c) for c in created],
        "skipped": skipped,
        "gates": [gate_dict(g) for g in gates],
        "cameras": [camera_dict(c) for c in db.scalars(select(Camera).order_by(Camera.id)).all()],
        "note": (
            "Each numbered lane (1# / 2#) is entry + exit. Each side has camera, controller (Board*), "
            "and display (IpAddr*). Only camera IPs are SDK-connected. Press Connect all for a real NetSDK login."
        ),
    }


@app.post("/cameras/import-discovered")
async def import_discovered_cameras(
    payload: CameraImport | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require("cameras.manage")),
):
    payload = payload or CameraImport()
    username = (payload.username or "admin").strip() or "admin"
    password = payload.password if payload.password is not None else "admin"
    specs = []
    if payload.cameras:
        for item in payload.cameras:
            adapter = (item.adapter_id or "rtsp").strip().lower() or "rtsp"
            spec = camera_spec_for_ip(item.ip_address, adapter_id=adapter)
            spec["adapter_id"] = adapter
            spec["username"] = username
            spec["password"] = password
            spec["lane_direction"] = item.lane_direction or spec.get("lane_direction") or "ENTRY"
            if item.name:
                spec["name"] = item.name
            specs.append(spec)
    elif payload.ips:
        specs = [camera_spec_for_ip(ip) for ip in payload.ips]
    else:
        discovered = await _discover_cameras(db, scan_lan=payload.scan_lan)
        specs = []
        for row in discovered["cameras"]:
            if not row.get("reachable"):
                continue
            spec = camera_spec_for_ip(row["ip_address"], adapter_id=row.get("adapter_id") or "hvx")
            spec["adapter_id"] = row.get("adapter_id") or "hvx"
            spec["username"] = username
            spec["password"] = password
            specs.append(spec)
        if not specs:
            specs = [camera_spec_for_ip(row["ip_address"]) for row in KNOWN_SITE_CAMERAS]
    for spec in specs:
        spec["username"] = spec.get("username") or username
        spec["password"] = spec.get("password") or password
    created, skipped = _import_camera_specs(db, user, specs)
    connected = []
    if payload.connect:
        ids = [c.id for c in created]
        for row in skipped:
            if row.get("camera_id"):
                ids.append(int(row["camera_id"]))
        seen = set()
        for camera_id in ids:
            if camera_id in seen:
                continue
            seen.add(camera_id)
            camera = db.get(Camera, camera_id)
            if camera is None:
                continue
            connected.append(await apply_camera_connect(camera, db, user, raise_on_host_error=False))
    return {
        "created": [camera_dict(c) for c in created],
        "skipped": skipped,
        "connected": connected,
        "cameras": [camera_dict(c) for c in db.scalars(select(Camera).order_by(Camera.id)).all()],
    }


@app.post("/cameras/sdk/connect-all")
async def sdk_connect_all(db: Session = Depends(get_db), user: User = Depends(require("cameras.connect"))):
    rows = db.scalars(select(Camera).where(Camera.enabled == True).order_by(Camera.id)).all()
    results = []
    connected = 0
    skipped = 0
    for camera in rows:
        item = await apply_camera_connect(camera, db, user, raise_on_host_error=False)
        if item.get("status") in {CameraStatus.SDK_CONNECTED.value, CameraStatus.VIDEO_CONNECTED.value}:
            connected += 1
        if (item.get("sdk_result") or {}).get("skipped"):
            skipped += 1
        results.append(item)
    return {
        "connected": connected,
        "attempted": len(results),
        "skipped": skipped,
        "results": results,
        "note": (
            "Connect all logs in camera IPs only (NetSDK port 30000 for HVX). "
            "Generic IP cameras (rtsp/dahua/hikvision) use HTTP snapshot or RTSP and FastALPR — not SDK_CONNECTED. "
            "Unreachable HVX cameras are skipped after a short TCP probe so one slow camera cannot stall the rest."
        ),
    }


def camera_dict(c: Camera):
    gate = c.gate
    lane_name = None if gate is None else gate.name
    from .services.stream_roles import public_profiles
    from .domain.cameras import camera_type_for
    native = adapter_has_native_plates(c)
    from .services.ocr_policy import LOCAL_ONLY, NATIVE_ONLY, camera_recognition_mode
    canonical = camera_recognition_mode(c)
    if canonical == LOCAL_ONLY:
        recog = "FASTALPR_ONLY"
        plate_engine = "fastalpr"
    elif canonical == NATIVE_ONLY:
        recog = "NATIVE_ONLY"
        plate_engine = "native"
    else:
        recog = "HYBRID"
        plate_engine = "fastalpr"
    return {
        "id": c.id, "name": c.name, "ip_address": c.ip_address, "sdk_port": c.sdk_port,
        "site_id": getattr(c, "site_id", None) or DEFAULT_SITE_ID,
        "username": c.username, "gate_id": c.gate_id, "gate_name": lane_name,
        "credentials_ref": getattr(c, "credentials_ref", "") or "",
        "password_configured": bool(c.has_password()) if hasattr(c, "has_password") else False,
        "lane_name": lane_name or "",
        "side": side_label(c.lane_direction),
        "lane_direction": c.lane_direction,
        "controller_ip": c.controller_ip or "",
        "display_ip": c.display_ip or "",
        "adapter_id": camera_adapter_id(c),
        "connection_mode": camera_connection_mode(c),
        "native_plates": native,
        "plate_engine": plate_engine,
        "recognition_mode": recog,
        "camera_type": getattr(c, "camera_type", None) or camera_type_for(camera_adapter_id(c), native_plates=native),
        "vendor": getattr(c, "vendor", None) or "",
        "model_name": getattr(c, "model_name", None) or "",
        "serial": getattr(c, "serial", None) or "",
        "timezone": getattr(c, "timezone", None) or "",
        # Embedded RTSP credentials never leave the API; PATCH accepts the masked
        # form back unchanged (see update_camera).
        "rtsp_url": redact_text(c.rtsp_url or ""), "status": c.status, "sdk_handle": c.sdk_handle,
        "ffmpeg_profile": getattr(c, "ffmpeg_profile", None) or settings.ffmpeg_profile,
        "rtsp_transport": getattr(c, "rtsp_transport", None) or settings.rtsp_transport,
        "stream_profiles": public_profiles(getattr(c, "stream_profiles", None) or {}),
        "media_capabilities": list(getattr(c, "media_capabilities", None) or []),
        "onvif": _camera_onvif_brief(c),
        "media": _camera_media_brief(c.id),
        "operator": {
            "camera": "Online" if c.status in (CameraStatus.SDK_CONNECTED.value, CameraStatus.VIDEO_CONNECTED.value) else "Offline",
        },
        "last_error": c.last_error, "last_seen_at": c.last_seen_at, "enabled": c.enabled,
    }


def _camera_onvif_brief(c: Camera) -> dict:
    """Public-safe ONVIF summary (no credentials in URIs)."""
    profile = dict(getattr(c, "onvif_profile", None) or {})
    if not profile:
        return {}
    caps = dict(profile.get("capabilities") or {})
    from .services import onvif_runtime
    return {
        "media_version": profile.get("media_version") or 0,
        "media2": bool(caps.get("media2")),
        "events": bool(caps.get("events")),
        "profile_m": bool(caps.get("profile_m")),
        "plate_metadata": bool(caps.get("plate_metadata")),
        "plate_topics": list(caps.get("plate_topics") or [])[:10],
        "snapshot_uri": profile.get("snapshot_uri_redacted") or "",
        "events_enabled": bool(profile.get("events_enabled")),
        "events_url_present": bool(profile.get("events_url")),
        "discovered_at": profile.get("discovered_at"),
        "poller": onvif_runtime.stats_for(c.id),
    }


def _camera_media_brief(camera_id: int) -> dict:
    from .services.media_gateway import gateway
    row = gateway.session(camera_id)
    if row is None:
        return {"connection_state": "DISCONNECTED", "viewers": viewers_for(camera_id)}
    live = row.live.latest()
    detect = row.detect.latest()
    pumping = row.producer is not None and not row.producer.done()
    from .services.stream_roles import profile_warnings
    return {
        "connection_state": row.state if pumping or row.state != "DISCONNECTED" else "DISCONNECTED",
        "viewers": viewers_for(camera_id),
        "live_frame_age_ms": live.age_ms() if live else None,
        "ai_frame_age_ms": detect.age_ms() if detect else None,
        "fps": row.live_fps,
        "ai_fps": row.ai_fps,
        "codec": row.codec,
        "transport": row.transport,
        "ffmpeg_profile": row.ffmpeg_profile,
        "reconnects": row.reconnects,
        "warnings": profile_warnings(row.spec.stream_profiles, upstream_consumers=1 if pumping else 0),
    }


def gate_dict(g: Gate):
    cameras = list(g.cameras or [])
    return {
        "id": g.id, "name": g.name, "mode": g.mode, "enabled": g.enabled,
        "physical_control_verified": g.physical_control_verified,
        "cameras": [
            {
                "id": c.id,
                "name": c.name,
                "ip_address": c.ip_address,
                "lane_name": g.name,
                "side": side_label(c.lane_direction),
                "lane_direction": c.lane_direction,
                "controller_ip": c.controller_ip or "",
                "display_ip": c.display_ip or "",
                "status": c.status,
            }
            for c in cameras
        ],
    }


def commit_or_conflict(db: Session, message: str):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, message)


def get_camera_or_404(db: Session, camera_id: int) -> Camera:
    c = db.get(Camera, camera_id)
    if not c:
        raise HTTPException(404, "Camera not found")
    return c


async def live_snapshot(c: Camera) -> dict:
    return await snapshot_for_camera(
        c.id, c.ip_address, c.username, c.password_secret, c.rtsp_url, sdk_handle=c.sdk_handle,
    )


def get_gate_or_404(db: Session, gate_id: int) -> Gate:
    g = db.get(Gate, gate_id)
    if not g:
        raise HTTPException(404, "Gate not found")
    return g


def persist_video(db: Session, camera: Camera, url: str | None = None) -> None:
    changed = False
    if url and str(url).startswith("rtsp://") and camera.rtsp_url != url:
        camera.rtsp_url = url
        changed = True
    if camera.status in {
        CameraStatus.UNKNOWN.value, CameraStatus.DISCOVERED.value,
        CameraStatus.SDK_CONNECTED.value,
    }:
        camera.status = CameraStatus.VIDEO_CONNECTED.value
        changed = True
    if changed:
        camera.last_seen_at = datetime.now(timezone.utc)
        camera.last_error = ""
        db.commit()


async def _native_capture_for_camera(camera: Camera) -> dict:
    """Best-effort QY capture callback plate. Missing SDK host is not a plate."""
    if camera.sdk_handle is None:
        return native_from_sdk_capture(None)
    try:
        state = await HVXHostClient().state(int(camera.sdk_handle))
    except Exception:
        return native_from_sdk_capture(None)
    capture = state.get("last_capture") if isinstance(state, dict) else None
    return native_from_sdk_capture(capture)


async def _discover_cameras(db: Session, *, scan_lan: bool = False) -> dict:
    defaults = site_camera_defaults()
    existing = {c.ip_address: camera_dict(c) for c in db.scalars(select(Camera)).all()}
    ips = [row["ip_address"] for row in KNOWN_SITE_CAMERAS]
    hvx = {"ok": False, "ips": [], "error": None, "note": "32-bit HVX host not queried yet"}
    try:
        hvx = await HVXHostClient().discover(wait_seconds=2.0)
        for ip in hvx.get("ips") or []:
            if ip and ip not in ips:
                ips.append(ip)
    except HVXHostUnavailable as exc:
        hvx = {
            "ok": False,
            "ips": [],
            "error": str(exc),
            "note": "Start tools\\hvx_sdk_host\\run_hvx_host.bat on 32-bit Python. TCP probe still runs.",
        }
    lan_ips: list[str] = []
    generic: list[dict] = []
    if scan_lan:
        devices = await scan_lan_devices()
        for device in devices:
            ip = device["ip"]
            if device.get("kind") == "hvx":
                if ip not in ips:
                    ips.append(ip)
                lan_ips.append(ip)
            else:
                generic.append(device)
    probed = await probe_ips(ips, defaults["sdk_port"])
    hvx_set = set(hvx.get("ips") or [])
    generic_by_ip = {row["ip"]: row for row in generic}
    cameras = []
    for ip in ips:
        sdk_open = bool(probed.get(ip))
        extra = generic_by_ip.pop(ip, None)
        if not sdk_open and ip not in hvx_set and extra is not None:
            cameras.append(generic_discovery_row(extra, existing.get(ip)))
            continue
        cameras.append(discovery_row(
            ip,
            tcp_open=sdk_open,
            hvx_found=ip in hvx_set,
            existing=existing.get(ip),
        ))
    for extra in generic_by_ip.values():
        cameras.append(generic_discovery_row(extra, existing.get(extra["ip"])))
    return {
        "sdk_port": defaults["sdk_port"],
        "username": defaults["username"],
        "scan_lan": scan_lan,
        "hvx": hvx,
        "lan_ips": lan_ips,
        "cameras": cameras,
        "note": (
            "TCP open or vendor FindDeviceIp is not SDK_CONNECTED. Use Connect / Connect all. "
            "Dahua/Hikvision/web cameras need only username and password; they stream video and FastALPR reads plates."
        ),
    }


def _ensure_known_gates(db: Session) -> dict[str, Gate]:
    by_name: dict[str, Gate] = {}
    for spec in KNOWN_SITE_GATES:
        gate = db.scalar(select(Gate).where(Gate.name == spec["name"]))
        if gate is None:
            gate = Gate(name=spec["name"], mode=GateMode.COMMISSIONING.value)
            db.add(gate)
            db.flush()
        by_name[spec["name"]] = gate
    return by_name


def _import_site_layout(db: Session, user: User) -> tuple[list[Camera], list[dict], list[Gate]]:
    gates = _ensure_known_gates(db)
    specs = []
    for row in KNOWN_SITE_CAMERAS:
        spec = camera_spec_for_ip(row["ip_address"])
        gate = gates.get(row["gate_name"])
        if gate is not None:
            spec["gate_id"] = gate.id
            spec["gate_name"] = gate.name
        specs.append(spec)
    created, skipped = _import_camera_specs(db, user, specs)
    names = [spec["name"] for spec in KNOWN_SITE_GATES]
    gates_list = list(db.scalars(select(Gate).where(Gate.name.in_(names)).order_by(Gate.id)).all())
    return created, skipped, gates_list


def _import_camera_specs(db: Session, user: User, specs: list[dict]) -> tuple[list[Camera], list[dict]]:
    existing_ips = {c.ip_address: c for c in db.scalars(select(Camera)).all()}
    existing_names = {c.name for c in existing_ips.values()}
    created: list[Camera] = []
    skipped: list[dict] = []
    defaults = site_camera_defaults()
    for spec in specs:
        ip = spec["ip_address"]
        if ip in existing_ips:
            camera = existing_ips[ip]
            if spec.get("gate_id") is not None:
                camera.gate_id = spec["gate_id"]
            if spec.get("controller_ip") is not None:
                camera.controller_ip = spec.get("controller_ip") or ""
            if spec.get("display_ip") is not None:
                camera.display_ip = spec.get("display_ip") or ""
            if spec.get("lane_direction"):
                camera.lane_direction = spec["lane_direction"]
            new_name = spec.get("name")
            if new_name and new_name != camera.name and new_name not in existing_names:
                existing_names.discard(camera.name)
                camera.name = new_name
                existing_names.add(new_name)
            skipped.append({"ip_address": ip, "reason": "already added", "camera_id": camera.id, "updated": True})
            continue
        name = spec.get("name") or f"Camera {ip}"
        if name in existing_names:
            name = f"{name} ({ip})"
        camera = Camera(
            name=name,
            ip_address=ip,
            sdk_port=int(spec.get("sdk_port") or defaults["sdk_port"]),
            username=spec.get("username") or defaults["username"],
            password_secret=spec.get("password") or defaults["password"],
            lane_direction=spec.get("lane_direction") or "ENTRY",
            controller_ip=spec.get("controller_ip") or "",
            display_ip=spec.get("display_ip") or "",
            gate_id=spec.get("gate_id"),
            adapter_id=(spec.get("adapter_id") or "hvx").strip().lower() or "hvx",
            rtsp_url=spec.get("rtsp_url") or "",
            status=CameraStatus.DISCOVERED.value,
        )
        db.add(camera)
        db.flush()
        existing_ips[ip] = camera
        existing_names.add(camera.name)
        created.append(camera)
        write_audit(db, user, "camera.create", "camera", str(camera.id), f"Imported {camera.name} {camera.ip_address}")
    db.commit()
    for camera in created:
        db.refresh(camera)
    return created, skipped


def _connect_audit(result: dict) -> dict:
    return {k: v for k, v in result.items() if k not in {"password", "jpeg"}}


def _commit_camera(db: Session, camera: Camera) -> None:
    """Commit camera row changes; recover from stale/rolled-back sessions."""
    from sqlalchemy.exc import PendingRollbackError, InvalidRequestError
    from sqlalchemy.orm.attributes import flag_modified
    from sqlalchemy.orm.exc import StaleDataError

    for json_field in ("stream_profiles", "media_capabilities"):
        if json_field in camera.__dict__:
            try:
                flag_modified(camera, json_field)
            except Exception:
                pass
    try:
        db.commit()
        return
    except (StaleDataError, PendingRollbackError, InvalidRequestError):
        try:
            db.rollback()
        except Exception:
            pass
    camera_id = getattr(camera, "id", None)
    if camera_id is None:
        raise RuntimeError("Camera row is missing an id after rollback")
    fresh = db.get(Camera, camera_id)
    if fresh is None:
        raise RuntimeError(f"Camera {camera_id} was deleted during connect")
    for field in (
        "status", "sdk_handle", "last_error", "last_seen_at", "rtsp_url",
        "adapter_id", "stream_profiles", "media_capabilities",
    ):
        if field in camera.__dict__:
            setattr(fresh, field, getattr(camera, field))
            if field in {"stream_profiles", "media_capabilities"}:
                flag_modified(fresh, field)
    db.commit()
    for field in (
        "status", "sdk_handle", "last_error", "last_seen_at", "rtsp_url",
        "adapter_id", "stream_profiles", "media_capabilities",
    ):
        setattr(camera, field, getattr(fresh, field))


async def apply_camera_connect(camera: Camera, db: Session, user: User, *, raise_on_host_error: bool = True) -> dict:
    adapter = camera_adapter_for(camera)
    caps = await adapter.capabilities(camera)
    if not caps.get("sdk_login"):
        return await apply_video_connect(camera, db, user, raise_on_host_error=raise_on_host_error)
    port = int(camera.sdk_port or settings.default_hvx_sdk_port)
    if await tcp_open(camera.ip_address, port, timeout=settings.camera_tcp_probe_seconds):
        return await apply_sdk_connect(camera, db, user, raise_on_host_error=raise_on_host_error)
    web = False
    for web_port in (80, 8000, 8080, 554):
        if await tcp_open(camera.ip_address, web_port, timeout=0.4):
            web = True
            break
    if web:
        previous = camera.adapter_id
        camera.adapter_id = "rtsp"
        _commit_camera(db, camera)
        video = await apply_video_connect(camera, db, user, raise_on_host_error=False)
        if video.get("status") == CameraStatus.VIDEO_CONNECTED.value:
            return video
        camera.adapter_id = previous
        _commit_camera(db, camera)
    return await apply_sdk_connect(camera, db, user, raise_on_host_error=raise_on_host_error)


async def apply_video_connect(camera: Camera, db: Session, user: User, *, raise_on_host_error: bool = True) -> dict:
    adapter = camera_adapter_for(camera)
    try:
        result = await adapter.connect(camera)
        jpeg = result.get("jpeg") or b""
        if result.get("connected"):
            camera.status = CameraStatus.VIDEO_CONNECTED.value
            camera.sdk_handle = None
            camera.last_seen_at = datetime.now(timezone.utc)
            camera.last_error = ""
            url = str(result.get("url") or "")
            if url.startswith("rtsp://"):
                camera.rtsp_url = url
            from .services.stream_roles import default_capabilities, recommend_roles
            camera.media_capabilities = default_capabilities(rtsp=True)
            if url:
                camera.stream_profiles = recommend_roles([{
                    "uri": url,
                    "protocol": str(result.get("source") or "rtsp"),
                    "codec": str(result.get("codec") or ""),
                }])
            if jpeg[:2] == b"\xff\xd8":
                remember_frame(
                    camera.id, jpeg,
                    url=url,
                    url_redacted=str(result.get("url_redacted") or ""),
                    source=str(result.get("source") or "rtsp"),
                )
            from .infrastructure.media.registry import mediamtx_detect_active
            if not mediamtx_detect_active(camera.id, db):
                acquire_detect(_live_spec(camera, need_detect=True))
            else:
                from .services.mediamtx_detect import ensure_detect_consumer
                ensure_detect_consumer(_live_spec(camera, need_detect=True))
            try:
                from .services.mediamtx_sources import sync_camera
                sync_camera(camera, db=db)
            except Exception:
                pass
        else:
            camera.status = CameraStatus.OFFLINE.value
            camera.sdk_handle = None
            camera.last_error = result.get("error") or f"{adapter.id} did not return a live JPEG"
        _commit_camera(db, camera)
        write_audit(db, user, "camera.video_connect", "camera", str(camera.id), str(_connect_audit(result)))
        return {**camera_dict(camera), "sdk_result": _connect_audit(result)}
    except HTTPException:
        raise
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        try:
            fresh = db.get(Camera, camera.id) if getattr(camera, "id", None) else None
            target = fresh or camera
            target.status = CameraStatus.OFFLINE.value
            target.sdk_handle = None
            target.last_error = str(exc)
            _commit_camera(db, target)
            if fresh is not None:
                camera.status = target.status
                camera.sdk_handle = target.sdk_handle
                camera.last_error = target.last_error
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
        if raise_on_host_error:
            raise HTTPException(502, f"IP camera connection failed: {exc}")
        return {**camera_dict(camera), "sdk_result": {"connected": False, "error": str(exc)}}


async def apply_sdk_connect(camera: Camera, db: Session, user: User, *, raise_on_host_error: bool = True) -> dict:
    adapter = camera_adapter_for(camera)
    caps = await adapter.capabilities(camera)
    if not caps.get("sdk_login"):
        raise HTTPException(
            400,
            f"SDK connect is HVX-only. Camera adapter {adapter.id} cannot replace the working NetSDK login.",
        )
    port = int(camera.sdk_port or settings.default_hvx_sdk_port)
    reachable = await tcp_open(camera.ip_address, port, timeout=settings.camera_tcp_probe_seconds)
    if not reachable:
        camera.status = CameraStatus.SDK_FAILED.value
        camera.last_error = (
            f"No TCP on {camera.ip_address}:{port} — skipped SDK login so other cameras can still connect."
        )
        _commit_camera(db, camera)
        write_audit(db, user, "camera.sdk_connect", "camera", str(camera.id), camera.last_error)
        return {
            **camera_dict(camera),
            "sdk_result": {"connected": False, "skipped": True, "error": camera.last_error},
        }
    camera.status = CameraStatus.SDK_CONNECTING.value
    camera.last_error = ""
    _commit_camera(db, camera)
    try:
        result = await adapter.connect(camera)
        if result.get("connected"):
            camera.status = CameraStatus.SDK_CONNECTED.value
            camera.sdk_handle = result.get("handle")
            camera.last_seen_at = datetime.now(timezone.utc)
            camera.last_error = ""
            from .services.stream_roles import default_capabilities, hvx_profiles
            camera.stream_profiles = hvx_profiles(camera.sdk_handle)
            camera.media_capabilities = default_capabilities(native_alpr=True, sdk=True)
            _commit_camera(db, camera)
            try:
                from .services.mediamtx_sources import sync_camera
                sync_camera(camera, db=db)
            except Exception:
                pass
        else:
            camera.status = CameraStatus.SDK_FAILED.value
            name = result.get("connect_rc_name") or result.get("connect_rc")
            camera.last_error = result.get("error") or f"SDK return code: {name}"
        _commit_camera(db, camera)
        write_audit(
            db, user, "camera.sdk_connect", "camera", str(camera.id),
            str(_connect_audit(result)),
        )
        return {**camera_dict(camera), "sdk_result": result}
    except HTTPException:
        raise
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        try:
            fresh = db.get(Camera, camera.id) if getattr(camera, "id", None) else None
            target = fresh or camera
            target.status = CameraStatus.SDK_FAILED.value
            target.last_error = str(exc)
            _commit_camera(db, target)
            if fresh is not None:
                camera.status = target.status
                camera.last_error = target.last_error
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
        if raise_on_host_error:
            raise HTTPException(502, f"HVX SDK connection failed: {exc}")
        return {**camera_dict(camera), "sdk_result": {"connected": False, "error": str(exc)}}


def _plate_payload(camera: Camera, native: dict, alpr: dict | None, db: Session | None = None) -> dict:
    from .services.flags import native_alpr_enabled
    if not native_alpr_enabled():
        native = {**(native or {}), "plate": "", "confidence": 0.0}
    local = local_from_fastalpr(alpr)
    fused = resolve_readings(
        native_plate=native.get("plate") or "",
        native_confidence=float(native.get("confidence") or 0),
        local_plate=local.get("plate") or "",
        local_confidence=float(local.get("confidence") or 0),
        mode=fusion_mode(camera),
    )
    overlay = choose_overlay_box(native, local)
    live = get_state(camera.id)
    last = live.last_car or None
    if not last and db is not None:
        row = latest_for_camera(db, camera.id)
        last = capture_dict(row) if row else None
        if last:
            remember_last_car(camera.id, last)
    return {
        "camera": camera_dict(camera),
        "native": native,
        "local": local,
        "fusion": fused.as_dict(),
        "alpr": alpr,
        "resolved_plate": fused.resolved_plate,
        "overlay": overlay,
        "last_car": last,
        "live": bool(live.jpeg[:2] == b"\xff\xd8"),
        "live_source": live.source,
        "live_fps": live.fps,
        "url_redacted": live.url_redacted,
        "live_frame_age_ms": (time.monotonic() - live.captured_at) * 1000 if live.captured_at else None,
        "media": _camera_media_brief(camera.id),
    }


_local_alpr_at: dict[int, float] = {}
_alpr_fp: dict[int, int] = {}


def _coil_indexes(camera_id: int | None = None) -> list[int]:
    learned = coil_watch.learned_index(camera_id) if camera_id is not None else None
    if learned is not None:
        return [learned]
    raw = str(getattr(settings, "coil_poll_indexes", "1,2,3,4,5,6,7") or "1,2,3,4,5,6,7")
    indexes: list[int] = []
    barrier = int(getattr(settings, "gpio_index", 0) or 0)
    for part in raw.split(","):
        part = part.strip()
        if not part.isdigit():
            continue
        value = int(part)
        if value == barrier:
            continue
        if value not in indexes:
            indexes.append(value)
    default = int(getattr(settings, "coil_gpio_index", 1) or 1)
    if default != barrier and default not in indexes:
        indexes.insert(0, default)
    return indexes or [1]


def _local_alpr_due(camera_id: int) -> bool:
    wait = float(getattr(settings, "local_alpr_cooldown_seconds", 2.0) or 2.0)
    return time.monotonic() - _local_alpr_at.get(camera_id, 0.0) >= wait


def _mark_local_alpr(camera_id: int) -> None:
    _local_alpr_at[camera_id] = time.monotonic()


def _local_alpr_ready(camera_id: int) -> bool:
    if not _local_alpr_due(camera_id):
        return False
    _mark_local_alpr(camera_id)
    return True


def _crop_from_alpr(alpr: dict | None) -> bytes:
    best = (alpr or {}).get("best") or {}
    rel = best.get("plate_crop_path")
    if not rel:
        return b""
    path = settings.media_dir / rel
    try:
        data = path.read_bytes()
    except Exception:
        return b""
    return data if data[:2] == b"\xff\xd8" else b""


def _capture_from_readings(native: dict, local: dict, fused, *, image_id: int = 0, pending: bool = False) -> dict:
    from .services.camera_lpr import capture_from_readings

    return capture_from_readings(native, local, fused, image_id=image_id, pending=pending)


async def _run_local_alpr(
    db: Session,
    camera: Camera,
    jpeg: bytes,
    *,
    native: dict | None = None,
    presence: bool = True,
    image_id: int = 0,
    force: bool = False,
) -> dict | None:
    jpeg = jpeg or b""
    if jpeg[:2] != b"\xff\xd8":
        return None
    native = native or {}
    if not should_run_local(
        native_plate=str(native.get("plate") or ""),
        native_confidence=float(native.get("confidence") or 0),
        explicit=force,
        presence=presence,
        native_plates=adapter_has_native_plates(camera),
    ):
        return None
    if not force and not _local_alpr_ready(camera.id):
        return None
    if not force and _alpr_busy():
        return None
    _alpr_enter()
    try:
        return await _run_local_alpr_locked(
            db, camera, jpeg, native=native, presence=presence, image_id=image_id, force=force,
        )
    except Exception as exc:
        from .services.health import note_worker_failure
        note_worker_failure("alpr", str(exc))
        return {"ok": False, "backend": "fastalpr", "plates": [], "detail": str(exc), "error": str(exc)}
    finally:
        _alpr_leave()


def _alpr_busy() -> bool:
    return int(_alpr_inflight["n"]) > 0


def _alpr_enter() -> None:
    _alpr_inflight["n"] = int(_alpr_inflight["n"]) + 1


def _alpr_leave() -> None:
    _alpr_inflight["n"] = max(0, int(_alpr_inflight["n"]) - 1)


_alpr_inflight = {"n": 0}


async def _run_local_alpr_locked(
    db: Session,
    camera: Camera,
    jpeg: bytes,
    *,
    native: dict | None = None,
    presence: bool = True,
    image_id: int = 0,
    force: bool = False,
) -> dict | None:
    native = native or {}
    from .services.media_gateway import gateway
    from .services.queues import AI_FRAMES
    sample = gateway.peek_detect(camera.id)
    if sample:
        AI_FRAMES.put((camera.id, sample.seq))
    started = time.perf_counter()
    alpr = await asyncio.to_thread(recognize_frame, jpeg, camera_label=f"cam-{camera.id}-{camera.ip_address}")
    gateway.note_ai_sample(camera.id, infer_ms=(time.perf_counter() - started) * 1000, dropped=False)
    remember_alpr(camera.id, alpr)
    local = local_from_fastalpr(alpr)
    from .core.consensus import DEFAULT_HIGH_CONF, resolve_local_reads
    reads = [(str(local.get("plate") or ""), float(local.get("confidence") or 0))]
    consensus_ok = False
    if float(local.get("confidence") or 0) < DEFAULT_HIGH_CONF:
        extras = gateway.peek_detect_recent(camera.id, 3)
        for sample in extras:
            if not sample or sample.jpeg[:2] != b"\xff\xd8" or sample.jpeg == jpeg:
                continue
            extra = await asyncio.to_thread(
                recognize_frame, sample.jpeg, camera_label=f"cam-{camera.id}-detect",
            )
            hit = local_from_fastalpr(extra)
            if hit.get("plate"):
                reads.append((str(hit.get("plate") or ""), float(hit.get("confidence") or 0)))
                break
        decided = resolve_local_reads(reads)
        if decided.plate:
            local = {**local, "plate": decided.plate, "confidence": decided.confidence, "consensus": decided.as_dict()}
            consensus_ok = bool(decided.accepted)
    fused = resolve_readings(
        native_plate=native.get("plate") or "",
        native_confidence=float(native.get("confidence") or 0),
        local_plate=local.get("plate") or "",
        local_confidence=float(local.get("confidence") or 0),
        mode=fusion_mode(camera),
        local_consensus=consensus_ok,
    )
    if not fused.resolved_plate:
        return alpr
    # Unique image id so FastALPR hits create a VehicleCapture only when the frame looks like a car/plate.
    if not image_id:
        image_id = int(time.time() * 1000) % 2_000_000_000
    capture = _capture_from_readings(native, local, fused, image_id=image_id)
    from .services.presence import coil_watch
    allowed, reason = should_persist_vehicle_capture(
        capture, coil_occupied=coil_watch.occupied(camera.id),
        plate_policy=site_policy(db).get("plate_validation", "NONE"),
    )
    if not allowed:
        alpr = dict(alpr or {})
        alpr["persist_skipped"] = reason
        return alpr
    await _persist_capture_event(db, camera, capture, jpeg, _crop_from_alpr(alpr))
    return alpr


def validate_gate_mode(mode: str) -> str:
    allowed = {item.value for item in GateMode}
    if mode not in allowed:
        raise HTTPException(400, f"Invalid gate mode. Use one of: {', '.join(sorted(allowed))}")
    return mode


@app.get("/cameras/{camera_id}")
def get_camera(camera_id: int, db: Session = Depends(get_db), _: User = Depends(require("cameras.view"))):
    return camera_dict(get_camera_or_404(db, camera_id))


@app.post("/cameras")
def create_camera(payload: CameraCreate, db: Session = Depends(get_db), user: User = Depends(require("cameras.manage"))):
    c = Camera(
        name=payload.name, ip_address=payload.ip_address, sdk_port=payload.sdk_port,
        username=payload.username, password_secret=payload.password or settings.default_camera_password, gate_id=payload.gate_id,
        lane_direction=payload.lane_direction, controller_ip=payload.controller_ip, display_ip=payload.display_ip,
        rtsp_url=payload.rtsp_url, adapter_id=payload.adapter_id or "hvx",
        connection_mode=(payload.connection_mode or "DIRECT").upper(),
        ffmpeg_profile=payload.ffmpeg_profile or settings.ffmpeg_profile,
        rtsp_transport=(payload.rtsp_transport or settings.rtsp_transport).upper(),
        stream_profiles=payload.stream_profiles or {},
        recognition_mode=(payload.recognition_mode or "").strip().upper(),
        vendor=payload.vendor or "",
        model_name=payload.model_name or "",
        serial=payload.serial or "",
        timezone=payload.timezone or "",
        camera_type=payload.camera_type or "",
        status=CameraStatus.DISCOVERED.value,
    )
    db.add(c)
    commit_or_conflict(db, "A camera with that name already exists")
    db.refresh(c)
    write_audit(db, user, "camera.create", "camera", str(c.id), f"Created {c.name} {c.ip_address}")
    return camera_dict(c)


@app.patch("/cameras/{camera_id}")
def update_camera(camera_id: int, payload: CameraUpdate, db: Session = Depends(get_db), user: User = Depends(require("cameras.manage"))):
    c = get_camera_or_404(db, camera_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("password") in (None, ""):
        data.pop("password", None)
    else:
        data["password_secret"] = data.pop("password")
    if "rtsp_url" in data and data["rtsp_url"] and data["rtsp_url"] == redact_text(c.rtsp_url or ""):
        data.pop("rtsp_url")  # masked value round-tripped from the edit form; keep the stored URL
    if "gate_id" in data and data["gate_id"] is not None:
        get_gate_or_404(db, data["gate_id"])
    if data.get("adapter_id"):
        data["adapter_id"] = str(data["adapter_id"]).strip().lower()
    if data.get("connection_mode"):
        data["connection_mode"] = str(data["connection_mode"]).strip().upper()
        if data["connection_mode"] not in {"DIRECT", "EDGE_AGENT"}:
            raise HTTPException(400, "connection_mode must be DIRECT or EDGE_AGENT")
    if data.get("ffmpeg_profile"):
        from .services.ffmpeg_profiles import normalize_profile
        data["ffmpeg_profile"] = normalize_profile(data["ffmpeg_profile"])
    if data.get("rtsp_transport"):
        from .services.ffmpeg_profiles import normalize_transport
        data["rtsp_transport"] = normalize_transport(data["rtsp_transport"])
    if data.get("recognition_mode"):
        data["recognition_mode"] = str(data["recognition_mode"]).strip().upper()
    if data.get("stream_profiles"):
        from .services.stream_roles import merge_profiles
        data["stream_profiles"] = merge_profiles(c.stream_profiles, data["stream_profiles"])
    for k, v in data.items():
        setattr(c, k, v)
    commit_or_conflict(db, "A camera with that name already exists")
    db.refresh(c)
    write_audit(db, user, "camera.update", "camera", str(c.id), "Camera settings updated")
    return camera_dict(c)


@app.delete("/cameras/{camera_id}")
def delete_camera(camera_id: int, db: Session = Depends(get_db), user: User = Depends(require("cameras.manage"))):
    c = get_camera_or_404(db, camera_id)
    name = c.name
    ref = getattr(c, "credentials_ref", "") or ""
    db.delete(c)
    db.commit()
    if ref:
        from .infrastructure.secrets import secret_store
        try:
            secret_store().delete(ref)
        except Exception as exc:
            log.warning("camera %s: could not delete stored credential %s: %s", camera_id, ref, exc)
    write_audit(db, user, "camera.delete", "camera", str(camera_id), f"Deleted {name}")
    return {"ok": True}


@app.get("/hardware/hvx/info")
async def hvx_info(_: User = Depends(require("hardware.view"))):
    package = vendor_inventory()
    alpr = alpr_status()
    try:
        host = await HVXHostClient().info()
    except HVXHostUnavailable as exc:
        host = {"available": False, "error": str(exc)}
    return {
        "available": bool(host.get("available")),
        "vendor_sdk_loaded": bool(host.get("available")),
        "vendor_package": package,
        "host": host,
        "alpr": alpr,
        "states": {
            "vendor_package_present": package["present"] and not package["missing"],
            "vendor_sdk_x86": bool(package.get("pe", {}).get("x86")),
            "sdk_host_reachable": bool(host.get("available")),
            "fastalpr_installed": alpr["installed"],
        },
        "edge_agent": edge_agent_status(),
    }


@app.get("/devices")
def list_registered_devices(db: Session = Depends(get_db), _: User = Depends(require("hardware.view"))):
    """Projection of cameras/gates. Not a second hardware store."""
    return {"devices": devices_as_dicts(db), "edge_agent": edge_agent_status()}


@app.post("/cameras/{camera_id}/sdk/connect")
async def sdk_connect(camera_id: int, db: Session = Depends(get_db), user: User = Depends(require("cameras.connect"))):
    c = get_camera_or_404(db, camera_id)
    return await apply_camera_connect(c, db, user, raise_on_host_error=False)


@app.post("/cameras/{camera_id}/sdk/disconnect")
async def sdk_disconnect(camera_id: int, db: Session = Depends(get_db), user: User = Depends(require("cameras.connect"))):
    c=db.get(Camera, camera_id)
    if not c: raise HTTPException(404, "Camera not found")
    if c.sdk_handle is not None:
        try: await HVXHostClient().disconnect(c.sdk_handle)
        except Exception: pass
    release_detect(c.id)
    stop_live_pump(c.id)
    from .services.media_gateway import gateway
    try:
        await gateway.unregister_stream(c.id)
    except Exception:
        pass
    c.sdk_handle=None; c.status=CameraStatus.DISCOVERED.value; db.commit()
    write_audit(db, user, "camera.sdk_disconnect", "camera", str(c.id), "Disconnected SDK session")
    return camera_dict(c)


@app.post("/cameras/{camera_id}/rtsp/probe")
async def rtsp_probe(camera_id: int, db: Session = Depends(get_db), _: User = Depends(require("cameras.connect"))):
    c=get_camera_or_404(db, camera_id)
    sdk = await _sdk_probe_status(c)
    http = await grab_http_snapshot(c.ip_address, c.username, c.password_secret)
    if http.get("ok"):
        persist_video(db, c)
    results=[]
    for url in vendor_candidates(c.ip_address, c.username, c.password_secret, c.rtsp_url):
        r=await probe(url)
        results.append(r.__dict__)
        if r.ok:
            c.rtsp_url=url
            if c.status == CameraStatus.SDK_CONNECTED.value:
                c.status=CameraStatus.VIDEO_CONNECTED.value
            db.commit()
            try:
                from app.services.mediamtx_sources import sync_camera
                sync_camera(c, db=db)
            except Exception:
                pass
            break
    return {
        "camera_id": c.id,
        "note": (
            "Live view is SDK JPEG on port 30000, not RTSP. "
            "ffprobe is optional. HTTP stills use camera port 80. "
            "Close any other SDK client if sessions conflict."
        ),
        "sdk": sdk,
        "http": {k: v for k, v in http.items() if k != "jpeg"},
        "results": results,
    }


@app.get("/cameras/{camera_id}/streams")
async def camera_streams(camera_id: int, db: Session = Depends(get_db), _: User = Depends(require("cameras.view"))):
    c = get_camera_or_404(db, camera_id)
    from .services.media_gateway import gateway
    from .services.stream_roles import profile_warnings, public_profiles
    from .services.ffmpeg_profiles import list_profiles
    profiles = getattr(c, "stream_profiles", None) or {}
    health = await gateway.health(c.id)
    from app.infrastructure.media import registry as media_registry
    live_endpoint = await media_registry.get_live_endpoint(c.id, db)
    detect_endpoint = await media_registry.get_detect_endpoint(c.id, db)
    evidence_endpoint = await media_registry.get_evidence_endpoint(c.id, db)
    mediamtx_telemetry = (
        media_registry.media_telemetry(c.id)
        if media_registry.mediamtx_detect_active(c.id, db) or media_registry.mediamtx_live_active(c.id, db)
        else None
    )
    warnings = profile_warnings(profiles, upstream_consumers=1 if health.get("pumping") else 0)
    if mediamtx_telemetry:
        compat = mediamtx_telemetry.get("webrtc") or {}
        if compat.get("compatible") is False and compat.get("reason"):
            warnings.append(str(compat["reason"]))
        for role, row in (mediamtx_telemetry.get("roles") or {}).items():
            lost = int(((row.get("rtp") or {}).get("packets_lost")) or 0)
            if lost:
                warnings.append(f"{role}: {lost} RTP packets lost")
    return {
        "camera": camera_dict(c),
        "ffmpeg_profile": getattr(c, "ffmpeg_profile", None) or settings.ffmpeg_profile,
        "rtsp_transport": getattr(c, "rtsp_transport", None) or settings.rtsp_transport,
        "stream_profiles": public_profiles(profiles),
        "media_capabilities": list(getattr(c, "media_capabilities", None) or []),
        "warnings": warnings,
        "media": {**health, "mediamtx": mediamtx_telemetry},
        "profiles": list_profiles(),
        "live_url": f"/cameras/{c.id}/live.mjpeg",
        "main_url": f"/cameras/{c.id}/live.mjpeg?role=MAIN",
        "live_endpoint": live_endpoint,
        "detect": detect_endpoint,
        "evidence": evidence_endpoint,
    }


@app.patch("/cameras/{camera_id}/streams")
async def update_camera_streams(
    camera_id: int,
    payload: StreamProfilesUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require("cameras.manage")),
):
    c = get_camera_or_404(db, camera_id)
    from .services.ffmpeg_profiles import normalize_profile, normalize_transport
    from .services.stream_roles import ROLE_DETECT, ROLE_LIVE, merge_profiles
    if payload.ffmpeg_profile:
        c.ffmpeg_profile = normalize_profile(payload.ffmpeg_profile)
    if payload.rtsp_transport:
        c.rtsp_transport = normalize_transport(payload.rtsp_transport)
    profiles = dict(c.stream_profiles or {})
    if payload.stream_profiles:
        profiles = merge_profiles(profiles, payload.stream_profiles)
    if payload.live_role:
        profiles[ROLE_LIVE] = {**(profiles.get(ROLE_LIVE) or {}), "source": payload.live_role.upper(), "role": ROLE_LIVE}
    if payload.detect_source:
        profiles[ROLE_DETECT] = {**(profiles.get(ROLE_DETECT) or {}), "source": payload.detect_source.upper(), "role": ROLE_DETECT}
    if payload.ai_fps is not None:
        profiles[ROLE_DETECT] = {**(profiles.get(ROLE_DETECT) or {}), "ai_fps": payload.ai_fps, "role": ROLE_DETECT}
    c.stream_profiles = profiles
    db.commit()
    write_audit(db, user, "camera.streams", "camera", str(c.id), f"profile={c.ffmpeg_profile} transport={c.rtsp_transport}")
    spec = _live_spec(c)
    if pumping_spec(c.id) is not None or viewers_for(c.id) > 0:
        start_live_pump(spec)
    return await camera_streams(c.id, db)


@app.post("/cameras/{camera_id}/onvif/discover")
async def camera_onvif_discover(camera_id: int, db: Session = Depends(get_db), user: User = Depends(require("cameras.connect"))):
    c = get_camera_or_404(db, camera_id)
    from .services.stream_discover import discover_camera_streams
    from .services.stream_roles import merge_profiles
    from .services.onvif_profile import apply_discovery
    found = await discover_camera_streams(c.ip_address, c.username, c.password_secret, c.rtsp_url or "")
    if found.get("stream_profiles"):
        c.stream_profiles = merge_profiles(c.stream_profiles, found["stream_profiles"])
    apply_discovery(c, found.get("onvif") or {})
    db.commit()
    write_audit(db, user, "camera.onvif_discover", "camera", str(c.id), found.get("source") or "")
    from .services.stream_roles import public_profiles
    public = {k: v for k, v in found.items() if k not in {"onvif", "discovered", "stream_profiles"}}
    public["discovered"] = _strip_credential_uris(found.get("discovered") or [])
    public["stream_profiles"] = public_profiles(found.get("stream_profiles") or {})
    public["onvif"] = _public_onvif_discovery(found.get("onvif") or {})
    return {"camera": camera_dict(c), **public}


def _strip_credential_uris(rows: list) -> list:
    return [{k: v for k, v in dict(row).items() if k not in {"uri", "url", "snapshot_uri"}} for row in rows]


def _public_onvif_discovery(onvif: dict) -> dict:
    """Discovery payload without credential-bearing URIs."""
    out = {k: v for k, v in onvif.items() if k not in {"profiles", "snapshot_uri"}}
    out["profiles"] = _strip_credential_uris(onvif.get("profiles") or [])
    return out


@app.patch("/cameras/{camera_id}/onvif/events")
async def camera_onvif_events_toggle(camera_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require("cameras.connect"))):
    """Enable/disable Profile M plate-event pulling for a camera that advertises it."""
    c = get_camera_or_404(db, camera_id)
    from .services.onvif_profile import set_events_enabled
    try:
        set_events_enabled(c, bool(payload.get("enabled")))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    db.commit()
    write_audit(db, user, "camera.onvif_events", "camera", str(c.id), "on" if payload.get("enabled") else "off")
    return camera_dict(c)


@app.post("/cameras/{camera_id}/onvif/events/pull")
async def camera_onvif_events_pull(camera_id: int, db: Session = Depends(get_db), user: User = Depends(require("cameras.connect"))):
    """Hardware-lab diagnostic: one subscribe → pull → unsubscribe round trip."""
    c = get_camera_or_404(db, camera_id)
    profile = dict(c.onvif_profile or {})
    events_url = str(profile.get("events_url") or "")
    if not events_url:
        raise HTTPException(409, "Camera did not advertise an ONVIF Events service; run ONVIF discovery first.")
    from .services.onvif_events import ONVIFPullPoint, event_to_capture
    from .services.onvif_discover import ONVIFError
    pullpoint = ONVIFPullPoint(events_url, c.username or "", c.password_secret or "", timeout=6.0)
    try:
        await pullpoint.subscribe()
        events = await pullpoint.pull(wait="PT3S", limit=20)
    except ONVIFError as exc:
        raise HTTPException(502, str(exc))
    finally:
        await pullpoint.unsubscribe()
    write_audit(db, user, "camera.onvif_events_pull", "camera", str(c.id), f"{len(events)} messages")
    return {
        "ok": True,
        "messages": len(events),
        "events": [{**e, "capture": event_to_capture(e)} for e in events[:20]],
    }


@app.get("/media/gateway")
async def media_gateway_health(db: Session = Depends(get_db), _: User = Depends(require("hardware.view"))):
    from .services.media_gateway import gateway
    from .services.ffmpeg_profiles import list_profiles
    from .services.hw_decode import detect_decode_path
    from .services import mediamtx
    from .services.flags import flags as migration_flags
    sessions = gateway.live_metrics()
    pids = gateway.child_pids()
    mediamtx_health = mediamtx.health()
    mediamtx_paths: dict = {}
    if mediamtx_health.get("running"):
        try:
            from .services.mediamtx_telemetry import refresh as mediamtx_refresh
            mediamtx_paths = dict(mediamtx_refresh().get("paths") or {})
        except Exception as exc:
            mediamtx_paths = {"error": str(exc)[:200]}
    return {
        "cameras": sessions,
        "child_pids": pids,
        "ffmpeg_profiles": list_profiles(),
        "decode": await detect_decode_path(),
        "local": {"sessions": sessions, "child_pids": pids},
        "mediamtx": mediamtx_health,
        "mediamtx_paths": mediamtx_paths,
        "flags": migration_flags(db),
        "rollback": {
            "live_view_provider": ["DIRECT_LEGACY", "MEDIAMTX"],
            "recognition_pipeline": ["FASTALPR_LEGACY", "FASTALPR_NEW"],
        },
    }


@app.get("/hardware/decode")
async def hardware_decode(_: User = Depends(require("hardware.view"))):
    from .services.hw_decode import detect_decode_path
    return await detect_decode_path()


async def _sdk_probe_status(c: Camera) -> dict:
    if c.sdk_handle is None:
        return {"handle": None, "status": c.status, "jpeg": False, "note": "SDK Connect first. RTSP is not required."}
    try:
        jpeg = await HVXHostClient().capture_jpeg(int(c.sdk_handle), trigger=True)
    except Exception as exc:
        return {"handle": c.sdk_handle, "status": c.status, "jpeg": False, "error": str(exc)}
    return {
        "handle": c.sdk_handle,
        "status": c.status,
        "jpeg": bool(jpeg),
        "jpeg_bytes": len(jpeg or b""),
        "note": "CONN_STATE_UNKNOW after Net_ConnCameraEx rc=0 is normal on this site.",
    }


@app.get("/alpr/status")
def get_alpr_status(_: User = Depends(require("hardware.view"))):
    body = alpr_status()
    body["engines"] = list_engines()
    return body


@app.get("/recognition/engine")
def get_plate_engine(_: User = Depends(require("cameras.view"))):
    engine = active_engine()
    described = engine.describe()
    described["engines"] = list_engines()
    described["training"] = training_status(engine_id=engine.id)
    described["platform"] = {
        "desktop": "PySide6",
        "windows": True,
        "linux": True,
    }
    return described


@app.post("/recognition/corrections")
def post_plate_correction(
    payload: PlateEngineCorrection,
    _: User = Depends(require("cameras.connect")),
):
    engine = active_engine()
    row = record_correction(
        image_ref=payload.image_ref,
        predicted=payload.predicted,
        corrected=payload.corrected,
        engine_id=engine.id,
        country=payload.country,
    )
    return {"ok": True, "correction": row, "training": training_status(engine_id=engine.id)}


@app.get("/ai/health")
def ai_health(db: Session = Depends(get_db), _: User = Depends(require("hardware.view"))):
    """Optional cloud AI reviewer: disabled by default, never a gate authority."""
    from .services import ai_review
    return ai_review.health(db)


@app.get("/ai/reviews")
def ai_recent_reviews(_: User = Depends(require("cameras.view"))):
    from .services import ai_review
    return {"items": ai_review.recent(), "stats": ai_review.stats()}


@app.post("/ai/review/{capture_id}")
async def ai_review_capture(capture_id: int, db: Session = Depends(get_db), user: User = Depends(require("cameras.connect"))):
    """Operator-requested second opinion on a stored capture. Stores the verdict; never edits the plate."""
    from .services import ai_review
    if not ai_review.enabled(db):
        raise HTTPException(409, "AI review is disabled (SMARTPARK_AI_ENABLED=false)")
    try:
        review = await ai_review.review_capture(db, capture_id)
    except LookupError:
        raise HTTPException(404, "Capture not found")
    write_audit(db, user, "ai.review", "capture", str(capture_id), f"AI verdict {review.verdict}")
    return {"ok": review.verdict != "unavailable", "review": review.as_dict()}


@app.post("/ai/incidents/summary")
async def ai_incident_summary(payload: AIIncidentSummaryRequest, db: Session = Depends(get_db), _: User = Depends(require("cameras.view"))):
    from .services import ai_review
    body = await ai_review.summarize_incident(
        db, capture_ids=payload.capture_ids, plate=payload.plate, limit=payload.limit, question=payload.question or "",
    )
    if not body.get("ok") and body.get("reason") == "ai_disabled":
        raise HTTPException(409, "AI review is disabled (SMARTPARK_AI_ENABLED=false)")
    return body


@app.post("/recognition/model-pack")
def post_model_pack(
    payload: ModelPackRequest,
    _: User = Depends(require("settings.manage")),
):
    directory = payload.directory.strip()
    if not directory:
        raise HTTPException(400, "directory is required")
    engine = active_engine()
    try:
        applied = apply_model_pack(directory, engine_id=engine.id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return applied


@app.post("/alpr/fuse")
def fuse_plates(payload: FusionRequest, _: User = Depends(require("cameras.connect"))):
    return resolve_readings(
        native_plate=payload.native_plate,
        native_confidence=payload.native_confidence,
        local_plate=payload.local_plate,
        local_confidence=payload.local_confidence,
        operator_plate=payload.operator_plate,
        mode=payload.mode,
    ).as_dict()


@app.post("/alpr/recognize")
async def alpr_recognize_upload(
    file: UploadFile = File(...),
    _: User = Depends(require("cameras.connect")),
):
    jpeg = await file.read()
    if not jpeg:
        raise HTTPException(400, "Empty image")
    result = recognize_frame(jpeg, camera_label=file.filename or "upload")
    return result


@app.post("/cameras/{camera_id}/alpr/recognize")
async def camera_alpr(camera_id: int, db: Session = Depends(get_db), user: User = Depends(require("cameras.connect"))):
    c = get_camera_or_404(db, camera_id)
    grabbed = await live_snapshot(c)
    if not grabbed.get("ok"):
        write_audit(db, user, "camera.alpr", "camera", str(c.id), grabbed.get("error") or "no frame")
        raise HTTPException(409, grabbed.get("error") or "Could not grab a live frame")
    remember_frame(c.id, grabbed["jpeg"], url=grabbed.get("url") or "", url_redacted=grabbed.get("url_redacted") or "")
    persist_video(db, c, grabbed.get("url"))
    result = recognize_frame(grabbed["jpeg"], camera_label=f"cam-{c.id}-{c.ip_address}")
    native = await _native_capture_for_camera(c)
    local = local_from_fastalpr(result)
    fused = resolve_readings(
        native_plate=native.get("plate") or "",
        native_confidence=float(native.get("confidence") or 0),
        local_plate=local.get("plate") or "",
        local_confidence=float(local.get("confidence") or 0),
        mode=fusion_mode(c),
    )
    result["camera_id"] = c.id
    result["frame"] = {k: v for k, v in grabbed.items() if k not in {"jpeg", "url"}}
    result["native"] = native
    result["local"] = local
    result["fusion"] = fused.as_dict()
    remember_alpr(c.id, result)
    if fused.resolved_plate:
        capture = _capture_from_readings(
            native, local, fused, image_id=int(time.time() * 1000) % 2_000_000_000,
        )
        last = await _persist_capture_event(db, c, capture, grabbed["jpeg"], _crop_from_alpr(result))
        result["last_car"] = last
        result["capture"] = last
    write_audit(db, user, "camera.alpr", "camera", str(c.id), fused.resolved_plate or result.get("detail") or "FastALPR")
    return result


def _resolve_stream_profiles(camera: Camera) -> dict:
    profiles = dict(getattr(camera, "stream_profiles", None) or {})
    if profiles:
        return profiles
    if camera.sdk_handle is not None:
        from .services.stream_roles import hvx_profiles
        return hvx_profiles(camera.sdk_handle)
    if camera.rtsp_url:
        from .services.stream_roles import recommend_roles
        return recommend_roles([{"uri": camera.rtsp_url, "width": 1280, "height": 720, "fps": 15}])
    return profiles


def _live_spec(camera: Camera, *, need_detect: bool = False, live_role: str = "LIVE") -> CameraLiveSpec:
    detect = need_detect or (not adapter_has_native_plates(camera))
    return CameraLiveSpec(
        id=camera.id,
        ip=camera.ip_address,
        username=camera.username,
        password=camera.password_secret,
        rtsp_url=camera.rtsp_url or "",
        sdk_handle=camera.sdk_handle,
        ffmpeg_profile=getattr(camera, "ffmpeg_profile", None) or settings.ffmpeg_profile,
        transport=getattr(camera, "rtsp_transport", None) or settings.rtsp_transport,
        need_detect=detect,
        live_role=live_role,
        stream_profiles=_resolve_stream_profiles(camera),
    )


def _camera_live_spec(camera_id: int) -> CameraLiveSpec:
    with short_session() as db:
        c = get_camera_or_404(db, camera_id)
        return _live_spec(c)


@app.get("/cameras/{camera_id}/live/endpoint")
async def camera_live_endpoint(camera_id: int, db: Session = Depends(get_db), _: User = Depends(require("cameras.view"))):
    get_camera_or_404(db, camera_id)
    from app.infrastructure.media import registry as media_registry
    return await media_registry.get_live_endpoint(camera_id, db)


_snapshot_status_checked: set[int] = set()


@app.get("/cameras/{camera_id}/snapshot.jpg")
async def camera_snapshot(camera_id: int, _: User = Depends(require_media("cameras.view"))):
    spec = pumping_spec(camera_id) or _camera_live_spec(camera_id)
    row = get_state(camera_id)

    def _jpeg_response(jpeg: bytes, seq: int | None = None) -> Response:
        headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
        }
        if seq is not None:
            headers["X-Frame-Seq"] = str(seq)
        return Response(content=jpeg, media_type="image/jpeg", headers=headers)

    if row.jpeg[:2] == b"\xff\xd8":
        touch_live(spec)
        # Promote DISCOVERED→VIDEO_CONNECTED once; never open SQLite on every 40ms poll.
        if camera_id not in _snapshot_status_checked:
            with short_session() as db:
                camera = db.get(Camera, spec.id)
                if camera is not None:
                    if camera.status in {
                        CameraStatus.UNKNOWN.value, CameraStatus.DISCOVERED.value,
                    }:
                        persist_video(db, camera, row.url or None)
                    _snapshot_status_checked.add(camera_id)
        return _jpeg_response(row.jpeg, row.seq)
    touch_live(spec)
    if pumping_spec(camera_id) is not None:
        for _ in range(24):
            await asyncio.sleep(0.05)
            row = get_state(camera_id)
            if row.jpeg[:2] == b"\xff\xd8":
                return Response(
                    content=row.jpeg,
                    media_type="image/jpeg",
                    headers={
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                        "Pragma": "no-cache",
                        "X-Frame-Seq": str(row.seq),
                    },
                )
    grabbed = await snapshot_for_camera(
        spec.id, spec.ip, spec.username, spec.password, spec.rtsp_url, sdk_handle=spec.sdk_handle,
    )
    if not grabbed.get("ok"):
        raise HTTPException(409, grabbed.get("error") or "No live JPEG")
    if not grabbed.get("cached"):
        with short_session() as db:
            camera = db.get(Camera, spec.id)
            if camera is not None and camera.status in {
                CameraStatus.UNKNOWN.value, CameraStatus.DISCOVERED.value,
            }:
                persist_video(db, camera, grabbed.get("url"))
    return Response(
        content=grabbed["jpeg"],
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"},
    )


@app.post("/cameras/{camera_id}/live/watch")
def watch_camera_live(camera_id: int, _: User = Depends(require_media("cameras.view"))):
    spec = _camera_live_spec(camera_id)
    acquire_live(spec)
    return {"ok": True, "camera_id": camera_id, "viewers": viewers_for(camera_id)}


@app.post("/cameras/{camera_id}/live/unwatch")
def unwatch_camera_live(camera_id: int, _: User = Depends(require_media("cameras.view"))):
    release_live(camera_id)
    return {"ok": True, "camera_id": camera_id, "viewers": viewers_for(camera_id)}


@app.post("/cameras/{camera_id}/snapshot/capture")
async def capture_camera_snapshot(camera_id: int, db: Session = Depends(get_db), user: User = Depends(require("cameras.view"))):
    """Grab one live JPEG and save a car snapshot only when a vehicle/plate is present."""
    c = get_camera_or_404(db, camera_id)
    spec = _live_spec(c)
    touch_live(spec)
    grabbed = await snapshot_for_camera(
        spec.id, spec.ip, spec.username, spec.password, spec.rtsp_url, sdk_handle=spec.sdk_handle,
    )
    if not grabbed.get("ok"):
        raise HTTPException(409, grabbed.get("error") or "No live JPEG")
    jpeg = grabbed["jpeg"]
    native = await _native_capture_for_camera(c)
    alpr = await asyncio.to_thread(recognize_frame, jpeg, camera_label=f"cam-{c.id}-snap")
    local = local_from_fastalpr(alpr)
    fused = resolve_readings(
        native_plate=native.get("plate") or "",
        native_confidence=float(native.get("confidence") or 0),
        local_plate=local.get("plate") or "",
        local_confidence=float(local.get("confidence") or 0),
        mode=fusion_mode(c),
    )
    image_id = int(time.time() * 1000) % 2_000_000_000
    if fused.resolved_plate or native.get("have_vehicle"):
        capture = _capture_from_readings(native, local, fused, image_id=image_id)
        if native.get("have_vehicle"):
            capture["have_vehicle"] = True
        allowed, reason = should_persist_vehicle_capture(capture, coil_occupied=coil_watch.occupied(c.id), plate_policy=site_policy(db).get("plate_validation", "NONE"))
        if not allowed and native.get("have_vehicle"):
            capture = {
                "plate": "", "image_id": image_id, "have_vehicle": True,
                "score": 0, "source": native.get("source") or "camera",
            }
            allowed, reason = should_persist_vehicle_capture(capture, plate_policy=site_policy(db).get("plate_validation", "NONE"))
        if not allowed:
            raise HTTPException(409, f"No vehicle in frame ({reason}). Snapshot not saved.")
        row = persist_event(db, c, jpeg=jpeg, crop=_crop_from_alpr(alpr), capture=capture)
    else:
        raise HTTPException(409, "No vehicle or plate in frame. Snapshot not saved.")
    write_audit(db, user, "camera.snapshot", "camera", str(c.id), c.name)
    latest = row or latest_for_camera(db, c.id)
    return {
        "ok": True,
        "camera_id": c.id,
        "bytes": len(jpeg),
        "snapshot_url": f"/cameras/{c.id}/snapshot.jpg",
        "capture": capture_dict(latest) if latest else None,
        "plate": (latest.plate if latest else "") or fused.resolved_plate or "",
    }


@app.get("/cameras/{camera_id}/live.mjpeg")
async def camera_live(camera_id: int, role: str = "LIVE", _: User = Depends(require_media("cameras.view"))):
    spec = _camera_live_spec(camera_id)
    wanted = (role or "LIVE").upper()
    if wanted in {"MAIN", "EVIDENCE"}:
        from dataclasses import replace
        spec = replace(spec, live_role="MAIN")
    acquire_live(spec)
    try:
        for _ in range(80):
            if get_state(spec.id).jpeg[:2] == b"\xff\xd8":
                break
            await asyncio.sleep(0.05)
        if get_state(spec.id).jpeg[:2] != b"\xff\xd8":
            release_live(spec.id)
            raise HTTPException(409, "No live video yet. Connect the camera, then wait a second.")

        async def parts():
            try:
                async for part in mjpeg_from_cache(spec.id):
                    yield part
            finally:
                release_live(spec.id)

        return StreamingResponse(
            parts(),
            media_type=f"multipart/x-mixed-replace; boundary={MJPEG_BOUNDARY}",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except HTTPException:
        raise
    except Exception:
        release_live(spec.id)
        raise


@app.get("/cameras/{camera_id}/preview")
async def camera_preview(
    camera_id: int,
    run_alpr: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require("cameras.view")),
):
    c = get_camera_or_404(db, camera_id)
    cached = get_state(c.id)
    live = bool(cached.jpeg and cached.jpeg[:2] == b"\xff\xd8")
    grabbed = {"ok": live, "jpeg": cached.jpeg, "url_redacted": cached.url_redacted}
    if not live:
        grabbed = await live_snapshot(c)
        live = bool(grabbed.get("ok"))
    alpr = get_state(c.id).alpr or None
    native = await _native_capture_for_camera(c)
    if live and grabbed.get("jpeg") and should_run_local(
        native_plate=str(native.get("plate") or ""),
        native_confidence=float(native.get("confidence") or 0),
        explicit=run_alpr,
        native_plates=adapter_has_native_plates(c),
    ):
        alpr = await asyncio.to_thread(
            recognize_frame, grabbed["jpeg"], camera_label=f"cam-{c.id}-{c.ip_address}",
        )
        remember_alpr(c.id, alpr)
    plates = _plate_payload(c, native, alpr, db)
    return {
        "camera": camera_dict(c),
        "live": live,
        "error": None if live else (grabbed.get("error") or "No live JPEG"),
        "url_redacted": grabbed.get("url_redacted") or get_state(c.id).url_redacted,
        "snapshot_url": f"/cameras/{c.id}/snapshot.jpg",
        "live_url": f"/cameras/{c.id}/live.mjpeg",
        "live_source": cached.source or grabbed.get("source") or "",
        "live_fps": cached.fps,
        "alpr": alpr,
        "native": plates["native"],
        "local": plates["local"],
        "fusion": plates["fusion"],
        "resolved_plate": plates["resolved_plate"],
        "overlay": plates["overlay"],
        "last_car": plates["last_car"],
    }


@app.get("/cameras/{camera_id}/plates")
async def camera_plates(camera_id: int, db: Session = Depends(get_db), _: User = Depends(require("cameras.view"))):
    c = get_camera_or_404(db, camera_id)
    native = await _native_capture_for_camera(c)
    return _plate_payload(c, native, get_state(c.id).alpr or None, db)


@app.post("/cameras/{camera_id}/plate-corrections")
async def correct_camera_plate(
    camera_id: int,
    payload: PlateCorrection,
    db: Session = Depends(get_db),
    user: User = Depends(require_any("gates.open", "sessions.view", "cameras.connect")),
):
    """Operator confirms or corrects a held misread. Raw OCR stays on plate_raw."""
    from .core.plate import apply_site_plate, normalize_plate
    from .services.captures import apply_operator_plate_correction

    camera = get_camera_or_404(db, camera_id)
    row = db.get(VehicleCapture, int(payload.capture_id)) if payload.capture_id else latest_for_camera(db, camera.id)
    if row is None or row.camera_id != camera.id:
        raise HTTPException(404, "No vehicle capture to correct")
    original = row.plate_raw or row.plate
    chosen = normalize_plate(payload.plate) if payload.plate else normalize_plate(row.plate)
    if not chosen:
        raise HTTPException(400, "Corrected plate is empty")
    assessed = apply_site_plate(chosen, validation=str(getattr(settings, "plate_validation", "NONE") or "NONE"))
    apply_operator_plate_correction(row, chosen)
    write_audit(
        db, user, "plate.correct", "vehicle_capture", str(row.id),
        f"ocr={original} corrected={chosen} confirm={bool(payload.confirm)}",
    )
    db.commit()
    db.refresh(row)
    gate = db.get(Gate, camera.gate_id) if camera.gate_id else None
    side = (camera.lane_direction or "ENTRY").upper()
    if side == "ENTRY":
        from .application.live_parking import handle_live_entry
        result = await handle_live_entry(
            db, camera=camera, capture=row, gate=gate, source="operator-correction",
        )
    else:
        result = await handle_plate_event(
            db, plate=chosen, gate=gate, side=side, simulated=False,
            alpr=capture_dict(row), source="operator-correction", camera=camera,
        )
    last = capture_dict(row)
    remember_last_car(camera.id, last)
    return {
        "ok": True,
        "capture": last,
        "session": result.get("session"),
        "barrier_opened": result.get("barrier_opened"),
        "likely": assessed.get("likely"),
        "message": result.get("message") or "Plate confirmed",
    }


@app.get("/cameras/{camera_id}/presence")
async def get_camera_presence(camera_id: int, db: Session = Depends(get_db), _: User = Depends(require("cameras.view"))):
    c = get_camera_or_404(db, camera_id)
    gpio = None
    pins: list[dict] = []
    if c.sdk_handle is not None:
        pins = await HVXHostClient().scan_gpio(int(c.sdk_handle), _coil_indexes(c.id))
        gpio = next((row for row in pins if row.get("index") == coil_watch.learned_index(c.id)), None)
        if gpio is None:
            gpio = await HVXHostClient().read_gpio(int(c.sdk_handle), int(settings.coil_gpio_index))
    learned = coil_watch.learned_index(c.id)
    return {
        "camera_id": c.id,
        "occupied": coil_watch.occupied(c.id),
        "recent": coil_watch.recently_triggered(c.id),
        "gpio_index": learned if learned is not None else int(settings.coil_gpio_index),
        "learned_index": learned,
        "scanning": learned is None,
        "active_value": int(settings.coil_active_value),
        "gpio": gpio,
        "pins": pins,
        "last_car": get_state(c.id).last_car or None,
        "note": (
            "You do not need to know the GPIO number. SmartPark scans camera GPIO IN pins 1–7 "
            "(not the barrier output on 0) and locks onto the pin that changes when a car hits the loop. "
            "If the camera already snaps on the coil, that image callback is enough even without GPIO. "
            "POST this URL with occupied=true to simulate a car on the loop."
        ),
    }


@app.post("/cameras/{camera_id}/presence")
async def post_camera_presence(
    camera_id: int,
    occupied: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(require("cameras.connect")),
):
    c = get_camera_or_404(db, camera_id)
    edge = coil_watch.observe(c.id, occupied, source="api")
    write_audit(db, user, "camera.presence", "camera", str(c.id), f"occupied={occupied}")
    if edge.rising and c.sdk_handle is not None:
        await _read_presence_now(c.id, int(c.sdk_handle))
    elif edge.rising:
        jpeg = get_state(c.id).jpeg
        if jpeg[:2] != b"\xff\xd8":
            grabbed = await live_snapshot(c)
            jpeg = grabbed.get("jpeg") or b""
        await _run_local_alpr(db, c, jpeg, presence=True, force=True)
    return {**edge.as_dict(), "last_car": get_state(c.id).last_car or None}


async def _read_presence_now(camera_id: int, handle: int) -> None:
    coil_watch.mark_triggered(camera_id)
    hvx = HVXHostClient()
    try:
        await hvx.snapshot_trigger(handle)
    except Exception:
        pass
    await asyncio.sleep(0.2)
    await _drain_camera_events(camera_id, handle)
    with short_session() as db:
        camera = db.get(Camera, camera_id)
        if camera is None:
            return
        latest = latest_for_camera(db, camera.id)
        if latest and latest.plate:
            return
        jpeg = await hvx.live_jpeg(handle)
        if jpeg[:2] != b"\xff\xd8":
            jpeg = get_state(camera_id).jpeg
        await _run_local_alpr(db, camera, jpeg, presence=True, force=True)


@app.get("/media/{kind}/{name}")
def serve_media(kind: str, name: str, _: User = Depends(require("cameras.view"))):
    path = media_path(kind, name)
    if path is None:
        raise HTTPException(404, "Media not found")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/gates")
def list_gates(db: Session = Depends(get_db), _: User = Depends(require("gates.view"))):
    return [gate_dict(g) for g in db.scalars(select(Gate).order_by(Gate.id)).all()]


_last_image_id: dict[int, int] = {}


async def _persist_capture_event(db: Session, camera: Camera, capture: dict | None, jpeg: bytes, crop: bytes) -> dict | None:
    previous = latest_for_camera(db, camera.id)
    previous_id = previous.id if previous else None
    previous_plate = str(previous.plate or "") if previous else ""
    row = persist_event(
        db, camera, jpeg=jpeg, crop=crop, capture=capture,
        coil_occupied=coil_watch.occupied(camera.id),
    )
    if row is None:
        return capture_dict(previous) if previous else None
    latest = row or previous
    if latest:
        remember_last_car(camera.id, capture_dict(latest))
    if row is not None and row.id != previous_id:
        # Optional cloud second opinion: background task, never on the gate path.
        from .services import ai_review
        ai_review.schedule_capture_review(capture_dict(row), crop=crop, jpeg=jpeg, db=db)
    from .services.modules import is_enabled
    if not is_enabled("parking.sessions", db):
        return capture_dict(latest) if latest else None
    side = (camera.lane_direction or "ENTRY").upper()
    new_capture = bool(row and (row.id != previous_id or row.plate != previous_plate))
    entitlement = lookup_entitlement(db, row.plate, site_id=camera.site_id) if row and row.plate else None
    registered_auto = bool(
        entitlement and entitlement.registered and entitlement.auto_open
    )
    gate = None
    if camera.gate_id:
        gate = db.get(Gate, camera.gate_id)
    elif row and row.plate:
        # Auto-link only when the site has a single enabled lane (unambiguous).
        gates = list(db.scalars(select(Gate).where(Gate.enabled == True).order_by(Gate.id)).all())
        if len(gates) == 1:
            gate = gates[0]
            if camera.gate_id is None:
                camera.gate_id = gate.id
                db.commit()
    needs_session = False
    if row and row.plate and side == "ENTRY":
        from .services.parking_sessions import active_for_plate
        needs_session = active_for_plate(db, row.plate, site_id=camera.site_id) is None
    from .core.plate import apply_site_plate
    hold = bool((capture or {}).get("needs_review") or (capture or {}).get("pending_confirmation"))
    if row and row.plate:
        assessed = apply_site_plate(row.plate, validation=site_policy(db).get("plate_validation", "NONE"))
        if assessed.get("hold_for_operator"):
            hold = True
    if latest and hold:
        payload = capture_dict(latest)
        payload["pending_confirmation"] = True
        payload["needs_review"] = True
        remember_last_car(camera.id, payload)
        if isinstance(row.bbox, dict):
            row.bbox = {**row.bbox, "pending_confirmation": True, "needs_review": True}
            db.commit()
    # Plate-first: create/update parking sessions even when the camera has no Gate.
    # Barrier open still needs a gate; the session (plate + receipt token) does not.
    should_handle = bool(
        row and row.plate and not hold
        and (new_capture or side == "EXIT" or registered_auto or needs_session)
    )
    if should_handle:
        from .services.dedup import camera_events
        image_id = int(getattr(row, "image_id", 0) or 0)
        dedupe_id = image_id or int(row.id or 0)
        if camera_events.seen(camera_id=camera.id, plate=row.plate, image_id=dedupe_id):
            return capture_dict(latest) if latest else None
        try:
            source_name = str((capture or {}).get("source") or "camera")
            if side == "ENTRY":
                from .application.live_parking import handle_live_entry
                result = await handle_live_entry(
                    db, camera=camera, capture=row, gate=gate, source=source_name,
                )
            else:
                ent = lookup_entitlement(db, row.plate, site_id=camera.site_id)
                event_plate = ent.plate if ent.registered else row.plate
                result = await handle_plate_event(
                    db, plate=event_plate, gate=gate, side=side,
                    simulated=False, alpr=capture,
                    source=source_name,
                    camera=camera,
                )
            if result.get("session") and latest:
                session_id = (result["session"] or {}).get("id")
                if session_id:
                    session_row = db.get(ParkingSession, session_id)
                    if session_row is not None:
                        if not session_row.camera_id:
                            session_row.camera_id = camera.id
                        if gate is None:
                            camera.last_error = (
                                f"Session saved for {row.plate} (no Gate on camera — "
                                "assign a lane/gate to enable barrier control)."
                            )
                        elif camera.last_error and "no Gate" in (camera.last_error or ""):
                            camera.last_error = ""
                        db.commit()
        except Exception as exc:
            from .services.health import note_worker_failure
            from .services.queues import parking_outbox
            note_worker_failure("plate-event", str(exc))
            parking_outbox().enqueue("plate-event", {
                "plate": row.plate,
                "gate_id": gate.id if gate else None,
                "side": side,
                "camera_id": camera.id,
                "capture_id": row.id,
            })
    return capture_dict(latest) if latest else None


async def _drain_camera_events(camera_id: int, handle: int) -> None:
    hvx = HVXHostClient()
    try:
        events = await hvx.drain_events(handle)
    except Exception:
        events = None
    if events is None:
        try:
            state = await hvx.state(handle)
        except Exception:
            return
        capture = state.get("last_capture") if isinstance(state, dict) else None
        events = [capture] if isinstance(capture, dict) else []
    for capture in events:
        image_id = int(capture.get("image_id") or 0)
        plate = str(capture.get("plate") or "")
        from .services.dedup import camera_events
        if camera_events.seen(camera_id=camera_id, plate=plate, image_id=image_id):
            continue
        if image_id and _last_image_id.get(camera_id) == image_id:
            continue
        try:
            jpeg = await hvx.event_jpeg(handle, image_id=image_id or None)
            crop = await hvx.event_crop(handle, image_id=image_id or None)
        except Exception:
            continue
        # Do not inject event stills into live preview — that freezes the UI on the car snap.
        # Live frames come only from the media gateway producer (Net_GetJpgBuffer / RTSP / HTTP).
        native = native_from_sdk_capture(capture)
        # Only treat real vehicle signals as presence — not "any JPEG arrived".
        presence = bool(native.get("have_vehicle") or native.get("plate"))
        if presence:
            coil_watch.observe(camera_id, True, source="image-callback")
        with short_session() as db:
            row = db.get(Camera, camera_id)
            if row is None:
                return
            from .services import hybrid_fusion
            if presence and native.get("plate") and hybrid_fusion.routes_camera(row, db):
                # HYBRID with a live Recognition Worker: the native reading is one
                # candidate; the worker's FastALPR reading arrives via the outbox.
                # The coordinator persists exactly one fused capture per vehicle.
                await hybrid_fusion.offer_native(db, row, native, jpeg=jpeg, crop=crop, capture=capture)
                if image_id:
                    _last_image_id[camera_id] = image_id
                continue
            if presence:
                await _persist_capture_event(db, row, capture, jpeg, crop)
            from .recognition_worker import worker_owns_software_reads
            if not worker_owns_software_reads(camera_id) and should_run_local(
                native_plate=str(native.get("plate") or ""),
                native_confidence=float(native.get("confidence") or 0),
                presence=presence,
            ):
                frame = jpeg if jpeg[:2] == b"\xff\xd8" else crop
                await _run_local_alpr(
                    db, row, frame, native=native, presence=presence,
                    image_id=image_id, force=False,
                )
        if image_id:
            _last_image_id[camera_id] = image_id


async def _poll_coil_and_read(camera_id: int, handle: int) -> None:
    """Read camera GPIO IN (ground loop) and trigger a plate read on a rising edge."""
    hvx = HVXHostClient()
    active = int(getattr(settings, "coil_active_value", 1) or 1)
    rising = False
    last_edge = None
    pins = await hvx.scan_gpio(handle, _coil_indexes(camera_id))
    learned = coil_watch.learned_index(camera_id)
    for state in pins:
        if not state.get("ok"):
            continue
        index = int(state.get("index") or 0)
        if learned is not None and index != learned:
            continue
        occupied = int(state.get("value") or 0) == active
        edge = coil_watch.observe(
            camera_id, occupied, source="gpio", index=index, value=int(state.get("value") or 0),
        )
        last_edge = edge
        if edge.rising:
            rising = True
            break
    reports = await hvx.drain_reports(handle)
    if reports and not coil_watch.occupied(camera_id):
        last_edge = coil_watch.observe(camera_id, True, source="sdk-report")
        rising = rising or last_edge.rising
    if last_edge is not None:
        from .services.health import note_camera
        note_camera(
            camera_id,
            coil_occupied=last_edge.occupied,
            coil_source=last_edge.source,
            coil_index=last_edge.index,
        )
    if not rising:
        return
    await _read_presence_now(camera_id, handle)


async def _maybe_watch_local_alpr(camera_id: int, handle: int) -> None:
    """FastALPR samples the detect buffer. It never sits in the live-view decode loop."""
    from .recognition_worker import worker_owns_software_reads
    if worker_owns_software_reads(camera_id):
        return
    from .services.media_gateway import gateway
    watching = viewers_for(camera_id) > 0
    sample = gateway.peek_detect(camera_id) or gateway.peek_live(camera_id)
    if sample and sample.jpeg[:2] == b"\xff\xd8":
        jpeg = sample.jpeg
        fp = get_state(camera_id).fingerprint
    elif watching:
        jpeg = get_state(camera_id).jpeg
        if jpeg[:2] != b"\xff\xd8":
            return
        fp = get_state(camera_id).fingerprint
    else:
        from app.infrastructure.media.registry import mediamtx_detect_active
        if mediamtx_detect_active(camera_id):
            sample = gateway.peek_detect(camera_id)
            if not sample or sample.jpeg[:2] != b"\xff\xd8":
                return
            jpeg = sample.jpeg
            fp = hash(jpeg)
        elif not _local_alpr_due(camera_id):
            return
        else:
            try:
                jpeg = await HVXHostClient().live_jpeg(handle)
            except Exception:
                jpeg = b""
            if jpeg[:2] != b"\xff\xd8":
                return
            remember_frame(camera_id, jpeg, source="sdk")
            fp = get_state(camera_id).fingerprint
    if fp and _alpr_fp.get(camera_id) == fp:
        if not watching:
            _mark_local_alpr(camera_id)
        gateway.note_ai_sample(camera_id, dropped=True)
        return
    with short_session() as db:
        camera = db.get(Camera, camera_id)
        if camera is None:
            return
        native = await _native_capture_for_camera(camera)
        alpr = await _run_local_alpr(db, camera, jpeg, native=native, presence=True)
        if alpr is not None:
            _alpr_fp[camera_id] = fp
        elif not watching:
            _mark_local_alpr(camera_id)


async def _outbox_loop():
    from .services.queues import parking_outbox
    from .services.health import note_worker_failure

    while True:
        try:
            box = parking_outbox()
            for item in box.pending(limit=20):
                payload = item.get("payload") or {}
                from .services.events import recognition_from_outbox
                recognized = recognition_from_outbox(item)
                if recognized is None and item.get("kind") != "plate-event":
                    box.ack(item["id"])
                    continue
                # Durable idempotency: a crash after business processing but before
                # ACK redelivers the row; the processed mark (same SQLite file,
                # committed with the ACK) and the capture event_id (main DB) both
                # stop it from creating a second capture/session.
                event_key = str((recognized or {}).get("event_id") or payload.get("event_id") or "") or None
                if event_key and box.was_processed(event_key):
                    box.ack(item["id"])
                    continue
                try:
                    with short_session() as db:
                        if recognized is not None:
                            from .services.modules import is_enabled
                            if not is_enabled("recognition.alpr", db):
                                continue
                            camera = db.get(Camera, int(recognized.get("camera_id") or 0)) if recognized.get("camera_id") else None
                            if camera is None or not camera.enabled:
                                box.ack(item["id"], processed_key=event_key)
                                continue
                            if event_key and db.scalar(select(VehicleCapture.id).where(VehicleCapture.event_id == event_key)) is not None:
                                box.ack(item["id"], processed_key=event_key)
                                continue
                            jpeg = b""
                            crop = b""
                            reference = str(recognized.get("image_ref") or "")
                            if reference.startswith("/media/"):
                                pieces = reference.removeprefix("/media/").split("/")
                                if len(pieces) == 2:
                                    evidence = media_path(*pieces)
                                    if evidence is not None:
                                        jpeg = evidence.read_bytes()
                            crop_ref = str(recognized.get("plate_crop_ref") or "")
                            if crop_ref.startswith("/media/"):
                                pieces = crop_ref.removeprefix("/media/").split("/")
                                if len(pieces) == 2:
                                    evidence = media_path(*pieces)
                                    if evidence is not None:
                                        crop = evidence.read_bytes()
                            from .services import hybrid_fusion
                            if hybrid_fusion.routes_camera(camera, db):
                                await hybrid_fusion.offer_local(db, camera, recognized, jpeg=jpeg, crop=crop)
                                box.ack(item["id"], processed_key=event_key)
                                continue
                            if adapter_has_native_plates(camera):
                                from .services.ocr_policy import LOCAL_ONLY, camera_recognition_mode
                                if camera_recognition_mode(camera) != LOCAL_ONLY:
                                    # Native camera not fused by the worker path: the
                                    # in-process native/fusion loop stays authoritative.
                                    box.ack(item["id"], processed_key=event_key)
                                    continue
                            capture = {**recognized, "plate_raw": recognized.get("raw_plate"),
                                       "score": recognized.get("confidence") or recognized.get("recognition_confidence") or 0}
                            await _persist_capture_event(db, camera, capture, jpeg, b"")
                            box.ack(item["id"], processed_key=event_key)
                            continue
                        gate = db.get(Gate, int(payload.get("gate_id") or 0)) if payload.get("gate_id") else None
                        from .services.modules import is_enabled
                        if not is_enabled("parking.sessions", db):
                            # Keep pending business work for an explicit profile
                            # re-enable rather than processing it while disabled.
                            continue
                        camera = db.get(Camera, int(payload.get("camera_id") or 0)) if payload.get("camera_id") else None
                        if gate is None and camera is None and not payload.get("plate"):
                            box.ack(item["id"])
                            continue
                        side = str(payload.get("side") or "ENTRY").upper()
                        capture_id = int(payload.get("capture_id") or 0)
                        if side == "ENTRY" and camera is not None and capture_id:
                            capture_row = db.get(VehicleCapture, capture_id)
                            if capture_row is None or capture_row.camera_id != camera.id:
                                box.ack(item["id"])
                                continue
                            from .application.live_parking import handle_live_entry
                            await handle_live_entry(
                                db, camera=camera, capture=capture_row, gate=gate, source="outbox",
                            )
                        else:
                            # EXIT remains on the legacy orchestrator until the
                            # Phase-6 ExitLaneController replaces it.
                            await handle_plate_event(
                                db,
                                plate=str(payload.get("plate") or ""),
                                gate=gate,
                                side=side,
                                simulated=False,
                                source="outbox",
                                camera=camera,
                            )
                    box.ack(item["id"], processed_key=event_key)
                except Exception as exc:
                    box.note_failure()
                    note_worker_failure("outbox", str(exc))
                    break
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(2.0)


async def _fusion_flush_loop():
    """Decide hybrid candidates whose counterpart never arrived (bounded wait)."""
    from .services import hybrid_fusion
    from .services.health import note_worker_failure

    while True:
        try:
            await hybrid_fusion.flush(short_session)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            note_worker_failure("hybrid-fusion", str(exc))
        await asyncio.sleep(0.5)


async def _onvif_capture(camera_id: int, capture: dict, jpeg: bytes) -> None:
    """Profile M plate metadata enters the same path as an HVX native read."""
    from .services.dedup import camera_events
    from .services import hybrid_fusion

    plate = str(capture.get("plate") or "")
    image_id = int(capture.get("image_id") or 0)
    if camera_events.seen(camera_id=camera_id, plate=plate, image_id=image_id):
        return
    native = native_from_sdk_capture(capture)
    if not native.get("plate"):
        return
    coil_watch.observe(camera_id, True, source="onvif-metadata")
    with short_session() as db:
        row = db.get(Camera, camera_id)
        if row is None or not row.enabled:
            return
        if hybrid_fusion.routes_camera(row, db):
            await hybrid_fusion.offer_native(db, row, native, jpeg=jpeg, crop=b"", capture=capture)
            return
        await _persist_capture_event(db, row, capture, jpeg, b"")


async def _onvif_events_loop():
    """Keep one Profile M poller per ONVIF camera that advertises plate events."""
    from .services import onvif_runtime
    from .services.health import note_worker_failure

    while True:
        try:
            await onvif_runtime.reconcile(short_session)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            note_worker_failure("onvif-events", str(exc))
        await asyncio.sleep(5.0)


async def _payments_reconcile_loop():
    """Settle PENDING external intents whose webhook never arrived.

    Runs only while payments.core is enabled and an external provider is the
    active mobile provider; an LPR-only site never touches provider code.
    """
    from .services import mobile_payments
    from .services.health import note_worker_failure
    from .services.modules import is_enabled

    while True:
        delay = max(5.0, float(settings.payments_reconcile_seconds or 60.0))
        try:
            with short_session() as db:
                enabled = is_enabled("payments.core", db)
            if enabled and mobile_payments.active_mobile_provider_id() in mobile_payments.external_provider_ids():
                await mobile_payments.reconcile_pending(SessionLocal)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            note_worker_failure("payments-reconcile", str(exc))
        await asyncio.sleep(delay)


async def _hvx_watch_loop():
    from .services.circuit import breaker
    from .services.runtime import mark_hardware

    hvx_breaker = breaker("hvx-host")
    while True:
        try:
            info = await asyncio.wait_for(HVXHostClient().info(), timeout=1.0)
            ok = bool(info)
            if ok:
                hvx_breaker.success()
            else:
                hvx_breaker.failure()
            mark_hardware(ok)
        except asyncio.CancelledError:
            raise
        except Exception:
            hvx_breaker.failure()
            mark_hardware(False)
        await asyncio.sleep(5.0)


async def _maybe_local_ipcam_alpr(camera_id: int) -> None:
    """Periodic FastALPR for cameras that have no onboard plate engine."""
    from .recognition_worker import worker_owns_software_reads
    if worker_owns_software_reads(camera_id):
        return
    if not _local_alpr_ready(camera_id):
        return
    from .services.media_gateway import gateway
    sample = gateway.peek_detect(camera_id) or gateway.peek_live(camera_id)
    jpeg = sample.jpeg if sample else get_state(camera_id).jpeg
    if jpeg[:2] != b"\xff\xd8":
        from app.infrastructure.media.registry import mediamtx_detect_active
        if mediamtx_detect_active(camera_id):
            from app.services.mediamtx_detect import ensure_detect_consumer
            with short_session() as db:
                camera = db.get(Camera, camera_id)
                if camera is None or adapter_has_native_plates(camera):
                    return
                ensure_detect_consumer(_live_spec(camera, need_detect=True))
            return
        with short_session() as db:
            camera = db.get(Camera, camera_id)
            if camera is None or adapter_has_native_plates(camera):
                return
            acquire_detect(_live_spec(camera, need_detect=True))
        return
    with short_session() as db:
        camera = db.get(Camera, camera_id)
        if camera is None or adapter_has_native_plates(camera):
            return
        fp = get_state(camera_id).fingerprint
        if fp and _alpr_fp.get(camera_id) == fp:
            gateway.note_ai_sample(camera_id, dropped=True)
            return
        alpr = await _run_local_alpr(db, camera, jpeg, presence=True, force=True)
        if alpr is not None:
            _alpr_fp[camera_id] = fp


async def _camera_event_loop():
    """Pull QY plate callbacks and FastALPR frames so cars are not missed while the UI is idle."""
    from .services.circuit import breaker
    from .services.health import note_camera, note_worker_failure
    from .config import settings as cfg

    hvx_breaker = breaker("hvx-host")
    poll = float(getattr(cfg, "camera_event_poll_seconds", 0.25) or 0.25)
    while True:
        try:
            with short_session() as db:
                from .services.modules import is_enabled
                rows = list(db.scalars(select(Camera).where(Camera.enabled == True)).all()) if is_enabled("recognition.alpr", db) else []
                hvx_specs = [
                    (int(c.id), int(c.sdk_handle))
                    for c in rows
                    if c.sdk_handle is not None
                ]
                ipcam_ids = [
                    int(c.id) for c in rows
                    if c.sdk_handle is None and c.status in {
                        CameraStatus.VIDEO_CONNECTED.value, CameraStatus.SDK_CONNECTED.value,
                    }
                ]
            started = time.perf_counter()
            if hvx_breaker.allow():
                for camera_id, handle in hvx_specs:
                    try:
                        await _drain_camera_events(camera_id, handle)
                        await _poll_coil_and_read(camera_id, handle)
                        await _maybe_watch_local_alpr(camera_id, handle)
                        hvx_breaker.success()
                        note_camera(camera_id, sdk_callback="ok", last_event_at=time.time())
                    except Exception as exc:
                        hvx_breaker.failure()
                        note_worker_failure("camera-events", str(exc))
                        note_camera(camera_id, sdk_callback="error")
            for camera_id in ipcam_ids:
                try:
                    await _maybe_local_ipcam_alpr(camera_id)
                    note_camera(camera_id, sdk_callback="local-alpr", last_event_at=time.time())
                except Exception as exc:
                    note_worker_failure("camera-events", str(exc))
                    note_camera(camera_id, sdk_callback="error")
            latency_ms = int((time.perf_counter() - started) * 1000)
            for camera_id, _handle in hvx_specs:
                note_camera(camera_id, event_latency_ms=latency_ms)
            for camera_id in ipcam_ids:
                note_camera(camera_id, event_latency_ms=latency_ms)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            note_worker_failure("camera-events", str(exc))
            await asyncio.sleep(1.0)
            continue
        await asyncio.sleep(poll)


async def _ingest_camera_event(db: Session, camera: Camera) -> dict | None:
    if camera.sdk_handle is not None:
        await _drain_camera_events(int(camera.id), int(camera.sdk_handle))
    latest = latest_for_camera(db, camera.id)
    return capture_dict(latest) if latest else None


def _side_payload(camera: Camera | None, last: dict | None) -> dict | None:
    if camera is None:
        return None
    snap = (last or {}).get("snapshot_url")
    return {
        "camera": camera_dict(camera),
        "snapshot_url": snap,
        "last": last,
    }


async def _lane_view_dict(db: Session, gate: Gate) -> dict:
    by_side: dict[str, Camera] = {}
    extras: list[Camera] = []
    for camera in gate.cameras or []:
        side = (camera.lane_direction or "").upper()
        if side in {"ENTRY", "EXIT"} and side not in by_side:
            by_side[side] = camera
        else:
            extras.append(camera)

    def last_for(camera: Camera | None) -> dict | None:
        if camera is None:
            return None
        latest = latest_for_camera(db, camera.id)
        return capture_dict(latest) if latest else None

    entry_last = last_for(by_side.get("ENTRY"))
    exit_last = last_for(by_side.get("EXIT"))
    sides = []
    if "ENTRY" in by_side:
        sides.append({"side": "ENTRY", **_side_payload(by_side["ENTRY"], entry_last)})
    if "EXIT" in by_side:
        sides.append({"side": "EXIT", **_side_payload(by_side["EXIT"], exit_last)})
    for camera in extras:
        last = last_for(camera)
        sides.append({"side": (camera.lane_direction or "OTHER").upper(), **_side_payload(camera, last)})
    recent = [capture_dict(row) for row in list_captures(db, gate_id=gate.id, limit=16)]
    return {
        "gate": gate_dict(gate),
        "sides": sides,
        "entry": _side_payload(by_side.get("ENTRY"), entry_last),
        "exit": _side_payload(by_side.get("EXIT"), exit_last),
        "recent": recent,
    }


@app.get("/lanes")
def list_lanes(db: Session = Depends(get_db), _: User = Depends(require("cameras.view"))):
    return [gate_dict(g) for g in db.scalars(select(Gate).order_by(Gate.id)).all()]


@app.get("/lanes/overview")
async def lanes_overview(db: Session = Depends(get_db), _: User = Depends(require("cameras.view"))):
    gates = db.scalars(select(Gate).order_by(Gate.id)).all()
    lanes = [await _lane_view_dict(db, gate) for gate in gates]
    return {"lanes": lanes}


@app.get("/lanes/{gate_id}/view")
async def lane_view(gate_id: int, db: Session = Depends(get_db), _: User = Depends(require("cameras.view"))):
    gate = get_gate_or_404(db, gate_id)
    return await _lane_view_dict(db, gate)


@app.get("/captures")
def get_captures(
    gate_id: int | None = None,
    limit: int = 20,
    db: Session = Depends(get_db),
    _: User = Depends(require("cameras.view")),
):
    return [capture_dict(row) for row in list_captures(db, gate_id=gate_id, limit=limit)]


@app.get("/gates/{gate_id}")
def get_gate(gate_id: int, db: Session = Depends(get_db), _: User = Depends(require("gates.view"))):
    return gate_dict(get_gate_or_404(db, gate_id))


@app.post("/gates")
def create_gate(payload: GateCreate, db: Session = Depends(get_db), user: User = Depends(require("gates.manage"))):
    g = Gate(name=payload.name, mode=validate_gate_mode(payload.mode), enabled=payload.enabled)
    db.add(g)
    commit_or_conflict(db, "A gate with that name already exists")
    db.refresh(g)
    write_audit(db, user, "gate.create", "gate", str(g.id), g.name)
    return gate_dict(g)


@app.patch("/gates/{gate_id}")
def update_gate(gate_id: int, payload: GateUpdate, db: Session = Depends(get_db), user: User = Depends(require("gates.manage"))):
    g = get_gate_or_404(db, gate_id)
    data = payload.model_dump(exclude_unset=True)
    if "mode" in data and data["mode"] is not None:
        data["mode"] = validate_gate_mode(data["mode"])
    for k, v in data.items():
        setattr(g, k, v)
    commit_or_conflict(db, "A gate with that name already exists")
    db.refresh(g)
    write_audit(db, user, "gate.update", "gate", str(g.id), "Gate settings updated")
    return gate_dict(g)


@app.delete("/gates/{gate_id}")
def delete_gate(gate_id: int, db: Session = Depends(get_db), user: User = Depends(require("gates.manage"))):
    g = get_gate_or_404(db, gate_id)
    name = g.name
    for camera in db.scalars(select(Camera).where(Camera.gate_id == gate_id)).all():
        camera.gate_id = None
    db.delete(g)
    db.commit()
    write_audit(db, user, "gate.delete", "gate", str(gate_id), f"Deleted {name}")
    return {"ok": True}


@app.post("/gates/{gate_id}/open")
async def gate_open(gate_id: int, payload: ManualGateCommand, db: Session = Depends(get_db), user: User = Depends(require("gates.open"))):
    g = get_gate_or_404(db, gate_id)
    cameras = list(g.cameras or [])
    result = await controller().open(
        g, cameras, payload.reason,
        side=payload.side, dry_run=payload.dry_run, led_text=payload.led_text, action=payload.action or "open",
    )
    if result.ok and not result.simulated and not payload.dry_run:
        g.physical_control_verified = True
    write_audit(db, user, "gate.open", "gate", str(g.id), result.message)
    db.commit()
    if not result.ok:
        raise HTTPException(409, result.message)
    return result.__dict__


@app.post("/cameras/{camera_id}/led")
async def camera_led(camera_id: int, payload: LedWrite, db: Session = Depends(get_db), user: User = Depends(require("gates.open"))):
    camera = db.get(Camera, camera_id)
    if not camera:
        raise HTTPException(404, "Camera not found")
    result = await send_led_text(camera.display_ip or "", payload.text, dry_run=payload.dry_run)
    write_audit(db, user, "led.write", "camera", str(camera.id), result.message)
    db.commit()
    if not result.ok:
        raise HTTPException(409, result.message)
    return result.__dict__


@app.post("/cameras/{camera_id}/barrier/open")
async def camera_barrier_open(camera_id: int, payload: ManualGateCommand, db: Session = Depends(get_db), user: User = Depends(require("gates.open"))):
    camera = db.get(Camera, camera_id)
    if not camera:
        raise HTTPException(404, "Camera not found")
    gate = camera.gate or Gate(id=0, name=camera.name)
    result = await controller().open(
        gate, [camera], payload.reason,
        dry_run=payload.dry_run, led_text=payload.led_text, action=payload.action or "open",
    )
    write_audit(db, user, "barrier.open", "camera", str(camera.id), result.message)
    db.commit()
    if not result.ok:
        raise HTTPException(409, result.message)
    return result.__dict__


def tariff_dict(row: Tariff) -> dict:
    from .services.fee_engine import tariff_editor
    return {
        "id": row.id, "name": row.name, "car_type": row.car_type, "currency": row.currency,
        "source": row.source, "rules": row.rules, "active": row.active,
        "editor": tariff_editor(row),
    }


def session_dict(row: ParkingSession) -> dict:
    return sim_session_dict(row)


@app.get("/fees/tariff")
def get_fee_tariff(db: Session = Depends(get_db), _: User = Depends(require("fees.view"))):
    row = ensure_car1_tariff(db)
    return tariff_dict(row)


@app.patch("/fees/tariff")
def patch_fee_tariff(
    payload: TariffEditorUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_any("fees.manage", "settings.manage")),
):
    from .services.fee_engine import apply_tariff_editor
    try:
        row = apply_tariff_editor(db, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    write_audit(db, user, "tariff.update", "tariff", str(row.id), row.name)
    db.commit()
    return tariff_dict(row)


@app.post("/fees/quote")
def fee_quote(payload: FeeQuoteRequest, db: Session = Depends(get_db), _: User = Depends(require("fees.view"))):
    rules = load_active_rules(db, payload.car_type or "Car1")
    exit_at = payload.exit_time or datetime.now(timezone.utc)
    result = calculate_car1_fee(payload.entry_time, exit_at, rules)
    return result.__dict__


@app.post("/sessions")
def open_session(payload: SessionCreate, db: Session = Depends(get_db), user: User = Depends(require("fees.view"))):
    plate = payload.plate.strip().upper()
    if not plate:
        raise HTTPException(400, "Plate is required")
    tariff = ensure_car1_tariff(db)
    camera = db.get(Camera, payload.camera_id) if payload.camera_id else None
    row = ParkingSession(
        plate=plate,
        gate_id=payload.gate_id or (camera.gate_id if camera else None),
        camera_id=payload.camera_id,
        lane_direction=(camera.lane_direction if camera else "ENTRY"),
        car_type=payload.car_type or "Car1",
        currency=tariff.currency,
        tariff_rules=tariff.rules or {},
        status="OPEN",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    write_audit(db, user, "session.entry", "parking_session", str(row.id), plate)
    db.commit()
    return session_dict(row)


@app.post("/sessions/{session_id}/exit")
def close_session(session_id: int, db: Session = Depends(get_db), user: User = Depends(require("fees.view"))):
    row = db.get(ParkingSession, session_id)
    if not row:
        raise HTTPException(404, "Session not found")
    row.exit_time = datetime.now(timezone.utc)
    result = calculate_car1_fee(row.entry_time, row.exit_time, row.tariff_rules or load_active_rules(db, row.car_type))
    row.amount_due = result.due
    row.currency = result.currency
    row.breakdown = result.breakdown
    row.status = "CLOSED"
    db.commit()
    write_audit(db, user, "session.exit", "parking_session", str(row.id), f"{row.plate} due={result.due}")
    db.commit()
    return {**session_dict(row), "fee": result.__dict__}


@app.get("/sessions")
def list_sessions(db: Session = Depends(get_db), _: User = Depends(require_any("sessions.view", "fees.view", "kiosk.use"))):
    return [session_dict(row) for row in db.scalars(select(ParkingSession).order_by(ParkingSession.id.desc()).limit(100)).all()]


@app.get("/sessions/{session_id}/receipt")
def get_session_receipt(session_id: int, db: Session = Depends(get_db), _: User = Depends(require_any("sessions.view", "fees.view", "kiosk.use"))):
    row = db.get(ParkingSession, session_id)
    if not row:
        raise HTTPException(404, "Session not found")
    slip = db.scalar(select(Receipt).where(Receipt.session_id == session_id).order_by(Receipt.id.desc()))
    if slip is None:
        raise HTTPException(404, "No receipt for this session")
    return receipt_dict(slip)


@app.get("/sessions/{session_id}/receipt.txt")
def get_session_receipt_text(session_id: int, db: Session = Depends(get_db), _: User = Depends(require_any("sessions.view", "fees.view", "kiosk.use"))):
    row = db.get(ParkingSession, session_id)
    if not row:
        raise HTTPException(404, "Session not found")
    slip = db.scalar(select(Receipt).where(Receipt.session_id == session_id).order_by(Receipt.id.desc()))
    if slip is None:
        raise HTTPException(404, "No receipt for this session")
    filename = f"parking-{''.join(ch for ch in (row.plate or str(session_id)) if ch.isalnum()) or session_id}.txt"
    return Response(
        content=slip.body_text or "",
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/sessions/{session_id}/receipt")
async def reprint_session_receipt(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_any("sessions.view", "payments.create", "kiosk.use", "simulation.run")),
):
    row = db.get(ParkingSession, session_id)
    if not row:
        raise HTTPException(404, "Session not found")
    gate = db.get(Gate, row.gate_id) if row.gate_id else None
    cfg = parking_settings(db)
    issued = await issue_receipt(
        db, row, gate=gate,
        adapter_id=cfg.get("printer_adapter"),
        printer_name=cfg.get("printer_name") or "",
    )
    write_audit(db, user, "receipt.print", "parking_session", str(row.id), row.plate)
    db.commit()
    return issued


@app.get("/settings/parking")
def get_parking_settings(db: Session = Depends(get_db), _: User = Depends(require("simulation.run"))):
    return parking_settings(db)


@app.patch("/settings/parking")
def patch_parking_settings(payload: ParkingSettingsUpdate, db: Session = Depends(get_db), user: User = Depends(require("simulation.run"))):
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    saved = save_parking_settings(db, data)
    write_audit(db, user, "settings.parking", "site", "parking", str(saved))
    db.commit()
    return saved


@app.get("/settings/site")
def get_site_policy(db: Session = Depends(get_db), _: User = Depends(require_any("dashboard.view", "fees.view", "simulation.run"))):
    from .services.site_policy import site_policy
    return site_policy(db)


@app.patch("/settings/site")
def patch_site_policy(payload: SitePolicyUpdate, db: Session = Depends(get_db), user: User = Depends(require("simulation.run"))):
    from .services.site_policy import save_site_policy
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    saved = save_site_policy(db, data)
    write_audit(db, user, "settings.site", "site", "site", str(saved.get("timezone")))
    return saved


@app.get("/settings/migration")
def get_migration_flags(db: Session = Depends(get_db), _: User = Depends(require("hardware.view"))):
    from .services.flags import flags as migration_flags
    return migration_flags(db)


@app.patch("/settings/migration")
def patch_migration_flags(payload: MigrationFlagsUpdate, db: Session = Depends(get_db), user: User = Depends(require("hardware.view"))):
    from .services.flags import save_flags
    saved = save_flags(db, payload.model_dump(exclude_unset=True))
    write_audit(db, user, "settings.migration", "site", "migration", saved.get("live_view_provider") or "")
    return saved


@app.get("/lanes/status")
def lanes_status(db: Session = Depends(get_db), _: User = Depends(require_any("dashboard.view", "cameras.view", "gates.view"))):
    from .services.lane_status import lane_operator_status
    return lane_operator_status(db)


@app.post("/cameras/onboard/probe")
async def cameras_onboard_probe(payload: CameraOnboardProbe, _: User = Depends(require("cameras.view"))):
    from .services.camera_onboard import probe_connection
    return await probe_connection(
        ip=payload.ip_address,
        username=payload.username,
        password=payload.password,
        port=payload.sdk_port,
        rtsp_url=payload.rtsp_url,
    )


@app.post("/cameras/onboard/test")
async def cameras_onboard_test(payload: CameraOnboardTest, _: User = Depends(require("cameras.connect"))):
    from .services.camera_onboard import test_path
    return await test_path(
        ip=payload.ip_address,
        username=payload.username,
        password=payload.password,
        adapter_id=payload.adapter_id,
        rtsp_url=payload.rtsp_url,
        port=payload.sdk_port,
        duration_seconds=payload.duration_seconds,
    )


@app.post("/sim/entry")
async def sim_entry(payload: SimEntryRequest, db: Session = Depends(get_db), user: User = Depends(require("simulation.run"))):
    gate = get_gate_or_404(db, payload.gate_id)
    try:
        result = await handle_plate_event(
            db, plate=payload.plate, gate=gate, side=payload.side, simulated=True, source="simulation",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    write_audit(db, user, "sim.entry", "parking_session", str((result.get("session") or {}).get("id") or ""), payload.plate)
    db.commit()
    return result


@app.post("/sim/capture")
async def sim_capture(
    gate_id: int = Form(...),
    side: str = Form("ENTRY"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require("simulation.run")),
):
    jpeg = await file.read()
    if jpeg[:2] != b"\xff\xd8":
        try:
            from io import BytesIO
            from PIL import Image, ImageOps
            image = ImageOps.exif_transpose(Image.open(BytesIO(jpeg))).convert("RGB")
            converted = BytesIO()
            image.save(converted, format="JPEG", quality=92)
            jpeg = converted.getvalue()
        except Exception:
            jpeg = b""
    if jpeg[:2] != b"\xff\xd8":
        raise HTTPException(400, "Upload a JPEG or PNG photo of the car")
    alpr = recognize_frame(jpeg, camera_label=file.filename or "sim-upload")
    best = (alpr or {}).get("best") or {}
    plate = str(best.get("plate") or "").strip()
    if not plate:
        reason = alpr.get("detail") or "FastALPR did not read a number plate in that photo"
        raise HTTPException(
            409,
            f"{reason}. Simulation does not use the cameras — FastALPR reads the plate from the uploaded photo on this PC.",
        )
    gate = get_gate_or_404(db, gate_id)
    camera = None
    want = (side or "ENTRY").upper()
    for row in gate.cameras or []:
        if (row.lane_direction or "").upper() == want:
            camera = row
            break
    stored = None
    if camera is not None:
        box = best.get("bbox") if isinstance(best.get("bbox"), dict) else None
        stored = persist_event(
            db, camera, jpeg=jpeg, crop=_crop_from_alpr(alpr),
            capture={
                "plate": plate,
                "plate_raw": str(best.get("plate_raw") or plate),
                "score": float(best.get("confidence") or 0),
                "bbox": box,
                "source": "fastalpr",
                "plate_crop_path": best.get("plate_crop_path"),
                "image_id": int(time.time() * 1000) % 2_000_000_000,
            },
        )
        if stored is not None:
            remember_last_car(camera.id, capture_dict(stored))
    try:
        result = await handle_plate_event(
            db, plate=plate, gate=gate, side=side, simulated=True, alpr=alpr,
            source="fastalpr-upload", camera=camera,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    write_audit(db, user, "sim.capture", "parking_session", str((result.get("session") or {}).get("id") or ""), f"{plate} {side}")
    db.commit()
    if stored is not None:
        info = capture_dict(stored)
        session = dict(result.get("session") or {})
        session["snapshot_url"] = session.get("snapshot_url") or info.get("snapshot_url")
        session["crop_url"] = session.get("crop_url") or info.get("crop_url")
        session["plate_confidence"] = session.get("plate_confidence") or info.get("confidence")
        result["session"] = session
        result["capture"] = info
        result["last_car"] = info
    if not result.get("ok") and not result.get("pay_required"):
        raise HTTPException(409, result.get("message") or "Capture failed")
    return result


@app.post("/sim/sessions/{session_id}/receipt-taken")
async def sim_receipt_taken(session_id: int, db: Session = Depends(get_db), user: User = Depends(require_any("simulation.run", "gates.open"))):
    row = db.get(ParkingSession, session_id)
    if not row:
        raise HTTPException(404, "Session not found")
    taken = await take_receipt(db, row, reason=f"receipt taken {row.plate}")
    write_audit(db, user, "sim.receipt_taken", "parking_session", str(row.id), row.plate)
    db.commit()
    return taken


@app.post("/sessions/{session_id}/receipt-taken")
async def session_receipt_taken(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require("gates.open")),
):
    """Confirm a real entry ticket removal through the authoritative controller.

    Generic printers without a taken sensor fail closed. The simulation endpoint
    remains separate and is never used as production receipt authority.
    """
    from app.application.entry_lane import EntryLaneController, policy_from_parking_settings
    from app.domain.receipt_engine import InvalidPrintJob
    from app.infrastructure.hardware.receipt_printers import receipt_printer_for

    row = db.get(ParkingSession, session_id)
    if row is None:
        raise HTTPException(404, "Session not found")
    cfg = parking_settings(db)
    controller = EntryLaneController(
        printer=receipt_printer_for(
            str(cfg.get("printer_adapter") or settings.printer_adapter or "simulated"),
            str(cfg.get("printer_name") or settings.printer_name or ""),
        )
    )
    gate = db.get(Gate, row.gate_id) if row.gate_id else None
    camera = db.get(Camera, row.camera_id) if row.camera_id else None
    try:
        result = await controller.confirm_receipt_taken(
            db,
            row,
            policy=policy_from_parking_settings(cfg),
            gate=gate,
            camera=camera,
            sensor_confirmed=False,
        )
    except InvalidPrintJob as exc:
        raise HTTPException(409, str(exc)) from exc
    write_audit(db, user, "receipt.taken", "parking_session", str(row.id), "sensor-confirmed path")
    return result


@app.post("/sessions/{session_id}/correct-plate")
async def correct_session_plate(
    session_id: int,
    payload: PlateCorrection,
    db: Session = Depends(get_db),
    user: User = Depends(require_any("gates.open", "sessions.view", "simulation.run")),
):
    from .core.plate import normalize_plate
    from .services.captures import apply_operator_plate_correction

    row = db.get(ParkingSession, session_id)
    if row is None:
        raise HTTPException(404, "Session not found")
    chosen = normalize_plate(payload.plate)
    if not chosen:
        raise HTTPException(400, "Corrected plate is empty")
    original = row.plate
    row.plate = chosen
    capture = None
    if row.camera_id:
        capture = latest_for_camera(db, row.camera_id)
        if capture and (not capture.plate or capture.plate == original):
            apply_operator_plate_correction(capture, chosen)
    write_audit(db, user, "plate.correct", "parking_session", str(row.id), f"ocr={original} corrected={chosen}")
    db.commit()
    return {"ok": True, "session": sim_session_dict(row), "capture": capture_dict(capture) if capture else None}


@app.post("/sim/sessions/{session_id}/pay")
def sim_pay(session_id: int, db: Session = Depends(get_db), user: User = Depends(require("simulation.run"))):
    row = db.get(ParkingSession, session_id)
    if not row:
        raise HTTPException(404, "Session not found")
    try:
        row = mark_paid(db, row, operator_id=user.id, method="KIOSK_CASH")
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    write_audit(db, user, "sim.pay", "parking_session", str(row.id), f"{row.plate} {row.amount_paid}")
    db.commit()
    return sim_session_dict(row)


@app.post("/sessions/{session_id}/pay")
def confirm_session_payment(
    session_id: int,
    payload: PaymentConfirm = PaymentConfirm(),
    db: Session = Depends(get_db),
    user: User = Depends(require_any("payments.create", "kiosk.use", "simulation.run")),
):
    row = db.get(ParkingSession, session_id)
    if not row:
        raise HTTPException(404, "Session not found")
    method = payload.method or "KIOSK_CASH"
    try:
        row = mark_paid(db, row, operator_id=user.id, method=method)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    write_audit(db, user, "payments.create", "parking_session", str(row.id), f"{row.plate} {row.amount_paid} {method}")
    db.commit()
    return sim_session_dict(row)


@app.get("/payments")
def list_payments(db: Session = Depends(get_db), _: User = Depends(require_any("payments.view", "fees.view", "kiosk.use"))):
    return [transaction_dict(row) for row in list_transactions(db)]


@app.post("/payments/mobile-money/webhook")
async def mobile_money_webhook(request: Request, db: Session = Depends(get_db)):
    """Verified aggregator callback only. A redirect/success URL must not mark paid."""
    from .infrastructure.payments import payment_provider_for
    from .infrastructure.payments.ledger import record_succeeded_payment, transaction_dict as txn_dict

    raw = await request.body()
    signature = request.headers.get("x-signature") or request.headers.get("x-smartpark-signature") or ""
    try:
        import json
        payload = json.loads(raw.decode("utf-8") or "{}") if raw else {}
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    provider = payment_provider_for("mobile_money")
    verified = await provider.verify_callback({
        **payload,
        "signature": signature or payload.get("signature") or "",
        "raw_body": raw,
        "x_signature": signature,
    })
    if not verified.get("verified"):
        raise HTTPException(400, verified.get("error") or "Unverified webhook")
    session_id = int(verified.get("session_id") or payload.get("session_id") or 0)
    row = db.get(ParkingSession, session_id) if session_id else None
    if row is None:
        raise HTTPException(404, "Session not found")
    amount = float(verified.get("amount") or payload.get("amount") or row.amount_due or 0)
    recorded = record_succeeded_payment(
        db, row,
        amount=amount,
        method="MOBILE_MONEY",
        provider_id="mobile_money",
        idempotency_key=str(verified.get("provider_ref") or payload.get("provider_ref") or f"mm:{row.id}:{amount}"),
    )
    write_audit(db, None, "payments.webhook", "parking_session", str(row.id), f"mobile_money {amount}")
    return {
        "ok": True,
        "verified": True,
        "session": sim_session_dict(recorded["session"]),
        "transaction": txn_dict(recorded["transaction"]),
        "duplicate": bool(recorded.get("duplicate")),
    }


@app.post("/sim/exit")
async def sim_exit_ep(payload: SimExitRequest, db: Session = Depends(get_db), user: User = Depends(require("simulation.run"))):
    gate = get_gate_or_404(db, payload.gate_id)
    result = await handle_exit(db, plate=payload.plate, gate=gate, side=payload.side)
    write_audit(db, user, "sim.exit", "gate", str(gate.id), payload.plate)
    db.commit()
    if not result.get("ok") and not result.get("pay_required"):
        raise HTTPException(409, result.get("message") or "Exit failed")
    return result


@app.get("/p/{token}", include_in_schema=False)
def public_receipt(token: str, db: Session = Depends(get_db)):
    from app.services.public_pay import public_session_payload, session_by_public_token

    row = session_by_public_token(db, token)
    if not row:
        raise HTTPException(404, "Receipt not found")
    data = public_session_payload(db, row)
    external_pay = str(data.get("pay_endpoint") or "").startswith("/api/public/")
    remaining = float(data["amount_remaining"])
    paid = float(data["amount_paid"])
    due = float(data["amount_due"])
    currency = data["currency"]
    entry = row.entry_time.strftime("%d %b %Y %H:%M") if row.entry_time else "—"
    status_label = "PAID" if data["paid"] else data["status"]
    pay_disabled = "disabled" if not data.get("payable") else ""
    stay = data.get("duration_label") or "—"
    image_note = data.get("image_note") or ""
    snapshot = data.get("snapshot_url") or ""
    crop = data.get("crop_url") or ""
    photo_block = ""
    if snapshot:
        photo_block = f'<p><img class="car" src="{snapshot}" alt="Car at entry"></p>'
        if crop:
            photo_block += f'<p><img class="crop" src="{crop}" alt="Plate crop"></p>'
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Pay — {row.plate}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
      body{{font:16px/1.45 system-ui,sans-serif;margin:0;background:#f5f7fb;color:#172033}}
      main{{max-width:420px;margin:0 auto;padding:24px}}
      .plate{{font-size:28px;letter-spacing:.12em;font-weight:700}}
      .card{{background:#fff;border:1px solid #dfe5ef;border-radius:12px;padding:20px;margin:16px 0}}
      .due{{font-size:26px;font-weight:700}}
      .muted{{color:#5b6b82}}
      .ok{{color:#0a7a3e;font-weight:700}}
      img.qr{{width:168px;height:168px;background:#fff;padding:8px;border:1px solid #dfe5ef;border-radius:8px}}
      img.car{{width:100%;max-height:220px;object-fit:contain;background:#0b1220;border-radius:8px}}
      img.crop{{max-width:100%;max-height:72px;object-fit:contain;background:#fff;border:1px solid #dfe5ef;border-radius:6px}}
      .btn{{display:block;width:100%;box-sizing:border-box;text-align:center;background:#1f5eff;color:#fff;
           border:0;border-radius:8px;padding:14px;margin-top:12px;font-weight:600;font-size:16px;cursor:pointer}}
      .btn:disabled{{opacity:.5;cursor:not-allowed}}
      .btn.secondary{{background:#eef2f8;color:#172033;text-decoration:none}}
      code{{background:#eef2f8;padding:2px 6px;border-radius:4px}}
      #msg{{min-height:1.4em;margin-top:10px}}
    </style></head>
    <body><main>
    <p class="muted">{settings.site_name}</p>
    <p class="plate">{row.plate}</p>
    {photo_block}
    <div class="card">
      <p>Entry {entry}</p>
      <p>Time inside <b id="stay">{stay}</b></p>
      <p>{data['parker_kind']} · <span id="status">{status_label}</span></p>
      <p class="due" id="due">{currency} {remaining:,.0f}</p>
      <p class="muted">Paid {currency} {paid:,.0f} of {due:,.0f}.</p>
      <p class="muted">{image_note}</p>
      <p class="muted">Receipt code <code id="code">{token}</code></p>
      <input id="phone" type="tel" inputmode="tel" autocomplete="tel" placeholder="Mobile number e.g. 07XX XXX XXX"
             class="{'' if external_pay else 'hidden'}" style="width:100%;box-sizing:border-box;padding:12px;border:1px solid #dfe5ef;border-radius:8px;margin-top:12px;font-size:16px;{'' if external_pay else 'display:none'}">
      <button class="btn" id="pay-mobile" {pay_disabled}>Pay on phone (mobile)</button>
      <a class="btn secondary" href="#kiosk">Pay at kiosk</a>
      <p id="msg" class="muted"></p>
    </div>
    <p><img class="qr" src="/p/{token}/qr.png" alt="Payment QR"></p>
    <div class="card" id="kiosk">
      <p><b>Kiosk</b></p>
      <p class="muted">Scan this same QR (or type code <code>{token}</code>) at the site kiosk. An operator confirms cash and the ledger updates immediately.</p>
    </div>
    <p class="muted">Lost paper is OK — the plate is the identity. This page is the payment link encoded in the receipt QR.</p>
    <script>
      const token = {token!r};
      const externalPay = {'true' if external_pay else 'false'};
      const payBtn = document.getElementById("pay-mobile");
      const phoneInput = document.getElementById("phone");
      const msg = document.getElementById("msg");
      let pendingSince = 0;
      const statusUrl = externalPay
        ? "/api/public/payment-status/" + encodeURIComponent(token)
        : "/p/" + encodeURIComponent(token) + "/status";
      async function refresh() {{
        const res = await fetch(statusUrl);
        if (!res.ok) return;
        const data = await res.json();
        document.getElementById("status").textContent = data.paid ? "PAID" : data.status;
        document.getElementById("due").textContent = data.currency + " " + Math.round(data.amount_remaining).toLocaleString();
        if (data.duration_label) document.getElementById("stay").textContent = data.duration_label;
        const intent = data.intent || null;
        const waiting = externalPay && intent && intent.status === "PENDING" && !data.paid;
        payBtn.disabled = !data.payable || waiting;
        if (!data.payable) {{
          msg.textContent = data.pay_blocked_reason || (data.paid ? "Paid. You can leave when the exit camera reads your plate." : "Nothing to pay.");
          msg.className = data.paid ? "ok" : "muted";
        }} else if (waiting) {{
          msg.textContent = "Approve the payment prompt on your phone. This page updates when the provider confirms.";
          msg.className = "muted";
        }} else if (externalPay && intent && ["FAILED", "EXPIRED", "BLOCKED", "MISMATCH"].includes(intent.status) && pendingSince) {{
          msg.textContent = intent.status === "MISMATCH"
            ? "Payment needs staff review at the kiosk."
            : ("Payment was not completed" + (intent.message ? " (" + intent.message + ")" : "") + ". Try again or pay at the kiosk.");
          msg.className = "muted";
          pendingSince = 0;
        }}
      }}
      payBtn.addEventListener("click", async () => {{
        payBtn.disabled = true;
        msg.className = "muted";
        try {{
          let res, data;
          if (externalPay) {{
            const phone = (phoneInput && phoneInput.value || "").trim();
            if (!phone) throw new Error("Enter the mobile number that will pay.");
            msg.textContent = "Sending payment prompt to your phone…";
            res = await fetch("/api/public/payment-intents", {{
              method: "POST",
              headers: {{"Content-Type": "application/json"}},
              body: JSON.stringify({{token: token, phone: phone}}),
            }});
            data = await res.json();
            if (!res.ok) throw new Error(data.detail || data.error || "Payment could not be started");
            if (data.already_paid) {{ msg.textContent = "Already paid."; msg.className = "ok"; }}
            else {{ pendingSince = Date.now(); msg.textContent = "Approve the prompt on your phone. Waiting for confirmation…"; }}
          }} else {{
            msg.textContent = "Confirming payment…";
            res = await fetch("/p/" + encodeURIComponent(token) + "/pay", {{
              method: "POST",
              headers: {{"Content-Type": "application/json"}},
              body: JSON.stringify({{method: "MOBILE_SIMULATED"}}),
            }});
            data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Payment failed");
            msg.textContent = data.already_paid ? "Already paid." : "Payment recorded.";
            msg.className = "ok";
          }}
          await refresh();
        }} catch (err) {{
          msg.textContent = err.message || String(err);
          msg.className = "muted";
          payBtn.disabled = false;
        }}
      }});
      setInterval(refresh, externalPay ? 3000 : 5000);
    </script>
    </main></body></html>"""
    return HTMLResponse(html)


@app.get("/p/{token}/status")
def public_receipt_status(token: str, db: Session = Depends(get_db)):
    from app.services.public_pay import public_session_payload, session_by_public_token

    row = session_by_public_token(db, token)
    if not row:
        raise HTTPException(404, "Receipt not found")
    return public_session_payload(db, row)


@app.post("/p/{token}/pay")
async def public_receipt_pay(token: str, payload: PaymentConfirm = PaymentConfirm(method="MOBILE_SIMULATED"), db: Session = Depends(get_db)):
    """Phone payment from the receipt QR page.

    Uses the simulated provider until a live mobile-money aggregator is wired.
    Kiosk cash must use the authenticated kiosk endpoint instead.
    """
    from app.services.public_pay import pay_public_session, session_by_public_token

    row = session_by_public_token(db, token)
    if not row:
        raise HTTPException(404, "Receipt not found")
    method = (payload.method or "MOBILE_SIMULATED").strip().upper()
    if method in {"KIOSK_CASH", "CASH", "KIOSK"}:
        raise HTTPException(401, "Kiosk cash requires a signed-in operator. Open Sessions and pay there, or POST /p/{token}/kiosk-pay.")
    from app.services import mobile_payments

    if mobile_payments.active_mobile_provider_id() in mobile_payments.external_provider_ids():
        # A real aggregator is configured: the instant simulated path must not
        # be reachable from a browser. Money only moves via payment intents.
        raise HTTPException(409, "Mobile payments use POST /api/public/payment-intents on this site.")
    try:
        result = await pay_public_session(db, row, method=method, amount=payload.amount)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, str(exc))
    return result


# ---------------------------------------------------------------------------
# Narrow public payment surface (tunnel-exposed). Everything else stays LAN.
# ---------------------------------------------------------------------------


@app.post("/api/public/payment-intents")
async def public_payment_intent(payload: PublicPaymentIntentRequest, db: Session = Depends(get_db)):
    """Start a mobile-money collection for a receipt token.

    Creates a PENDING PaymentIntent and asks the provider to push a USSD
    prompt. Nothing is marked paid here; verification happens server-side.
    """
    from app.services import mobile_payments
    from app.services.public_pay import session_by_public_token

    row = session_by_public_token(db, payload.token)
    if not row:
        raise HTTPException(404, "Receipt not found")
    provider_id = (payload.provider or "").strip().lower() or mobile_payments.active_mobile_provider_id()
    if provider_id not in mobile_payments.external_provider_ids():
        raise HTTPException(409, "No external mobile-money provider is active on this site.")
    try:
        result = await mobile_payments.start_mobile_payment(
            db, row, phone=payload.phone, provider_id=provider_id, network=payload.network, amount=payload.amount,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not result.get("ok"):
        return JSONResponse(status_code=503, content={**result, "token": row.public_token})
    return {**result, "token": row.public_token}


@app.get("/api/public/payment-status/{token}")
def public_payment_status(token: str, db: Session = Depends(get_db)):
    """Read-only status for the phone page: session paid state + latest intent."""
    from app.services import mobile_payments
    from app.services.public_pay import public_session_payload, session_by_public_token

    row = session_by_public_token(db, token)
    if not row:
        raise HTTPException(404, "Receipt not found")
    body = public_session_payload(db, row)
    latest = mobile_payments.latest_intent_for_session(db, row.id)
    body["intent"] = mobile_payments.intent_dict(latest) if latest else None
    body["mobile_provider"] = mobile_payments.active_mobile_provider_id()
    return body


@app.post("/api/webhooks/{provider_id}")
async def payment_provider_webhook(provider_id: str, request: Request, db: Session = Depends(get_db)):
    """Authenticated provider callback. Never opens a barrier; never trusts the body for money."""
    from app.services import mobile_payments

    if provider_id not in mobile_payments.external_provider_ids():
        raise HTTPException(404, "Unknown provider")
    raw = await request.body()
    status, body = await mobile_payments.handle_webhook(
        db, provider_id, raw_body=raw, headers={k.lower(): v for k, v in request.headers.items()},
    )
    return JSONResponse(status_code=status, content=body)


@app.get("/payments/health")
def payments_health_ep(db: Session = Depends(get_db), _: User = Depends(require_any("payments.view", "fees.view", "kiosk.use"))):
    from app.services import mobile_payments
    from app.services.public_ingress import describe as ingress_describe

    return {**mobile_payments.payments_health(db), "public_ingress": ingress_describe()}


@app.post("/payments/reconcile")
async def payments_reconcile_ep(db: Session = Depends(get_db), _: User = Depends(require_any("payments.view", "payments.create"))):
    """Operator-triggered reconciliation (same code path as the background job)."""
    from app.services import mobile_payments

    return await mobile_payments.reconcile_pending(db=db)


@app.post("/p/{token}/kiosk-pay")
async def kiosk_receipt_pay(
    token: str,
    payload: PaymentConfirm = PaymentConfirm(method="KIOSK_CASH"),
    db: Session = Depends(get_db),
    user: User = Depends(require_any("payments.create", "kiosk.use", "simulation.run")),
):
    """Operator confirms cash after scanning the receipt QR at the kiosk."""
    from app.services.public_pay import pay_public_session, session_by_public_token

    row = session_by_public_token(db, token)
    if not row:
        raise HTTPException(404, "Receipt not found")
    try:
        result = await pay_public_session(
            db, row, method=payload.method or "KIOSK_CASH", amount=payload.amount, operator_id=user.id,
        )
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    write_audit(db, user, "payments.create", "parking_session", str(row.id), f"kiosk QR {row.plate}")
    return result


@app.get("/sessions/by-token/{token}")
def session_by_token(token: str, db: Session = Depends(get_db), _: User = Depends(require_any("sessions.view", "fees.view", "kiosk.use", "payments.create"))):
    from app.services.public_pay import public_session_payload, session_by_public_token

    row = session_by_public_token(db, token)
    if not row:
        raise HTTPException(404, "No session for that receipt code")
    return public_session_payload(db, row)


@app.get("/sessions/lookup")
def lookup_session(q: str = "", db: Session = Depends(get_db), _: User = Depends(require_any("sessions.view", "fees.view", "kiosk.use", "payments.create"))):
    """Find a visit from a scanned QR, a receipt link, or a number plate."""
    from app.services.kiosk_lookup import find_session
    from app.services.public_pay import public_session_payload

    row = find_session(db, q)
    if not row:
        raise HTTPException(404, "No visit matches that QR code or plate")
    return public_session_payload(db, row)


def _session_image(db: Session, token: str, kind: str):
    from app.services.kiosk_lookup import image_fields
    from app.services.preview import media_path
    from app.services.public_pay import session_by_public_token

    row = session_by_public_token(db, token)
    if not row:
        raise HTTPException(404, "Receipt not found")
    fields = image_fields(db, row)
    url = fields.get("snapshot_url") if kind == "snapshot" else fields.get("crop_url")
    if not url:
        raise HTTPException(404, "No photo for this visit")
    # url is /p/{token}/... — the file path lives on the capture row.
    from sqlalchemy import select
    from app.models import VehicleCapture
    from app.core.plate import normalize_plate
    plate = normalize_plate(row.plate)
    capture = None
    if plate:
        capture = db.scalar(select(VehicleCapture).where(VehicleCapture.plate == plate).order_by(VehicleCapture.id.desc()))
    if capture is None and row.camera_id:
        capture = db.scalar(select(VehicleCapture).where(VehicleCapture.camera_id == row.camera_id).order_by(VehicleCapture.id.desc()))
    stored = (capture.snapshot_path if kind == "snapshot" else capture.crop_path) if capture else ""
    if not stored or "/" not in stored.replace("\\", "/"):
        raise HTTPException(404, "No photo for this visit")
    folder, name = str(stored).replace("\\", "/").split("/", 1)
    path = media_path(folder, name)
    if path is None:
        raise HTTPException(404, "No photo for this visit")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/p/{token}/snapshot.jpg", include_in_schema=False)
def public_snapshot(token: str, db: Session = Depends(get_db)):
    return _session_image(db, token, "snapshot")


@app.get("/p/{token}/crop.jpg", include_in_schema=False)
def public_crop(token: str, db: Session = Depends(get_db)):
    return _session_image(db, token, "crop")


@app.get("/p/{token}/qr.png", include_in_schema=False)
def public_receipt_qr(token: str, db: Session = Depends(get_db)):
    row = db.scalar(select(Receipt).where(Receipt.public_token == token).order_by(Receipt.id.desc()))
    path = Path(row.qr_path) if row and row.qr_path else None
    if path and path.exists():
        return FileResponse(path, media_type="image/png")
    from app.domain.receipt_engine import session_qr_payload
    from app.services.receipts import _qr_png, resolve_public_base_url
    png = _qr_png(session_qr_payload(token, base_url=resolve_public_base_url(db)))
    if not png:
        raise HTTPException(404, "QR not available")
    return Response(content=png, media_type="image/png")


@app.get("/reports/summary")
def reports_summary(
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_any("dashboard.view", "fees.view", "payments.view")),
):
    from .services.reports_desk import report_summary
    return report_summary(db, start, end)


@app.get("/reports/export.csv")
def reports_export(
    kind: str = "payments",
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_any("dashboard.view", "fees.view", "payments.view")),
):
    from .services.reports_desk import report_by_id, report_summary, table_csv
    summary = report_summary(db, start, end)
    try:
        sheet = report_by_id(summary, kind)
    except KeyError:
        raise HTTPException(404, "Unknown report")
    filename = f"smartpark-{sheet['id']}.csv"
    return Response(
        content=table_csv(sheet),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/reports/payments.csv")
def reports_csv(
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_any("dashboard.view", "fees.view", "payments.view")),
):
    from .services.reports_desk import report_csv, report_summary
    summary = report_summary(db, start, end)
    return Response(
        content=report_csv(summary),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="smartpark-payments.csv"'},
    )


@app.get("/backup")
def backup_status(db: Session = Depends(get_db), _: User = Depends(require_any("dashboard.view", "settings.manage"))):
    from .services.backup import public_backup_status
    return public_backup_status(db)


@app.patch("/backup")
def backup_update(
    payload: BackupSettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require("settings.manage")),
):
    from .services.backup import public_backup_status, save_backup_settings
    try:
        save_backup_settings(db, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    write_audit(db, user, "backup.update", "site", "backup", "")
    db.commit()
    return public_backup_status(db)


@app.post("/backup/offline")
def backup_mark_offline(db: Session = Depends(get_db), user: User = Depends(require("settings.manage"))):
    from .services.backup import mark_offline_saved
    status = mark_offline_saved(db)
    write_audit(db, user, "backup.offline", "site", "backup", status.get("last_offline_at") or "")
    db.commit()
    return status


@app.post("/backup/snooze")
def backup_snooze(db: Session = Depends(get_db), _: User = Depends(require_any("dashboard.view", "settings.manage"))):
    from .services.backup import snooze_offline_reminder
    return snooze_offline_reminder(db)


@app.get("/backup/download")
def backup_download(db: Session = Depends(get_db), user: User = Depends(require("settings.manage"))):
    from .services.backup import backup_filename, dump_sql, mark_offline_saved
    try:
        body = dump_sql(db)
    except Exception as exc:
        raise HTTPException(409, str(exc)) from exc
    mark_offline_saved(db)
    write_audit(db, user, "backup.download", "site", "backup", backup_filename())
    db.commit()
    return Response(
        content=body,
        media_type="application/sql",
        headers={"Content-Disposition": f'attachment; filename="{backup_filename()}"'},
    )


@app.post("/backup/cloud")
def backup_cloud(db: Session = Depends(get_db), user: User = Depends(require("settings.manage"))):
    from .services.backup import push_cloud_backup
    try:
        status = push_cloud_backup(db)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc
    write_audit(db, user, "backup.cloud", "site", "backup", "ok")
    db.commit()
    return status


@app.get("/dashboard")
def dashboard_stats(db: Session = Depends(get_db), _: User = Depends(require_any("dashboard.view", "cameras.view"))):
    from app.services.cache import dashboard_cache
    from app.services.runtime import startup_state
    from app.services.simulation import OPEN_STATUSES
    from app.services.site_policy import site_policy, format_money
    from app.services.lane_status import lane_operator_status

    cached = dashboard_cache.get("overview")
    if cached is not None:
        return cached
    policy = site_policy(db)
    lanes = lane_operator_status(db)
    cams = list(db.scalars(select(Camera)).all())
    connected = sum(1 for c in cams if c.status in ("SDK_CONNECTED", "VIDEO_CONNECTED"))
    offline = sum(1 for c in cams if c.enabled and c.status in ("OFFLINE", "SDK_FAILED", "UNKNOWN"))
    inside = db.scalar(
        select(func.count(ParkingSession.id)).where(ParkingSession.status.in_(tuple(OPEN_STATUSES)))
    ) or 0
    registered = db.scalar(select(func.count(RegisteredVehicle.id)).where(RegisteredVehicle.enabled.is_(True))) or 0
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    entries_today = db.scalar(
        select(func.count(ParkingSession.id)).where(ParkingSession.entry_time >= start)
    ) or 0
    exits_today = db.scalar(
        select(func.count(ParkingSession.id)).where(ParkingSession.exit_time >= start)
    ) or 0
    revenue_today = db.scalar(
        select(func.coalesce(func.sum(PaymentTransaction.amount), 0)).where(
            PaymentTransaction.status == "SUCCEEDED",
            PaymentTransaction.confirmed_at >= start,
        )
    ) or 0
    unpaid_active = db.scalar(
        select(func.count(ParkingSession.id)).where(
            ParkingSession.status.in_(("ACTIVE", "OPEN", "WAITING_RECEIPT")),
            ParkingSession.parker_kind == "CASUAL",
        )
    ) or 0
    subscribers_inside = db.scalar(
        select(func.count(ParkingSession.id)).where(
            ParkingSession.status.in_(tuple(OPEN_STATUSES)),
            ParkingSession.parker_kind != "CASUAL",
        )
    ) or 0
    review = db.scalar(
        select(func.count(AccessDecision.id)).where(AccessDecision.outcome.in_(("WAITING_RECEIPT", "DENIED_PAYMENT")))
    ) or 0
    alerts = []
    if offline:
        alerts.append(f"{offline} camera(s) not live")
    if review:
        alerts.append(f"{int(review)} recent hold/unpaid decisions")
    body = {
        "cameras": len(cams),
        "sdk_connected": connected,
        "vehicles_inside": int(inside),
        "registered_plates": int(registered),
        "entries_today": int(entries_today),
        "exits_today": int(exits_today),
        "revenue_today": float(revenue_today),
        "revenue_today_label": format_money(revenue_today, policy),
        "unpaid_active": int(unpaid_active),
        "subscribers_inside": int(subscribers_inside),
        "alerts": alerts,
        "receipt_policies": list(RECEIPT_POLICIES),
        "runtime": {"state": startup_state(), "version": settings.app_version},
        "currency": policy.get("currency"),
        "timezone": policy.get("timezone"),
        "lanes": lanes.get("lanes") or [],
    }
    return dashboard_cache.set("overview", body)


@app.get("/printers/status")
async def printer_status(
    db: Session = Depends(get_db),
    _: User = Depends(require_any("hardware.view", "sessions.view", "fees.view", "simulation.run")),
):
    cfg = parking_settings(db)
    adapter = printer_adapter(cfg.get("printer_adapter"), printer_name=cfg.get("printer_name") or "")
    health = await adapter.health()
    printers = health.get("printers")
    if printers is None:
        printers = list_system_printers()
    return {
        "adapter_id": adapter.id,
        **health,
        "printer_name": cfg.get("printer_name") or health.get("printer_name") or "",
        "printers": printers,
        "policies": list(RECEIPT_POLICIES),
    }


@app.post("/printers/test")
async def printer_test(
    db: Session = Depends(get_db),
    user: User = Depends(require_any("hardware.view", "simulation.run")),
):
    from app.infrastructure.hardware.printers import ReceiptDocument
    from app.services.receipts import _qr_png, public_receipt_url, resolve_public_base_url
    cfg = parking_settings(db)
    token = "TEST"
    public_url = public_receipt_url(token, base_url=resolve_public_base_url(db))
    document = ReceiptDocument(
        site_name=settings.site_name or settings.app_name,
        plate="T000TST",
        entry_time="Test print",
        entry_gate="Simulation",
        public_reference=token,
        public_url=public_url,
        payment_instructions="SmartPark thermal printer test ticket. Scan the QR code.",
        body_text="SmartPark test receipt\nPlate: T000TST\n",
        qr_payload=public_url,
        qr_png=_qr_png(public_url),
        lines=["SmartPark test receipt"],
    )
    adapter = printer_adapter(cfg.get("printer_adapter"), printer_name=cfg.get("printer_name") or "")
    printed = await adapter.print_receipt(document)
    write_audit(db, user, "printer.test", "printer", adapter.id, printed.message)
    db.commit()
    return printed.__dict__


@app.get("/access-plans")
def list_access_plans(db: Session = Depends(get_db), _: User = Depends(require("subscribers.view"))):
    ensure_access_plans(db)
    return [plan_dict(row) for row in db.scalars(select(AccessPlan).order_by(AccessPlan.id)).all()]


@app.post("/access-plans")
def create_access_plan(payload: AccessPlanCreate, db: Session = Depends(get_db), user: User = Depends(require("subscribers.manage"))):
    row = AccessPlan(
        name=payload.name.strip(), kind=payload.kind.strip().upper(),
        auto_open=payload.auto_open, print_receipt=payload.print_receipt,
        enabled=payload.enabled, notes=payload.notes or "",
    )
    db.add(row)
    commit_or_conflict(db, "A plan with that name already exists")
    db.refresh(row)
    write_audit(db, user, "plan.create", "access_plan", str(row.id), row.name)
    return plan_dict(row)


@app.patch("/access-plans/{plan_id}")
def update_access_plan(plan_id: int, payload: AccessPlanUpdate, db: Session = Depends(get_db), user: User = Depends(require("subscribers.manage"))):
    row = db.get(AccessPlan, plan_id)
    if not row:
        raise HTTPException(404, "Plan not found")
    data = payload.model_dump(exclude_unset=True)
    if "kind" in data and data["kind"]:
        data["kind"] = str(data["kind"]).strip().upper()
    for key, value in data.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    write_audit(db, user, "plan.update", "access_plan", str(row.id), row.name)
    return plan_dict(row)


@app.get("/vehicles")
def list_vehicles(db: Session = Depends(get_db), _: User = Depends(require("subscribers.view"))):
    ensure_access_plans(db)
    return [vehicle_dict(row) for row in db.scalars(select(RegisteredVehicle).order_by(RegisteredVehicle.plate)).all()]


@app.post("/vehicles")
def create_vehicle(payload: VehicleCreate, db: Session = Depends(get_db), user: User = Depends(require("subscribers.manage"))):
    ensure_access_plans(db)
    plate = normalize_plate(payload.plate)
    if not plate:
        raise HTTPException(400, "Enter a number plate")
    plan_id = payload.plan_id
    if plan_id is None:
        first = db.scalar(select(AccessPlan).order_by(AccessPlan.id))
        plan_id = first.id if first else None
    if plan_id and db.get(AccessPlan, plan_id) is None:
        raise HTTPException(404, "Access plan not found")
    row = RegisteredVehicle(
        plate=plate, owner_name=payload.owner_name or "", plan_id=plan_id,
        enabled=payload.enabled, valid_from=payload.valid_from, valid_until=payload.valid_until,
        notes=payload.notes or "",
    )
    db.add(row)
    commit_or_conflict(db, "That number plate is already registered")
    db.refresh(row)
    write_audit(db, user, "vehicle.register", "registered_vehicle", str(row.id), plate)
    return vehicle_dict(row)


@app.patch("/vehicles/{vehicle_id}")
def update_vehicle(vehicle_id: int, payload: VehicleUpdate, db: Session = Depends(get_db), user: User = Depends(require("subscribers.manage"))):
    row = db.get(RegisteredVehicle, vehicle_id)
    if not row:
        raise HTTPException(404, "Vehicle not found")
    data = payload.model_dump(exclude_unset=True)
    if "plate" in data:
        data["plate"] = normalize_plate(data["plate"] or "")
        if not data["plate"]:
            raise HTTPException(400, "Enter a number plate")
    if data.get("plan_id") and db.get(AccessPlan, data["plan_id"]) is None:
        raise HTTPException(404, "Access plan not found")
    for key, value in data.items():
        setattr(row, key, value)
    commit_or_conflict(db, "That number plate is already registered")
    db.refresh(row)
    write_audit(db, user, "vehicle.update", "registered_vehicle", str(row.id), row.plate)
    return vehicle_dict(row)


@app.post("/vehicles/bulk")
def create_vehicles_bulk(payload: VehicleBulkCreate, db: Session = Depends(get_db), user: User = Depends(require("subscribers.manage"))):
    """Register many plates at once. One bad row does not skip the others that succeed."""
    from .core.plate import normalize_plate as norm
    ensure_access_plans(db)
    created = []
    errors = []
    for index, item in enumerate(payload.vehicles):
        plate = norm(item.plate)
        if not plate:
            errors.append({"index": index, "error": "Enter a number plate"})
            continue
        plan_id = item.plan_id
        if plan_id is None:
            first = db.scalar(select(AccessPlan).order_by(AccessPlan.id))
            plan_id = first.id if first else None
        if plan_id and db.get(AccessPlan, plan_id) is None:
            errors.append({"index": index, "plate": plate, "error": "Access plan not found"})
            continue
        row = RegisteredVehicle(
            plate=plate, owner_name=item.owner_name or "", plan_id=plan_id,
            enabled=item.enabled, valid_from=item.valid_from, valid_until=item.valid_until,
            notes=item.notes or "",
        )
        db.add(row)
        try:
            db.commit()
            db.refresh(row)
        except IntegrityError:
            db.rollback()
            errors.append({"index": index, "plate": plate, "error": "That number plate is already registered"})
            continue
        write_audit(db, user, "vehicle.register", "registered_vehicle", str(row.id), plate)
        db.commit()
        created.append(vehicle_dict(row))
    return {"ok": True, "created": created, "errors": errors}


@app.post("/vehicles/bulk-delete")
def delete_vehicles_bulk(payload: VehicleBulkDelete, db: Session = Depends(get_db), user: User = Depends(require("subscribers.manage"))):
    deleted = []
    for vehicle_id in payload.ids:
        row = db.get(RegisteredVehicle, int(vehicle_id))
        if row is None:
            continue
        plate = row.plate
        db.delete(row)
        deleted.append(vehicle_id)
        write_audit(db, user, "vehicle.delete", "registered_vehicle", str(vehicle_id), plate)
    db.commit()
    return {"ok": True, "deleted": deleted}


@app.delete("/vehicles/{vehicle_id}")
def delete_vehicle(vehicle_id: int, db: Session = Depends(get_db), user: User = Depends(require("subscribers.manage"))):
    row = db.get(RegisteredVehicle, vehicle_id)
    if not row:
        raise HTTPException(404, "Vehicle not found")
    plate = row.plate
    db.delete(row)
    db.commit()
    write_audit(db, user, "vehicle.delete", "registered_vehicle", str(vehicle_id), plate)
    return {"ok": True}


@app.get("/vehicles/lookup/{plate}")
def lookup_vehicle(plate: str, db: Session = Depends(get_db), _: User = Depends(require("subscribers.view"))):
    return lookup_entitlement(db, plate).__dict__


@app.get("/roles")
def list_roles(db: Session = Depends(get_db), _: User = Depends(require("users.view"))):
    return [{"id": r.id, "name": r.name, "permissions": sorted(r.permissions()), "system_role": r.system_role}
            for r in db.scalars(select(Role).order_by(Role.id)).all()]


@app.get("/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(require("users.view"))):
    return [user_dict(u) for u in load_users(db)]


@app.get("/users/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db), _: User = Depends(require("users.view"))):
    user = load_user(db, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return user_dict(user)


@app.post("/users")
def add_user(payload: UserCreate, db: Session = Depends(get_db), actor: User = Depends(require("users.manage"))):
    user = create_user(
        db,
        username=payload.username.strip(),
        full_name=payload.full_name.strip(),
        password=payload.password,
        status=payload.status,
        roles=payload.roles,
    )
    write_audit(db, actor, "user.create", "user", str(user.id), f"Created {user.username}")
    return user_dict(user)


@app.patch("/users/{user_id}")
def patch_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db), actor: User = Depends(require("users.manage"))):
    user = load_user(db, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    user = update_user(
        db,
        user,
        full_name=payload.full_name,
        password=payload.password,
        status=payload.status,
        roles=payload.roles,
    )
    write_audit(db, actor, "user.update", "user", str(user.id), f"Updated {user.username}")
    return user_dict(user)


@app.delete("/users/{user_id}")
def remove_user(user_id: int, db: Session = Depends(get_db), actor: User = Depends(require("users.manage"))):
    user = load_user(db, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    username = user.username
    delete_user(db, user, actor.id)
    write_audit(db, actor, "user.delete", "user", str(user_id), f"Deleted {username}")
    return {"ok": True}


@app.get("/audit")
def audits(db: Session = Depends(get_db), _: User = Depends(require("audit.view"))):
    from .models import AuditLog
    rows=db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(200)).all()
    return [{"id":x.id,"user_id":x.user_id,"action":x.action,"target_type":x.target_type,"target_id":x.target_id,"detail":x.detail,"created_at":x.created_at} for x in rows]
