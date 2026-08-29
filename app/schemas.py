from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    access_token: str
    token_type: str = "bearer"
    username: str
    permissions: list[str]


class CameraCreate(BaseModel):
    name: str
    ip_address: str
    sdk_port: int = Field(default=30000, ge=1, le=65535)
    username: str = "admin"
    password: str = "admin"
    gate_id: int | None = None
    lane_direction: str = "ENTRY"
    controller_ip: str = ""
    display_ip: str = ""
    rtsp_url: str = ""
    adapter_id: str = "hvx"
    connection_mode: str = "DIRECT"
    ffmpeg_profile: str = "LOW_LATENCY_LAN"
    rtsp_transport: str = "TCP"
    stream_profiles: dict | None = None
    recognition_mode: str = ""
    vendor: str = ""
    model_name: str = ""
    serial: str = ""
    timezone: str = ""
    camera_type: str = ""


class CameraImportItem(BaseModel):
    ip_address: str
    adapter_id: str = "rtsp"
    name: str | None = None
    lane_direction: str = "ENTRY"


class CameraImport(BaseModel):
    ips: list[str] | None = None
    cameras: list[CameraImportItem] | None = None
    scan_lan: bool = False
    username: str = "admin"
    password: str = "admin"
    connect: bool = False


class CameraUpdate(BaseModel):
    name: str | None = None
    ip_address: str | None = None
    sdk_port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = None
    password: str | None = None
    gate_id: int | None = None
    lane_direction: str | None = None
    controller_ip: str | None = None
    display_ip: str | None = None
    rtsp_url: str | None = None
    adapter_id: str | None = None
    connection_mode: str | None = None
    ffmpeg_profile: str | None = None
    rtsp_transport: str | None = None
    stream_profiles: dict | None = None
    enabled: bool | None = None
    recognition_mode: str | None = None
    vendor: str | None = None
    model_name: str | None = None
    serial: str | None = None
    timezone: str | None = None
    camera_type: str | None = None


class GateCreate(BaseModel):
    name: str
    mode: str = "COMMISSIONING"
    enabled: bool = True


class GateUpdate(BaseModel):
    name: str | None = None
    mode: str | None = None
    enabled: bool | None = None


class ManualGateCommand(BaseModel):
    reason: str
    side: str | None = None
    dry_run: bool = False
    led_text: str | None = None
    action: str = "open"


class LedWrite(BaseModel):
    text: str
    dry_run: bool = False


class FeeQuoteRequest(BaseModel):
    entry_time: datetime
    exit_time: datetime | None = None
    car_type: str = "Car1"


class SessionCreate(BaseModel):
    plate: str
    gate_id: int | None = None
    camera_id: int | None = None
    car_type: str = "Car1"


class StreamProfilesUpdate(BaseModel):
    ffmpeg_profile: str | None = None
    rtsp_transport: str | None = None
    live_role: str | None = None
    detect_source: str | None = None
    ai_fps: float | None = Field(default=None, ge=1, le=15)
    stream_profiles: dict | None = None


class FusionRequest(BaseModel):
    native_plate: str = ""
    native_confidence: float = 0.0
    local_plate: str = ""
    local_confidence: float = 0.0
    operator_plate: str = ""
    mode: str = "HYBRID"


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=80)
    full_name: str = ""
    password: str = Field(min_length=10)
    status: str = "ACTIVE"
    roles: list[str] = Field(default_factory=lambda: ["Operator"])


class UserUpdate(BaseModel):
    full_name: str | None = None
    password: str | None = Field(default=None, min_length=10)
    status: str | None = None
    roles: list[str] | None = None


class SimEntryRequest(BaseModel):
    plate: str
    gate_id: int
    side: str = "ENTRY"


class SimExitRequest(BaseModel):
    plate: str
    gate_id: int
    side: str = "EXIT"


class PaymentConfirm(BaseModel):
    method: str = "KIOSK_CASH"
    amount: float | None = None


class ParkingSettingsUpdate(BaseModel):
    receipt_required_before_open: bool | None = None
    receipt_policy: str | None = None
    exit_requires_payment: bool | None = None
    pay_prompt: str | None = None
    printer_adapter: str | None = None
    printer_name: str | None = None


class SitePolicyUpdate(BaseModel):
    name: str | None = None
    timezone: str | None = None
    locale: str | None = None
    language: str | None = None
    currency: str | None = None
    currency_precision: int | None = None
    date_format: str | None = None
    time_format: str | None = None
    distance_units: str | None = None
    plate_normalization: str | None = None
    plate_validation: str | None = None
    tax_behavior: str | None = None
    branding: str | None = None
    support_contacts: str | None = None


class MigrationFlagsUpdate(BaseModel):
    media_gateway_enabled: bool | None = None
    media_gateway_camera_ids: list[int] | str | None = None
    fastalpr_new_pipeline_enabled: bool | None = None
    webrtc_live_enabled: bool | None = None
    native_alpr_enabled: bool | None = None
    live_view_provider: str | None = None
    recognition_pipeline: str | None = None


class CameraOnboardProbe(BaseModel):
    ip_address: str
    username: str = "admin"
    password: str = "admin"
    sdk_port: int | None = Field(default=None, ge=1, le=65535)
    rtsp_url: str = ""


class CameraOnboardTest(BaseModel):
    ip_address: str
    username: str = "admin"
    password: str = "admin"
    adapter_id: str = "rtsp"
    sdk_port: int = Field(default=30000, ge=1, le=65535)
    rtsp_url: str = ""
    duration_seconds: float = Field(default=8.0, ge=0.2, le=60)


class AccessPlanCreate(BaseModel):
    name: str
    kind: str = "MONTHLY"
    auto_open: bool = True
    print_receipt: bool = False
    enabled: bool = True
    notes: str = ""


class AccessPlanUpdate(BaseModel):
    name: str | None = None
    kind: str | None = None
    auto_open: bool | None = None
    print_receipt: bool | None = None
    enabled: bool | None = None
    notes: str | None = None


class VehicleCreate(BaseModel):
    plate: str
    owner_name: str = ""
    plan_id: int | None = None
    enabled: bool = True
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    notes: str = ""


class VehicleUpdate(BaseModel):
    plate: str | None = None
    owner_name: str | None = None
    plan_id: int | None = None
    enabled: bool | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    notes: str | None = None
