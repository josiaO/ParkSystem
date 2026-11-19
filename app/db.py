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
        kwargs["pool_timeout"] = float(getattr(settings, "db_pool_timeout_seconds", 5) or 5)
        # Recycle before NAT/firewalls silently drop idle connections.
        kwargs["pool_recycle"] = 1800
        kwargs["connect_args"] = postgres_connect_args()
    return kwargs


def postgres_connect_args() -> dict:
    """libpq options so a lane never hangs on a dead or slow Site Server link.

    * connect_timeout: give up on an unreachable server in seconds.
    * TCP keepalives: notice a silently dropped link (cable, switch, power)
      instead of waiting for the OS's two-hour default.
    * statement_timeout / idle_in_transaction_session_timeout: the server
      cancels a query stuck behind a lock or a slow disk. Migrations lift it.
    """
    import os

    options = []
    statement_ms = int(getattr(settings, "db_statement_timeout_ms", 15000) or 0)
    idle_ms = int(getattr(settings, "db_idle_in_transaction_timeout_ms", 60000) or 0)
    if statement_ms > 0:
        options.append(f"-c statement_timeout={statement_ms}")
    if idle_ms > 0:
        options.append(f"-c idle_in_transaction_session_timeout={idle_ms}")
    args: dict = {
        "connect_timeout": max(1, int(getattr(settings, "db_connect_timeout_seconds", 5) or 5)),
        "keepalives": 1,
        "keepalives_idle": max(1, int(getattr(settings, "db_keepalives_idle_seconds", 10) or 10)),
        "keepalives_interval": max(1, int(getattr(settings, "db_keepalives_interval_seconds", 5) or 5)),
        "keepalives_count": max(1, int(getattr(settings, "db_keepalives_count", 3) or 3)),
        "options": " ".join(options),
        "application_name": f"smartpark-{os.path.basename(os.environ.get('SMARTPARK_PROCESS_NAME', 'service'))}"[:60],
    }
    sslmode = str(getattr(settings, "db_sslmode", "") or "").strip().lower()
    if sslmode:
        args["sslmode"] = sslmode
    return args


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


def release_connection(session) -> None:
    """Return a checked-out connection before slow external work.

    Camera SDK calls, OCR, printers, payment providers, and gate controllers
    can await for seconds. A transaction checkpoint lets SQLAlchemy return the
    connection to the pool while that external work is in flight.
    """
    if session is None:
        return
    try:
        session.commit()
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass


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
        # WAL needs free disk for -wal/-shm. On a full disk, fall back so the
        # API can still answer instead of crashing every request on connect.
        try:
            cur.execute("PRAGMA journal_mode=WAL")
        except Exception:
            try:
                cur.execute("PRAGMA journal_mode=DELETE")
            except Exception:
                pass
        try:
            cur.execute("PRAGMA busy_timeout=5000")
            cur.execute(f"PRAGMA synchronous={sqlite_synchronous_mode()}")
        except Exception:
            pass
    finally:
        cur.close()


def sqlite_synchronous_mode(profile: str | None = None) -> str:
    """FULL wherever the SQLite file is a lane's parking authority.

    In WAL mode ``synchronous=NORMAL`` can roll back the last commits after a
    power cut, so a barrier could have opened for a decision that no longer
    exists (docs/ZIRP_HIGH_THROUGHPUT_ARCHITECTURE.md section 4). FULL costs
    one more disk flush per commit. Development keeps NORMAL for speed.
    """
    if profile is None:
        profile = str(getattr(settings, "deployment_profile", "DEVELOPMENT") or "DEVELOPMENT")
    return "NORMAL" if profile.strip().upper() == "DEVELOPMENT" else "FULL"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema() -> dict:
    """Bring the live database to the newest Alembic revision.

    Fresh files are created with ``create_all`` and stamped; pre-Alembic files
    get the frozen legacy column fixups once, then Alembic takes over. Schema
    changes are Alembic revisions under ``app/migrations/alembic/versions`` —
    never ad-hoc ``ALTER TABLE`` here.
    """
    from .migrations.runner import upgrade_to_head

    return upgrade_to_head(engine)
