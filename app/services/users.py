from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.models import AuthSession, Role, User, UserRole, UserStatus
from app.security import hash_password, user_permissions


def load_user(db: Session, user_id: int) -> User | None:
    return db.scalar(
        select(User)
        .options(selectinload(User.roles).selectinload(UserRole.role))
        .where(User.id == user_id)
    )


def load_users(db: Session) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .options(selectinload(User.roles).selectinload(UserRole.role))
            .order_by(User.id)
        ).all()
    )


def user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "status": user.status,
        "created_at": user.created_at,
        "roles": [ur.role.name for ur in user.roles],
        "permissions": sorted(user_permissions(user)),
    }


def validate_status(status: str) -> str:
    allowed = {item.value for item in UserStatus}
    if status not in allowed:
        raise HTTPException(400, f"Invalid status. Use one of: {', '.join(sorted(allowed))}")
    return status


def set_user_roles(db: Session, user: User, role_names: list[str]) -> None:
    names = [name.strip() for name in role_names if name.strip()]
    if not names:
        raise HTTPException(400, "A user needs at least one role")
    roles = list(db.scalars(select(Role).where(Role.name.in_(names))).all())
    found = {role.name for role in roles}
    missing = [name for name in names if name not in found]
    if missing:
        raise HTTPException(400, f"Unknown roles: {', '.join(missing)}")
    db.execute(delete(UserRole).where(UserRole.user_id == user.id))
    db.flush()
    for role in roles:
        db.add(UserRole(user_id=user.id, role_id=role.id))
    db.flush()


def is_admin(user: User) -> bool:
    return any(ur.role.name == "Admin" for ur in user.roles)


def admin_count(db: Session) -> int:
    admin = db.scalar(select(Role).where(Role.name == "Admin"))
    if not admin:
        return 0
    return db.scalar(select(func.count()).select_from(UserRole).where(UserRole.role_id == admin.id)) or 0


def ensure_not_last_admin(db: Session, user: User, next_roles: list[str] | None = None, deleting: bool = False) -> None:
    if not is_admin(user):
        return
    dropping_admin = deleting or (next_roles is not None and "Admin" not in next_roles)
    if dropping_admin and admin_count(db) <= 1:
        raise HTTPException(409, "Cannot remove or delete the last Admin")


def create_user(db: Session, *, username: str, full_name: str, password: str, status: str, roles: list[str]) -> User:
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(409, "Username already exists")
    user = User(
        username=username,
        full_name=full_name,
        password_hash=hash_password(password),
        status=validate_status(status),
    )
    db.add(user)
    db.flush()
    set_user_roles(db, user, roles)
    db.commit()
    db.expire_all()
    loaded = load_user(db, user.id)
    assert loaded is not None
    return loaded


def update_user(db: Session, user: User, *, full_name: str | None, password: str | None, status: str | None, roles: list[str] | None) -> User:
    ensure_not_last_admin(db, user, next_roles=roles)
    if full_name is not None:
        user.full_name = full_name
    if password:
        user.password_hash = hash_password(password)
    if status is not None:
        user.status = validate_status(status)
    if roles is not None:
        set_user_roles(db, user, roles)
    db.commit()
    db.expire_all()
    loaded = load_user(db, user.id)
    assert loaded is not None
    return loaded


def delete_user(db: Session, user: User, acting_user_id: int) -> None:
    if user.id == acting_user_id:
        raise HTTPException(409, "Cannot delete the signed-in account")
    ensure_not_last_admin(db, user, deleting=True)
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.delete(user)
    db.commit()
