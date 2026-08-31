"""Product module definitions and deployment profiles.

Module entitlement (this site owns the capability) is separate from operational
feature flags (``app/domain/flags.py``) and RBAC permissions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


MODULE_VERSION = "1.0.0"

# --- deployment profiles -------------------------------------------------------

PROFILE_LPR_ONLY = "LPR_ONLY"
PROFILE_SECURITY = "SECURITY"
PROFILE_ACCESS_CONTROL = "ACCESS_CONTROL"
PROFILE_PARKING_LITE = "PARKING_LITE"
PROFILE_PARKING_PRO = "PARKING_PRO"
PROFILE_ENTERPRISE = "ENTERPRISE"
PROFILE_CUSTOM = "CUSTOM"

DEPLOYMENT_PROFILES: dict[str, dict[str, Any]] = {
    PROFILE_LPR_ONLY: {
        "name": "License Plate Recognition",
        "description": "Cameras, detections, plate search/history, exports — no gates, sessions or payments.",
        "modules": [
            "core.identity", "core.sites", "core.devices", "core.audit",
            "media.streaming", "camera.management", "recognition.alpr", "reports",
        ],
    },
    PROFILE_SECURITY: {
        "name": "Security Monitoring",
        "description": "Cameras, recognition, watchlists, alerts, incidents; optional access actions.",
        "modules": [
            "core.identity", "core.sites", "core.devices", "core.audit",
            "media.streaming", "camera.management", "recognition.alpr",
            "security.watchlists", "security.alerts", "reports",
        ],
    },
    PROFILE_ACCESS_CONTROL: {
        "name": "Vehicle Access Control",
        "description": "Registered vehicles, schedules, gates and permissions — no billing required.",
        "modules": [
            "core.identity", "core.sites", "core.devices", "core.audit",
            "camera.management", "recognition.alpr", "access.gates",
            "parking.subscribers", "reports",
        ],
    },
    PROFILE_PARKING_LITE: {
        "name": "Parking Lite",
        "description": "One entry, one exit, sessions, tariffs, optional kiosk payments.",
        "modules": [
            "core.identity", "core.sites", "core.devices", "core.audit",
            "media.streaming", "camera.management", "recognition.alpr",
            "access.gates", "parking.sessions", "parking.tariffs",
            "parking.subscribers", "payments.core", "payments.kiosk", "reports",
        ],
    },
    PROFILE_PARKING_PRO: {
        "name": "Parking Pro",
        "description": "Arbitrary entries/exits, kiosks, site-wide sessions and payments.",
        "modules": [
            "core.identity", "core.sites", "core.devices", "core.audit",
            "media.streaming", "camera.management", "recognition.alpr",
            "access.gates", "parking.sessions", "parking.tariffs",
            "parking.subscribers", "payments.core", "payments.kiosk",
            "payments.public_web", "kiosk", "reports", "notifications",
        ],
    },
    PROFILE_ENTERPRISE: {
        "name": "Enterprise / Multi-Site",
        "description": "All modules enabled for mixed vendors, topologies and locales.",
        "modules": "ALL",
    },
    PROFILE_CUSTOM: {
        "name": "Custom",
        "description": "Manually selected module set.",
        "modules": [],
    },
}

DEFAULT_PROFILE = PROFILE_PARKING_LITE

USE_CASE_TO_PROFILE = {
    "LPR": PROFILE_LPR_ONLY,
    "SECURITY": PROFILE_SECURITY,
    "ACCESS": PROFILE_ACCESS_CONTROL,
    "PARKING": PROFILE_PARKING_LITE,
    "PARKING_PRO": PROFILE_PARKING_PRO,
    "ENTERPRISE": PROFILE_ENTERPRISE,
    "CUSTOM": PROFILE_CUSTOM,
}


@dataclass(frozen=True)
class ModuleDefinition:
    id: str
    name: str
    version: str = MODULE_VERSION
    required_dependencies: tuple[str, ...] = ()
    optional_dependencies: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    routes: tuple[str, ...] = ()
    navigation_items: tuple[str, ...] = ()
    background_jobs: tuple[str, ...] = ()
    health_checks: tuple[str, ...] = ()
    configuration_schema: dict[str, Any] = field(default_factory=dict)


MODULES: dict[str, ModuleDefinition] = {
    "core.identity": ModuleDefinition(
        id="core.identity",
        name="Identity & RBAC",
        permissions=("users.view", "users.manage"),
        navigation_items=("users",),
        health_checks=("core",),
    ),
    "core.sites": ModuleDefinition(
        id="core.sites",
        name="Sites & Configuration",
        permissions=("dashboard.view", "settings.view", "settings.manage"),
        navigation_items=("dashboard", "settings"),
        health_checks=("core",),
    ),
    "core.devices": ModuleDefinition(
        id="core.devices",
        name="Device Registry",
        required_dependencies=("core.sites",),
        permissions=("hardware.view",),
        navigation_items=("hardware", "health"),
        background_jobs=("hvx-watch",),
        health_checks=("core", "cameras"),
    ),
    "core.audit": ModuleDefinition(
        id="core.audit",
        name="Audit",
        required_dependencies=("core.identity",),
    ),
    "media.streaming": ModuleDefinition(
        id="media.streaming",
        name="Media Streaming",
        required_dependencies=("core.devices", "camera.management"),
        permissions=("cameras.view",),
        background_jobs=("media-gateway",),
        health_checks=("media",),
    ),
    "camera.management": ModuleDefinition(
        id="camera.management",
        name="Camera Management",
        required_dependencies=("core.devices",),
        permissions=("cameras.view", "cameras.manage", "cameras.connect"),
        routes=("/cameras",),
        navigation_items=("cameras",),
        background_jobs=("camera-events",),
        health_checks=("cameras",),
    ),
    "recognition.alpr": ModuleDefinition(
        id="recognition.alpr",
        name="Plate Recognition",
        required_dependencies=("camera.management",),
        permissions=("cameras.view",),
        background_jobs=("camera-events", "fastalpr-poll"),
        health_checks=("alpr",),
    ),
    "security.watchlists": ModuleDefinition(
        id="security.watchlists",
        name="Watchlists",
        required_dependencies=("recognition.alpr",),
        permissions=("subscribers.view", "subscribers.manage"),
        navigation_items=("watchlists",),
        health_checks=("security",),
    ),
    "security.alerts": ModuleDefinition(
        id="security.alerts",
        name="Alerts & Incidents",
        required_dependencies=("security.watchlists",),
        permissions=("subscribers.view",),
        navigation_items=("alerts", "incidents"),
        health_checks=("security",),
    ),
    "access.gates": ModuleDefinition(
        id="access.gates",
        name="Gate Access",
        required_dependencies=("core.devices",),
        permissions=("gates.view", "gates.manage", "gates.open", "gates.open_simulated"),
        routes=("/gates",),
        navigation_items=("gates",),
        health_checks=("gates",),
    ),
    "parking.sessions": ModuleDefinition(
        id="parking.sessions",
        name="Parking Sessions",
        required_dependencies=("recognition.alpr", "access.gates"),
        permissions=("sessions.view", "kiosk.use"),
        routes=("/sessions",),
        navigation_items=("sessions",),
        background_jobs=("parking-outbox",),
        health_checks=("parking",),
    ),
    "parking.tariffs": ModuleDefinition(
        id="parking.tariffs",
        name="Tariffs",
        required_dependencies=("parking.sessions",),
        permissions=("fees.view", "fees.manage"),
        routes=("/tariffs",),
        navigation_items=("fees",),
        health_checks=("parking",),
    ),
    "parking.subscribers": ModuleDefinition(
        id="parking.subscribers",
        name="Subscribers & Vehicles",
        required_dependencies=("core.identity",),
        permissions=("subscribers.view", "subscribers.manage"),
        navigation_items=("vehicles",),
    ),
    "payments.core": ModuleDefinition(
        id="payments.core",
        name="Payments",
        required_dependencies=("parking.sessions",),
        permissions=("payments.view", "payments.create"),
        routes=("/payments",),
        navigation_items=("payments",),
        health_checks=("payments",),
    ),
    "payments.kiosk": ModuleDefinition(
        id="payments.kiosk",
        name="Kiosk Payments",
        required_dependencies=("payments.core",),
        permissions=("kiosk.use", "payments.create"),
    ),
    "payments.public_web": ModuleDefinition(
        id="payments.public_web",
        name="Public Payment Web",
        required_dependencies=("payments.core",),
        permissions=("payments.view",),
    ),
    "kiosk": ModuleDefinition(
        id="kiosk",
        name="Kiosk",
        required_dependencies=("payments.kiosk", "parking.sessions"),
        permissions=("kiosk.use",),
    ),
    "reports": ModuleDefinition(
        id="reports",
        name="Reports",
        permissions=("dashboard.view",),
        navigation_items=("reports",),
    ),
    "notifications": ModuleDefinition(
        id="notifications",
        name="Notifications",
        optional_dependencies=("security.alerts", "parking.sessions"),
    ),
}


@dataclass(frozen=True)
class NavItem:
    id: str
    label: str
    module_id: str
    permission: str | None
    page: str
    group: str
    profile_labels: dict[str, str] = field(default_factory=dict)


NAVIGATION: tuple[NavItem, ...] = (
    NavItem("dashboard", "Dashboard", "core.sites", "dashboard.view", "dashboard", "Overview"),
    NavItem(
        "cameras", "Live Gates", "camera.management", "cameras.view", "cameras", "Overview",
        profile_labels={
            PROFILE_LPR_ONLY: "Live Cameras",
            PROFILE_SECURITY: "Live Cameras",
        },
    ),
    NavItem("health", "System Health", "core.devices", "hardware.view", "health", "Overview"),
    NavItem("sessions", "Parking Sessions", "parking.sessions", "sessions.view", "sessions", "Operations",
            profile_labels={PROFILE_LPR_ONLY: "Detections", PROFILE_SECURITY: "Detections"}),
    NavItem("vehicles", "Vehicles", "parking.subscribers", "subscribers.view", "vehicles", "Operations"),
    NavItem("watchlists", "Watchlists", "security.watchlists", "subscribers.view", "watchlists", "Operations"),
    NavItem("alerts", "Alerts", "security.alerts", "subscribers.view", "alerts", "Operations"),
    NavItem("incidents", "Incidents", "security.alerts", "subscribers.view", "incidents", "Operations"),
    NavItem("payments", "Payments", "payments.core", "payments.view", "payments", "Operations"),
    NavItem("fees", "Tariffs & Schedules", "parking.tariffs", "fees.view", "fees", "Management",
            profile_labels={PROFILE_LPR_ONLY: "Reports", PROFILE_SECURITY: "Reports"}),
    NavItem("reports", "Reports", "reports", "dashboard.view", "reports", "Management"),
    NavItem("gates", "Gates", "access.gates", "gates.view", "gates", "System"),
    NavItem("users", "Users & Roles", "core.identity", "users.view", "users", "System"),
    NavItem("hardware", "Hardware Lab", "core.devices", "hardware.view", "hardware", "System"),
    NavItem("sim", "Simulation", "parking.sessions", "simulation.run", "sim", "System"),
    NavItem("settings", "Settings", "core.sites", "settings.view", "settings", "System"),
    NavItem("onboarding", "Setup Wizard", "core.sites", "settings.manage", "onboarding", "System"),
)

ALL_MODULE_IDS: tuple[str, ...] = tuple(MODULES.keys())
