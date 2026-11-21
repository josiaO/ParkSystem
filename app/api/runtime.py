"""Compose the Site Service API from bounded implementation parts.

The public import remains ``app.api_main``.  This module is the compatibility
runtime used by that entry point; its implementation is intentionally split
by subsystem in ``runtime_parts``.  Parts execute in this module namespace so
the long-standing ``app.api_main`` monkeypatch/import surface remains stable
while the source ownership becomes navigable.
"""

from pathlib import Path


_PARTS_DIR = Path(__file__).resolve().parent / "runtime_parts"


def _load_runtime_parts() -> None:
    namespace = globals()
    from app.core.parts import part_code, part_names

    # Source in a checkout; compiled ``.partc`` files in an installed release.
    for name in part_names(_PARTS_DIR, "*.py"):
        exec(part_code(_PARTS_DIR / name), namespace, namespace)


_load_runtime_parts()
del _load_runtime_parts, _PARTS_DIR
