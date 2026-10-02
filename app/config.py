from __future__ import annotations

from pathlib import Path
import os
import platform

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_data_dir() -> Path:
    if platform.system() == "Windows":
        base = Path(os.getenv("PROGRAMDATA", Path.home()))
        return base / "SmartParkEdge"
    return Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "smartpark-edge"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SMARTPARK_", env_file=".env", extra="ignore")

    app_name: str = "SmartPark Edge"
    app_version: str = "0.3.0"
    site_name: str = "Parking Site"
    api_host: str = "127.0.0.1"
    api_port: int = 8760
    database_url: str | None = None
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_timeout_seconds: float = 8.0
    # Where camera credentials live: auto (= dpapi on Windows, db elsewhere),
    # dpapi, file, memory, or db (legacy raw column).
    secrets_backend: str = "auto"
    hvx_host_url: str = "http://127.0.0.1:8765"
    alpr_mode: str = "FASTALPR_ONLY"
    alpr_engine: str = "fastalpr"
    live_idle_seconds: float = 20.0
    live_sdk_interval_seconds: float = 0.05
    snapshot_cache_seconds: float = 0.05
    stale_stream_seconds: float = 2.5
    detect_fps: float = 5.0
    ffmpeg_profile: str = "LOW_LATENCY_LAN"
    rtsp_transport: str = "TCP"
    camera_event_poll_seconds: float = 0.25
    local_alpr_cooldown_seconds: float = 0.5
    recognition_max_concurrency: int = 2
    recognition_absence_reset_seconds: float = 0.6
    recognition_worker_stall_seconds: float = 5.0
    live_plate_fresh_seconds: float = 4.0
    live_mjpeg_fps: float = 10.0
    entry_dedupe_seconds: float = 2.0
    entry_dedupe_similarity: float = 0.85
    coil_gpio_index: int = 1
    coil_active_value: int = 1
    coil_poll_indexes: str = "1,2,3,4,5,6,7"
    media_retention_days: int = 14
    log_level: str = "INFO"
    log_max_bytes: int = 5_000_000
    log_backup_count: int = 8
    gate_command_timeout_seconds: float = 3.0
    hvx_vendor_dir: str | None = None
    request_timeout_seconds: float = 4.0
    hvx_connect_http_timeout_seconds: float = 20.0
    camera_tcp_probe_seconds: float = 1.0
    rtsp_probe_timeout_seconds: float = 5.0
    alpr_timeout_seconds: float = 15.0
    alpr_country: str = ""
    alpr_csf: float = 0.918
    alpr_detector_confidence: float = 0.18
    alpr_crop_padding_ratio: float = 0.18
    alpr_ocr_target_width: int = 320
    default_hvx_sdk_port: int = 30000
    bootstrap_username: str = "admin"
    bootstrap_password: str = ""
    mobile_money_webhook_secret: str = ""
    # --- External payment providers (Phase 2 §8) -------------------------
    # Which provider backs the public "pay by phone" flow. simulated keeps the
    # legacy instant path; flutterwave / clickpesa create PENDING intents that
    # only become SUCCEEDED after server-side verification.
    payments_mobile_provider: str = "simulated"
    # Browser-triggered fake payments are for explicit development only. A real
    # deployment must never let a public receipt URL mint SUCCEEDED ledger rows.
    allow_public_simulated_payments: bool = False
    # ClickPesa has no sandbox. A live collection is refused unless BOTH flags
    # below are set explicitly by the operator (LIVE_PROVIDER_CONFIRMATION_REQUIRED).
    payments_live_provider_confirmation_required: bool = True
    payments_live_provider_confirmed: bool = False
    payments_reconcile_seconds: float = 60.0
    payments_intent_expiry_minutes: int = 30
    payments_http_timeout_seconds: float = 8.0
    flutterwave_secret_key: str = ""          # FLWSECK_TEST-... by default
    flutterwave_secret_hash: str = ""         # webhook verif-hash / signature secret
    flutterwave_base_url: str = "https://api.flutterwave.com/v3"
    flutterwave_allow_live_keys: bool = False
    flutterwave_customer_email: str = "payments@smartpark.local"
    flutterwave_default_network: str = ""     # Airtel | Tigo | Halopesa | Vodafone | ""
    clickpesa_client_id: str = ""
    clickpesa_api_key: str = ""
    clickpesa_checksum_key: str = ""
    clickpesa_base_url: str = "https://api.clickpesa.com/third-parties"
    clickpesa_live_enabled: bool = False
    # Comma-separated hostnames that a public tunnel/reverse proxy forwards to
    # this Site Service. Requests arriving on those hosts may only reach the
    # narrow public payment surface (see app/services/public_ingress.py).
    public_ingress_hosts: str = ""
    # Optional cloud AI review (Codex §9). Off by default; never a gate authority.
    ai_enabled: bool = False
    ai_provider: str = "gemini"
    ai_model: str = "gemini-2.5-flash-lite"
    ai_timeout_seconds: float = 4.0
    ai_max_concurrency: int = 2
    ai_daily_request_cap: int = 200
    ai_min_interval_seconds: float = 2.0  # per camera
    ai_low_confidence_below: float = 0.75  # trigger a second opinion under this
    ai_send_vehicle_image: bool = False  # only the plate crop unless explicitly allowed
    ai_vehicle_image_max_px: int = 640
    # Free-tier Gemini may use submitted content to improve Google products.
    # Real (non-simulated) imagery is only sent once a deployment accepts that.
    ai_data_treatment_accepted: bool = False
    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    default_camera_password: str = "admin"
    gate_physical_control_enabled: bool = True
    board_tcp_port: int = 5000
    board_tcp_timeout_seconds: float = 1.5
    board_tcp_frame: str = "stx_open"
    led_udp_port: int = 6666
    led_udp_local_port: int = 8881
    gpio_index: int = 0
    gpio_pulse_ms: int = 500
    fee_currency: str = "TZS"
    fee_car_type: str = "Car1"
    printer_adapter: str = "simulated"
    printer_name: str = ""
    printer_escpos_host: str = ""
    printer_escpos_port: int = 9100
    public_base_url: str = ""
    printer_width_dots: int = 384
    printer_qr_mode: str = "auto"
    media_gateway_enabled: bool = False
    media_gateway_camera_ids: str = ""
    fastalpr_new_pipeline_enabled: bool = False
    webrtc_live_enabled: bool = False
    native_alpr_enabled: bool = True
    live_view_provider: str = "DIRECT_LEGACY"
    recognition_pipeline: str = "FASTALPR_LEGACY"
    site_timezone: str = "UTC"
    site_locale: str = "en"
    site_language: str = "en"
    plate_normalization: str = "ALNUM_UPPER"
    plate_validation: str = "NONE"
    recognition_consensus_window_seconds: float = 2.0
    recognition_high_confidence: float = 0.92
    recognition_medium_confidence: float = 0.75

    @field_validator("api_port", "default_hvx_sdk_port", "board_tcp_port", "led_udp_port", "printer_escpos_port")
    @classmethod
    def _port_range(cls, value: int) -> int:
        port = int(value)
        if not 1 <= port <= 65535:
            raise ValueError(f"Invalid SMARTPARK port {port}; expected 1-65535")
        return port

    @field_validator("detect_fps", "live_mjpeg_fps")
    @classmethod
    def _video_fps_range(cls, value: float) -> float:
        fps = float(value)
        if not 1.0 <= fps <= 30.0:
            raise ValueError("SmartPark video FPS values must be between 1 and 30")
        return fps

    @field_validator("recognition_max_concurrency")
    @classmethod
    def _recognition_concurrency(cls, value: int) -> int:
        workers = int(value)
        if not 1 <= workers <= 8:
            raise ValueError("SMARTPARK_RECOGNITION_MAX_CONCURRENCY must be between 1 and 8")
        return workers

    @field_validator(
        "recognition_absence_reset_seconds",
        "recognition_worker_stall_seconds",
        "live_plate_fresh_seconds",
        "entry_dedupe_seconds",
    )
    @classmethod
    def _positive_runtime_seconds(cls, value: float) -> float:
        seconds = float(value)
        if seconds <= 0:
            raise ValueError("SmartPark runtime timing values must be greater than 0")
        return seconds

    @field_validator("entry_dedupe_similarity")
    @classmethod
    def _dedupe_similarity(cls, value: float) -> float:
        score = float(value)
        if not 0.5 <= score <= 1.0:
            raise ValueError("SMARTPARK_ENTRY_DEDUPE_SIMILARITY must be between 0.5 and 1")
        return score

    @field_validator("recognition_consensus_window_seconds")
    @classmethod
    def _consensus_window(cls, value: float) -> float:
        seconds = float(value)
        if not 0.2 <= seconds <= 30.0:
            raise ValueError("SMARTPARK_RECOGNITION_CONSENSUS_WINDOW_SECONDS must be between 0.2 and 30")
        return seconds

    @field_validator("alpr_detector_confidence", "alpr_crop_padding_ratio")
    @classmethod
    def _alpr_fraction(cls, value: float) -> float:
        score = float(value)
        if not 0.0 <= score <= 1.0:
            raise ValueError("ALPR detector/crop ratios must be between 0 and 1")
        return score

    @field_validator("alpr_ocr_target_width")
    @classmethod
    def _alpr_crop_width(cls, value: int) -> int:
        width = int(value)
        if not 96 <= width <= 1024:
            raise ValueError("SMARTPARK_ALPR_OCR_TARGET_WIDTH must be between 96 and 1024")
        return width

    @field_validator("recognition_high_confidence", "recognition_medium_confidence")
    @classmethod
    def _confidence_range(cls, value: float) -> float:
        score = float(value)
        if not 0.0 <= score <= 1.0:
            raise ValueError("Recognition confidence thresholds must be between 0 and 1")
        return score

    @field_validator("alpr_mode")
    @classmethod
    def _alpr_mode(cls, value: str) -> str:
        chosen = str(value or "FASTALPR_ONLY").upper()
        allowed = {
            "NATIVE_ONLY", "NATIVE_WITH_LOCAL_VERIFY", "HYBRID",
            "LOCAL_ONLY", "FASTALPR_ONLY", "LOCAL", "FASTALPR",
        }
        if chosen not in allowed:
            raise ValueError(f"Invalid SMARTPARK_ALPR_MODE {value!r}")
        return chosen

    @field_validator("log_level")
    @classmethod
    def _log_level(cls, value: str) -> str:
        chosen = str(value or "INFO").upper()
        if chosen not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"Invalid SMARTPARK_LOG_LEVEL {value!r}")
        return chosen

    @field_validator("rtsp_transport")
    @classmethod
    def _rtsp_transport(cls, value: str) -> str:
        chosen = str(value or "TCP").upper()
        if chosen not in {"TCP", "UDP", "AUTO"}:
            raise ValueError(f"Invalid SMARTPARK_RTSP_TRANSPORT {value!r}")
        return chosen

    @field_validator("gate_command_timeout_seconds", "request_timeout_seconds", "live_idle_seconds")
    @classmethod
    def _positive_seconds(cls, value: float) -> float:
        seconds = float(value)
        if seconds <= 0:
            raise ValueError("SMARTPARK timeout/idle values must be greater than 0")
        return seconds

    @property
    def data_dir(self) -> Path:
        p = default_data_dir()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def media_dir(self) -> Path:
        p = self.data_dir / "media"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'smartpark.db').as_posix()}"


settings = Settings()
