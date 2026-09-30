"""Start-up migration runner. Alembic is the only schema authority once active.

Strategy (``upgrade_to_head``):

1. **Fresh database** (no application tables): ``Base.metadata.create_all`` then
   ``alembic stamp head``. create_all is faster and always matches the models.
2. **Pre-Alembic database** (tables, no ``alembic_version``): run the frozen
   legacy column fixups, create any tables that never existed, stamp
   ``0001_baseline`` and ``upgrade head``.
3. **Alembic-managed database**: ``upgrade head``.

The runner takes a process-wide lock file so two Site Service starts do not
race the same SQLite file. Errors propagate: a half-migrated schema must stop
the Site Service instead of running against unknown columns.
"""

from __future__ import annotations

import logging
from pathlib import Path
import threading
import time
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

log = logging.getLogger("smartpark")

BASELINE_REVISION = "0001_baseline"
SCRIPT_LOCATION = Path(__file__).resolve().parent / "alembic"
_APP_TABLES = ("cameras", "gates", "users")
_lock = threading.Lock()
_last: dict[str, Any] = {"mode": "", "at": None, "revision": None, "head": None, "legacy_fixups": []}


def alembic_config(engine: Engine | None = None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(SCRIPT_LOCATION))
    cfg.set_main_option("version_path_separator", "os")
    if engine is not None:
        cfg.set_main_option("sqlalchemy.url", str(engine.url.render_as_string(hide_password=False)))
    return cfg


def head_revision() -> str | None:
    script = ScriptDirectory.from_config(alembic_config())
    return script.get_current_head()


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def _has_app_tables(engine: Engine) -> bool:
    names = set(inspect(engine).get_table_names())
    return any(t in names for t in _APP_TABLES)


def _run(engine: Engine, fn, *args) -> None:
    cfg = alembic_config(engine)
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        fn(cfg, *args)


def upgrade_to_head(engine: Engine) -> dict[str, Any]:
    """Bring *engine*'s database to the newest revision. Returns a summary dict."""
    from app.db import Base
    from app import models as _models  # noqa: F401
    from app.migrations.legacy import apply_legacy_fixups

    with _lock:
        started = time.perf_counter()
        current = current_revision(engine)
        fixups: list[str] = []
        if current is not None:
            mode = "upgrade"
            _run(engine, command.upgrade, "head")
        elif not _has_app_tables(engine):
            mode = "fresh"
            Base.metadata.create_all(engine)
            _run(engine, command.stamp, "head")
        else:
            mode = "adopt"
            fixups = apply_legacy_fixups(engine)
            Base.metadata.create_all(engine)  # tables that never existed before
            _run(engine, command.stamp, BASELINE_REVISION)
            _run(engine, command.upgrade, "head")
        revision = current_revision(engine)
        head = head_revision()
        _last.update(
            mode=mode,
            at=time.time(),
            revision=revision,
            head=head,
            legacy_fixups=fixups,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        if mode != "upgrade" or fixups:
            log.info("schema %s: revision=%s head=%s legacy_fixups=%d", mode, revision, head, len(fixups))
        return dict(_last)


def status(engine: Engine | None = None) -> dict[str, Any]:
    """Health payload: current vs head revision and how the last start applied it."""
    out = dict(_last)
    try:
        out["head"] = head_revision()
        if engine is not None:
            out["revision"] = current_revision(engine)
    except Exception as exc:  # never let health die on migration metadata
        out["error"] = str(exc)[:200]
    out["up_to_date"] = bool(out.get("revision")) and out.get("revision") == out.get("head")
    return out
