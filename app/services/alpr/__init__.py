"""Compatibility facade for the split ``alpr`` module."""

from __future__ import annotations

from pathlib import Path as _Path

_PACKAGE_DIR = _Path(__file__).resolve().parent
_ORIGINAL_FILE = _PACKAGE_DIR.parent / "alpr.py"
__file__ = str(_ORIGINAL_FILE)
_COMPONENTS = [
    '00_context.py',
    '10_types.py',
    '20_runtime.py',
    '30_preprocessing.py',
    '40_detection.py',
    '50_service.py'
]

for _component in _COMPONENTS:
    _path = _PACKAGE_DIR / _component
    from app.core.parts import part_code as _part_code
    _code = _part_code(_path)
    exec(_code, globals(), globals())

del _code, _component, _path, _COMPONENTS, _ORIGINAL_FILE, _PACKAGE_DIR, _Path
