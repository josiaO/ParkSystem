"""Compatibility facade for the split ``recognition_worker`` module."""

from __future__ import annotations

from pathlib import Path as _Path

_PACKAGE_DIR = _Path(__file__).resolve().parent
_ORIGINAL_FILE = _PACKAGE_DIR.parent / "recognition_worker.py"
__file__ = str(_ORIGINAL_FILE)
_COMPONENTS = [
    '00_context.py',
    '10_health.py',
    '20_publishing.py',
    '30_camera_worker.py',
    '90_supervisor.py',
    '99_entrypoint.py'
]

for _component in _COMPONENTS:
    _path = _PACKAGE_DIR / _component
    from app.core.parts import part_code as _part_code
    _code = _part_code(_path)
    exec(_code, globals(), globals())

del _code, _component, _path, _COMPONENTS, _ORIGINAL_FILE, _PACKAGE_DIR, _Path
