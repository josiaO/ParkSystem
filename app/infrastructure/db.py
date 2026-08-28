"""Database access. SQLite is the live store; PostgreSQL is an optional URL switch.

Do not migrate production to PostgreSQL as a prerequisite. Set
``SMARTPARK_DATABASE_URL=postgresql+psycopg://...`` when you are ready.
"""

from app.db import (  # noqa: F401
    Base,
    SessionLocal,
    engine,
    engine_kwargs,
    ensure_schema,
    get_db,
    is_postgres,
    is_sqlite,
)
