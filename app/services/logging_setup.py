"""Rotating INFO logs. No per-frame, binary, secret, or healthy-heartbeat INFO lines."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

_configured: set[str] = set()


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
    dest = logs_dir() / f"{process_name.replace(' ', '-').lower()}.log"
    handler = RotatingFileHandler(
        dest,
        maxBytes=int(getattr(settings, "log_max_bytes", 5_000_000) or 5_000_000),
        backupCount=int(getattr(settings, "log_backup_count", 8) or 8),
        encoding="utf-8",
    )
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
    return log
