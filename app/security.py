from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .db import get_db, short_session
from .models import AuthSession, User, UserRole, UserStatus


# These are the only API capabilities a Processing Node may use.  A node may
# still use an administrator account from the shared database for backwards
# compatibility, but the installation boundary wins over that account: the
# node cannot use the token to browse or modify central users, settings,
# payments, tariffs, subscribers, backups, or site topology.
_PROCESSING_NODE_ALLOWED_PERMISSIONS = frozenset({
    "cameras.view",
    "cameras.manage",
    "cameras.connect",
    "gates.view",
    "gates.open",
    "gates.open_simulated",
    "hardware.view",
})


def processing_node_permissions(permissions: set[str]) -> set[str]:
    """Return the permissions safe to advertise from a Processing Node."""
    if not _processing_node_installation():
        return set(permissions)
    return set(permissions) & _PROCESSING_NODE_ALLOWED_PERMISSIONS


def _node_permission_allowed(permission: str, *, processing_node_allowed: bool = False) -> bool:
    if not _processing_node_installation():
        return True
    # This opt-in is deliberately used only by the persisted gate-owner
    # assignment endpoint. It is not a general way to bypass the node wall.
    if processing_node_allowed and permission == "settings.manage":
        return True
    return permission in _PROCESSING_NODE_ALLOWED_PERMISSIONS


def _processing_node_installation() -> bool:
    try:
        from app.services.node_scope import is_processing_node

        return bool(is_processing_node())
    except Exception:
        return False

_ph = PasswordHasher()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHash, VerificationError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User, hours: int = 12) -> str:
    token = secrets.token_urlsafe(48)
    db.add(AuthSession(
        user_id=user.id,
        token_hash=_token_hash(token),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=hours),
    ))
    db.commit()
    return token


def user_permissions(user: User) -> set[str]:
    perms: set[str] = set()
    for ur in user.roles:
        perms |= ur.role.permissions()
    return perms


def is_processing_node_account(user: User) -> bool:
    """Whether a shared-database user is reserved for one Processing Node."""
    return any(getattr(getattr(link, "role", None), "name", "") == "Processing Node" for link in user.roles)


def _configured_node_username() -> str:
    try:
        from app.deployment import load_deployment_config

        return load_deployment_config().node_username.strip().casefold()
    except Exception:
        return ""


def _enforce_installation_account_boundary(user: User) -> None:
    """Keep node accounts on their node and site accounts on the server."""
    if _processing_node_installation():
        expected = _configured_node_username()
        if not expected or str(user.username).strip().casefold() != expected:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This Processing Node accepts only its own configured account.",
            )
    elif is_processing_node_account(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Processing Node accounts can sign in only on their paired Processing Node.",
        )


def authenticate_user(db: Session, username: str, password: str) -> User:
    user = db.scalar(
        select(User)
        .options(selectinload(User.roles).selectinload(UserRole.role))
        .where(User.username == username)
    )
    if not user or not verify_password(user.password_hash, password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    if user.status != UserStatus.ACTIVE.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account unavailable")
    return user


def revoke_session(db: Session, token: str) -> None:
    row = db.scalar(select(AuthSession).where(AuthSession.token_hash == _token_hash(token)))
    if row:
        db.delete(row)
        db.commit()


def load_user_from_token(db: Session, token: str | None) -> User:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    row = db.scalar(select(AuthSession).where(AuthSession.token_hash == _token_hash(token)))
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    user = db.scalar(
        select(User)
        .options(selectinload(User.roles).selectinload(UserRole.role))
        .where(User.id == row.user_id)
    )
    if not user or user.status != UserStatus.ACTIVE.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account unavailable")
    _enforce_installation_account_boundary(user)
    return user


def current_user(
    token: str | None = Depends(oauth2_scheme),
    access_token: str | None = Query(default=None, include_in_schema=False),
    db: Session = Depends(get_db),
) -> User:
    return load_user_from_token(db, token or access_token)


def media_user(
    token: str | None = Depends(oauth2_scheme),
    access_token: str | None = Query(default=None, include_in_schema=False),
) -> User:
    """Auth for long-lived streams. Closes the DB before MJPEG/snapshot starts."""
    db = short_session()
    try:
        return load_user_from_token(db, token or access_token)
    finally:
        db.close()


def require(permission: str, *, processing_node_allowed: bool = False):
    def dep(user: User = Depends(current_user)) -> User:
        if not _node_permission_allowed(permission, processing_node_allowed=processing_node_allowed):
            raise HTTPException(
                status_code=403,
                detail="Processing Nodes cannot access central site data or configuration. Use the Site Server.",
            )
        perms = user_permissions(user)
        if "*" not in perms and permission not in perms:
            raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")
        return user
    return dep


def require_any(*permissions: str):
    def dep(user: User = Depends(current_user)) -> User:
        if _processing_node_installation() and permissions and not all(
            _node_permission_allowed(permission) for permission in permissions
        ):
            raise HTTPException(
                status_code=403,
                detail="Processing Nodes cannot access central site data or configuration. Use the Site Server.",
            )
        perms = user_permissions(user)
        if "*" in perms or any(permission in perms for permission in permissions):
            return user
        raise HTTPException(status_code=403, detail=f"Missing permission: {permissions[0]}")
    return dep


def require_media(permission: str):
    def dep(user: User = Depends(media_user)) -> User:
        if not _node_permission_allowed(permission):
            raise HTTPException(
                status_code=403,
                detail="Processing Nodes can stream only their assigned camera resources.",
            )
        perms = user_permissions(user)
        if "*" not in perms and permission not in perms:
            raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")
        return user
    return dep
