from __future__ import annotations

import secrets
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Role, User, UserRole, UserStatus
from app.security import hash_password, verify_password

MIN_BOOTSTRAP_LEN = 12


def bootstrap_password_path() -> Path:
    return settings.data_dir / "bootstrap_password.txt"


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


def setup_status(db: Session) -> dict:
    from app.services.platform_capabilities import platform_snapshot, recommended_camera_adapter

    created = ensure_bootstrap_admin(db)
    bootstrap = db.scalar(select(User).where(User.username == settings.bootstrap_username))
    password_ok = bootstrap_password_works(db)
    usernames = [user.username for user in db.scalars(select(User)).all()]
    platform = platform_snapshot()
    password = effective_bootstrap_password() if created or password_ok else ""
    if created:
        hint = (
            f"First-run admin is {settings.bootstrap_username} / {password}. "
            f"This password is also written once to {bootstrap_password_path()}."
        )
    elif password_ok:
        hint = f"Sign in as {settings.bootstrap_username} with the install password"
    else:
        hint = (
            "This PC already has an admin account, so the first-run password will not work. "
            "Use the existing password, or run: python -m app.cli reset-admin"
        )
        password = ""
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
        "usernames": usernames,
        "hint": hint,
        "platform": platform,
        "recommended_camera_adapter": recommended_camera_adapter(),
    }
