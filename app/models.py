from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .db import Base


def utcnow():
    return datetime.now(timezone.utc)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
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
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    mode: Mapped[str] = mapped_column(String(30), default=GateMode.COMMISSIONING.value)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    physical_control_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id"), nullable=True)
    zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id"), nullable=True)
    cameras: Mapped[list["Camera"]] = relationship(back_populates="gate")
    sessions: Mapped[list["ParkingSession"]] = relationship(back_populates="gate")
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
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    ip_address: Mapped[str] = mapped_column(String(64), index=True)
    sdk_port: Mapped[int] = mapped_column(Integer, default=30000)
    username: Mapped[str] = mapped_column(String(120), default="admin")
    password_secret: Mapped[str] = mapped_column(String(300), default="")  # local MVP; replace with OS secret store
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
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    recognition_mode: Mapped[str] = mapped_column(String(40), default="")
    vendor: Mapped[str] = mapped_column(String(80), default="")
    model_name: Mapped[str] = mapped_column(String(80), default="")
    serial: Mapped[str] = mapped_column(String(80), default="")
    timezone: Mapped[str] = mapped_column(String(80), default="")
    camera_type: Mapped[str] = mapped_column(String(40), default="")
    gate: Mapped[Gate | None] = relationship(back_populates="cameras")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    target_type: Mapped[str] = mapped_column(String(80), default="")
    target_id: Mapped[str] = mapped_column(String(80), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Tariff(Base):
    """Car1 tariff snapshot. Portable JSON so PostgreSQL can take over later."""
    __tablename__ = "tariffs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    car_type: Mapped[str] = mapped_column(String(40), default="Car1", index=True)
    currency: Mapped[str] = mapped_column(String(8), default="TZS")
    source: Mapped[str] = mapped_column(String(200), default="Car1")
    rules: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ParkingSession(Base):
    __tablename__ = "parking_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    plate: Mapped[str] = mapped_column(String(32), index=True)
    gate_id: Mapped[int | None] = mapped_column(ForeignKey("gates.id"), nullable=True)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id"), nullable=True)
    lane_direction: Mapped[str] = mapped_column(String(20), default="ENTRY")
    car_type: Mapped[str] = mapped_column(String(40), default="Car1")
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    exit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="TZS")
    amount_due: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    amount_paid: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    breakdown: Mapped[list] = mapped_column(JSON, default=list)
    tariff_rules: Mapped[dict] = mapped_column(JSON, default=dict)
    public_token: Mapped[str] = mapped_column(String(64), default="", index=True)
    receipt_status: Mapped[str] = mapped_column(String(20), default="")
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    parker_kind: Mapped[str] = mapped_column(String(40), default="CASUAL", index=True)
    access_plan_id: Mapped[int | None] = mapped_column(ForeignKey("access_plans.id"), nullable=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("registered_vehicles.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    gate: Mapped[Gate | None] = relationship(back_populates="sessions")


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AccessPlan(Base):
    """Season / VIP / staff policy. Registered plates use a plan, not RFID cards."""
    __tablename__ = "access_plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    kind: Mapped[str] = mapped_column(String(40), default="MONTHLY", index=True)
    auto_open: Mapped[bool] = mapped_column(Boolean, default=True)
    print_receipt: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    vehicles: Mapped[list["RegisteredVehicle"]] = relationship(back_populates="plan")


class RegisteredVehicle(Base):
    """Plate that may auto-open because it is on an access plan."""
    __tablename__ = "registered_vehicles"
    id: Mapped[int] = mapped_column(primary_key=True)
    plate: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    owner_name: Mapped[str] = mapped_column(String(160), default="")
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("access_plans.id"), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
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
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


