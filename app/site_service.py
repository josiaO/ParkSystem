"""Site Service: FastAPI + camera events. No Qt UI. No NetSDK in-process."""

from __future__ import annotations

import os
import sys


def _database_startup_check(deployment) -> None:
    """Fail before importing the API when the persisted DB cannot be opened.

    The wizard tests a candidate URL in its own process.  The Windows task
    later resolves the persisted secret and creates the ORM engine again, so a
    missing DPAPI file/ACL or a changed PostgreSQL password otherwise appears
    only as "API did not start".  Keep this check small and side-effect free;
    migrations remain owned by the API lifespan.
    """
    from sqlalchemy import create_engine, text

    from app.database_config import POSTGRESQL, database_url
    from app.services.redaction import redact_text

    config = deployment.database
    if config.engine == POSTGRESQL and config.postgres_secret_reference:
        from app.infrastructure.secrets import resolve_secret

        if not resolve_secret(config.postgres_secret_reference):
            raise RuntimeError(
                "PostgreSQL password could not be read from the protected SmartParkEdge secret store "
                f"(reference {config.postgres_secret_reference}). Check the service account access to "
                "the SmartParkEdge data directory or run Deployment Configuration again."
            )

    url = database_url(config)
    connect_args = {"connect_timeout": 5} if config.engine == POSTGRESQL else {}
    engine = create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        safe = redact_text(f"{type(exc).__name__}: {exc}")[:800]
        raise RuntimeError(f"{config.display_name} connection failed: {safe}") from exc
    finally:
        engine.dispose()


def main() -> int:
    from app.services.logging_setup import configure_logging
    from app.services.runtime import acquire_instance_lock, install_crash_hooks
    from app.services.platform_capabilities import platform_snapshot

    install_crash_hooks("SmartParkSiteService")
    configure_logging("site-service")
    if not acquire_instance_lock("site-service"):
        print("SmartPark Site Service is already running.", file=sys.stderr)
        return 0
    from app.config import settings
    from app.deployment import CONFIGURED, load_deployment_config
    from app.database_config import apply_runtime_database_config
    import logging

    deployment = load_deployment_config()
    if not deployment.runs_local_gate_runtime:
        print("Operator Workstation does not start SmartPark Site Service.", file=sys.stderr)
        return 2
    if not deployment.configured or deployment.state != CONFIGURED:
        print("SmartPark deployment is not configured; complete Deployment Configuration first.", file=sys.stderr)
        return 2
    print(
        f"Zirp Site Service role={deployment.role} state={deployment.state} "
        f"database={deployment.database.display_name} node_role={os.environ.get('SMARTPARK_NODE_ROLE', 'SERVER')}",
        flush=True,
    )
    apply_runtime_database_config(deployment.database)
    try:
        _database_startup_check(deployment)
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        logging.getLogger("smartpark").error("DATABASE STARTUP FAILED: %s", message, exc_info=True)
        print(f"Zirp Site Service database startup failed: {message}", file=sys.stderr, flush=True)
        return 3
    # Keep the offline detector/OCR cache with the Site Server data so a
    # scheduled task and the operator account use the same model files. This
    # does not warm FastALPR; the engine remains lazy and only loads when a
    # camera actually needs software recognition.
    os.environ.setdefault("SMARTPARK_ALPR_CACHE_DIR", str(settings.data_dir / "model-cache"))
    snap = platform_snapshot()
    if not snap["hvx_host_supported"]:
        print(f"Site Service on {snap['os']}: HVX host skipped. Prefer browser UI + rtsp adapters.")
    import uvicorn
    from app.api_main import app

    bind_host = deployment.server_bind_host if deployment.runs_local_gate_runtime else settings.api_host
    bind_port = int(deployment.server_bind_port or settings.api_port) if deployment.runs_local_gate_runtime else settings.api_port
    uvicorn.run(
        app,
        host=bind_host,
        port=bind_port,
        log_level="warning",
        access_log=False,
        reload=False,
        workers=1,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
