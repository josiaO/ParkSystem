"""Load the parts of a split module from source or from compiled code.

Several large modules (the Site Service API, the desktop, the media gateway,
...) are kept as numbered part files that run in one namespace. During
development the parts are read as source. An installed release ships no
source: the installer build compiles every part to ``<part>.partc`` (the same
16-byte header as a ``.pyc``, then the marshalled code object), the way
classic parking systems ship compiled programs rather than their source.

``part_code`` prefers the source when it is there, so tests and a developer
checkout behave exactly as before.
"""

from __future__ import annotations

import importlib.util
import marshal
from pathlib import Path

COMPILED_SUFFIX = ".partc"
_HEADER = 16


def compiled_path(path: Path) -> Path:
    return path.with_name(path.name + COMPILED_SUFFIX)


def part_code(path: Path):
    """Code object for one part: its source if present, else its compiled form."""
    path = Path(path)
    if path.is_file():
        return compile(path.read_text(encoding="utf-8"), str(path), "exec")
    compiled = compiled_path(path)
    if compiled.is_file():
        data = compiled.read_bytes()
        if data[:4] != importlib.util.MAGIC_NUMBER:
            raise ImportError(
                f"{compiled.name} was compiled for another Python version; reinstall this Zirp release"
            )
        return marshal.loads(data[_HEADER:])
    raise FileNotFoundError(f"Missing module part {path} (neither source nor {compiled.name})")


def part_names(folder: Path, pattern: str = "*.py") -> list[str]:
    """Sorted part file names in ``folder``, whether shipped as source or compiled."""
    folder = Path(folder)
    names = {p.name for p in folder.glob(pattern) if not p.name.endswith(COMPILED_SUFFIX)}
    names |= {p.name[: -len(COMPILED_SUFFIX)] for p in folder.glob(pattern + COMPILED_SUFFIX)}
    return sorted(names)


def compile_part(path: Path, *, display_name: str | None = None) -> Path:
    """Write ``<part>.partc`` next to ``path``. Used by the installer build."""
    path = Path(path)
    code = compile(path.read_text(encoding="utf-8"), display_name or str(path), "exec")
    header = importlib.util.MAGIC_NUMBER + b"\0" * (_HEADER - len(importlib.util.MAGIC_NUMBER))
    target = compiled_path(path)
    target.write_bytes(header + marshal.dumps(code))
    return target
