"""Local deployment identity and role configuration.

This file deliberately contains only non-secret installation metadata. Site
data and parking rules remain in the server database; camera/database/payment
credentials remain in the existing secret mechanisms.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import tempfile
import uuid
from urllib.parse import urlsplit, urlunsplit

from app.config import settings


CONFIG_VERSION = 1
SITE_SERVER = "SITE_SERVER"
OPERATOR_CLIENT = "OPERATOR_CLIENT"
EDGE_NODE = "EDGE_NODE"


def config_path() -> Path:
    return settings.data_dir / "deployment.json"


def _normalise_url(value: str, *, default: str = "") -> str:
    raw = str(value or default).strip().rstrip("/")
    if not raw:
        return ""
    parsed = urlsplit(raw if "://" in raw else f"http://{raw}")
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Server URL must be an HTTP(S) address without credentials")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def _stable_installation_id() -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"smartpark-installation:{settings.node_id}"))


@dataclass(frozen=True)
class DeploymentConfig:
    config_version: int = CONFIG_VERSION
    configured: bool = False
    role: str = SITE_SERVER
    server_base_url: str = "http://127.0.0.1:8760"
    server_bind_host: str = "127.0.0.1"
    server_bind_port: int = 8760
    installation_id: str = ""
    server_id: str = ""
    client_id: str = ""
    site_name: str = "Parking Site"
    machine_name: str = ""
    configured_at: str = ""

    @property
    def is_server(self) -> bool:
        return self.role in {SITE_SERVER, EDGE_NODE}

    @property
    def is_operator_client(self) -> bool:
        return self.role == OPERATOR_CLIENT


def _from_mapping(data: dict) -> DeploymentConfig:
    role = str(data.get("role") or SITE_SERVER).upper()
    if role == "CLIENT":
        role = OPERATOR_CLIENT
    if role not in {SITE_SERVER, OPERATOR_CLIENT, EDGE_NODE}:
        raise ValueError(f"Unsupported deployment role: {role}")
    server_port = int(data.get("server_bind_port") or settings.api_port)
    base = _normalise_url(data.get("server_base_url") or "", default=f"http://127.0.0.1:{server_port}")
    return DeploymentConfig(
        config_version=int(data.get("config_version") or CONFIG_VERSION),
        configured=bool(data.get("configured")),
        role=role,
        server_base_url=base,
        server_bind_host=str(data.get("server_bind_host") or "127.0.0.1"),
        server_bind_port=server_port,
        installation_id=str(data.get("installation_id") or ""),
        server_id=str(data.get("server_id") or ""),
        client_id=str(data.get("client_id") or ""),
        site_name=str(data.get("site_name") or settings.site_name),
        machine_name=str(data.get("machine_name") or socket.gethostname()),
        configured_at=str(data.get("configured_at") or ""),
    )


def _legacy_config() -> DeploymentConfig:
    """Recognize the current working installation without forcing re-entry."""
    db_file = settings.data_dir / "smartpark.db"
    production_existing = db_file.is_file() or bool(settings.database_url)
    development_default = str(settings.deployment_profile).upper() != "PRODUCTION"
    configured = production_existing or development_default
    server_id = str(settings.node_id or socket.gethostname())
    return DeploymentConfig(
        configured=configured,
        role=SITE_SERVER,
        server_base_url=f"http://127.0.0.1:{int(settings.api_port)}",
        server_bind_host=str(settings.api_host or "127.0.0.1"),
        server_bind_port=int(settings.api_port),
        installation_id=_stable_installation_id(),
        server_id=server_id,
        site_name=str(settings.site_name or "Parking Site"),
        machine_name=socket.gethostname(),
        configured_at="legacy-compatible" if configured else "",
    )


def load_deployment_config() -> DeploymentConfig:
    path = config_path()
    if not path.is_file():
        return _legacy_config()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        config = _from_mapping(data)
        if config.config_version != CONFIG_VERSION or not config.installation_id:
            raise ValueError("unsupported or incomplete deployment configuration")
        return config
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        # The launcher will send an invalid file to the wizard rather than
        # silently starting a role with unknown ownership.
        return DeploymentConfig(configured=False, role=SITE_SERVER, installation_id=_stable_installation_id())


def save_deployment_config(config: DeploymentConfig | dict) -> DeploymentConfig:
    resolved = config if isinstance(config, DeploymentConfig) else _from_mapping(config)
    resolved = DeploymentConfig(
        **{
            **asdict(resolved),
            "config_version": CONFIG_VERSION,
            "configured": True,
            "installation_id": resolved.installation_id or _stable_installation_id(),
            "server_id": resolved.server_id or str(settings.node_id),
            "client_id": resolved.client_id or (str(uuid.uuid4()) if resolved.is_operator_client else ""),
            "machine_name": resolved.machine_name or socket.gethostname(),
            "configured_at": resolved.configured_at or datetime.now(timezone.utc).isoformat(),
        }
    )
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="deployment-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(asdict(resolved), stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return resolved


def ensure_legacy_config_saved() -> DeploymentConfig:
    """Persist a compatible identity for an existing installation once."""
    path = config_path()
    config = load_deployment_config()
    if not path.is_file() and config.configured:
        return save_deployment_config(config)
    return config


def server_base_url(config: DeploymentConfig | None = None) -> str:
    config = config or load_deployment_config()
    if config.is_operator_client:
        return config.server_base_url
    return f"http://127.0.0.1:{int(config.server_bind_port or settings.api_port)}"


def public_server_identity(config: DeploymentConfig | None = None) -> dict:
    config = config or load_deployment_config()
    return {
        "application": "SmartPark",
        "version": settings.app_version,
        "installation_id": config.installation_id,
        "server_id": config.server_id,
        "site_name": config.site_name,
        "role": config.role,
        "api_protocol": 1,
    }
