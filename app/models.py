from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, TypeDecorator

from .db import Base
from .domain.site import DEFAULT_SITE_ID


def utcnow():
    return datetime.now(timezone.utc)


def as_utc(dt: datetime | None) -> datetime | None:
    """SQLite often returns naive datetimes; compare only in UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class AwareDateTime(TypeDecorator):
    """Always return UTC-aware datetimes from SQLite."""

    impl = DateTime
    cache_ok = True

    def __init__(self) -> None:
        super().__init__(timezone=True)

    def process_bind_param(self, value, dialect):
        return as_utc(value) if value is not None else None

    def process_result_value(self, value, dialect):
        return as_utc(value)


class UserStatus(str, Enum):
    ACTIVE = "ACTIVE"
    LOCKED = "LOCKED"
    DISABLED = "DISABLED"


class CameraStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    DISCOVERED = "DISCOVERED"
    SDK_CONNECTING = "SDK_CONNECTING"
    SDK_CONNECTED = "SDK_CONNECTED"
    SDK_FAILED = "SDK_FAILED"
    VIDEO_CONNECTED = "VIDEO_CONNECTED"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"


class GateMode(str, Enum):
    COMMISSIONING = "COMMISSIONING"
    SHADOW = "SHADOW"
    PRODUCTION = "PRODUCTION"
    MAINTENANCE = "MAINTENANCE"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160), default="")
    password_hash: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(30), default=UserStatus.ACTIVE.value)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)
    roles: Mapped[list["UserRole"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    permissions_csv: Mapped[str] = mapped_column(Text, default="")
    system_role: Mapped[bool] = mapped_column(Boolean, default=False)
    users: Mapped[list["UserRole"]] = relationship(back_populates="role")

    def permissions(self) -> set[str]:
        return {p.strip() for p in self.permissions_csv.split(",") if p.strip()}


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    user: Mapped[User] = relationship(back_populates="roles")
    role: Mapped[Role] = relationship(back_populates="users")


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(AwareDateTime())
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)


class Site(Base):
    __tablename__ = "sites"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), default="Default Site")
    timezone: Mapped[str] = mapped_column(String(80), default="UTC")
    locale: Mapped[str] = mapped_column(String(20), default="en")
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    zones: Mapped[list["Zone"]] = relationship(back_populates="site")


class Zone(Base):
    __tablename__ = "zones"
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    site: Mapped[Site] = relationship(back_populates="zones")
    lanes: Mapped[list["Lane"]] = relationship(back_populates="zone")


class Gate(Base):
    __tablename__ = "gates"
    __table_args__ = (UniqueConstraint("site_id", "name", name="uq_gates_site_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    mode: Mapped[str] = mapped_column(String(30), default=GateMode.COMMISSIONING.value)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    physical_control_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id"), nullable=False, default=DEFAULT_SITE_ID, server_default=str(DEFAULT_SITE_ID), index=True
    )
    zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id"), nullable=True)
    cameras: Mapped[list["Camera"]] = relationship(back_populates="gate")
    sessions: Mapped[list["ParkingSession"]] = relationship(back_populates="gate", foreign_keys="ParkingSession.gate_id")
    lanes: Mapped[list["Lane"]] = relationship(back_populates="gate")


class Lane(Base):
    __tablename__ = "lanes"
    id: Mapped[int] = mapped_column(primary_key=True)
    gate_id: Mapped[int | None] = mapped_column(ForeignKey("gates.id"), nullable=True, index=True)
    zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    direction: Mapped[str] = mapped_column(String(20), default="ENTRY")
    bidirectional: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    gate: Mapped[Gate | None] = relationship(back_populates="lanes")
    zone: Mapped[Zone | None] = relationship(back_populates="lanes")


class Camera(Base):
    __tablename__ = "cameras"
    __table_args__ = (UniqueConstraint("site_id", "name", name="uq_cameras_site_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id"), nullable=False, default=DEFAULT_SITE_ID, server_default=str(DEFAULT_SITE_ID), index=True
    )
    name: Mapped[str] = mapped_column(String(120), index=True)
    ip_address: Mapped[str] = mapped_column(String(64), index=True)
    sdk_port: Mapped[int] = mapped_column(Integer, default=30000)
    username: Mapped[str] = mapped_column(String(120), default="admin")
    # Legacy column. With an external SecretStore this holds "" and the real
    # value lives behind ``credentials_ref``; use the ``password_secret``
    # property, never the column directly.
    _password_secret: Mapped[str] = mapped_column("password_secret", String(300), default="")
    credentials_ref: Mapped[str] = mapped_column(String(120), default="", server_default="")
    gate_id: Mapped[int | None] = mapped_column(ForeignKey("gates.id"), nullable=True)
    lane_id: Mapped[int | None] = mapped_column(ForeignKey("lanes.id"), nullable=True)
    lane_direction: Mapped[str] = mapped_column(String(20), default="ENTRY")
    controller_ip: Mapped[str] = mapped_column(String(64), default="")
    display_ip: Mapped[str] = mapped_column(String(64), default="")
    adapter_id: Mapped[str] = mapped_column(String(40), default="hvx")
    connection_mode: Mapped[str] = mapped_column(String(20), default="DIRECT")
    rtsp_url: Mapped[str] = mapped_column(Text, default="")
    stream_profiles: Mapped[dict] = mapped_column(JSON, default=dict)
    ffmpeg_profile: Mapped[str] = mapped_column(String(40), default="LOW_LATENCY_LAN")
    rtsp_transport: Mapped[str] = mapped_column(String(16), default="TCP")
    media_capabilities: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default=CameraStatus.UNKNOWN.value)
    sdk_handle: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_seen_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    recognition_mode: Mapped[str] = mapped_column(String(40), default="")
    vendor: Mapped[str] = mapped_column(String(80), default="")
    model_name: Mapped[str] = mapped_column(String(80), default="")
    serial: Mapped[str] = mapped_column(String(80), default="")
    timezone: Mapped[str] = mapped_column(String(80), default="")
    camera_type: Mapped[str] = mapped_column(String(40), default="")
    # ONVIF capability snapshot from the last discovery: services, capabilities,
    # snapshot URI, plate topics and whether Profile M event pulling is enabled.
    onvif_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    gate: Mapped[Gate | None] = relationship(back_populates="cameras")

    @property
    def password_secret(self) -> str:
        """Raw camera password for adapters. Resolved through the SecretStore when configured."""
        from app.infrastructure.secrets import resolve_secret

        return resolve_secret(self.credentials_ref, fallback=self._password_secret or "")

    @password_secret.setter
    def password_secret(self, value: str | None) -> None:
        from app.infrastructure.secrets import SecretStoreError, store_secret, uses_external_store

        value = value or ""
        if uses_external_store():
            try:
                self.credentials_ref = store_secret(value, kind="camera", ref=self.credentials_ref or None)
                self._password_secret = ""
                return
            except SecretStoreError:
                pass  # fall back to the legacy column rather than losing the credential
        self._password_secret = value

    def has_password(self) -> bool:
        return bool(self._password_secret) or bool(self.credentials_ref)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    target_type: Mapped[str] = mapped_column(String(80), default="")
    target_id: Mapped[str] = mapped_column(String(80), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)


class Tariff(Base):
    """Car1 tariff snapshot. Portable JSON so PostgreSQL can take over later."""
    __tablename__ = "tariffs"
    __table_args__ = (UniqueConstraint("site_id", "name", name="uq_tariffs_site_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id"), nullable=False, default=DEFAULT_SITE_ID, server_default=str(DEFAULT_SITE_ID), index=True
    )
    name: Mapped[str] = mapped_column(String(80), index=True)
    car_type: Mapped[str] = mapped_column(String(40), default="Car1", index=True)
    currency: Mapped[str] = mapped_column(String(8), default="TZS")
    source: Mapped[str] = mapped_column(String(200), default="Car1")
    rules: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)


class ParkingSession(Base):
    __tablename__ = "parking_sessions"
    __table_args__ = (
        Index(
            "uq_parking_sessions_site_entry_event",
            "site_id",
            "entry_event_id",
            unique=True,
            sqlite_where=text("entry_event_id != ''"),
            postgresql_where=text("entry_event_id != ''"),
        ),
        Index(
            "uq_parking_sessions_one_open_plate",
            "site_id",
            "plate",
            unique=True,
            sqlite_where=text("status IN ('WAITING_RECEIPT','ACTIVE','PAID','OPEN')"),
            postgresql_where=text("status IN ('WAITING_RECEIPT','ACTIVE','PAID','OPEN')"),
        ),
        Index(
            "uq_parking_sessions_public_token",
            "public_token",
            unique=True,
            sqlite_where=text("public_token != ''"),
            postgresql_where=text("public_token != ''"),
        ),
        Index(
            "uq_parking_sessions_human_reference",
            "human_reference",
            unique=True,
            sqlite_where=text("human_reference != ''"),
            postgresql_where=text("human_reference != ''"),
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id"), nullable=False, default=DEFAULT_SITE_ID, server_default=str(DEFAULT_SITE_ID), index=True
    )
    plate: Mapped[str] = mapped_column(String(32), index=True)
    plate_raw: Mapped[str] = mapped_column(String(32), default="", server_default="")
    plate_status: Mapped[str] = mapped_column(String(20), default="", server_default="")
    # gate_id stays as the legacy/entry relationship for backwards compatibility.
    # New code preserves both ends of a visit explicitly.
    gate_id: Mapped[int | None] = mapped_column(ForeignKey("gates.id"), nullable=True)
    entry_gate_id: Mapped[int | None] = mapped_column(ForeignKey("gates.id"), nullable=True, index=True)
    exit_gate_id: Mapped[int | None] = mapped_column(ForeignKey("gates.id"), nullable=True, index=True)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id"), nullable=True)
    entry_lane_id: Mapped[int | None] = mapped_column(ForeignKey("lanes.id"), nullable=True)
    exit_lane_id: Mapped[int | None] = mapped_column(ForeignKey("lanes.id"), nullable=True)
    exit_camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id"), nullable=True)
    lane_direction: Mapped[str] = mapped_column(String(20), default="ENTRY")
    car_type: Mapped[str] = mapped_column(String(40), default="Car1")
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    lifecycle: Mapped[str] = mapped_column(String(40), default="", server_default="")
    entry_time: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)
    exit_time: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="TZS")
    amount_due: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    amount_paid: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    breakdown: Mapped[list] = mapped_column(JSON, default=list)
    tariff_rules: Mapped[dict] = mapped_column(JSON, default=dict)
    public_token: Mapped[str] = mapped_column(String(64), default="", index=True)
    human_reference: Mapped[str] = mapped_column(String(16), default="", server_default="")
    receipt_status: Mapped[str] = mapped_column(String(20), default="")
    receipt_printed_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    receipt_taken_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    print_job_id: Mapped[str] = mapped_column(String(64), default="", server_default="")
    print_job_status: Mapped[str] = mapped_column(String(20), default="", server_default="")
    print_retry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    printer_error: Mapped[str] = mapped_column(String(240), default="", server_default="")
    payment_status: Mapped[str] = mapped_column(String(20), default="", server_default="")
    paid_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    payment_exit_grace_until: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    entry_event_id: Mapped[str] = mapped_column(String(64), default="", server_default="")
    exit_event_id: Mapped[str] = mapped_column(String(64), default="", server_default="")
    entry_image_ref: Mapped[str] = mapped_column(String(260), default="", server_default="")
    open_command_uuid: Mapped[str] = mapped_column(String(64), default="", server_default="")
    exit_open_command_uuid: Mapped[str] = mapped_column(String(64), default="", server_default="")
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    parker_kind: Mapped[str] = mapped_column(String(40), default="CASUAL", index=True)
    access_plan_id: Mapped[int | None] = mapped_column(ForeignKey("access_plans.id"), nullable=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("registered_vehicles.id"), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    gate: Mapped[Gate | None] = relationship(back_populates="sessions", foreign_keys=[gate_id])


class SiteSetting(Base):
    __tablename__ = "site_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON, nullable=True)


class VehicleCapture(Base):
    """One car event from a QY image callback: full snapshot + plate crop + characters."""
    __tablename__ = "vehicle_captures"
    id: Mapped[int] = mapped_column(primary_key=True)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id"), nullable=True, index=True)
    gate_id: Mapped[int | None] = mapped_column(ForeignKey("gates.id"), nullable=True, index=True)
    lane_direction: Mapped[str] = mapped_column(String(20), default="ENTRY")
    plate: Mapped[str] = mapped_column(String(32), default="", index=True)
    plate_raw: Mapped[str] = mapped_column(String(32), default="")
    confidence: Mapped[float] = mapped_column(Numeric(6, 3), default=0)
    image_id: Mapped[int] = mapped_column(Integer, default=0, index=True)
    snapshot_path: Mapped[str] = mapped_column(String(260), default="")
    crop_path: Mapped[str] = mapped_column(String(260), default="")
    bbox: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    plate_country: Mapped[str] = mapped_column(String(8), default="")
    plate_region: Mapped[str] = mapped_column(String(40), default="")
    plate_type: Mapped[str] = mapped_column(String(40), default="")
    source: Mapped[str] = mapped_column(String(40), default="")
    event_id: Mapped[str] = mapped_column(String(64), default="")
    # Optional cloud AI second opinion (supporting/conflicting/unreadable). Never the plate authority.
    ai_review: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)


class AccessPlan(Base):
    """Season / VIP / staff policy. Registered plates use a plan, not RFID cards."""
    __tablename__ = "access_plans"
    __table_args__ = (UniqueConstraint("site_id", "name", name="uq_access_plans_site_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id"), nullable=False, default=DEFAULT_SITE_ID, server_default=str(DEFAULT_SITE_ID), index=True
    )
    name: Mapped[str] = mapped_column(String(80), index=True)
    kind: Mapped[str] = mapped_column(String(40), default="MONTHLY", index=True)
    auto_open: Mapped[bool] = mapped_column(Boolean, default=True)
    print_receipt: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    vehicles: Mapped[list["RegisteredVehicle"]] = relationship(back_populates="plan")


class RegisteredVehicle(Base):
    """Plate that may auto-open because it is on an access plan."""
    __tablename__ = "registered_vehicles"
    __table_args__ = (UniqueConstraint("site_id", "plate", name="uq_registered_vehicles_site_plate"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id"), nullable=False, default=DEFAULT_SITE_ID, server_default=str(DEFAULT_SITE_ID), index=True
    )
    plate: Mapped[str] = mapped_column(String(32), index=True)
    owner_name: Mapped[str] = mapped_column(String(160), default="")
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("access_plans.id"), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    valid_from: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)
    plan: Mapped[AccessPlan | None] = relationship(back_populates="vehicles")


class Receipt(Base):
    """Issued parking slip. Printer adapter is simulated until a device is attached."""
    __tablename__ = "receipts"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("parking_sessions.id"), nullable=True, index=True)
    plate: Mapped[str] = mapped_column(String(32), default="", index=True)
    public_token: Mapped[str] = mapped_column(String(64), default="", index=True)
    body_text: Mapped[str] = mapped_column(Text, default="")
    qr_payload: Mapped[str] = mapped_column(Text, default="")
    qr_path: Mapped[str] = mapped_column(String(260), default="")
    printer_adapter: Mapped[str] = mapped_column(String(40), default="simulated")
    status: Mapped[str] = mapped_column(String(20), default="SIMULATED")
    print_job_id: Mapped[str] = mapped_column(String(64), default="", server_default="", index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    printer_error: Mapped[str] = mapped_column(String(240), default="", server_default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)


class AccessDecision(Base):
    """Authorization outcome for one plate event. Does not pulse hardware."""
    __tablename__ = "access_decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("parking_sessions.id"), nullable=True, index=True)
    plate: Mapped[str] = mapped_column(String(32), default="", index=True)
    gate_id: Mapped[int | None] = mapped_column(ForeignKey("gates.id"), nullable=True, index=True)
    lane_direction: Mapped[str] = mapped_column(String(20), default="ENTRY")
    outcome: Mapped[str] = mapped_column(String(40), index=True)
    reason: Mapped[str] = mapped_column(String(200), default="")
    parker_kind: Mapped[str] = mapped_column(String(40), default="CASUAL")
    automatic: Mapped[bool] = mapped_column(Boolean, default=True)
    barrier_opened: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)


class GateCommandRecord(Base):
    """Durable record of a boom command. Written after GPIO/Board/LED I/O returns."""
    __tablename__ = "gate_commands"
    __table_args__ = (UniqueConstraint("command_uuid", name="uq_gate_command_uuid"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    command_uuid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    gate_id: Mapped[int | None] = mapped_column(ForeignKey("gates.id"), nullable=True, index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("parking_sessions.id"), nullable=True, index=True)
    reason: Mapped[str] = mapped_column(String(200), default="")
    automatic: Mapped[bool] = mapped_column(Boolean, default=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)


class PaymentIntent(Base):
    """Request to collect money. Not paid until a verified transaction succeeds."""
    __tablename__ = "payment_intents"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_payment_intent_idempotency"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("parking_sessions.id"), nullable=True, index=True)
    provider_id: Mapped[str] = mapped_column(String(40), default="kiosk_manual")
    method: Mapped[str] = mapped_column(String(40), default="KIOSK_CASH")
    amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    currency: Mapped[str] = mapped_column(String(8), default="TZS")
    status: Mapped[str] = mapped_column(String(20), default="CREATED", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)


class PaymentTransaction(Base):
    """Immutable ledger row. Session paid amount is derived from SUCCEEDED rows."""
    __tablename__ = "payment_transactions"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_payment_txn_idempotency"),
        UniqueConstraint("provider_transaction_id", name="uq_payment_provider_txn"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    intent_id: Mapped[int | None] = mapped_column(ForeignKey("payment_intents.id"), nullable=True, index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("parking_sessions.id"), nullable=True, index=True)
    provider_id: Mapped[str] = mapped_column(String(40), default="kiosk_manual")
    method: Mapped[str] = mapped_column(String(40), default="KIOSK_CASH")
    amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    currency: Mapped[str] = mapped_column(String(8), default="TZS")
    status: Mapped[str] = mapped_column(String(20), default="CREATED", index=True)
    provider_transaction_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)


