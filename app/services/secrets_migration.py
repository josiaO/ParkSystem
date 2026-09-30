"""Move legacy plaintext camera passwords into the configured SecretStore.

Runs once per Site Service start (cheap when nothing is left to move). Only
active when the store is external (dpapi/file/memory); with the legacy ``db``
backend rows are left as they are. A failure on one camera never blocks the
others or the start-up.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.secrets import SecretStoreError, describe, store_secret, uses_external_store
from app.models import Camera

log = logging.getLogger("smartpark")


def migrate_plaintext_secrets(db: Session) -> dict:
    """Return ``{"backend", "moved", "failed", "skipped"}``."""
    summary = {"backend": describe()["backend"], "moved": 0, "failed": 0, "skipped": 0}
    if not uses_external_store():
        return summary
    rows = db.scalars(select(Camera)).all()
    for cam in rows:
        raw = cam._password_secret or ""
        if not raw:
            summary["skipped"] += 1
            continue
        try:
            cam.credentials_ref = store_secret(raw, kind="camera", ref=cam.credentials_ref or None)
            cam._password_secret = ""
            summary["moved"] += 1
        except SecretStoreError as exc:
            summary["failed"] += 1
            log.warning("camera %s: could not move credential into %s store: %s", cam.id, summary["backend"], exc)
    if summary["moved"]:
        db.commit()
        log.info("secrets: moved %d camera credential(s) into the %s store", summary["moved"], summary["backend"])
    return summary
