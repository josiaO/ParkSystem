"""Database engine. SQLite is the current store; PostgreSQL is a URL switch later.

Set ``SMARTPARK_DATABASE_URL=postgresql+psycopg://user:pass@host/smartpark``
when you are ready. Models use portable SQLAlchemy types (no SQLite-only columns).
"""

from __future__ import annotations

import time

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool

from .config import settings


class Base(DeclarativeBase):
    pass


def is_sqlite(url: str | None = None) -> bool:
    return (url or settings.resolved_database_url).startswith("sqlite")


def is_postgres(url: str | None = None) -> bool:
    value = (url or settings.resolved_database_url).lower()
    return value.startswith("postgresql") or value.startswith("postgres")


def engine_kwargs(url: str) -> dict:
    kwargs: dict = {"future": True, "pool_pre_ping": True}
    if is_sqlite(url):
        # Default QueuePool(5, overflow=10) dies when live MJPEG and snapshot
        # polls hold connections. NullPool opens/closes per session.
        kwargs["poolclass"] = NullPool
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 15}
    else:
        kwargs["poolclass"] = QueuePool
        kwargs["pool_size"] = max(1, int(getattr(settings, "db_pool_size", 5) or 5))
        kwargs["max_overflow"] = max(0, int(getattr(settings, "db_max_overflow", 5) or 5))
        kwargs["pool_timeout"] = float(getattr(settings, "db_pool_timeout_seconds", 8) or 8)
    return kwargs


engine = create_engine(settings.resolved_database_url, **engine_kwargs(settings.resolved_database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
_session_factory = None


def set_session_factory(factory=None) -> None:
    """Tests point short-lived media/auth sessions at the same in-memory DB."""
    global _session_factory
    _session_factory = factory


def short_session():
    """Open a session that the caller must close. Do not use for MJPEG Depends()."""
    factory = _session_factory or SessionLocal
    return factory()


@event.listens_for(engine, "before_cursor_execute")
def _before_cursor(conn, cursor, statement, parameters, context, executemany):
    conn.info["smartpark_query_started"] = time.perf_counter()


@event.listens_for(engine, "after_cursor_execute")
def _after_cursor(conn, cursor, statement, parameters, context, executemany):
    started = conn.info.pop("smartpark_query_started", None)
    if started is None:
        return
    ms = (time.perf_counter() - started) * 1000
    try:
        from app.services.health import note_db_latency
        note_db_latency(ms, str(statement or "").split("\n", 1)[0])
    except Exception:
        pass


@event.listens_for(engine, "connect")
def _sqlite_on_connect(dbapi_conn, _connection_record):
    if not is_sqlite():
        return
    cur = dbapi_conn.cursor()
    try:
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA synchronous=NORMAL")
    finally:
        cur.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema() -> None:
    """create_all will not add columns to an existing SQLite file."""
    from . import models as _models  # noqa: F401

    Base.metadata.create_all(engine)
    if not is_sqlite():
        return
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(cameras)")}
        if "controller_ip" not in cols:
            conn.exec_driver_sql("ALTER TABLE cameras ADD COLUMN controller_ip VARCHAR(64) DEFAULT ''")
        if "display_ip" not in cols:
            conn.exec_driver_sql("ALTER TABLE cameras ADD COLUMN display_ip VARCHAR(64) DEFAULT ''")
        if "adapter_id" not in cols:
            conn.exec_driver_sql("ALTER TABLE cameras ADD COLUMN adapter_id VARCHAR(40) DEFAULT 'hvx'")
        if "connection_mode" not in cols:
            conn.exec_driver_sql("ALTER TABLE cameras ADD COLUMN connection_mode VARCHAR(20) DEFAULT 'DIRECT'")
        session_cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(parking_sessions)")}
        if session_cols:
            if "public_token" not in session_cols:
                conn.exec_driver_sql("ALTER TABLE parking_sessions ADD COLUMN public_token VARCHAR(64) DEFAULT ''")
            if "receipt_status" not in session_cols:
                conn.exec_driver_sql("ALTER TABLE parking_sessions ADD COLUMN receipt_status VARCHAR(20) DEFAULT ''")
            if "simulated" not in session_cols:
                conn.exec_driver_sql("ALTER TABLE parking_sessions ADD COLUMN simulated BOOLEAN DEFAULT 0")
            if "parker_kind" not in session_cols:
                conn.exec_driver_sql("ALTER TABLE parking_sessions ADD COLUMN parker_kind VARCHAR(40) DEFAULT 'CASUAL'")
            if "access_plan_id" not in session_cols:
                conn.exec_driver_sql("ALTER TABLE parking_sessions ADD COLUMN access_plan_id INTEGER")
            if "vehicle_id" not in session_cols:
                conn.exec_driver_sql("ALTER TABLE parking_sessions ADD COLUMN vehicle_id INTEGER")
