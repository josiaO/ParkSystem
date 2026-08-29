from __future__ import annotations

from pathlib import Path
import os
import platform

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
    hvx_host_url: str = "http://127.0.0.1:8765"
    alpr_mode: str = "NATIVE_ONLY"
    live_idle_seconds: float = 20.0
    live_sdk_interval_seconds: float = 0.04
    snapshot_cache_seconds: float = 0.04
    stale_stream_seconds: float = 2.5
    detect_fps: float = 5.0
    ffmpeg_profile: str = "LOW_LATENCY_LAN"
    rtsp_transport: str = "TCP"
    camera_event_poll_seconds: float = 0.25
    local_alpr_cooldown_seconds: float = 2.0
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
    alpr_country: str = "Tanzania"
    alpr_csf: float = 0.918
    default_hvx_sdk_port: int = 30000
    bootstrap_username: str = "admin"
    bootstrap_password: str = "SmartPark1!"
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
