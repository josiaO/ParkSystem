from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from html import escape
import asyncio
import json
import logging
import mimetypes
import time

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.config import settings
from app.db import Base, engine, ensure_schema, get_db, short_session, SessionLocal, release_connection
from app.domain.site import DEFAULT_SITE_ID
from app.models import AccessPlan, AccessDecision, AuditLog, Camera, CameraStatus, Gate, GateCommandRecord, GateMode, Node, NodeGateAssignment, ParkingEntryClaim, ParkingSession, PaymentIntent, PaymentTransaction, Receipt, RegisteredVehicle, Role, Site, Tariff, User, VehicleCapture
from app.schemas import (
    CameraCreate, CameraFramingUpdate, CameraImport, CameraOnboardProbe, CameraOnboardTest, CameraUpdate, FeeQuoteRequest, FusionRequest, GateCreate, GateUpdate, LedWrite,
    LoginRequest, LoginResponse, ManualGateCommand, MigrationFlagsUpdate, ModelPackRequest, ParkingSettingsUpdate, PaymentConfirm, PublicPaymentIntentRequest, ExitQrScanRequest, PlateCorrection, PlateEngineCorrection, SessionCreate, SimEntryRequest, SimExitRequest,
    SitePolicyUpdate, StreamProfilesUpdate, UserCreate, UserUpdate, AccessPlanCreate, AccessPlanUpdate, VehicleCreate, VehicleUpdate,
    VehicleBulkCreate, VehicleBulkDelete, TariffEditorUpdate, BackupSettingsUpdate,
    ModuleProfileApply, ModuleEnablement, ZoneCreate, LaneCreate, OnboardingStep, AIIncidentSummaryRequest,
    RecognitionScopeUpdate, DeveloperSettingsUpdate, DeveloperDeleteRequest,
)
from app.security import authenticate_processing_node, authenticate_user, create_session, current_node, current_user, oauth2_scheme, processing_node_permissions, require, require_any, require_media, revoke_session, user_permissions
from app.core.fusion import resolve_readings
from app.infrastructure.recognition.engines import active_engine, list_engines, recognize_frame
from app.infrastructure.recognition.engines.training import apply_model_pack, record_correction, training_status
from app.services.alpr import status as alpr_status
from app.services.redaction import redact_text

log = logging.getLogger("smartpark")
from app.services.audit import write_audit
from app.services.bootstrap import ensure_bootstrap_admin, setup_status
from app.services.captures import captures_for_sessions, capture_dict, latest_for_camera, latest_for_cameras, list_captures, list_recent_detections, persist_event, should_persist_vehicle_capture
from app.services.fee_engine import calculate_car1_fee, ensure_car1_tariff, load_active_rules
from app.services.gates import controller
from app.services.led_udp import send_led_text
from app.services.hvx_client import HVXHostClient, HVXHostUnavailable
from app.services.hvx_vendor import vendor_inventory
from app.services.camera_lpr import choose_overlay_box, fit_plate_box, live_plate_overlay, local_from_fastalpr, native_from_sdk_capture
from app.services.ocr_policy import fusion_mode, should_run_local, software_ocr_enabled
from app.services.presence import coil_watch
from app.services.site_policy import site_policy
from app.services.preview import (
    MJPEG_BOUNDARY, CameraLiveSpec, acquire_detect, acquire_live, get_state, media_path, mjpeg_from_cache, mjpeg_parts,
    pumping_spec, release_detect, release_live, remember_alpr, remember_frame, remember_last_car, remember_plate_box, held_plate_box, remember_viewer_transport, fresh_alpr, fresh_last_car, snapshot_for_camera, start_idle_watch,
    watch_live, live_is_current,
    start_live_pump, stop_live_pump, stop_live_pumps, touch_live, viewers_for,
)
from app.services.http_snapshot import grab_http_snapshot
from app.services.ipcam_discover import generic_discovery_row, scan_lan_devices
from app.services.rtsp_probe import probe, vendor_candidates
from app.services.site_cameras import (
    KNOWN_SITE_CAMERAS, camera_spec_for_ip, discovery_row,
    probe_ips, side_label, site_camera_defaults, tcp_open, seed_site_lanes, flatten_site_cameras,
)
from app.services.simulation import (
    handle_exit, handle_plate_event, mark_paid, parking_settings,
    save_parking_settings, session_dict as sim_session_dict, take_receipt,
)
from app.services.users import create_user, delete_user, load_user, load_users, update_user, user_dict
from app.services.node_authorization import hash_node_credential, issue_node_session, verify_node_credential
from app.services.access import ensure_access_plans, lookup_entitlement, plan_dict, vehicle_dict
from app.services.receipts import RECEIPT_POLICIES, issue_receipt, receipt_dict
from app.core.plate import normalize_plate
from app.infrastructure.hardware.printers import list_system_printers, printer_adapter
from app.infrastructure.hardware.cameras import (
    adapter_has_native_plates,
    adapter_requires_native_stream,
    camera_adapter_for,
)
from app.infrastructure.hardware.edge import edge_agent_status
from app.infrastructure.hardware.registry import camera_adapter_id, camera_connection_mode, devices_as_dicts
from app.infrastructure.payments.ledger import list_transactions, transaction_dict

WEB_DIR = Path(__file__).resolve().parents[1] / "web"

# Manual reads are operator tools, not part of the production recognition
# pipeline.  Keep them single-flight so repeated button clicks cannot create a
# second ONNX workload in the Site Service process.
_manual_alpr_lock = asyncio.Lock()
_manual_alpr_pending: asyncio.Task | None = None
_local_alpr_pending: dict[int, asyncio.Task] = {}
_local_watch_tasks: dict[int, asyncio.Task] = {}
_live_still_digests: dict[str, str] = {}


def _camera_for_node(db: Session, camera_id: int, *, action: str = "access") -> Camera:
    """Load a camera only when this process owns its gate.

    Recognition/connect already used the node scope, but the live API used to
    accept any camera id.  That made a node request another node's local
    MediaMTX/SDK path and could make the UI show the wrong gate.  Keep the
    boundary here, immediately before any operation that can touch a camera
    or its media producer.
    """
    camera = get_camera_or_404(db, camera_id)
    from app.services.node_scope import camera_active_on_this_installation, camera_in_recognition_scope, is_processing_node

    # The Site Server owns the complete registry and may inspect/configure any
    # camera, but it must not touch the hardware plane of a gate assigned to
    # an Edge Node.  Keep non-hardware registry reads/configuration global.
    registry_actions = {
        "camera-read", "viewer-state", "stream-telemetry", "stream-profile-update",
        "framing-update", "recognition-commissioning-read",
    }
    if not is_processing_node() and (action in registry_actions or camera_active_on_this_installation(camera, db=db)):
        return camera
    if is_processing_node() and camera_in_recognition_scope(camera, db=db):
        return camera
    scope = None
    try:
        from app.services.node_scope import describe_recognition_scope

        scope = describe_recognition_scope(db)
    except Exception:
        scope = {}
    log.warning(
        "node scope denied action=%s camera_id=%s camera_gate_id=%s node_id=%s assigned_gate_id=%s",
        action,
        camera.id,
        camera.gate_id,
        getattr(settings, "node_id", ""),
        scope.get("gate_id") if isinstance(scope, dict) else None,
    )
    raise HTTPException(
        status_code=409 if not is_processing_node() else 403,
        detail=(
            "This camera is operated by another Edge Node. Use the owning node for hardware actions."
            if not is_processing_node()
            else "This camera belongs to another node's assigned gate. Connect to the owning node or assign this PC to the camera's gate."
        ),
    )


def _processing_node_gate_id(db: Session, *, required: bool = True) -> int | None:
    """Return this process's dynamic gate assignment, never a hardcoded ID."""
    from app.services.node_scope import is_processing_node, recognition_gate_id

    if not is_processing_node():
        return None
    assigned = sorted(_processing_node_gate_ids(db, required=required))
    gate_id = assigned[0] if len(assigned) == 1 else None
    if gate_id is None and required:
        raise HTTPException(409, "Assign this Processing Node to a gate before adding or controlling cameras.")
    return int(gate_id) if gate_id is not None else None


def _processing_node_gate_ids(db: Session, *, required: bool = True) -> set[int]:
    from app.services.node_scope import authoritative_node_gate_ids, is_processing_node, recognition_gate_id

    if not is_processing_node():
        return set()
    assigned = set(authoritative_node_gate_ids(db))
    if assigned:
        return assigned
    legacy = recognition_gate_id(db)
    if legacy is not None:
        return {int(legacy)}
    if required:
        raise HTTPException(409, "Assign this Processing Node to a gate before adding or controlling cameras.")
    return set()


def _gate_for_node(db: Session, gate_id: int, *, action: str = "access") -> Gate:
    """Load a gate only when this installation owns its camera lane."""
    gate = get_gate_or_404(db, gate_id)
    from app.services.node_scope import authoritative_node_gate_ids, is_processing_node
    assigned_gate_ids = authoritative_node_gate_ids(db)
    node_gate_id = _processing_node_gate_id(db, required=False)

    if is_processing_node() and ((assigned_gate_ids and int(gate.id) not in assigned_gate_ids) or (not assigned_gate_ids and (node_gate_id is None or int(gate.id) != int(node_gate_id)))):
        log.warning(
            "node scope denied action=%s gate_id=%s node_id=%s assigned_gate_id=%s",
            action, gate.id, getattr(settings, "node_id", ""), node_gate_id,
        )
        raise HTTPException(403, "This gate belongs to another node. Use the owning Processing Node or the Site Server.")
    return gate


def _camera_mutation_for_node(db: Session, camera_id: int, *, action: str) -> Camera:
    """Guard a camera mutation and ensure it belongs to this node's gate."""
    return _camera_for_node(db, camera_id, action=action)


def _consume_background_task(task: asyncio.Task) -> None:
    """Consume a detached timeout task's exception so it is never orphaned."""
    try:
        task.result()
    except BaseException:
        pass


async def _supervise_background_loop(name: str, factory, *, restart_delay: float = 2.0) -> None:
    """Keep a diagnostic/control loop observable and restartable.

    A failed asyncio task otherwise disappears while the parent process and
    its health endpoint continue to look alive.  This wrapper is intentionally
    limited to non-authoritative diagnostics; it never retries gate commands
    or camera control calls.
    """
    while True:
        try:
            await factory()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("background loop failed name=%s; restarting", name)
            await asyncio.sleep(restart_delay)
        else:
            log.warning("background loop exited name=%s; restarting", name)
            await asyncio.sleep(restart_delay)


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
    # Use this role for the local node login. The installation-level guard in
    # app.security remains authoritative even if somebody accidentally uses a
    # broader shared-database token on a Processing Node.
    "Processing Node": ",".join([
        "cameras.view", "cameras.manage", "cameras.connect", "gates.view",
        "gates.open", "gates.open_simulated", "hardware.view",
    ]),
}


async def _diagnostic_heartbeat_loop() -> None:
    """Write one compact, redacted health snapshot for Windows support bundles.

    This intentionally samples state rather than frames.  It makes reconnects,
    frozen producers, decoder errors, and worker ownership visible without
    turning the service log into a per-frame trace.
    """
    from app.services.media_gateway import gateway
    from app.recognition_worker import worker_health

    previous_signature = None
    last_media_prune = 0.0
    while True:
        try:
            if time.monotonic() - last_media_prune >= 6 * 3600:
                from app.services.captures import prune_unreferenced_media
                with short_session() as db:
                    cleanup = prune_unreferenced_media(db)
                log.info("MEDIA retention cleanup scanned=%s removed=%s days=%s", cleanup["scanned"], cleanup["removed"], cleanup["retention_days"])
                last_media_prune = time.monotonic()
            media_rows = gateway.live_metrics()
            worker = worker_health()
            cameras = []
            for row in media_rows:
                cameras.append({
                    "camera_id": row.get("camera_id"),
                    "state": row.get("connection_state"),
                    "pumping": bool(row.get("pumping")),
                    "fps": row.get("fps"),
                    "frame_age_ms": row.get("live_frame_age_ms"),
                    "reconnects": row.get("reconnects", 0),
                    "decoder_restarts": row.get("decoder_restarts", 0),
                    "frozen": bool(row.get("frozen")),
                    "queue_depth": row.get("queue_depth", 0),
                    "warnings": list(row.get("warnings") or [])[:4],
                })
            degraded = [row for row in cameras if row["frozen"] or row["state"] not in {"STREAMING", "READY"} or row["warnings"]]
            snapshot = {
                "event": "runtime-heartbeat",
                "cameras": cameras,
                "camera_count": len(cameras),
                "degraded_camera_ids": [row["camera_id"] for row in degraded],
                "worker": {
                    "ok": bool(worker.get("ok")),
                    "state": worker.get("state"),
                    "heartbeat_age_seconds": worker.get("heartbeat_age_seconds"),
                    "claimed_camera_ids": worker.get("claimed_camera_ids") or [],
                    "camera_states": [
                        {key: value for key, value in item.items() if key in {"camera_id", "state", "last_error", "reconnects", "stale_dropped", "recognition_stalls", "recognition_restarts"}}
                        for item in (worker.get("cameras") or []) if isinstance(item, dict)
                    ],
                },
            }
            signature = json.dumps(snapshot, sort_keys=True, default=str)
            if signature != previous_signature or degraded or not snapshot["worker"]["ok"]:
                level = log.warning if degraded or not snapshot["worker"]["ok"] else log.info
                level("RUNTIME %s", signature)
                previous_signature = signature
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("RUNTIME heartbeat failed: %s", redact_text(repr(exc)))
        await asyncio.sleep(30.0)


def ensure_roles(db: Session):
    for name, permissions in DEFAULT_ROLES.items():
        role = db.scalar(select(Role).where(Role.name == name))
        if not role:
            db.add(Role(name=name, permissions_csv=permissions, system_role=True))
        elif role.system_role:
            role.permissions_csv = permissions
    db.commit()


async def _warmup_alpr_background() -> None:
    """Load the local detector before the first vehicle reaches a lane."""
    from app.services.alpr import warmup

    try:
        result = await asyncio.to_thread(warmup)
        log.info("FastALPR warm-up ready: %s", result)
    except Exception as exc:
        log.error("FastALPR warm-up failed: %s", redact_text(f"{type(exc).__name__}: {exc}"), exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services.logging_setup import configure_logging
    from app.services.runtime import install_asyncio_exception_filter, mark_core_ready, set_process_name, set_startup_state

    configure_logging("site-service")
    set_process_name("SmartParkSiteService")
    set_startup_state("STARTING")
    install_asyncio_exception_filter()
    from app.db import engine
    from app.services.node_scope import is_processing_node

    processing_node = is_processing_node()
    if processing_node:
        # A Processing Node joins an already-initialized Site Server database.
        # It must never run migrations, bootstrap an admin, create default site
        # data, repair tariffs/modules, or rewrite central topology on startup.
        from app.migrations.runner import status as schema_status

        schema = schema_status(engine)
        if not schema.get("up_to_date"):
            raise RuntimeError(
                "Processing Node requires the Site Server database schema to be current; "
                "run the upgrade on the Site Server first."
            )
    else:
        ensure_schema()
    log.info("Site database ready: %s", engine.url.render_as_string(hide_password=True))
    with SessionLocal() as db:
        # Site-scoped rows (tariffs, access plans, cameras and gates) all have
        # a foreign key to sites.  PostgreSQL enforces that relationship
        # immediately, so the parent site must exist before any default row is
        # inserted.  SQLite often hid this ordering bug because foreign-key
        # enforcement is not enabled in every local/test connection.
        from app.services.topology import ensure_default_site, sync_gate_lanes_from_cameras

        if not processing_node:
            ensure_default_site(db)
            ensure_roles(db)
            ensure_bootstrap_admin(db)
            ensure_car1_tariff(db)
            ensure_access_plans(db)
            from app.services.modules import ensure_modules_initialized

            ensure_modules_initialized(db)
            sync_gate_lanes_from_cameras(db)
            from app.services.secrets_migration import migrate_plaintext_secrets

            try:
                migrate_plaintext_secrets(db)
            except Exception as exc:  # a secret-store problem must not stop parking
                log.warning("secrets migration skipped: %s", exc)
        else:
            log.info("Processing Node startup is read-only for central bootstrap, schema, modules, tariffs, and topology")
            from app.services.node_scope import ensure_processing_node_registry

            node = ensure_processing_node_registry(db)
            if node is not None:
                log.info(
                    "Processing Node registry identity=%s status=%s site_id=%s; gate ownership remains centrally assigned",
                    node.node_id,
                    node.status,
                    node.site_id,
                )
            else:
                log.warning("Processing Node identity=%s is not registered; shared Site Server database has no site row or registry write failed", settings.node_id)
        from app.services.node_scope import describe_recognition_scope

        try:
            scope = describe_recognition_scope(db)
            log.info(
                "NODE ownership node_id=%s node_role=%s deployment_profile=%s database=%s media_dir=%s assigned_gate_id=%s camera_ids=%s",
                settings.node_id,
                settings.node_role,
                settings.deployment_profile,
                engine.url.get_backend_name(),
                settings.media_dir,
                scope.get("gate_id"),
                [row.get("id") for row in scope.get("cameras") or []],
            )
        except Exception as exc:
            log.warning("NODE ownership scope unavailable: %s", redact_text(repr(exc)))
    alpr_warmup_task = None
    try:
        alpr = alpr_status()
        log.info(
            "FastALPR startup installed=%s available=%s detector=%s ocr=%s detail=%s",
            alpr.get("installed"),
            alpr.get("available"),
            (alpr.get("models") or {}).get("detector"),
            (alpr.get("models") or {}).get("ocr"),
            alpr.get("detail"),
        )
        if alpr.get("available"):
            alpr_warmup_task = asyncio.create_task(_warmup_alpr_background(), name="alpr-warmup")
    except Exception as exc:
        log.error("FastALPR startup check failed: %s", redact_text(f"{type(exc).__name__}: {exc}"), exc_info=True)
    mark_core_ready()
    start_idle_watch()
    # MediaMTX has one owner: SmartParkMediaService.  The Site Service only
    # consumes its local control/stream endpoints and must not spawn a competing
    # sidecar process.
    from app.services import hybrid_fusion
    hybrid_fusion.set_persist(_persist_capture_event)
    ingest = asyncio.create_task(_camera_event_loop(), name="camera-events")
    outbox = asyncio.create_task(_outbox_loop(), name="parking-outbox")
    hvx_watch = asyncio.create_task(_hvx_watch_loop(), name="hvx-watch")
    fusion_flush = asyncio.create_task(_fusion_flush_loop(), name="hybrid-fusion-flush")
    payments_reconcile = asyncio.create_task(_payments_reconcile_loop(), name="payments-reconcile")
    from app.services import onvif_runtime
    onvif_runtime.set_persist(_onvif_capture)
    onvif_events = asyncio.create_task(_onvif_events_loop(), name="onvif-events")
    diagnostics = asyncio.create_task(
        _supervise_background_loop("diagnostic-heartbeat", _diagnostic_heartbeat_loop),
        name="diagnostic-heartbeat",
    )
    try:
        yield
    finally:
        tasks = (ingest, outbox, hvx_watch, fusion_flush, payments_reconcile, onvif_events, diagnostics)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if alpr_warmup_task is not None:
            alpr_warmup_task.cancel()
            await asyncio.gather(alpr_warmup_task, return_exceptions=True)
        await onvif_runtime.shutdown()
        stop_live_pumps()
        from app.services.hvx_client import close_host_clients
        await close_host_clients()
        # Do not stop MediaMTX here; SmartParkMediaService owns that process.
        set_startup_state("OFFLINE")


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
from app.api.module_routes import ModuleRoute
from app.services.public_ingress import PublicIngressGuard
app.router.route_class = ModuleRoute
# Requests arriving via the public payments tunnel may only reach /p/*,
# /api/public/* and /api/webhooks/*. No-op when no ingress host is configured.
app.add_middleware(PublicIngressGuard)


@app.exception_handler(HTTPException)
async def _redacted_http_exception(request: Request, exc: HTTPException):
    """Error bodies never carry RTSP passwords, provider keys or webhook hashes."""
    from app.services.redaction import redact_obj

    return JSONResponse({"detail": redact_obj(exc.detail)}, status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(Exception)
async def _redacted_unhandled_exception(request: Request, exc: Exception):
    """Unhandled errors log the redacted traceback and return a redacted message."""
    from app.services.redaction import redact_text

    log.error("unhandled error on %s %s: %s", request.method, request.url.path, redact_text(repr(exc)), exc_info=exc)
    return JSONResponse({"detail": redact_text(f"{type(exc).__name__}: {exc}")[:400]}, status_code=500)


def _login_response(db: Session, username: str, password: str) -> LoginResponse:
    from app.services.modules import ensure_modules_initialized, load_config, navigation_items
    from app.services.node_scope import is_processing_node

    processing_node = is_processing_node()
    user = authenticate_processing_node(db, username, password) if processing_node else authenticate_user(db, username, password)
    token = create_session(db, user)
    if not processing_node:
        ensure_modules_initialized(db)
    # Human permissions are independent of installation role. Machine runtime
    # calls use the separate node principal/session API.
    perms = processing_node_permissions(user_permissions(user))
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


@app.get("/assets/mediamtx-reader.js", include_in_schema=False)
def mediamtx_reader():
    return FileResponse(WEB_DIR / "mediamtx-reader.js", media_type="application/javascript")


@app.get("/assets/{asset_path:path}", include_in_schema=False)
def web_asset(asset_path: str):
    """Serve versioned browser modules without exposing files outside assets."""
    asset_root = (WEB_DIR / "assets").resolve()
    target = (asset_root / asset_path).resolve()
    try:
        target.relative_to(asset_root)
    except ValueError as exc:
        raise HTTPException(404, "Web asset not found") from exc
    if not target.is_file():
        raise HTTPException(404, "Web asset not found")
    media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(target, media_type=media_type)


@app.get("/assets/zirp-logo.png", include_in_schema=False)
def zirp_logo():
    return FileResponse(WEB_DIR / "assets" / "zirp-logo.png", media_type="image/png")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(WEB_DIR / "assets" / "zirp.ico", media_type="image/x-icon")


@app.get("/downloads/zirp-installer.zip", include_in_schema=False)
def download_zirp_installer():
    """Download a clean installer package for another LAN computer.

    This endpoint deliberately excludes ``settings.data_dir``.  It can be
    linked from the unauthenticated login page because the archive contains
    application/runtime files only, never this site's database or secrets.
    """
    try:
        from app.services.installer_download import build_installer_archive

        archive = build_installer_archive()
    except (FileNotFoundError, OSError, ValueError) as exc:
        log.warning("LAN installer download unavailable: %s", redact_text(str(exc)))
        raise HTTPException(404, "The installer package is not available on this installation") from exc
    return FileResponse(
        archive,
        media_type="application/zip",
        filename="Zirp-Installer.zip",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/health")
def health():
    from app.services.health import live
    return live()


@app.get("/health/live")
def health_live():
    from app.services.health import live
    return live()


@app.get("/deployment/info")
def deployment_info():
    """Public, non-secret identity used when pairing an operator workstation."""
    from app.deployment import public_server_identity

    return public_server_identity()


@app.get("/health/ready")
def health_ready():
    from app.services.health import ready
    body = ready()
    if not body.get("ok"):
        return JSONResponse(body, status_code=503)
    return body


@app.get("/health/database")
def health_database():
    """Non-secret database readiness for the deployment wizard and support staff."""
    from app.services.health import database_health

    body = database_health()
    return JSONResponse(body, status_code=200 if body.get("state") == "HEALTHY" else 503)


@app.get("/health/details")
def health_details(_: User = Depends(require("hardware.view"))):
    from app.services.health import details
    return details()


@app.get("/health/diagnostics")
def health_diagnostics(db: Session = Depends(get_db), _: User = Depends(require("hardware.view"))):
    """Support bundle: health, schema, secrets backend, cameras. Always redacted."""
    from app.services.diagnostics import bundle
    return bundle(db, local_only=True)


@app.get("/health/realtime")
async def health_realtime(request: Request, db: Session = Depends(get_db), _: User = Depends(require("hardware.view"))):
    """Per-camera live/recognition snapshot for field diagnosis. No credentials."""
    from app.services.recognition_runtime import runtime
    from app.infrastructure.media.registry import get_live_endpoint, live_provider_label, media_telemetry
    from app.services.preview import viewer_live_provider
    from app.services.health import camera_stats
    from app.services.lane_timing import timeline_metrics

    cameras = list(db.scalars(select(Camera).order_by(Camera.id)).all())
    from app.services.node_scope import camera_active_on_this_installation
    cameras = [camera for camera in cameras if camera_active_on_this_installation(camera, db=db)]
    rows = []
    for camera in cameras:
        endpoint = await get_live_endpoint(int(camera.id), db)
        from app.services.whep import browser_endpoint
        endpoint = browser_endpoint(endpoint, request)
        negotiated = viewer_live_provider(int(camera.id))
        if negotiated:
            endpoint = {**endpoint, "viewer_transport": negotiated}
        rec = runtime.lane(int(camera.id)).snapshot()
        media = _camera_media_brief(int(camera.id)) or {}
        extra = camera_stats(int(camera.id))
        source = (media_telemetry(camera.id).get("roles") or {}).get("LIVE") or {}
        state = get_state(camera.id)
        fresh_jpeg = bool(state.jpeg[:2] == b"\xff\xd8" and state.captured_at and time.monotonic() - state.captured_at < settings.stale_stream_seconds)
        rows.append({
            "camera_id": int(camera.id),
            "camera_name": camera.name,
            "visit_latency_ms": timeline_metrics(camera.id),
            "live_provider": live_provider_label(endpoint),
            "configured_transport": endpoint.get("transport"),
            "viewer_transport": negotiated or "",
            "live_connected": live_is_current(camera.id),
            "last_frame_at": rec.get("last_frame_at"),
            "frame_seq": rec.get("frame_seq"),
            "fps": media.get("fps") or get_state(camera.id).fps,
            "estimated_frame_age_ms": media.get("live_frame_age_ms"),
            "ai_frame_age_ms": media.get("ai_frame_age_ms"),
            "recognition_state": rec.get("recognition_state"),
            "recognition_generation": rec.get("recognition_generation"),
            "recognition_inflight": rec.get("recognition_inflight"),
            "recognition_frame_seq": rec.get("recognition_frame_seq"),
            "last_recognition_completed_at": rec.get("last_recognition_completed_at"),
            "last_plate": rec.get("last_plate"),
            "last_plate_age_ms": rec.get("last_plate_age_ms"),
            "vehicle_present": rec.get("vehicle_present"),
            "visit_id": rec.get("visit_id"),
            "dropped_ai_frames": rec.get("dropped_ai_frames"),
            "recognition_stalls": rec.get("recognition_stalls"),
            "recognition_restarts": rec.get("recognition_restarts"),
            "native_events_received": rec.get("native_events_received"),
            "software_reads": rec.get("software_reads"),
            "published_events": rec.get("published_events"),
            "duplicate_events_suppressed": rec.get("duplicate_events_suppressed"),
            "sessions_created": rec.get("sessions_created"),
            "pending_queue_depth": rec.get("pending_queue_depth"),
            "inference_ms_p50": rec.get("inference_ms_p50"),
            "inference_ms_p95": rec.get("inference_ms_p95"),
            "inference_ms_max": rec.get("inference_ms_max"),
            "reconnects": int(media.get("reconnects") or extra.get("reconnect_count") or 0),
            "frozen": bool(media.get("frozen")),
            "duplicate_frames": int(media.get("duplicate_frames") or 0),
            "frames_changed": int(media.get("frames_changed") or 0),
            "queue_depth": int(media.get("queue_depth") or 0),
        })
    return {
        "cameras": rows,
        "scheduler": runtime.scheduler.snapshot(),
        "worker": __import__("app.recognition_worker", fromlist=["worker_health"]).worker_health(),
    }


@app.get("/cameras/{camera_id}/realtime")
async def camera_realtime(camera_id: int, request: Request, db: Session = Depends(get_db), _: User = Depends(require("hardware.view"))):
    body = await health_realtime(request, db)
    row = next((item for item in body["cameras"] if item["camera_id"] == int(camera_id)), None)
    if row is None:
        raise HTTPException(404, "Camera not found")
    return row


@app.post("/cameras/{camera_id}/live/viewer-state")
def camera_viewer_state(
    camera_id: int,
    payload: dict = Body(default_factory=dict),
    db: Session = Depends(get_db),
    _: User = Depends(require("cameras.view")),
):
    _camera_for_node(db, camera_id, action="viewer-state")
    transport = str((payload or {}).get("transport") or "").upper()
    allowed = {"WEBRTC", "MEDIAMTX_WEBRTC", "MJPEG", "DIRECT_MJPEG", "SNAPSHOT", "OFFLINE"}
    remember_viewer_transport(camera_id, transport if transport in allowed else "")
    return {"ok": True, "transport": get_state(camera_id).viewer_transport}


@app.get("/auth/setup")
def auth_setup(db: Session = Depends(get_db)):
    from app.services.node_scope import is_processing_node
    if is_processing_node():
        # This endpoint historically created the bootstrap administrator when
        # queried. A node must never be able to bootstrap or reveal the site's
        # administrator, even though it uses the shared database for runtime
        # events.
        from app.deployment import load_deployment_config

        config = load_deployment_config()
        return {
            "ready": True,
            "username": config.node_username,
            "password": "",
            "first_run": False,
            "bootstrap_user_present": True,
            "bootstrap_password_ok": False,
            "usernames": [config.node_username] if config.node_username else [],
            "hint": "Sign in with this Processing Node's configured account. Site Administrator accounts cannot sign in here.",
        }
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
    from app.services.modules import ensure_modules_initialized, load_config, navigation_items
    from app.security import processing_node_permissions, user_permissions
    ensure_modules_initialized(db)
    perms = processing_node_permissions(user_permissions(user))
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


def _node_response(db: Session, node: Node, *, token: str | None = None) -> dict:
    assignments = db.scalars(
        select(NodeGateAssignment).where(
            NodeGateAssignment.node_id == node.id,
            NodeGateAssignment.enabled == True,  # noqa: E712
        )
    ).all()
    body = {
        "node_id": node.node_id,
        "name": node.name,
        "site_id": node.site_id,
        "node_type": node.node_type,
        "status": node.status,
        "capabilities": node.capabilities or {},
        "version": node.version,
        "assigned_gate_ids": [int(row.gate_id) for row in assignments],
    }
    if token:
        body.update({"token": token, "access_token": token, "token_type": "bearer"})
    return body


@app.post("/node/auth")
def node_login(payload: dict = Body(default_factory=dict), db: Session = Depends(get_db)):
    """Authenticate a physical runtime with its revocable node credential."""
    node_id = str(payload.get("node_id") or "").strip()
    credential = str(payload.get("credential") or payload.get("secret") or "")
    node = db.scalar(select(Node).where(Node.node_id == node_id))
    if node is None or node.status != "ACTIVE" or node.revoked_at is not None or not verify_node_credential(node.credential_hash, credential):
        raise HTTPException(status_code=401, detail="Invalid node identity or credential")
    token = issue_node_session(db, node)
    return _node_response(db, node, token=token)


@app.get("/node/me")
def node_me(principal=Depends(current_node), db: Session = Depends(get_db)):
    node = db.get(Node, principal.node_pk)
    if node is None:
        raise HTTPException(status_code=401, detail="Node unavailable")
    return _node_response(db, node)


@app.get("/node/config")
def node_config(principal=Depends(current_node), db: Session = Depends(get_db)):
    """Return only central configuration scoped to this node's assignments."""
    node = db.get(Node, principal.node_pk)
    if node is None:
        raise HTTPException(status_code=401, detail="Node unavailable")
    gate_ids = sorted({int(row.gate_id) for row in node.assignments if row.enabled})
    cameras = db.scalars(select(Camera).where(Camera.gate_id.in_(gate_ids))).all() if gate_ids else []
    return {
        "node": _node_response(db, node),
        "gates": [{"id": gate.id, "name": gate.name, "site_id": gate.site_id} for gate in db.scalars(select(Gate).where(Gate.id.in_(gate_ids))).all()] if gate_ids else [],
        "cameras": [{"id": camera.id, "name": camera.name, "gate_id": camera.gate_id, "lane_direction": camera.lane_direction} for camera in cameras],
    }


@app.post("/node/heartbeat")
def node_heartbeat(payload: dict = Body(default_factory=dict), principal=Depends(current_node), db: Session = Depends(get_db)):
    node = db.get(Node, principal.node_pk)
    if node is None:
        raise HTTPException(status_code=401, detail="Node unavailable")
    node.last_seen_at = datetime.now(timezone.utc)
    if payload.get("version") is not None:
        node.version = str(payload["version"])[:80]
    db.commit()
    return {"ok": True, "server_time": datetime.now(timezone.utc).isoformat(), **_node_response(db, node)}


@app.get("/nodes")
def list_nodes(db: Session = Depends(get_db), _: User = Depends(require("settings.view"))):
    from app.services.node_scope import site_server_can_manage_unassigned_cameras

    if not site_server_can_manage_unassigned_cameras():
        raise HTTPException(status_code=403, detail="Edge Node assignments are managed from the Site Server.")

    return [_node_response(db, node) for node in db.scalars(select(Node).order_by(Node.id)).all()]


@app.post("/nodes")
def register_node(payload: dict = Body(default_factory=dict), db: Session = Depends(get_db), _: User = Depends(require("settings.manage"))):
    from app.services.node_scope import site_server_can_manage_unassigned_cameras

    if not site_server_can_manage_unassigned_cameras():
        raise HTTPException(status_code=403, detail="Edge Node assignments are managed from the Site Server.")

    node_id = str(payload.get("node_id") or "").strip()
    credential = str(payload.get("credential") or "")
    if not node_id or len(credential) < 16:
        raise HTTPException(status_code=422, detail="node_id and a node credential of at least 16 characters are required")
    site_id = int(payload.get("site_id") or DEFAULT_SITE_ID)
    if db.get(Site, site_id) is None:
        raise HTTPException(status_code=404, detail="Site not found")
    if db.scalar(select(Node).where(Node.node_id == node_id)) is not None:
        raise HTTPException(status_code=409, detail="Node identity already exists")
    node = Node(
        node_id=node_id,
        site_id=site_id,
        name=str(payload.get("name") or node_id)[:160],
        node_type=str(payload.get("node_type") or "EDGE_NODE")[:40],
        credential_hash=hash_node_credential(credential),
        capabilities=dict(payload.get("capabilities") or {}),
        version=str(payload.get("version") or "")[:80],
    )
    db.add(node)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Node identity already exists") from None
    db.refresh(node)
    return _node_response(db, node)


@app.put("/nodes/{node_id}/assignments")
def assign_node_gate(node_id: str, payload: dict = Body(default_factory=dict), db: Session = Depends(get_db), _: User = Depends(require("settings.manage"))):
    from app.services.node_scope import site_server_can_manage_unassigned_cameras

    if not site_server_can_manage_unassigned_cameras():
        raise HTTPException(status_code=403, detail="Edge Node assignments are managed from the Site Server.")

    node = db.scalar(select(Node).where(Node.node_id == node_id))
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    gate_id = int(payload.get("gate_id") or 0)
    gate = db.get(Gate, gate_id)
    if gate is None:
        raise HTTPException(status_code=404, detail="Gate not found")
    if int(gate.site_id or DEFAULT_SITE_ID) != int(node.site_id or DEFAULT_SITE_ID):
        raise HTTPException(status_code=409, detail="Gate belongs to a different site")
    current_owner = db.scalar(
        select(NodeGateAssignment)
        .where(
            NodeGateAssignment.gate_id == gate.id,
            NodeGateAssignment.enabled.is_(True),
            NodeGateAssignment.node_id != node.id,
        )
    )
    if bool(payload.get("enabled", True)) and current_owner is not None:
        owner = db.get(Node, current_owner.node_id)
        raise HTTPException(
            status_code=409,
            detail=(
                f"Gate is already assigned to active node "
                f"{owner.node_id if owner else current_owner.node_id}. "
                "Disable that assignment before moving the gate."
            ),
        )
    if bool(payload.get("replace", False)):
        for existing in db.scalars(select(NodeGateAssignment).where(NodeGateAssignment.node_id == node.id)).all():
            existing.enabled = False
    row = db.scalar(select(NodeGateAssignment).where(NodeGateAssignment.node_id == node.id, NodeGateAssignment.gate_id == gate.id))
    if row is None:
        row = NodeGateAssignment(node_id=node.id, gate_id=gate.id, enabled=bool(payload.get("enabled", True)))
        db.add(row)
    else:
        row.enabled = bool(payload.get("enabled", True))
    db.commit()
    return _node_response(db, node)


@app.post("/nodes/{node_id}/revoke")
def revoke_node(node_id: str, db: Session = Depends(get_db), _: User = Depends(require("settings.manage"))):
    from app.services.node_scope import site_server_can_manage_unassigned_cameras

    if not site_server_can_manage_unassigned_cameras():
        raise HTTPException(status_code=403, detail="Edge Node assignments are managed from the Site Server.")

    node = db.scalar(select(Node).where(Node.node_id == node_id))
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    node.status = "REVOKED"
    node.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return _node_response(db, node)


@app.get("/modules")
def modules_list(db: Session = Depends(get_db), _: User = Depends(require("settings.view"))):
    from app.services.modules import list_modules, load_config

    return {"modules": list_modules(db), "config": load_config(db)}


@app.get("/modules/profiles")
def modules_profiles(_: User = Depends(require("settings.view"))):
    from app.services.modules import list_profiles

    return {"profiles": list_profiles()}


@app.get("/modules/navigation")
def modules_navigation(user: User = Depends(current_user), db: Session = Depends(get_db)):
    from app.services.modules import navigation_items
    from app.security import processing_node_permissions, user_permissions

    return {"navigation": navigation_items(db, processing_node_permissions(user_permissions(user)))}


@app.get("/modules/health")
def modules_health(db: Session = Depends(get_db), _: User = Depends(require("dashboard.view"))):
    from app.services.modules import module_health

    return module_health(db)


@app.put("/modules/profile")
def modules_apply_profile(
    payload: ModuleProfileApply,
    db: Session = Depends(get_db),
    _: User = Depends(require("settings.manage")),
):
    from app.services.modules import apply_profile

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
    from app.services.modules import set_enabled

    try:
        return set_enabled(db, payload.enabled, profile=payload.profile)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/topology")
def topology_get(db: Session = Depends(get_db), _: User = Depends(require("settings.view"))):
    from app.services.topology import site_topology

    return site_topology(db)


@app.post("/topology/zones")
def topology_create_zone(
    payload: ZoneCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require("settings.manage")),
):
    from app.services.topology import create_zone, zone_dict

    row = create_zone(db, site_id=payload.site_id, name=payload.name)
    return zone_dict(row)


@app.post("/topology/lanes")
def topology_create_lane(
    payload: LaneCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require("settings.manage")),
):
    from app.services.topology import create_lane, lane_dict

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
    from app.services.modules import onboarding_status

    return onboarding_status(db)


@app.post("/onboarding/step")
def onboarding_step_route(
    payload: OnboardingStep,
    db: Session = Depends(get_db),
    _: User = Depends(require("settings.manage")),
):
    from app.services.modules import save_onboarding_step

    try:
        return save_onboarding_step(db, payload.step, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
