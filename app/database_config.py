"""Authoritative database configuration and preflight helpers.

The deployment file contains only connection metadata.  Passwords are kept in
the configured SmartPark secret store and are resolved only while building a
runtime SQLAlchemy URL for the Site Service.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import socket
import time
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

from app.config import settings


SQLITE = "SQLITE"
POSTGRESQL = "POSTGRESQL"


@dataclass(frozen=True)
class DatabaseConfig:
    engine: str = SQLITE
    sqlite_path: str = ""
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432
    postgres_database: str = "smartpark"
    postgres_username: str = "smartpark"
    postgres_secret_reference: str = ""

    def __post_init__(self) -> None:
        engine = str(self.engine or SQLITE).upper()
        if engine not in {SQLITE, POSTGRESQL}:
            raise ValueError(f"Unsupported database engine: {engine}")
        object.__setattr__(self, "engine", engine)
        if not 1 <= int(self.postgres_port) <= 65535:
            raise ValueError("PostgreSQL port must be between 1 and 65535")

    @property
    def is_sqlite(self) -> bool:
        return self.engine == SQLITE

    @property
    def display_name(self) -> str:
        return "SQLite" if self.is_sqlite else "PostgreSQL"

    def sqlite_file(self) -> Path:
        return Path(self.sqlite_path or (settings.data_dir / "smartpark.db"))

    def to_mapping(self) -> dict[str, Any]:
        return asdict(self)


def default_database_config() -> DatabaseConfig:
    configured = str(settings.database_url or "").strip()
    if configured:
        parsed = make_url(configured)
        if parsed.get_backend_name() == "sqlite":
            return DatabaseConfig(sqlite_path=str(parsed.database or settings.data_dir / "smartpark.db"))
        if parsed.get_backend_name() in {"postgresql", "postgres"}:
            return DatabaseConfig(
                engine=POSTGRESQL,
                postgres_host=str(parsed.host or "127.0.0.1"),
                postgres_port=int(parsed.port or 5432),
                postgres_database=str(parsed.database or "smartpark"),
                postgres_username=str(parsed.username or "smartpark"),
            )
    return DatabaseConfig(sqlite_path=str(settings.data_dir / "smartpark.db"))


def database_config_from_mapping(value: Any) -> DatabaseConfig:
    if isinstance(value, DatabaseConfig):
        return value
    if not isinstance(value, dict):
        return default_database_config()
    return DatabaseConfig(
        engine=str(value.get("engine") or SQLITE),
        sqlite_path=str(value.get("sqlite_path") or ""),
        postgres_host=str(value.get("postgres_host") or "127.0.0.1"),
        postgres_port=int(value.get("postgres_port") or 5432),
        postgres_database=str(value.get("postgres_database") or "smartpark"),
        postgres_username=str(value.get("postgres_username") or "smartpark"),
        postgres_secret_reference=str(value.get("postgres_secret_reference") or ""),
    )


def _postgres_password(config: DatabaseConfig, password: str | None = None) -> str:
    # An empty wizard field means “use the already stored secret” during a
    # reconfiguration. It must not replace a valid DPAPI secret with an empty
    # password and make an otherwise healthy site fail authentication.
    if password:
        return password
    if config.postgres_secret_reference:
        from app.infrastructure.secrets import resolve_secret

        return resolve_secret(config.postgres_secret_reference)
    return os.environ.get("SMARTPARK_DATABASE_PASSWORD", "")


def database_url(config: DatabaseConfig, *, password: str | None = None) -> str:
    if config.is_sqlite:
        path = config.sqlite_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path.resolve().as_posix()}"
    secret = _postgres_password(config, password=password)
    return URL.create(
        "postgresql+psycopg",
        username=config.postgres_username,
        password=secret,
        host=config.postgres_host,
        port=int(config.postgres_port),
        database=config.postgres_database,
    ).render_as_string(hide_password=False)


def _tcp_preflight(config: DatabaseConfig) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with socket.create_connection((config.postgres_host, int(config.postgres_port)), timeout=3):
            return {"ok": True, "latency_ms": round((time.perf_counter() - started) * 1000, 1)}
    except OSError as exc:
        return {"ok": False, "error": "PostgreSQL could not be reached on this computer.", "technical": str(exc)[:240]}


def preflight(config: DatabaseConfig, *, initialize: bool = False, password: str | None = None) -> dict[str, Any]:
    """Validate a candidate database and optionally bring its schema to head."""
    result: dict[str, Any] = {
        "engine": config.engine,
        "display_name": config.display_name,
        "checks": [],
        "ok": False,
    }
    if config.is_sqlite:
        path = config.sqlite_file()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            usage = __import__("shutil").disk_usage(path.parent)
            result["path"] = str(path)
            result["free_bytes"] = int(usage.free)
            result["checks"].append({"name": "data directory writable", "ok": os.access(path.parent, os.W_OK)})
            engine = create_engine(database_url(config), future=True, pool_pre_ping=True)
            with engine.begin() as conn:
                conn.execute(text("PRAGMA journal_mode=WAL"))
                integrity = str(conn.execute(text("PRAGMA integrity_check")).scalar() or "")
                conn.execute(text("CREATE TABLE IF NOT EXISTS _smartpark_preflight (id INTEGER PRIMARY KEY, checked_at TEXT)"))
                conn.execute(text("INSERT INTO _smartpark_preflight (checked_at) VALUES (CURRENT_TIMESTAMP)"))
                conn.execute(text("DELETE FROM _smartpark_preflight"))
            result["checks"].extend([
                {"name": "database opens", "ok": True},
                {"name": "integrity_check", "ok": integrity.lower() == "ok", "detail": integrity},
                {"name": "read/write transaction", "ok": True},
                {"name": "WAL capability", "ok": True},
            ])
            if initialize:
                from app.migrations.runner import upgrade_to_head

                result["migration"] = upgrade_to_head(engine)
            else:
                from app.migrations.runner import status

                result["migration"] = status(engine)
            result["migration"]["up_to_date"] = bool(result["migration"].get("revision")) and result["migration"].get("revision") == result["migration"].get("head")
            engine.dispose()
            # A fresh database is valid but not yet migrated; Apply performs
            # the authoritative Alembic initialization.
            result["ok"] = all(bool(row.get("ok")) for row in result["checks"])
        except Exception as exc:
            result["checks"].append({"name": "database", "ok": False, "error": str(exc)[:300]})
            result["error"] = "SQLite could not be opened or configured."
        return result

    result["host"] = config.postgres_host
    result["port"] = int(config.postgres_port)
    result["database"] = config.postgres_database
    result["username"] = config.postgres_username
    tcp = _tcp_preflight(config)
    result["checks"].append({"name": "PostgreSQL server", **tcp})
    if not tcp.get("ok"):
        result["error"] = "PostgreSQL could not be reached on this computer. Install PostgreSQL or select SQLite for testing."
        return result
    try:
        engine = create_engine(database_url(config, password=password), future=True, pool_pre_ping=True)
        with engine.begin() as conn:
            conn.execute(text("SELECT 1"))
            conn.execute(text("CREATE TEMP TABLE smartpark_preflight (id integer)"))
            conn.execute(text("INSERT INTO smartpark_preflight VALUES (1)"))
            conn.execute(text("SELECT id FROM smartpark_preflight"))
        result["checks"].extend([
            {"name": "authentication", "ok": True},
            {"name": "database", "ok": True},
            {"name": "permissions", "ok": True},
            {"name": "read/write transaction", "ok": True},
        ])
        if initialize:
            from app.migrations.runner import upgrade_to_head

            result["migration"] = upgrade_to_head(engine)
        else:
            from app.migrations.runner import status

            result["migration"] = status(engine)
        result["migration"]["up_to_date"] = bool(result["migration"].get("revision")) and result["migration"].get("revision") == result["migration"].get("head")
        # A reachable database with a pending migration is still a valid
        # candidate; Apply will migrate it before the service is started.
        result["ok"] = True
        engine.dispose()
    except Exception as exc:
        message = str(exc)
        result["checks"].append({"name": "authentication/database", "ok": False, "error": message[:300]})
        result["error"] = "PostgreSQL was found but authentication, database access, or permissions failed."
        result["technical"] = message[:300]
    return result


def apply_runtime_database_config(config: DatabaseConfig) -> str:
    """Set the final database before importing the API/ORM module graph."""
    url = database_url(config)
    os.environ["SMARTPARK_DATABASE_URL"] = url
    # Settings is instantiated early by deployment metadata. Keep its runtime
    # view aligned before app.db creates its import-time engine.
    settings.database_url = url
    return url

