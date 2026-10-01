"""Alembic environment. URL comes from settings; the runner may pass a live connection."""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.db import Base
from app import models as _models  # noqa: F401  (register tables on Base.metadata)

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    from app.config import settings

    return config.get_main_option("sqlalchemy.url") or settings.resolved_database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _configure(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _configure(connection)
        return
    section = dict(config.get_section(config.config_ini_section) or {})
    section["sqlalchemy.url"] = _url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as conn:
        _configure(conn)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
