"""Compile the staged ``app`` folder so the installer ships no readable source.

Run by build.ps1 with the *staged* embedded Python, so the bytecode matches
the runtime that will load it. Classic parking systems install compiled
programs, not their source; this is the same idea for Zirp.

* Split-module parts (numbered files executed into one module, see
  app/core/parts.py) become ``<part>.partc``: a ``.pyc``-style header and the
  marshalled code object. The source file is removed.
* Every other module becomes a ``.pyc`` next to where its ``.py`` was (the
  layout Python imports without the source) and the ``.py`` is removed.
* Kept as source on purpose: ``app/migrations/alembic`` (Alembic loads env.py
  and the revision files by path).

Usage: python compile_app.py <stage>\\app
"""

from __future__ import annotations

import importlib.util
import marshal
import py_compile
import re
import shutil
import sys
from pathlib import Path

SPLIT_PACKAGES = (
    "api/runtime_parts",
    "desktop/main",
    "desktop/setup_parts",
    "recognition_worker",
    "services/alpr",
    "services/captures",
    "services/media_gateway",
    "services/simulation",
)
KEEP_SOURCE = ("migrations/alembic",)
_PART_NAME = re.compile(r"^\d\d_")


def _is_part(package: str, path: Path) -> bool:
    if not path.is_file() or path.name == "__init__.py" or path.name.endswith(".partc"):
        return False
    if package == "api/runtime_parts":
        return path.suffix == ".py"
    return bool(_PART_NAME.match(path.name))


def compile_app(app_dir: Path) -> tuple[int, int]:
    app_dir = Path(app_dir).resolve()
    keep = [app_dir / rel for rel in KEEP_SOURCE]
    header = importlib.util.MAGIC_NUMBER + b"\0" * (16 - len(importlib.util.MAGIC_NUMBER))
    parts = modules = 0
    for package in SPLIT_PACKAGES:
        folder = app_dir / package
        for path in sorted(folder.iterdir()):
            if not _is_part(package, path):
                continue
            display = f"app/{package}/{path.name}"
            code = compile(path.read_text(encoding="utf-8"), display, "exec")
            path.with_name(path.name + ".partc").write_bytes(header + marshal.dumps(code))
            path.unlink()
            parts += 1
    for path in sorted(app_dir.rglob("*.py")):
        if any(k == path or k in path.parents for k in keep):
            continue
        display = "app/" + path.relative_to(app_dir).as_posix()
        py_compile.compile(str(path), cfile=str(path.with_suffix(".pyc")), dfile=display, doraise=True)
        path.unlink()
        modules += 1
    for cache in sorted(app_dir.rglob("__pycache__"), reverse=True):
        if not any(k in cache.parents for k in keep):
            shutil.rmtree(cache, ignore_errors=True)
    return parts, modules


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: compile_app.py <stage>\\app")
    parts, modules = compile_app(Path(sys.argv[1]))
    print(f"compiled {parts} module parts and {modules} modules; no app source left outside migrations")
