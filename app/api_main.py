from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import asyncio
import time

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .db import Base, engine, ensure_schema, get_db, short_session, SessionLocal
from .models import AccessPlan, AccessDecision, Camera, CameraStatus, Gate, GateMode, ParkingSession, PaymentTransaction, Receipt, RegisteredVehicle, Role, Tariff, User
from .schemas import (
    CameraCreate, CameraImport, CameraUpdate, FeeQuoteRequest, FusionRequest, GateCreate, GateUpdate, LedWrite,
    LoginRequest, LoginResponse, ManualGateCommand, ParkingSettingsUpdate, PaymentConfirm, SessionCreate, SimEntryRequest, SimExitRequest,
    UserCreate, UserUpdate, AccessPlanCreate, AccessPlanUpdate, VehicleCreate, VehicleUpdate,
)
from .security import authenticate_user, create_session, current_user, oauth2_scheme, require, require_any, require_media, revoke_session, user_permissions
from .core.fusion import resolve_readings
from .services.alpr import recognize_bytes, status as alpr_status
from .services.audit import write_audit
from .services.bootstrap import ensure_bootstrap_admin, setup_status
from .services.captures import capture_dict, latest_for_camera, list_captures, persist_event
from .services.fee_engine import calculate_car1_fee, ensure_car1_tariff, load_active_rules
from .services.gates import controller
from .services.led_udp import send_led_text
from .services.hvx_client import HVXHostClient, HVXHostUnavailable
from .services.hvx_vendor import vendor_inventory
from .services.camera_lpr import choose_overlay_box, local_from_fastalpr, native_from_sdk_capture
from .services.preview import (
    MJPEG_BOUNDARY, CameraLiveSpec, acquire_live, get_state, media_path, mjpeg_from_cache, mjpeg_parts, release_live, remember_alpr, remember_frame, snapshot_for_camera, start_idle_watch, start_live_pump, stop_live_pump, stop_live_pumps, touch_live,
)
from .services.http_snapshot import grab_http_snapshot
from .services.rtsp_probe import probe, vendor_candidates
from .services.site_cameras import (
    KNOWN_SITE_CAMERAS, KNOWN_SITE_GATES, camera_spec_for_ip, discovery_row, lan_sdk_candidates,
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
from .infrastructure.hardware.cameras import camera_adapter_for
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
    ]),
    "Developer": ",".join([
        "dashboard.view", "cameras.view", "cameras.connect", "gates.view",
        "gates.open", "hardware.view", "fees.view", "simulation.run",
        "subscribers.view", "subscribers.manage", "sessions.view",
        "payments.view", "payments.create",
    ]),
    "Kiosk Operator": ",".join([
        "kiosk.use", "sessions.view", "payments.view", "payments.create",
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
    from .services.runtime import mark_core_ready, set_process_name, set_startup_state

    configure_logging("site-service")
    set_process_name("SmartParkSiteService")
    set_startup_state("STARTING")
    ensure_schema()
    with SessionLocal() as db:
        ensure_roles(db)
        ensure_bootstrap_admin(db)
        ensure_car1_tariff(db)
        ensure_access_plans(db)
    mark_core_ready()
    start_idle_watch()
    ingest = asyncio.create_task(_camera_event_loop(), name="camera-events")
    outbox = asyncio.create_task(_outbox_loop(), name="parking-outbox")
    hvx_watch = asyncio.create_task(_hvx_watch_loop(), name="hvx-watch")
    try:
        yield
    finally:
        for task in (ingest, outbox, hvx_watch):
            task.cancel()
        await asyncio.gather(ingest, outbox, hvx_watch, return_exceptions=True)
        stop_live_pumps()
        set_startup_state("OFFLINE")


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)


def _login_response(db: Session, username: str, password: str) -> LoginResponse:
    user = authenticate_user(db, username, password)
    token = create_session(db, user)
    return LoginResponse(
        token=token,
        access_token=token,
        token_type="bearer",
        username=user.username,
        permissions=sorted(user_permissions(user)),
    )


@app.get("/", include_in_schema=False)
def web_app():
    index = WEB_DIR / "index.html"
    if not index.exists():
        raise HTTPException(404, "Web UI not found")
    return FileResponse(index)


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
def me(user: User = Depends(current_user)):
    return {"id": user.id, "username": user.username, "full_name": user.full_name, "permissions": sorted(user_permissions(user))}


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
    if payload.ips:
        specs = [camera_spec_for_ip(ip) for ip in payload.ips]
    else:
        discovered = await _discover_cameras(db, scan_lan=payload.scan_lan)
        specs = [camera_spec_for_ip(row["ip_address"]) for row in discovered["cameras"] if row.get("reachable")]
        if not specs:
            specs = [camera_spec_for_ip(row["ip_address"]) for row in KNOWN_SITE_CAMERAS]
    created, skipped = _import_camera_specs(db, user, specs)
    return {
        "created": [camera_dict(c) for c in created],
        "skipped": skipped,
        "cameras": [camera_dict(c) for c in db.scalars(select(Camera).order_by(Camera.id)).all()],
    }


@app.post("/cameras/sdk/connect-all")
async def sdk_connect_all(db: Session = Depends(get_db), user: User = Depends(require("cameras.connect"))):
    rows = db.scalars(select(Camera).where(Camera.enabled == True).order_by(Camera.id)).all()
    results = []
    connected = 0
    skipped = 0
    for camera in rows:
        item = await apply_sdk_connect(camera, db, user, raise_on_host_error=False)
        if item.get("status") == CameraStatus.SDK_CONNECTED.value:
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
            "Connect all logs in camera IPs only (NetSDK port 30000). "
            "Unreachable cameras are skipped after a short TCP probe so one slow camera cannot stall the rest."
        ),
    }


def camera_dict(c: Camera):
    gate = c.gate
    lane_name = None if gate is None else gate.name
    return {
        "id": c.id, "name": c.name, "ip_address": c.ip_address, "sdk_port": c.sdk_port,
        "username": c.username, "gate_id": c.gate_id, "gate_name": lane_name,
        "lane_name": lane_name or "",
        "side": side_label(c.lane_direction),
        "lane_direction": c.lane_direction,
        "controller_ip": c.controller_ip or "",
        "display_ip": c.display_ip or "",
        "adapter_id": camera_adapter_id(c),
        "connection_mode": camera_connection_mode(c),
        "rtsp_url": c.rtsp_url, "status": c.status, "sdk_handle": c.sdk_handle,
        "last_error": c.last_error, "last_seen_at": c.last_seen_at, "enabled": c.enabled,
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
    if scan_lan:
        lan_ips = await lan_sdk_candidates(defaults["sdk_port"])
        for ip in lan_ips:
            if ip not in ips:
                ips.append(ip)
    probed = await probe_ips(ips, defaults["sdk_port"])
    hvx_set = set(hvx.get("ips") or [])
    cameras = [
        discovery_row(
            ip,
            tcp_open=bool(probed.get(ip)),
            hvx_found=ip in hvx_set,
            existing=existing.get(ip),
        )
        for ip in ips
    ]
    return {
        "sdk_port": defaults["sdk_port"],
        "username": defaults["username"],
        "scan_lan": scan_lan,
        "hvx": hvx,
        "lan_ips": lan_ips,
        "cameras": cameras,
        "note": "TCP open or vendor FindDeviceIp is not SDK_CONNECTED. Use SDK Connect / Connect all.",
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
        db.commit()
        write_audit(db, user, "camera.sdk_connect", "camera", str(camera.id), camera.last_error)
        return {
            **camera_dict(camera),
            "sdk_result": {"connected": False, "skipped": True, "error": camera.last_error},
        }
    camera.status = CameraStatus.SDK_CONNECTING.value
    camera.last_error = ""
    db.commit()
    try:
        result = await adapter.connect(camera)
        if result.get("connected"):
            camera.status = CameraStatus.SDK_CONNECTED.value
            camera.sdk_handle = result.get("handle")
            camera.last_seen_at = datetime.now(timezone.utc)
            camera.last_error = ""
            db.commit()
        else:
            camera.status = CameraStatus.SDK_FAILED.value
            name = result.get("connect_rc_name") or result.get("connect_rc")
            camera.last_error = result.get("error") or f"SDK return code: {name}"
        db.commit()
        write_audit(
            db, user, "camera.sdk_connect", "camera", str(camera.id),
            str({k: v for k, v in result.items() if k != "password"}),
        )
        return {**camera_dict(camera), "sdk_result": result}
    except HTTPException:
        raise
    except Exception as exc:
        camera.status = CameraStatus.SDK_FAILED.value
        camera.last_error = str(exc)
        db.commit()
        if raise_on_host_error:
            raise HTTPException(502, f"HVX SDK connection failed: {exc}")
        return {**camera_dict(camera), "sdk_result": {"connected": False, "error": str(exc)}}


def _plate_payload(camera: Camera, native: dict, alpr: dict | None) -> dict:
    from .services.ocr_policy import fusion_mode
    local = local_from_fastalpr(alpr)
    fused = resolve_readings(
        native_plate=native.get("plate") or "",
        native_confidence=float(native.get("confidence") or 0),
        local_plate=local.get("plate") or "",
        local_confidence=float(local.get("confidence") or 0),
        mode=fusion_mode(),
    )
    overlay = choose_overlay_box(native, local)
    return {
        "camera": camera_dict(camera),
        "native": native,
        "local": local,
        "fusion": fused.as_dict(),
        "alpr": alpr,
        "resolved_plate": fused.resolved_plate,
        "overlay": overlay,
    }


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
    if "gate_id" in data and data["gate_id"] is not None:
        get_gate_or_404(db, data["gate_id"])
    if data.get("adapter_id"):
        data["adapter_id"] = str(data["adapter_id"]).strip().lower()
    if data.get("connection_mode"):
        data["connection_mode"] = str(data["connection_mode"]).strip().upper()
        if data["connection_mode"] not in {"DIRECT", "EDGE_AGENT"}:
            raise HTTPException(400, "connection_mode must be DIRECT or EDGE_AGENT")
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
    db.delete(c)
    db.commit()
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
    return await apply_sdk_connect(c, db, user, raise_on_host_error=False)


@app.post("/cameras/{camera_id}/sdk/disconnect")
async def sdk_disconnect(camera_id: int, db: Session = Depends(get_db), user: User = Depends(require("cameras.connect"))):
    c=db.get(Camera, camera_id)
    if not c: raise HTTPException(404, "Camera not found")
    if c.sdk_handle is not None:
        try: await HVXHostClient().disconnect(c.sdk_handle)
        except Exception: pass
    stop_live_pump(c.id)
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
    return alpr_status()


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
    result = recognize_bytes(jpeg, camera_label=file.filename or "upload")
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
    result = recognize_bytes(grabbed["jpeg"], camera_label=f"cam-{c.id}-{c.ip_address}")
    native = await _native_capture_for_camera(c)
    local = local_from_fastalpr(result)
    fused = resolve_readings(
        native_plate=native.get("plate") or "",
        native_confidence=float(native.get("confidence") or 0),
        local_plate=local.get("plate") or "",
        local_confidence=float(local.get("confidence") or 0),
        mode="HYBRID",
    )
    result["camera_id"] = c.id
    result["frame"] = {k: v for k, v in grabbed.items() if k not in {"jpeg", "url"}}
    result["native"] = native
    result["local"] = local
    result["fusion"] = fused.as_dict()
    remember_alpr(c.id, result)
    write_audit(db, user, "camera.alpr", "camera", str(c.id), fused.resolved_plate or result.get("detail") or "FastALPR")
    return result


def _live_spec(camera: Camera) -> CameraLiveSpec:
    return CameraLiveSpec(
        id=camera.id,
        ip=camera.ip_address,
        username=camera.username,
        password=camera.password_secret,
        rtsp_url=camera.rtsp_url or "",
        sdk_handle=camera.sdk_handle,
    )


def _camera_live_spec(camera_id: int) -> CameraLiveSpec:
    with short_session() as db:
        c = get_camera_or_404(db, camera_id)
        return _live_spec(c)


@app.get("/cameras/{camera_id}/snapshot.jpg")
async def camera_snapshot(camera_id: int, _: User = Depends(require_media("cameras.view"))):
    spec = _camera_live_spec(camera_id)
    touch_live(spec)
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
    return Response(content=grabbed["jpeg"], media_type="image/jpeg")


@app.post("/cameras/{camera_id}/snapshot/capture")
async def capture_camera_snapshot(camera_id: int, db: Session = Depends(get_db), user: User = Depends(require("cameras.view"))):
    """Grab one live JPEG and save it as a car snapshot (plate may be empty)."""
    c = get_camera_or_404(db, camera_id)
    spec = _live_spec(c)
    touch_live(spec)
    grabbed = await snapshot_for_camera(
        spec.id, spec.ip, spec.username, spec.password, spec.rtsp_url, sdk_handle=spec.sdk_handle,
    )
    if not grabbed.get("ok"):
        raise HTTPException(409, grabbed.get("error") or "No live JPEG")
    jpeg = grabbed["jpeg"]
    persist_event(
        db, c, jpeg=jpeg, crop=b"",
        capture={"plate": "", "image_id": int(time.time() * 1000) % 2_000_000_000},
    )
    write_audit(db, user, "camera.snapshot", "camera", str(c.id), c.name)
    latest = latest_for_camera(db, c.id)
    return {
        "ok": True,
        "camera_id": c.id,
        "bytes": len(jpeg),
        "snapshot_url": f"/cameras/{c.id}/snapshot.jpg",
        "capture": capture_dict(latest) if latest else None,
    }


@app.get("/cameras/{camera_id}/live.mjpeg")
async def camera_live(camera_id: int, _: User = Depends(require_media("cameras.view"))):
    spec = _camera_live_spec(camera_id)
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

        return StreamingResponse(parts(), media_type=f"multipart/x-mixed-replace; boundary={MJPEG_BOUNDARY}")
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
    from .services.ocr_policy import should_run_local
    if live and grabbed.get("jpeg") and should_run_local(
        native_plate=str(native.get("plate") or ""),
        native_confidence=float(native.get("confidence") or 0),
        explicit=run_alpr,
    ):
        alpr = await asyncio.to_thread(
            recognize_bytes, grabbed["jpeg"], camera_label=f"cam-{c.id}-{c.ip_address}",
        )
        remember_alpr(c.id, alpr)
    plates = _plate_payload(c, native, alpr)
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
    }


@app.get("/cameras/{camera_id}/plates")
async def camera_plates(camera_id: int, db: Session = Depends(get_db), _: User = Depends(require("cameras.view"))):
    c = get_camera_or_404(db, camera_id)
    native = await _native_capture_for_camera(c)
    return _plate_payload(c, native, get_state(c.id).alpr or None)


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
    row = persist_event(db, camera, jpeg=jpeg, crop=crop, capture=capture)
    latest = row or previous
    if row and row.plate and row.id != previous_id and camera.gate_id:
        gate = db.get(Gate, camera.gate_id)
        if gate is not None:
            try:
                await handle_plate_event(
                    db, plate=row.plate, gate=gate, side=camera.lane_direction or "ENTRY",
                    simulated=False, source="camera",
                )
            except Exception as exc:
                from .services.health import note_worker_failure
                from .services.queues import parking_outbox
                note_worker_failure("plate-event", str(exc))
                parking_outbox().enqueue("plate-event", {
                    "plate": row.plate,
                    "gate_id": gate.id,
                    "side": camera.lane_direction or "ENTRY",
                    "camera_id": camera.id,
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
        with short_session() as db:
            row = db.get(Camera, camera_id)
            if row is None:
                return
            await _persist_capture_event(db, row, capture, jpeg, crop)
        if image_id:
            _last_image_id[camera_id] = image_id


async def _outbox_loop():
    from .services.queues import parking_outbox
    from .services.health import note_worker_failure

    while True:
        try:
            box = parking_outbox()
            for item in box.pending(limit=20):
                payload = item.get("payload") or {}
                if item.get("kind") != "plate-event":
                    box.ack(item["id"])
                    continue
                try:
                    with short_session() as db:
                        gate = db.get(Gate, int(payload.get("gate_id") or 0))
                        if gate is None:
                            box.ack(item["id"])
                            continue
                        await handle_plate_event(
                            db,
                            plate=str(payload.get("plate") or ""),
                            gate=gate,
                            side=str(payload.get("side") or "ENTRY"),
                            simulated=False,
                            source="outbox",
                        )
                    box.ack(item["id"])
                except Exception as exc:
                    box.note_failure()
                    note_worker_failure("outbox", str(exc))
                    break
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(2.0)


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


async def _camera_event_loop():
    """Pull QY plate callbacks in the background so cars are not missed while the UI is idle."""
    from .services.circuit import breaker
    from .services.health import note_camera, note_worker_failure
    from .config import settings as cfg

    hvx_breaker = breaker("hvx-host")
    poll = float(getattr(cfg, "camera_event_poll_seconds", 0.25) or 0.25)
    while True:
        try:
            if not hvx_breaker.allow():
                await asyncio.sleep(min(2.0, poll * 4))
                continue
            with short_session() as db:
                specs = [
                    (int(c.id), int(c.sdk_handle))
                    for c in db.scalars(select(Camera).where(Camera.sdk_handle.is_not(None))).all()
                    if c.sdk_handle is not None
                ]
            started = time.perf_counter()
            for camera_id, handle in specs:
                try:
                    await _drain_camera_events(camera_id, handle)
                    hvx_breaker.success()
                    note_camera(camera_id, sdk_callback="ok", last_event_at=time.time())
                except Exception as exc:
                    hvx_breaker.failure()
                    note_worker_failure("camera-events", str(exc))
                    note_camera(camera_id, sdk_callback="error")
            latency_ms = int((time.perf_counter() - started) * 1000)
            for camera_id, _handle in specs:
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
    return {
        "id": row.id, "name": row.name, "car_type": row.car_type, "currency": row.currency,
        "source": row.source, "rules": row.rules, "active": row.active,
    }


def session_dict(row: ParkingSession) -> dict:
    return sim_session_dict(row)


@app.get("/fees/tariff")
def get_fee_tariff(db: Session = Depends(get_db), _: User = Depends(require("fees.view"))):
    row = ensure_car1_tariff(db)
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
    alpr = recognize_bytes(jpeg, camera_label=file.filename or "sim-upload")
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
    if camera is not None:
        box = best.get("bbox") if isinstance(best.get("bbox"), dict) else None
        persist_event(
            db, camera, jpeg=jpeg, crop=b"",
            capture={
                "plate": plate,
                "score": float(best.get("confidence") or 0) * 100,
                "bbox": box,
                "image_id": int(time.time() * 1000) % 2_000_000_000,
            },
        )
    try:
        result = await handle_plate_event(
            db, plate=plate, gate=gate, side=side, simulated=True, alpr=alpr, source="fastalpr-upload",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    write_audit(db, user, "sim.capture", "parking_session", str((result.get("session") or {}).get("id") or ""), f"{plate} {side}")
    db.commit()
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
async def session_receipt_taken(session_id: int, db: Session = Depends(get_db), user: User = Depends(require_any("simulation.run", "gates.open"))):
    return await sim_receipt_taken(session_id, db, user)


@app.post("/sim/sessions/{session_id}/pay")
def sim_pay(session_id: int, db: Session = Depends(get_db), user: User = Depends(require("simulation.run"))):
    row = db.get(ParkingSession, session_id)
    if not row:
        raise HTTPException(404, "Session not found")
    row = mark_paid(db, row, operator_id=user.id, method="KIOSK_CASH")
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
    row = mark_paid(db, row, operator_id=user.id, method=method)
    write_audit(db, user, "payments.create", "parking_session", str(row.id), f"{row.plate} {row.amount_paid} {method}")
    db.commit()
    return sim_session_dict(row)


@app.get("/payments")
def list_payments(db: Session = Depends(get_db), _: User = Depends(require_any("payments.view", "fees.view", "kiosk.use"))):
    return [transaction_dict(row) for row in list_transactions(db)]


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
    row = db.scalar(select(ParkingSession).where(ParkingSession.public_token == token))
    if not row:
        raise HTTPException(404, "Receipt not found")
    if row.status not in ("CLOSED",):
        from app.services.simulation import quote_session
        quote_session(db, row)
    due = float(row.amount_due or 0)
    paid = float(row.amount_paid or 0)
    remaining = max(0.0, due - paid)
    kind = getattr(row, "parker_kind", None) or "CASUAL"
    entry = row.entry_time.strftime("%d %b %Y %H:%M") if row.entry_time else "—"
    status_label = "PAID" if paid + 0.0001 >= due and row.status in ("PAID", "CLOSED") else row.status
    if remaining <= 0 and row.status not in ("CLOSED",):
        status_label = "PAID" if row.status == "PAID" else "NO CHARGE YET"
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Parking — {row.plate}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
      body{{font:16px/1.45 system-ui,sans-serif;margin:0;background:#f5f7fb;color:#172033}}
      main{{max-width:420px;margin:0 auto;padding:24px}}
      .plate{{font-size:28px;letter-spacing:.12em;font-weight:700}}
      .card{{background:#fff;border:1px solid #dfe5ef;border-radius:12px;padding:20px;margin:16px 0}}
      .due{{font-size:26px;font-weight:700}}
      .muted{{color:#5b6b82}}
      img.qr{{width:160px;height:160px}}
      .btn{{display:block;text-align:center;background:#1f5eff;color:#fff;text-decoration:none;
           border-radius:8px;padding:12px;margin-top:12px;font-weight:600}}
      .btn.secondary{{background:#eef2f8;color:#172033}}
    </style></head>
    <body><main>
    <p class="muted">{settings.site_name}</p>
    <p class="plate">{row.plate}</p>
    <div class="card">
      <p>Entry {entry}</p>
      <p>{kind} · {status_label}</p>
      <p class="due">TZS {remaining:,.0f}</p>
      <p class="muted">Amount due now. Paid TZS {paid:,.0f} of {due:,.0f}.</p>
      <a class="btn secondary" href="#kiosk">Pay at kiosk</a>
    </div>
    <p><img class="qr" src="/p/{token}/qr.png" alt="QR"></p>
    <p class="muted" id="kiosk">Pay at the kiosk, or keep this page. Lost paper is OK — the plate is the identity. Mobile money will appear here when the site provider is connected.</p>
    </main></body></html>"""
    return HTMLResponse(html)


@app.get("/p/{token}/qr.png", include_in_schema=False)
def public_receipt_qr(token: str, db: Session = Depends(get_db)):
    row = db.scalar(select(Receipt).where(Receipt.public_token == token).order_by(Receipt.id.desc()))
    path = Path(row.qr_path) if row and row.qr_path else None
    if path and path.exists():
        return FileResponse(path, media_type="image/png")
    from app.services.receipts import _qr_png
    png = _qr_png(f"/p/{token}")
    if not png:
        raise HTTPException(404, "QR not available")
    return Response(content=png, media_type="image/png")


@app.get("/dashboard")
def dashboard_stats(db: Session = Depends(get_db), _: User = Depends(require_any("dashboard.view", "cameras.view"))):
    from app.services.cache import dashboard_cache
    from app.services.runtime import startup_state
    from app.services.simulation import OPEN_STATUSES

    cached = dashboard_cache.get("overview")
    if cached is not None:
        return cached
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
        "unpaid_active": int(unpaid_active),
        "subscribers_inside": int(subscribers_inside),
        "alerts": alerts,
        "receipt_policies": list(RECEIPT_POLICIES),
        "runtime": {"state": startup_state(), "version": settings.app_version},
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
    from app.services.receipts import _qr_png
    cfg = parking_settings(db)
    token = "TEST"
    public_url = "/p/TEST"
    document = ReceiptDocument(
        site_name=settings.site_name or settings.app_name,
        plate="T000TST",
        entry_time="Test print",
        entry_gate="Simulation",
        public_reference=token,
        public_url=public_url,
        payment_instructions="This is a SmartPark test page for the USB A4 printer.",
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
