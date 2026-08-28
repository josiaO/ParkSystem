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


def require(permission: str):
    def dep(user: User = Depends(current_user)) -> User:
        if "*" not in user_permissions(user) and permission not in user_permissions(user):
            raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")
        return user
    return dep


def require_any(*permissions: str):
    def dep(user: User = Depends(current_user)) -> User:
        perms = user_permissions(user)
        if "*" in perms or any(permission in perms for permission in permissions):
            return user
        raise HTTPException(status_code=403, detail=f"Missing permission: {permissions[0]}")
    return dep


def require_media(permission: str):
    def dep(user: User = Depends(media_user)) -> User:
        if "*" not in user_permissions(user) and permission not in user_permissions(user):
            raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")
        return user
    return dep
