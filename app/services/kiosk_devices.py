"""Kiosk device credentials (Phase 2.3), modelled on the node credential.

A kiosk PC is enrolled once by an administrator. It then signs in with
``POST /kiosk/auth`` (device id + credential) instead of a person's password,
and re-authenticates by itself when its session expires, so the kiosk does
not log out in the middle of a shift.

The device acts through a dedicated service account with the Kiosk Operator
role (kiosk.use, payments.create: find one visit and take payment for it; no
session list, payment history or dashboard). That account has an
unusable password and cannot use ``/auth/login``. Revoking the device disables
the account and deletes its sessions immediately.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.site import DEFAULT_SITE_ID
from app.models import AuthSession, KioskDevice, Role, User, UserRole, UserStatus
from app.security import create_session, hash_password, verify_password

KIOSK_ROLE = "Kiosk Operator"
KIOSK_USERNAME_PREFIX = "kiosk-device:"
# Longer than a shift; the desktop also re-authenticates silently on expiry.
KIOSK_SESSION_HOURS = 24


def is_kiosk_service_account(username: str | None) -> bool:
    return str(username or "").startswith(KIOSK_USERNAME_PREFIX)


def device_dict(row: KioskDevice) -> dict:
    return {
        "id": row.id,
        "device_id": row.device_id,
        "name": row.name,
        "status": row.status,
        "site_id": row.site_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
    }


def create_device(db: Session, *, name: str, created_by: int | None, site_id: int = DEFAULT_SITE_ID) -> tuple[KioskDevice, str]:
    role = db.scalar(select(Role).where(Role.name == KIOSK_ROLE))
    if role is None:
        raise HTTPException(503, "Kiosk Operator role is not initialized")
    device_id = f"kiosk-{secrets.token_hex(6)}"
    credential = secrets.token_urlsafe(32)
    account = User(
        username=f"{KIOSK_USERNAME_PREFIX}{device_id}",
        full_name=f"Kiosk device: {name}"[:160],
        # Nobody knows this password; the account is reachable only through
        # the device credential.
        password_hash=hash_password(secrets.token_urlsafe(48)),
        status=UserStatus.ACTIVE.value,
    )
    db.add(account)
    db.flush()
    db.add(UserRole(user_id=account.id, role_id=role.id))
    row = KioskDevice(
        device_id=device_id,
        site_id=int(site_id or DEFAULT_SITE_ID),
        name=(name or device_id)[:160],
        credential_hash=hash_password(credential),
        user_id=account.id,
        created_by=created_by,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, credential


def authenticate_device(db: Session, device_id: str, credential: str) -> tuple[KioskDevice, User, str]:
    row = db.scalar(select(KioskDevice).where(KioskDevice.device_id == str(device_id or "").strip()))
    if (
        row is None
        or row.status != "ACTIVE"
        or row.revoked_at is not None
        or not row.credential_hash
        or not verify_password(row.credential_hash, str(credential or ""))
    ):
        raise HTTPException(401, "Invalid kiosk device or credential")
    user = db.get(User, row.user_id)
    if user is None or user.status != UserStatus.ACTIVE.value:
        raise HTTPException(401, "Invalid kiosk device or credential")
    row.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    token = create_session(db, user, hours=KIOSK_SESSION_HOURS)
    return row, user, token


def revoke_device(db: Session, row: KioskDevice) -> KioskDevice:
    row.status = "REVOKED"
    row.revoked_at = row.revoked_at or datetime.now(timezone.utc)
    user = db.get(User, row.user_id)
    if user is not None:
        user.status = UserStatus.DISABLED.value
        db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.commit()
    db.refresh(row)
    return row
