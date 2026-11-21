"""Compatibility facade for the split ``simulation`` module."""

from __future__ import annotations

from pathlib import Path as _Path

_PACKAGE_DIR = _Path(__file__).resolve().parent
_ORIGINAL_FILE = _PACKAGE_DIR.parent / "simulation.py"
__file__ = str(_ORIGINAL_FILE)
_COMPONENTS = [
    '00_context.py',
    '10_settings.py',
    '20_sessions.py',
    '30_entry.py',
    '40_exit.py'
]

for _component in _COMPONENTS:
    _path = _PACKAGE_DIR / _component
    from app.core.parts import part_code as _part_code
    _code = _part_code(_path)
    exec(_code, globals(), globals())

del _code, _component, _path, _COMPONENTS, _ORIGINAL_FILE, _PACKAGE_DIR, _Path
