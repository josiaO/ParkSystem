"""Pre-Alembic column fixups, frozen.

This is the ALTER TABLE list that ``app.db.ensure_schema`` used to run on every
start. It now runs exactly once: when the runner finds a database that has
tables but no ``alembic_version`` row, it applies these fixups, stamps
``0001_baseline`` and hands over to Alembic. **Do not add new entries here** —
new schema changes are Alembic revisions under ``app/migrations/alembic/versions``.
"""

from __future__ import annotations

from sqlalchemy.engine import Connection, Engine

_CAMERA_COLUMNS = (
    ("controller_ip", "VARCHAR(64) DEFAULT ''"),
    ("display_ip", "VARCHAR(64) DEFAULT ''"),
    ("adapter_id", "VARCHAR(40) DEFAULT 'hvx'"),
    ("connection_mode", "VARCHAR(20) DEFAULT 'DIRECT'"),
    ("stream_profiles", "JSON"),
    ("ffmpeg_profile", "VARCHAR(40) DEFAULT 'LOW_LATENCY_LAN'"),
    ("rtsp_transport", "VARCHAR(16) DEFAULT 'TCP'"),
    ("media_capabilities", "JSON"),
    ("recognition_mode", "VARCHAR(40) DEFAULT ''"),
    ("vendor", "VARCHAR(80) DEFAULT ''"),
    ("model_name", "VARCHAR(80) DEFAULT ''"),
    ("serial", "VARCHAR(80) DEFAULT ''"),
    ("timezone", "VARCHAR(80) DEFAULT ''"),
    ("camera_type", "VARCHAR(40) DEFAULT ''"),
    ("lane_id", "INTEGER"),
    ("onvif_profile", "JSON"),
)
_GATE_COLUMNS = (("site_id", "INTEGER"), ("zone_id", "INTEGER"))
_CAPTURE_COLUMNS = (
    ("plate_country", "VARCHAR(8) DEFAULT ''"),
    ("plate_region", "VARCHAR(40) DEFAULT ''"),
    ("plate_type", "VARCHAR(40) DEFAULT ''"),
    ("source", "VARCHAR(40) DEFAULT ''"),
    ("event_id", "VARCHAR(64) DEFAULT ''"),
)
_SESSION_COLUMNS = (
    ("public_token", "VARCHAR(64) DEFAULT ''"),
    ("receipt_status", "VARCHAR(20) DEFAULT ''"),
    ("simulated", "BOOLEAN DEFAULT 0"),
    ("parker_kind", "VARCHAR(40) DEFAULT 'CASUAL'"),
    ("access_plan_id", "INTEGER"),
    ("vehicle_id", "INTEGER"),
)

LEGACY_TABLES = {
    "cameras": _CAMERA_COLUMNS,
    "gates": _GATE_COLUMNS,
    "vehicle_captures": _CAPTURE_COLUMNS,
    "parking_sessions": _SESSION_COLUMNS,
}


def _sqlite_columns(conn: Connection, table: str) -> set[str]:
    return {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}


def apply_legacy_fixups(engine: Engine) -> list[str]:
    """Add columns the legacy start-up path used to add. Returns the ALTERs applied."""
    if engine.dialect.name != "sqlite":
        return []
    applied: list[str] = []
    with engine.begin() as conn:
        for table, columns in LEGACY_TABLES.items():
            existing = _sqlite_columns(conn, table)
            if not existing:
                continue
            for name, ddl in columns:
                if name in existing:
                    continue
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
                applied.append(f"{table}.{name}")
    return applied
