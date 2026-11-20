"""Site database facts and reset, for the factory-reset script.

    python -m app.cli db status                      JSON: role, engine, where data and photos live
    python -m app.cli db reset --confirm-name NAME   Site Server only: empty the PostgreSQL database

A factory reset deletes ``%ProgramData%\\SmartParkEdge`` (photos, logs, local
SQLite). With PostgreSQL the visit records live elsewhere, so wiping only the
files left records pointing at missing photos (SERVER01 lost 4,435 photos
that way). ``zirpctl purge-data`` (packaging/installer/bin) asks this module what the PC holds and then
either resets the database too (Site Server) or keeps the site data.

Edge Nodes and operator workstations never reset the database: it is the
whole site's data, owned by the Site Server.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def status() -> dict[str, Any]:
    from app.config import settings
    from app.database_config import POSTGRESQL
    from app.deployment import load_deployment_config

    deployment = load_deployment_config()
    db = deployment.database
    shared_media = str(settings.shared_media_dir or "")
    return {
        "configured": bool(deployment.configured),
        "role": deployment.role,
        "engine": db.engine,
        "postgres": db.engine == POSTGRESQL,
        "database": db.postgres_database if db.engine == POSTGRESQL else str(db.sqlite_path or "smartpark.db"),
        "host": db.postgres_host if db.engine == POSTGRESQL else "",
        "media_dir": str(settings.media_dir),
        "shared_media": bool(shared_media),
        # Photos referenced by an external database live in this PC's local
        # data folder: deleting them alone orphans the records.
        "local_photos_referenced_externally": db.engine == POSTGRESQL and not shared_media,
        "may_reset_database": deployment.role == "SITE_SERVER" and db.engine == POSTGRESQL,
    }


def drop_all_tables(engine: Engine) -> list[str]:
    """Drop every table in the default schema (application data and Alembic state)."""
    names = inspect(engine).get_table_names()
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            for name in names:
                conn.execute(text(f'DROP TABLE IF EXISTS "{name}" CASCADE'))
        else:
            conn.execute(text("PRAGMA foreign_keys=OFF"))
            for name in names:
                conn.execute(text(f'DROP TABLE IF EXISTS "{name}"'))
    return names


def reset(confirm_name: str) -> dict[str, Any]:
    """Empty the site PostgreSQL database. Refuses unless every guard passes."""
    from sqlalchemy import create_engine

    from app.database_config import database_url
    from app.deployment import load_deployment_config

    facts = status()
    if not facts["postgres"]:
        raise PermissionError("This PC does not use PostgreSQL; the local database is deleted with the data folder.")
    if not facts["may_reset_database"]:
        raise PermissionError(
            f"This PC is a {facts['role']}: the PostgreSQL database holds the whole site's data and "
            "is reset only from the Site Server."
        )
    if str(confirm_name or "") != facts["database"]:
        raise PermissionError(f"Type the database name exactly to confirm (expected '{facts['database']}').")
    engine = create_engine(database_url(load_deployment_config().database), future=True)
    try:
        dropped = drop_all_tables(engine)
    finally:
        engine.dispose()
    return {"ok": True, "database": facts["database"], "host": facts["host"], "tables_dropped": len(dropped)}


def main(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m app.cli db")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("status")
    p = sub.add_parser("reset")
    p.add_argument("--confirm-name", required=True, help="the PostgreSQL database name, typed exactly")
    args = parser.parse_args(argv)
    try:
        result = status() if args.action == "status" else reset(args.confirm_name)
    except PermissionError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 3
    except Exception as exc:  # unreachable server, bad credentials
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"[:400]}))
        return 4
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
