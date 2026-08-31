"""Module registry runtime: enablement, profiles, navigation, health."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.domain.modules import (
    ALL_MODULE_IDS,
    DEFAULT_PROFILE,
    DEPLOYMENT_PROFILES,
    MODULES,
    NAVIGATION,
    NavItem,
    PROFILE_CUSTOM,
    PROFILE_ENTERPRISE,
    USE_CASE_TO_PROFILE,
)
from app.models import SiteSetting, User
from app.security import current_user, user_permissions

SETTINGS_KEY = "modules"

# Optional modules offered in onboarding step 5 (prompt §9).
OPTIONAL_MODULE_CHOICES: tuple[tuple[str, str, str], ...] = (
    ("security.watchlists", "Watchlists", "Allow/block lists for recognized plates."),
    ("security.alerts", "Alerts", "Alert rules and incident escalation."),
    ("parking.sessions", "Parking", "Entry/exit sessions and occupancy."),
    ("parking.tariffs", "Tariffs", "Versioned pricing rules."),
    ("parking.subscribers", "Subscribers", "Registered plates and access plans."),
    ("payments.core", "Payments", "Payment ledger and reconciliation."),
    ("payments.kiosk", "Kiosk", "Pay-on-exit kiosk workflow."),
    ("payments.public_web", "Public Payment", "Customer web payment connector."),
    ("reports", "Reports", "Operational reports and exports."),
)

RECOGNITION_MODES = ("NATIVE_ONLY", "FASTALPR_ONLY", "HYBRID", "VIDEO_ONLY")


def _default_config() -> dict[str, Any]:
    profile = DEFAULT_PROFILE
    enabled = _profile_modules(profile)
    return {
        "profile": profile,
        "enabled": sorted(enabled),
        "onboarding_completed": True,
        "onboarding_step": 8,
        "use_case": "PARKING",
        "recognition_default": "HYBRID",
    }


def _profile_modules(profile: str) -> set[str]:
    spec = DEPLOYMENT_PROFILES.get(profile) or DEPLOYMENT_PROFILES[DEFAULT_PROFILE]
    modules = spec.get("modules")
    if modules == "ALL":
        return set(ALL_MODULE_IDS)
    return set(modules or [])


def load_config(db: Session | None) -> dict[str, Any]:
    cfg = _default_config()
    if db is None:
        return cfg
    row = db.get(SiteSetting, SETTINGS_KEY)
    if row and isinstance(row.value, dict):
        stored = row.value
        if stored.get("profile"):
            cfg["profile"] = str(stored["profile"])
        if isinstance(stored.get("enabled"), list):
            cfg["enabled"] = sorted({m for m in stored["enabled"] if m in MODULES})
        for key in ("onboarding_completed", "onboarding_step", "use_case", "recognition_default",
                    "onboarding_hardware", "onboarding_health_ok"):
            if key in stored:
                cfg[key] = stored[key]
    profile = str(cfg.get("profile") or DEFAULT_PROFILE)
    enabled = set(cfg.get("enabled") or [])
    # Preset profiles always expand to their full module set. A truncated
    # enabled list (e.g. only core.sites) would hide Live Gates / Sessions.
    if profile != PROFILE_CUSTOM and profile in DEPLOYMENT_PROFILES:
        expected = _profile_modules(profile)
        if not enabled or not expected.issubset(enabled):
            enabled = expected
            cfg["enabled"] = sorted(enabled)
    elif not enabled:
        cfg["enabled"] = sorted(_profile_modules(DEFAULT_PROFILE))
        cfg["profile"] = DEFAULT_PROFILE
    return cfg


def save_config(db: Session, config: dict[str, Any]) -> dict[str, Any]:
    current = load_config(db)
    for key in ("profile", "onboarding_completed", "onboarding_step", "use_case",
                "recognition_default", "onboarding_hardware", "onboarding_health_ok"):
        if key in config:
            current[key] = config[key]
    if "enabled" in config and isinstance(config["enabled"], list):
        current["enabled"] = sorted({m for m in config["enabled"] if m in MODULES})
    row = db.get(SiteSetting, SETTINGS_KEY)
    if row is None:
        db.add(SiteSetting(key=SETTINGS_KEY, value=current))
    else:
        row.value = current
    db.commit()
    return current


def ensure_modules_initialized(db: Session) -> dict[str, Any]:
    cfg = load_config(db)
    row = db.get(SiteSetting, SETTINGS_KEY)
    if row is None:
        # First install: force the admin through the setup wizard.
        cfg = {
            **cfg,
            "onboarding_completed": False,
            "onboarding_step": 1,
        }
        db.add(SiteSetting(key=SETTINGS_KEY, value=cfg))
        db.commit()
        return cfg
    # Persist repaired preset enablement so UI and workers stay consistent.
    stored = row.value if isinstance(row.value, dict) else {}
    if stored.get("enabled") != cfg.get("enabled") or stored.get("profile") != cfg.get("profile"):
        row.value = {**stored, **{k: cfg[k] for k in ("profile", "enabled") if k in cfg}}
        # Keep onboarding flags from stored when present.
        for key in ("onboarding_completed", "onboarding_step", "use_case", "recognition_default"):
            if key in stored:
                row.value[key] = stored[key]
            elif key in cfg:
                row.value[key] = cfg[key]
        db.commit()
        return load_config(db)
    return cfg


def enabled_set(db: Session | None = None) -> set[str]:
    return set(load_config(db).get("enabled") or [])


def is_enabled(module_id: str, db: Session | None = None) -> bool:
    return module_id in enabled_set(db)


def validate_enablement(enabled: set[str]) -> list[str]:
    """Return list of validation errors (empty if valid)."""
    errors: list[str] = []
    unknown = enabled - set(MODULES)
    if unknown:
        errors.append(f"Unknown modules: {', '.join(sorted(unknown))}")
    for module_id in sorted(enabled):
        mod = MODULES[module_id]
        missing = [dep for dep in mod.required_dependencies if dep not in enabled]
        if missing:
            errors.append(f"{module_id} requires {', '.join(missing)}")
    return errors


def apply_profile(db: Session, profile: str, *, preserve_custom: bool = False) -> dict[str, Any]:
    if profile not in DEPLOYMENT_PROFILES:
        raise ValueError(f"Unknown profile: {profile}")
    if profile == PROFILE_CUSTOM and not preserve_custom:
        raise ValueError("Use set_enabled for CUSTOM profile changes")
    enabled = _profile_modules(profile)
    errors = validate_enablement(enabled)
    if errors:
        raise ValueError("; ".join(errors))
    current = load_config(db)
    current["profile"] = profile
    current["enabled"] = sorted(enabled)
    return save_config(db, current)


def set_enabled(db: Session, enabled: list[str], *, profile: str | None = None) -> dict[str, Any]:
    enabled_set_local = set(enabled)
    errors = validate_enablement(enabled_set_local)
    if errors:
        raise ValueError("; ".join(errors))
    current = load_config(db)
    current["enabled"] = sorted(enabled_set_local)
    current["profile"] = profile or PROFILE_CUSTOM
    return save_config(db, current)


def module_dict(module_id: str, *, enabled: bool) -> dict[str, Any]:
    mod = MODULES[module_id]
    return {
        "id": mod.id,
        "name": mod.name,
        "version": mod.version,
        "enabled": enabled,
        "required_dependencies": list(mod.required_dependencies),
        "optional_dependencies": list(mod.optional_dependencies),
        "permissions": list(mod.permissions),
        "routes": list(mod.routes),
        "navigation_items": list(mod.navigation_items),
        "background_jobs": list(mod.background_jobs),
        "health_checks": list(mod.health_checks),
    }


def list_modules(db: Session | None = None) -> list[dict[str, Any]]:
    active = enabled_set(db)
    return [module_dict(mid, enabled=mid in active) for mid in ALL_MODULE_IDS]


def list_profiles() -> list[dict[str, Any]]:
    rows = []
    for pid, spec in DEPLOYMENT_PROFILES.items():
        modules = _profile_modules(pid) if pid != PROFILE_CUSTOM else set()
        rows.append({
            "id": pid,
            "name": spec["name"],
            "description": spec["description"],
            "modules": sorted(modules),
        })
    return rows


def _nav_label(item: NavItem, profile: str) -> str:
    return item.profile_labels.get(profile, item.label)


def navigation_items(
    db: Session | None,
    permissions: set[str],
) -> list[dict[str, Any]]:
    cfg = load_config(db)
    profile = str(cfg.get("profile") or DEFAULT_PROFILE)
    active = enabled_set(db)
    rows: list[dict[str, Any]] = []
    for item in NAVIGATION:
        if item.module_id not in active:
            continue
        if item.permission and "*" not in permissions and item.permission not in permissions:
            continue
        # Hide setup wizard once onboarding is done (still reachable via API).
        if item.id == "onboarding" and cfg.get("onboarding_completed", True):
            continue
        rows.append({
            "id": item.id,
            "label": _nav_label(item, profile),
            "page": item.page,
            "group": item.group,
            "module_id": item.module_id,
            "permission": item.permission,
        })
    return rows


def job_allowed(job_name: str, db: Session | None = None) -> bool:
    active = enabled_set(db)
    for module_id in active:
        mod = MODULES.get(module_id)
        if mod and job_name in mod.background_jobs:
            return True
    return False


def module_health(db: Session | None = None) -> dict[str, Any]:
    from app.models import Camera, Gate
    from app.services.flags import flags as migration_flags
    from app.services import mediamtx
    _ = migration_flags  # rollout flags remain separate from module entitlement

    active = enabled_set(db)
    cfg = load_config(db)

    camera_total = camera_online = 0
    if db is not None:
        from sqlalchemy import select
        from app.models import Camera

        cameras = db.scalars(select(Camera).where(Camera.enabled == True)).all()  # noqa: E712
        camera_total = len(cameras)
        online_statuses = {"SDK_CONNECTED", "VIDEO_CONNECTED", "DEGRADED"}
        camera_online = sum(1 for c in cameras if c.status in online_statuses)

    def _state(module_id: str, *, healthy: bool | None = None, detail: str = "") -> dict[str, Any]:
        enabled = module_id in active
        if not enabled:
            return {"module_id": module_id, "state": "Disabled", "enabled": False, "detail": detail}
        if healthy is False:
            return {"module_id": module_id, "state": "Degraded", "enabled": True, "detail": detail}
        return {"module_id": module_id, "state": "Healthy" if healthy is not False else "Degraded", "enabled": True, "detail": detail}

    rows = {
        "CORE": _state("core.sites", healthy=True),
        "MEDIA": _state(
            "media.streaming",
            healthy=True,
            detail="MediaMTX optional" if "media.streaming" in active and not mediamtx.available() else "",
        ),
        "CAMERAS": {
            "module_id": "camera.management",
            "state": f"{camera_online}/{camera_total} Online" if "camera.management" in active else "Disabled",
            "enabled": "camera.management" in active,
            "detail": "",
        },
        "ALPR": _state("recognition.alpr", healthy=True, detail="Ready" if "recognition.alpr" in active else ""),
        "SECURITY": _state("security.watchlists", healthy=True, detail="Enabled" if "security.watchlists" in active else ""),
        "GATES": _state("access.gates", healthy=True),
        "PARKING": _state("parking.sessions", healthy=True),
        "PAYMENTS": _state("payments.core", healthy=True),
    }
    if "access.gates" not in active:
        rows["GATES"] = {"module_id": "access.gates", "state": "Disabled", "enabled": False, "detail": ""}
    if "parking.sessions" not in active:
        rows["PARKING"] = {"module_id": "parking.sessions", "state": "Disabled", "enabled": False, "detail": ""}
    if "payments.core" not in active:
        rows["PAYMENTS"] = {"module_id": "payments.core", "state": "Disabled", "enabled": False, "detail": ""}

    return {
        "profile": cfg.get("profile"),
        "components": rows,
        "enabled_modules": sorted(active),
    }


def require_module(module_id: str):
    def _dep(db: Session = Depends(get_db), user: User = Depends(current_user)):
        if not is_enabled(module_id, db):
            raise HTTPException(status_code=404, detail=f"Module not enabled: {module_id}")
        return user

    return _dep


def require_module_permission(module_id: str, permission: str):
    def _dep(db: Session = Depends(get_db), user: User = Depends(current_user)):
        if not is_enabled(module_id, db):
            raise HTTPException(status_code=404, detail=f"Module not enabled: {module_id}")
        perms = user_permissions(user)
        if "*" not in perms and permission not in perms:
            raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")
        return user

    return _dep


def onboarding_status(db: Session) -> dict[str, Any]:
    from sqlalchemy import select, func
    from app.models import Camera, Gate, User
    from app.services.topology import site_topology

    cfg = load_config(db)
    active = set(cfg.get("enabled") or [])
    topo = site_topology(db)
    camera_count = db.scalar(select(func.count()).select_from(Camera)) or 0
    gate_count = db.scalar(select(func.count()).select_from(Gate)) or 0
    user_count = db.scalar(select(func.count()).select_from(User)) or 0
    health = module_health(db)
    return {
        "completed": bool(cfg.get("onboarding_completed")),
        "step": int(cfg.get("onboarding_step") or 1),
        "use_case": cfg.get("use_case"),
        "profile": cfg.get("profile"),
        "recognition_default": cfg.get("recognition_default") or "HYBRID",
        "profiles": list_profiles(),
        "use_cases": [
            {"id": "LPR", "label": "License Plate Recognition", "profile": USE_CASE_TO_PROFILE["LPR"],
             "description": "Detect and search vehicle number plates."},
            {"id": "SECURITY", "label": "Security Monitoring", "profile": USE_CASE_TO_PROFILE["SECURITY"],
             "description": "Watchlists, alerts and vehicle history."},
            {"id": "ACCESS", "label": "Vehicle Access Control", "profile": USE_CASE_TO_PROFILE["ACCESS"],
             "description": "Authorize registered vehicles and control barriers."},
            {"id": "PARKING", "label": "Parking Management", "profile": USE_CASE_TO_PROFILE["PARKING"],
             "description": "Entry, exit, sessions, tariffs and payments."},
            {"id": "CUSTOM", "label": "Custom", "profile": PROFILE_CUSTOM,
             "description": "Choose individual modules for this site."},
        ],
        "optional_module_choices": [
            {
                "id": mid,
                "label": label,
                "description": desc,
                "enabled": mid in active,
            }
            for mid, label, desc in OPTIONAL_MODULE_CHOICES
        ],
        "enabled_modules": sorted(active),
        "topology": topo,
        "counts": {
            "cameras": int(camera_count),
            "gates": int(gate_count),
            "users": int(user_count),
            **(topo.get("counts") or {}),
        },
        "health": health,
        "recognition_modes": [
            {"id": "NATIVE_ONLY", "label": "Native ALPR", "description": "Use the camera vendor plate engine when available."},
            {"id": "FASTALPR_ONLY", "label": "SmartPark FastALPR", "description": "Edge FastALPR on live video frames."},
            {"id": "HYBRID", "label": "Hybrid", "description": "Prefer native, fall back to FastALPR."},
            {"id": "VIDEO_ONLY", "label": "Video only", "description": "Live video without plate recognition."},
        ],
        "steps": [
            {"id": 1, "key": "use_case", "label": "Purpose"},
            {"id": 2, "key": "topology", "label": "Topology"},
            {"id": 3, "key": "hardware", "label": "Hardware"},
            {"id": 4, "key": "recognition", "label": "Recognition"},
            {"id": 5, "key": "modules", "label": "Modules"},
            {"id": 6, "key": "users", "label": "Users"},
            {"id": 7, "key": "health", "label": "Health"},
            {"id": 8, "key": "activate", "label": "Activate"},
        ],
    }


def save_onboarding_step(db: Session, step: int, payload: dict[str, Any]) -> dict[str, Any]:
    from sqlalchemy import select
    from app.models import Camera
    from app.services.topology import apply_onboarding_topology

    cfg = load_config(db)
    cfg["onboarding_step"] = max(1, min(int(step or 1), 8))
    use_case = payload.get("use_case")
    if use_case and use_case in USE_CASE_TO_PROFILE:
        cfg["use_case"] = use_case
        profile = USE_CASE_TO_PROFILE[use_case]
        if profile != PROFILE_CUSTOM:
            apply_profile(db, profile)
            cfg = load_config(db)
            cfg["onboarding_step"] = max(1, min(int(step or 1), 8))
            cfg["use_case"] = use_case

    site = payload.get("site")
    if isinstance(site, dict) and site:
        from app.services.site_policy import save_site_policy
        data = {k: v for k, v in site.items() if v is not None and v != ""}
        if data:
            save_site_policy(db, data)

    topology = payload.get("topology")
    if isinstance(topology, dict) and (topology.get("gates") or topology.get("preset")):
        apply_onboarding_topology(db, topology)

    if payload.get("optional_modules") is not None and isinstance(payload["optional_modules"], list):
        # Start from profile baseline, then add selected optional modules.
        use = cfg.get("use_case") or payload.get("use_case")
        if use and use in USE_CASE_TO_PROFILE and USE_CASE_TO_PROFILE[use] != PROFILE_CUSTOM:
            base = _profile_modules(USE_CASE_TO_PROFILE[use])
        else:
            base = set(cfg.get("enabled") or [])
        for mid in payload["optional_modules"]:
            if mid in MODULES:
                base.add(mid)
                for dep in MODULES[mid].required_dependencies:
                    base.add(dep)
        # Drop optional choices that were unchecked (only those in OPTIONAL_MODULE_CHOICES).
        optional_ids = {row[0] for row in OPTIONAL_MODULE_CHOICES}
        selected = {m for m in payload["optional_modules"] if m in MODULES}
        for mid in optional_ids:
            if mid not in selected:
                base.discard(mid)
                # Also drop dependents that only exist for payments/kiosk chain when parking removed
        # Keep required deps of remaining modules.
        changed = True
        while changed:
            changed = False
            for mid in list(base):
                for dep in MODULES[mid].required_dependencies:
                    if dep not in base:
                        base.add(dep)
                        changed = True
        set_enabled(db, sorted(base), profile=PROFILE_CUSTOM if (use == "CUSTOM" or selected) else (cfg.get("profile") or PROFILE_CUSTOM))
        cfg = load_config(db)
        cfg["onboarding_step"] = max(1, min(int(step or 1), 8))

    recognition_mode = payload.get("recognition_mode")
    if not recognition_mode and isinstance(payload.get("recognition_defaults"), dict):
        recognition_mode = payload["recognition_defaults"].get("mode")
    if recognition_mode:
        mode = str(recognition_mode).upper()
        if mode in RECOGNITION_MODES:
            cfg["recognition_default"] = mode
            # Apply to existing cameras (VIDEO_ONLY clears recognition preference as FastALPR-off).
            apply_mode = "" if mode == "VIDEO_ONLY" else mode
            for camera in db.scalars(select(Camera)).all():
                camera.recognition_mode = apply_mode
            db.commit()

    user_payload = payload.get("user")
    if isinstance(user_payload, dict) and user_payload.get("username") and user_payload.get("password"):
        from app.models import Role, User, UserRole
        from app.security import hash_password
        username = str(user_payload["username"]).strip()
        existing = db.scalar(select(User).where(User.username == username))
        if existing is None:
            role_name = str(user_payload.get("role") or "Operator")
            role = db.scalar(select(Role).where(Role.name == role_name))
            if role is None:
                role = db.scalar(select(Role).where(Role.name == "Operator"))
            row = User(
                username=username,
                full_name=str(user_payload.get("full_name") or username),
                password_hash=hash_password(str(user_payload["password"])),
                status="ACTIVE",
            )
            db.add(row)
            db.flush()
            if role is not None:
                db.add(UserRole(user_id=row.id, role_id=role.id))
            db.commit()

    # Persist step progress (and optional draft flags).
    if payload.get("hardware") is not None:
        cfg["onboarding_hardware"] = payload["hardware"] if isinstance(payload["hardware"], dict) else {"noted": True}
    if payload.get("health_ok") is not None:
        cfg["onboarding_health_ok"] = bool(payload["health_ok"])

    if payload.get("activate") or int(step or 0) >= 8:
        cfg["onboarding_completed"] = True
        cfg["onboarding_step"] = 8
    else:
        cfg["onboarding_completed"] = False
        cfg["onboarding_step"] = max(1, min(int(step or 1), 8))

    return save_config(db, cfg)