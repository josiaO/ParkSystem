"""Compatibility facade for the split ``media_gateway`` module."""

from __future__ import annotations

from pathlib import Path as _Path

_PACKAGE_DIR = _Path(__file__).resolve().parent
_ORIGINAL_FILE = _PACKAGE_DIR.parent / "media_gateway.py"
__file__ = str(_ORIGINAL_FILE)
_COMPONENTS = [
    '00_context.py',
    '10_state.py',
    '20_frames',
    '30_producers',
    '40_facade.py'
]

for _component in _COMPONENTS:
    _path = _PACKAGE_DIR / _component
    _code = compile(_path.read_text(encoding="utf-8"), str(_path), "exec")
    exec(_code, globals(), globals())

del _code, _component, _path, _COMPONENTS, _ORIGINAL_FILE, _PACKAGE_DIR, _Path
