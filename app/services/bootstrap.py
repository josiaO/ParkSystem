from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Role, User, UserRole, UserStatus
from app.security import hash_password, verify_password

MIN_BOOTSTRAP_LEN = 12
# The first-run password is disclosed over HTTP at most once, to a request
# from the Site Server itself, and only this long after the admin was made.
FIRST_RUN_WINDOW = timedelta(hours=24)


def bootstrap_password_path() -> Path:
    return settings.data_dir / "bootstrap_password.txt"


def bootstrap_disclosure_marker() -> Path:
    return settings.data_dir / "bootstrap_password.disclosed"


def _within_first_run_window(user: User) -> bool:
    created = getattr(user, "created_at", None)
    if created is None:
        return False
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - created <= FIRST_RUN_WINDOW


def claim_bootstrap_disclosure() -> bool:
    """Atomically claim the single HTTP disclosure of the first-run password."""
    marker = bootstrap_disclosure_marker()
    marker.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(datetime.now(timezone.utc).isoformat() + "\n")
    return True


def generate_bootstrap_password() -> str:
    # URL-safe, mixed, long enough for the CLI create-admin rule (10+).
    return secrets.token_urlsafe(18)


def effective_bootstrap_password() -> str:
    """Env override wins. Otherwise reuse or create a per-install password file."""
    explicit = str(settings.bootstrap_password or "").strip()
    if explicit:
        return explicit
    path = bootstrap_password_path()
    if path.is_file():
        stored = path.read_text(encoding="utf-8").strip()
        if stored:
            return stored
    password = generate_bootstrap_password()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(password + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return password


def user_count(db: Session) -> int:
    return int(db.scalar(select(func.count(User.id))) or 0)


def ensure_bootstrap_admin(db: Session) -> bool:
    """Create the first admin so a Windows test PC can sign in without the CLI."""
    if user_count(db) > 0:
        return False
    admin_role = db.scalar(select(Role).where(Role.name == "Admin"))
    if admin_role is None:
        return False
    password = effective_bootstrap_password()
    user = User(
        username=settings.bootstrap_username,
        full_name="Site Admin",
        password_hash=hash_password(password),
    )
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=admin_role.id))
    db.commit()
    return True


def bootstrap_password_works(db: Session) -> bool:
    user = db.scalar(select(User).where(User.username == settings.bootstrap_username))
    if user is None:
        return False
    return verify_password(user.password_hash, effective_bootstrap_password())


def reset_bootstrap_admin(db: Session) -> str:
    """Reset the bootstrap admin to the effective install password."""
    admin_role = db.scalar(select(Role).where(Role.name == "Admin"))
    if admin_role is None:
        raise RuntimeError("Admin role is missing")
    user = db.scalar(select(User).where(User.username == settings.bootstrap_username))
    if user is None:
        ensure_bootstrap_admin(db)
        return "created"
    if not str(settings.bootstrap_password or "").strip():
        path = bootstrap_password_path()
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    password = effective_bootstrap_password()
    user.password_hash = hash_password(password)
    user.status = UserStatus.ACTIVE.value
    db.commit()
    return "reset"


def setup_status(db: Session, *, local_request: bool = False) -> dict:
    """First-run sign-in help.

    The bootstrap password is disclosed at most once: to a request from the
    Site Server itself (loopback, not proxied), while it still works, and
    within FIRST_RUN_WINDOW of the admin being created. After that it is
    only in the 0600 file on the server. Account names are never listed.
    """
    from app.services.platform_capabilities import platform_snapshot, recommended_camera_adapter

    created = ensure_bootstrap_admin(db)
    bootstrap = db.scalar(select(User).where(User.username == settings.bootstrap_username))
    password_ok = bootstrap_password_works(db)
    platform = platform_snapshot()
    path = bootstrap_password_path()
    password = ""
    if not local_request:
        hint = (
            "Sign in with your account. The first-run administrator password is shown only "
            f"on the Site Server itself (and stored in {path.name} there)."
        )
    elif not password_ok:
        hint = (
            "This PC already has an admin account, so an older password will be rejected. "
            f"The install password is in {path}. "
            "If that password is rejected, run: python -m app.cli reset-admin"
        )
    elif bootstrap is not None and _within_first_run_window(bootstrap) and claim_bootstrap_disclosure():
        password = effective_bootstrap_password()
        hint = (
            f"First-run admin is {settings.bootstrap_username} / {password}. "
            f"It is shown only once; it is also stored in {path}. Change it after signing in."
        )
    else:
        hint = f"Sign in as {settings.bootstrap_username} with the first-run password stored in {path} on this PC"
    if not platform["hvx_host_supported"]:
        hint = (
            f"{hint}. This host is {platform['os']}: use the browser UI. "
            "For normal IP cameras pick adapter rtsp (or dahua/hikvision). "
            "HVX LAPR cameras need a Windows PC running the 32-bit SDK host."
        )
    return {
        "ready": user_count(db) > 0,
        "username": settings.bootstrap_username,
        "password": password,
        "first_run": created,
        "bootstrap_user_present": bootstrap is not None,
        "bootstrap_password_ok": password_ok,
        "hint": hint,
        "platform": platform,
        "recommended_camera_adapter": recommended_camera_adapter(),
    }
