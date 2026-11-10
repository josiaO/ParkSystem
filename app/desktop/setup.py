"""Compatibility facade for the split deployment setup wizard."""

import sys as _sys

try:
    from app.desktop import setup_parts as _impl
except ModuleNotFoundError:  # pragma: no cover - direct installer execution
    import setup_parts as _impl

_sys.modules[__name__] = _impl
