"""Compatibility facade for the split ``captures`` module."""

from __future__ import annotations

from pathlib import Path as _Path

_PACKAGE_DIR = _Path(__file__).resolve().parent
_ORIGINAL_FILE = _PACKAGE_DIR.parent / "captures.py"
__file__ = str(_ORIGINAL_FILE)
_COMPONENTS = [
    '00_context.py',
    '10_validation.py',
    '20_media.py',
    '30_repository.py',
    '40_queries.py'
]

for _component in _COMPONENTS:
    _path = _PACKAGE_DIR / _component
    _code = compile(_path.read_text(encoding="utf-8"), str(_path), "exec")
    exec(_code, globals(), globals())

del _code, _component, _path, _COMPONENTS, _ORIGINAL_FILE, _PACKAGE_DIR, _Path
