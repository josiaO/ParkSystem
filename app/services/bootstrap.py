from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Role, User, UserRole, UserStatus
from app.security import hash_password, verify_password


def user_count(db: Session) -> int:
    return int(db.scalar(select(func.count(User.id))) or 0)


def ensure_bootstrap_admin(db: Session) -> bool:
    """Create the first admin so a Windows test PC can sign in without the CLI."""
    if user_count(db) > 0:
        return False
    admin_role = db.scalar(select(Role).where(Role.name == "Admin"))
    if admin_role is None:
        return False
    user = User(
        username=settings.bootstrap_username,
        full_name="Site Admin",
        password_hash=hash_password(settings.bootstrap_password),
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
    return verify_password(user.password_hash, settings.bootstrap_password)


def reset_bootstrap_admin(db: Session) -> str:
    """Set admin / SmartPark1! on this machine's database (local commissioning)."""
    admin_role = db.scalar(select(Role).where(Role.name == "Admin"))
    if admin_role is None:
        raise RuntimeError("Admin role is missing")
    user = db.scalar(select(User).where(User.username == settings.bootstrap_username))
    if user is None:
        ensure_bootstrap_admin(db)
        return "created"
    user.password_hash = hash_password(settings.bootstrap_password)
    user.status = UserStatus.ACTIVE.value
    db.commit()
    return "reset"


def setup_status(db: Session) -> dict:
    created = ensure_bootstrap_admin(db)
    bootstrap = db.scalar(select(User).where(User.username == settings.bootstrap_username))
    password_ok = bootstrap_password_works(db)
    usernames = [user.username for user in db.scalars(select(User)).all()]
    if created or password_ok:
        hint = f"Sign in as {settings.bootstrap_username} / {settings.bootstrap_password}"
        password = settings.bootstrap_password
    else:
        hint = (
            "This PC already has an admin account, so admin / SmartPark1! will not work. "
            "Use the existing password, or run: python -m app.cli reset-admin"
        )
        password = ""
    return {
        "ready": user_count(db) > 0,
        "username": settings.bootstrap_username,
        "password": password,
        "first_run": created,
        "bootstrap_user_present": bootstrap is not None,
        "bootstrap_password_ok": password_ok,
        "usernames": usernames,
        "hint": hint,
    }
