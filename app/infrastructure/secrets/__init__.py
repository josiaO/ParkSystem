"""SecretStore: the database keeps ``credentials_ref``, not raw passwords.

Backends (``SMARTPARK_SECRETS_BACKEND``):

* ``dpapi`` — Windows Data Protection API (``CryptProtectData`` /
  ``CryptUnprotectData`` via ctypes, machine scope so the Site Service and the
  32-bit HVX host running under the same machine can both read). Blobs live in
  ``data_dir/secrets/<ref>.bin``. **Default on Windows.**
* ``file`` — plain file per ref under ``data_dir/secrets`` with 0600
  permissions. For Linux evaluation/dev only; not an OS keyring.
* ``memory`` — process-local dict (tests).
* ``db`` — legacy: the raw value stays in the ``password_secret`` column.
  **Default on non-Windows** so existing evaluation databases keep working
  until an operator opts in.

References look like ``camera:<uuid>``. ``resolve()`` returns the raw secret
for adapters at connect time; nothing else should call it.
"""

from __future__ import annotations

import os
from pathlib import Path
import platform
import re
import threading
import uuid
from typing import Protocol

from app.config import settings

_REF_RE = re.compile(r"^[a-z][a-z0-9_-]*:[A-Za-z0-9._-]{4,80}$")
_lock = threading.Lock()


class SecretStoreError(RuntimeError):
    pass


class SecretStore(Protocol):
    backend: str

    def put(self, ref: str, secret: str) -> str: ...

    def get(self, ref: str) -> str: ...

    def delete(self, ref: str) -> None: ...

    def exists(self, ref: str) -> bool: ...


def new_ref(kind: str = "camera") -> str:
    return f"{kind}:{uuid.uuid4().hex}"


def is_ref(value: str | None) -> bool:
    return bool(value) and bool(_REF_RE.match(str(value)))


def _safe_name(ref: str) -> str:
    if not is_ref(ref):
        raise SecretStoreError(f"invalid credentials_ref: {ref!r}")
    return ref.replace(":", "__")


class MemorySecretStore:
    backend = "memory"

    def __init__(self):
        self._data: dict[str, str] = {}

    def put(self, ref: str, secret: str) -> str:
        _safe_name(ref)
        with _lock:
            self._data[ref] = secret
        return ref

    def get(self, ref: str) -> str:
        _safe_name(ref)
        with _lock:
            if ref not in self._data:
                raise SecretStoreError(f"secret not found for {ref}")
            return self._data[ref]

    def delete(self, ref: str) -> None:
        with _lock:
            self._data.pop(ref, None)

    def exists(self, ref: str) -> bool:
        with _lock:
            return ref in self._data


class FileSecretStore:
    """0600 files under data_dir/secrets. Evaluation-grade; not an OS keyring."""

    backend = "file"

    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else settings.data_dir / "secrets"

    def _path(self, ref: str) -> Path:
        return self.root / f"{_safe_name(ref)}.secret"

    def _write(self, path: Path, data: bytes) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass
        tmp = path.with_suffix(path.suffix + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def _encode(self, secret: str) -> bytes:
        return secret.encode("utf-8")

    def _decode(self, data: bytes) -> str:
        return data.decode("utf-8")

    def put(self, ref: str, secret: str) -> str:
        self._write(self._path(ref), self._encode(secret))
        return ref

    def get(self, ref: str) -> str:
        path = self._path(ref)
        if not path.exists():
            raise SecretStoreError(f"secret not found for {ref}")
        return self._decode(path.read_bytes())

    def delete(self, ref: str) -> None:
        self._path(ref).unlink(missing_ok=True)

    def exists(self, ref: str) -> bool:
        return self._path(ref).exists()


class DPAPISecretStore(FileSecretStore):
    """Windows DPAPI-protected blobs (machine scope). Windows only."""

    backend = "dpapi"

    def _path(self, ref: str) -> Path:
        return self.root / f"{_safe_name(ref)}.bin"

    @staticmethod
    def _crypt(data: bytes, *, protect: bool) -> bytes:
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        buf = ctypes.create_string_buffer(data, len(data))
        blob_in = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        blob_out = DATA_BLOB()
        CRYPTPROTECT_UI_FORBIDDEN = 0x01
        CRYPTPROTECT_LOCAL_MACHINE = 0x04
        flags = CRYPTPROTECT_UI_FORBIDDEN | CRYPTPROTECT_LOCAL_MACHINE
        fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
        entropy = ctypes.create_string_buffer(b"smartpark-edge-secrets")
        blob_entropy = DATA_BLOB(len(b"smartpark-edge-secrets"), ctypes.cast(entropy, ctypes.POINTER(ctypes.c_char)))
        ok = fn(ctypes.byref(blob_in), None, ctypes.byref(blob_entropy), None, None, flags, ctypes.byref(blob_out))
        if not ok:
            raise SecretStoreError(f"DPAPI {'protect' if protect else 'unprotect'} failed (error {kernel32.GetLastError()})")
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            kernel32.LocalFree(blob_out.pbData)

    def _encode(self, secret: str) -> bytes:
        return self._crypt(secret.encode("utf-8"), protect=True)

    def _decode(self, data: bytes) -> str:
        return self._crypt(data, protect=False).decode("utf-8")


class DatabaseSecretStore:
    """Legacy marker: values stay in the row. put/get are identity on the value."""

    backend = "db"

    def put(self, ref: str, secret: str) -> str:  # pragma: no cover - never called for db backend
        raise SecretStoreError("db backend keeps secrets in the row; nothing to store")

    def get(self, ref: str) -> str:  # pragma: no cover
        raise SecretStoreError("db backend keeps secrets in the row; nothing to resolve")

    def delete(self, ref: str) -> None:
        return None

    def exists(self, ref: str) -> bool:
        return False


_store: SecretStore | None = None
_store_backend: str = ""
_store_injected = False


def configured_backend() -> str:
    raw = str(getattr(settings, "secrets_backend", "auto") or "auto").strip().lower()
    if raw == "auto":
        return "dpapi" if platform.system() == "Windows" else "db"
    if raw not in {"dpapi", "file", "memory", "db"}:
        return "db"
    if raw == "dpapi" and platform.system() != "Windows":
        return "file"
    return raw


def secret_store() -> SecretStore:
    global _store, _store_backend
    with _lock:
        if _store_injected and _store is not None:
            return _store
        backend = configured_backend()
        if _store is None or _store_backend != backend:
            if backend == "dpapi":
                _store = DPAPISecretStore()
            elif backend == "file":
                _store = FileSecretStore()
            elif backend == "memory":
                _store = MemorySecretStore()
            else:
                _store = DatabaseSecretStore()
            _store_backend = backend
        return _store


def set_secret_store(store: SecretStore | None) -> None:
    """Tests: inject a store; None restores the configured backend."""
    global _store, _store_backend, _store_injected
    with _lock:
        _store = store
        _store_backend = getattr(store, "backend", "") if store else ""
        _store_injected = store is not None


def uses_external_store() -> bool:
    return secret_store().backend != "db"


def store_secret(secret: str, *, kind: str = "camera", ref: str | None = None) -> str:
    """Persist *secret* and return the ref to keep in the database."""
    store = secret_store()
    if store.backend == "db":
        raise SecretStoreError("db backend does not store secrets externally")
    ref = ref if is_ref(ref) else new_ref(kind)
    store.put(ref, secret)
    from app.services.redaction import register_secret

    register_secret(secret)
    return ref


def resolve_secret(ref: str | None, *, fallback: str = "") -> str:
    """Raw secret for a ref, or *fallback* (legacy raw value) when there is none."""
    if not is_ref(ref):
        return fallback
    store = secret_store()
    if store.backend == "db":
        if fallback:
            return fallback
        # Rollback path: SMARTPARK_SECRETS_BACKEND=db after credentials were
        # moved out. Read the platform's external store so cameras keep working.
        store = DPAPISecretStore() if platform.system() == "Windows" else FileSecretStore()
    try:
        value = store.get(str(ref))
    except (SecretStoreError, OSError):
        return fallback
    from app.services.redaction import register_secret

    register_secret(value)
    return value


def describe() -> dict:
    store = secret_store()
    root = getattr(store, "root", None)
    return {
        "backend": store.backend,
        "external": store.backend != "db",
        "location": str(root) if root else None,
        "platform": platform.system(),
    }
