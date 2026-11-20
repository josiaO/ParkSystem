"""Release helper used by the Windows installer tooling (packaging/installer/bin/zirpctl.ps1).

    python -m app.release_tool revision
    python -m app.release_tool backup  --out FILE.sql
    python -m app.release_tool restore --in  FILE.sql --yes
    python -m app.release_tool version

``backup`` writes the same consistent SQL dump as the Backups page
(app/services/backup.dump_sql) plus ``FILE.sql.json`` with the schema revision,
so a rollback knows which code version the dump belongs to. ``restore`` is
destructive and refuses to run without ``--yes``; it first keeps the database
it is about to replace (SQLite: renamed file; PostgreSQL: another dump).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _configure_database() -> None:
    """Use the site's real database, exactly like app.site_service does.

    The production PostgreSQL URL is built from deployment.json plus the
    DPAPI-stored password; without this the settings fall back to SQLite.
    Must run before app.db is imported.
    """
    if os.environ.get("SMARTPARK_DATABASE_URL"):
        return
    from app.database_config import apply_runtime_database_config
    from app.deployment import load_deployment_config

    deployment = load_deployment_config()
    if deployment.configured:
        apply_runtime_database_config(deployment.database)


def _postgres_tool(name: str, env_var: str) -> str | None:
    """pg_dump/psql: explicit setting, PATH, then the newest local PostgreSQL install."""
    explicit = os.environ.get(env_var)
    if explicit:
        return explicit
    found = shutil.which(name)
    if found:
        return found
    if os.name == "nt":
        base = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "PostgreSQL"
        candidates = list(base.glob(f"*/bin/{name}.exe"))
        candidates.sort(key=lambda p: int(p.parts[-3]) if p.parts[-3].isdigit() else 0, reverse=True)
        if candidates:
            return str(candidates[0])
    return None


def _engine():
    from app.db import engine

    return engine


def schema_revision() -> str | None:
    from app.migrations.runner import current_revision

    try:
        return current_revision(_engine())
    except Exception:
        return None


def product_version() -> str:
    from app.config import install_directory

    marker = install_directory() / "VERSION"
    if marker.is_file():
        return marker.read_text(encoding="utf-8").strip()
    return "development"


def backup(out: Path) -> dict:
    from app.db import SessionLocal
    from app.services.backup import dump_sql

    out.parent.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        body = dump_sql(db)
    tmp = out.with_suffix(out.suffix + ".partial")
    tmp.write_bytes(body)
    os.replace(tmp, out)
    meta = {
        "file": out.name,
        "bytes": len(body),
        "schema_revision": schema_revision(),
        "dialect": _engine().dialect.name,
        "product_version": product_version(),
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    Path(str(out) + ".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def restore(src: Path) -> dict:
    engine = _engine()
    script = src.read_text(encoding="utf-8")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    if engine.dialect.name == "sqlite":
        db_path = Path(engine.url.database or "")
        if not db_path.is_file():
            raise SystemExit(f"SQLite database not found: {db_path}")
        engine.dispose()
        kept = db_path.with_name(f"{db_path.stem}.before-restore-{stamp}{db_path.suffix}")
        shutil.move(str(db_path), str(kept))
        for suffix in ("-wal", "-shm"):
            side = Path(str(db_path) + suffix)
            if side.exists():
                shutil.move(str(side), str(kept) + suffix)
        conn = sqlite3.connect(str(db_path))
        try:
            conn.executescript(script)
            conn.commit()
        finally:
            conn.close()
        return {"restored": str(src), "kept_previous": str(kept)}
    if engine.dialect.name == "postgresql":
        kept = src.with_name(f"before-restore-{stamp}.sql")
        backup(kept)
        psql = _postgres_tool("psql", "SMARTPARK_PSQL")
        if not psql:
            raise SystemExit("PostgreSQL restore needs psql from the PostgreSQL installation (set SMARTPARK_PSQL)")
        url = engine.url
        engine.dispose()
        env = os.environ.copy()
        if url.password:
            env["PGPASSWORD"] = str(url.password)
        base = [psql, "-v", "ON_ERROR_STOP=1", "--host", str(url.host or "127.0.0.1"),
                "--port", str(url.port or 5432), "--username", str(url.username or ""), str(url.database)]
        # One transaction (--single-transaction wraps every -c/-f): the schema
        # reset and the load commit together or not at all. A dump that fails
        # half way leaves the site database exactly as it was, not empty.
        loaded = subprocess.run(
            base + ["--single-transaction",
                    "-c", "DROP SCHEMA public CASCADE; CREATE SCHEMA public;",
                    "-f", str(src)],
            env=env, capture_output=True, timeout=3600,
        )
        if loaded.returncode != 0:
            raise SystemExit(f"Restore failed and was rolled back; the database is unchanged "
                             f"(a copy was also kept in {kept}): "
                             + loaded.stderr.decode("utf-8", "replace")[-800:])
        return {"restored": str(src), "kept_previous": str(kept)}
    raise SystemExit(f"Unsupported database: {engine.dialect.name}")


def check() -> tuple[int, dict]:
    """Pre-upgrade checks: can this version reach the site database, and back it up?

    Exit 0: ready. 3: blocking problem (``problems``). Warnings never block.
    """
    from app.deployment import load_deployment_config
    from app.migrations.runner import head_revision

    deployment = load_deployment_config()
    report: dict = {"configured": bool(deployment.configured), "role": deployment.role, "problems": [], "warnings": []}
    if not deployment.configured:
        report["warnings"].append("This PC is not set up yet: the Zirp setup wizard opens on first start.")
        return 0, report
    db = deployment.database
    report["engine"] = db.engine
    if deployment.role != "SITE_SERVER" and deployment.role != "EDGE_NODE":
        return 0, report
    try:
        from sqlalchemy import text

        engine = _engine()
        report["dialect"] = engine.dialect.name
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        report["database_reachable"] = True
    except Exception as exc:  # unreachable server, wrong password, PostgreSQL stopped
        where = f"{db.postgres_host}:{db.postgres_port}" if engine_is_postgres(report) else "the local database"
        report["database_reachable"] = False
        report["problems"].append(
            f"The site database ({where}) cannot be reached: {type(exc).__name__}: {str(exc).splitlines()[0][:200]}. "
            "Start PostgreSQL (or check the network and the database settings) and run setup again."
        )
        return 3, report
    report["schema_revision"] = schema_revision()
    report["head_revision"] = head_revision()
    if report["dialect"] == "postgresql" and deployment.role == "SITE_SERVER":
        tool = _postgres_tool("pg_dump", "SMARTPARK_PG_DUMP")
        report["pg_dump"] = tool or ""
        if not tool:
            report["problems"].append(
                "pg_dump (PostgreSQL client tools) was not found, so the database cannot be backed up before the "
                "upgrade. Install the PostgreSQL command-line tools on this PC, or set SMARTPARK_PG_DUMP, then run setup again."
            )
    return (3 if report["problems"] else 0), report


def engine_is_postgres(report: dict) -> bool:
    return str(report.get("engine") or "").upper().startswith("POSTGRES")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.release_tool")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("revision")
    sub.add_parser("version")
    sub.add_parser("check")
    h = sub.add_parser("health")
    h.add_argument("--url", required=True)
    h.add_argument("--timeout", type=float, default=4.0)
    b = sub.add_parser("backup")
    b.add_argument("--out", required=True)
    r = sub.add_parser("restore")
    r.add_argument("--in", dest="src", required=True)
    r.add_argument("--yes", action="store_true", help="confirm: this replaces the current database")
    args = parser.parse_args(argv)
    if args.command == "health":
        # Plain HTTP GET with every proxy disabled: what the installer uses to
        # decide whether a version is healthy (PowerShell's web cmdlets proved
        # unreliable for this on site PCs).
        import urllib.request

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(args.url, timeout=args.timeout) as response:
                print(response.status)
                return 0 if response.status == 200 else 1
        except Exception as exc:
            print(f"{type(exc).__name__}: {exc}"[:300])
            return 1
    _configure_database()
    pg_dump = _postgres_tool("pg_dump", "SMARTPARK_PG_DUMP")
    if pg_dump:
        os.environ["SMARTPARK_PG_DUMP"] = pg_dump   # read by app.services.backup.dump_sql
    if args.command == "check":
        code, report = check()
        print(json.dumps(report))
        return code
    if args.command == "revision":
        print(schema_revision() or "")
        return 0
    if args.command == "version":
        print(product_version())
        return 0
    if args.command == "backup":
        print(json.dumps(backup(Path(args.out))))
        return 0
    if not args.yes:
        print("Refusing to restore without --yes (this replaces the current database).", file=sys.stderr)
        return 2
    print(json.dumps(restore(Path(args.src))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
