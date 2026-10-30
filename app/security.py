from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .db import get_db, short_session
from .models import AuthSession, Node, Role, User, UserRole, UserStatus
from .services.node_authorization import NodePrincipal, load_node_from_token


def processing_node_permissions(permissions: set[str]) -> set[str]:
    """Return human permissions without applying an installation-role wall.

    Human authorization is independent of the computer on which the person
    signs in. Node credentials use ``NodePrincipal`` and resource assignments
    instead; an Edge Node must not be represented as a restricted human user.
    """
    return set(permissions)


def _node_permission_allowed(permission: str, *, processing_node_allowed: bool = False) -> bool:
    # Kept as a compatibility hook for callers that imported it. Installation
    # role is not an authorization subject; resource-aware node checks happen
    # at the operation boundary in app.services.node_authorization.
    return True


def _processing_node_installation() -> bool:
    try:
        from app.services.node_scope import is_processing_node

        return bool(is_processing_node())
    except Exception:
        return False

_ph = PasswordHasher()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)
node_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/node/auth", auto_error=False)


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
    """Compatibility no-op: human sessions are not installation-bound.

    Machine authentication is represented by ``NodePrincipal`` and node
    sessions, never by a shared-database User row.
    """
    return None


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


def authenticate_processing_node(db: Session, username: str, password: str) -> User:
    """Authenticate the desktop on an Edge Node without widening its scope.

    The runtime identity is stored in ``nodes`` and is intentionally separate
    from human users.  The desktop, however, still uses the normal RBAC
    session endpoints for its operator UI.  Older node installations only
    created the machine row, so lazily repairing the small, scoped UI account
    here keeps upgrades/reinstalls idempotent while the node credential remains
    the source of truth.
    """
    from .config import settings
    from .deployment import load_deployment_config
    from .services.node_authorization import verify_node_credential

    expected = load_deployment_config().node_username.strip().casefold()
    supplied = str(username or "").strip().casefold()
    if not expected or supplied != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid node username or password")
    canonical_username = load_deployment_config().node_username.strip()

    user = db.scalar(
        select(User)
        .options(selectinload(User.roles).selectinload(UserRole.role))
        .where(func.lower(User.username) == expected)
    )
    is_node_user = bool(user and is_processing_node_account(user))
    if user is not None and not is_node_user:
        # A node username must never silently take over a human account.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid node username or password")

    if user is not None and user.status != UserStatus.ACTIVE.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account unavailable")

    # Prefer the existing scoped UI account.  If setup was interrupted or an
    # older installer created only the node registry row, verify the source
    # credential and repair that account atomically.
    if user is not None and verify_password(user.password_hash, password):
        return user

    node = db.scalar(select(Node).where(Node.node_id == str(settings.node_id).strip()))
    if node is None or node.status != "ACTIVE" or node.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid node username or password")
    if not verify_node_credential(node.credential_hash, password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid node username or password")

    role = db.scalar(select(Role).where(Role.name == "Processing Node"))
    if role is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Processing Node role is not initialized")
    if user is None:
        user = User(
            username=canonical_username,
            full_name="Processing Node",
            password_hash=hash_password(password),
            status=UserStatus.ACTIVE.value,
        )
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_id=role.id))
    else:
        user.password_hash = hash_password(password)
        if not any(link.role_id == role.id for link in user.roles):
            db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()
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


def current_node(
    token: str | None = Depends(node_oauth2_scheme),
    access_token: str | None = Query(default=None, include_in_schema=False),
    db: Session = Depends(get_db),
) -> NodePrincipal:
    """Authenticate a runtime as a node, never as a human User."""
    return load_node_from_token(db, token or access_token)


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
