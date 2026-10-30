"""Rotating INFO logs. No per-frame, binary, secret, or healthy-heartbeat INFO lines."""

from __future__ import annotations

import logging
import os
import platform
import json
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

_configured: set[str] = set()


def _startup_context(process_name: str, settings, log_path: Path) -> dict:
    """Return safe context that makes a field log useful without secrets."""
    from app.services.runtime import app_version, data_dir

    try:
        from app.deployment import load_deployment_config

        deployment = load_deployment_config()
        deployment_role = deployment.role
        deployment_id = deployment.installation_id
    except Exception:
        deployment_role = ""
        deployment_id = ""

    return {
        "event": "startup",
        "product": "Zirp",
        "process": process_name,
        "pid": os.getpid(),
        "version": app_version(),
        "python": sys.version.split()[0],
        "python_bits": 64 if sys.maxsize > 2**32 else 32,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cwd": str(Path.cwd()),
        "executable": sys.executable,
        "data_dir": str(data_dir()),
        "log_file": str(log_path),
        "log_level": str(getattr(settings, "log_level", "INFO") or "INFO").upper(),
        "deployment_profile": os.environ.get("SMARTPARK_DEPLOYMENT_PROFILE", ""),
        "deployment_role": deployment_role,
        "deployment_installation_id": deployment_id,
        "node_role": str(getattr(settings, "node_role", "") or ""),
        "node_id": str(getattr(settings, "node_id", "") or ""),
        "recognition_gate_id": getattr(settings, "recognition_gate_id", None),
        "node_id_configured": bool(os.environ.get("SMARTPARK_NODE_ID")),
        "hvx_vendor_configured": bool(os.environ.get("SMARTPARK_HVX_VENDOR_DIR")),
        "mediamtx_configured": bool(os.environ.get("SMARTPARK_MEDIAMTX_BIN") or os.environ.get("SMARTPARK_MEDIAMTX")),
    }


def configure_logging(process_name: str = "smartpark") -> logging.Logger:
    if process_name in _configured:
        return logging.getLogger("smartpark")
    from app.config import settings
    from app.services.runtime import logs_dir

    level_name = str(getattr(settings, "log_level", "INFO") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    log = logging.getLogger("smartpark")
    log.setLevel(level)
    log.propagate = False
    filename = f"{process_name.replace(' ', '-').lower()}.log"
    try:
        dest = logs_dir() / filename
    except OSError:
        dest = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "SmartParkEdge" / "logs" / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        handler = RotatingFileHandler(
            dest,
            maxBytes=int(getattr(settings, "log_max_bytes", 5_000_000) or 5_000_000),
            backupCount=int(getattr(settings, "log_backup_count", 8) or 8),
            encoding="utf-8",
        )
    except OSError as exc:
        # A stale ACL on a previous ProgramData log must not stop the Site
        # Service, Media Service or recognition worker from starting. The
        # installer repairs the ACL, but this fallback keeps upgrades and
        # manually copied installations operational while preserving logs.
        fallback = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "SmartParkEdge" / "logs"
        fallback.mkdir(parents=True, exist_ok=True)
        dest = fallback / dest.name
        handler = RotatingFileHandler(
            dest,
            maxBytes=int(getattr(settings, "log_max_bytes", 5_000_000) or 5_000_000),
            backupCount=int(getattr(settings, "log_backup_count", 8) or 8),
            encoding="utf-8",
        )
        logging.getLogger().warning("Primary log unavailable (%s); using fallback log %s", exc, dest)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(process)d %(message)s"))
    if not any(isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", "") == str(dest) for h in log.handlers):
        log.addHandler(handler)
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler) for h in log.handlers):
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(stream)
    _configured.add(process_name)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    # Secrets (RTSP passwords, provider keys, webhook hashes) never reach a log line.
    from app.services.redaction import install_logging_redaction

    install_logging_redaction(log, logging.getLogger(), logging.getLogger("uvicorn"), logging.getLogger("uvicorn.error"))
    log.info("STARTUP %s", json.dumps(_startup_context(process_name, settings, dest), sort_keys=True, default=str))
    return log
