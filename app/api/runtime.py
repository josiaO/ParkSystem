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
    for part in sorted(_PARTS_DIR.glob("*.py")):
        source = part.read_text(encoding="utf-8")
        exec(compile(source, str(part), "exec"), namespace, namespace)


_load_runtime_parts()
del _load_runtime_parts, _PARTS_DIR
