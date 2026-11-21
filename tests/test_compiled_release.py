"""The installer ships compiled code, not readable source, and it still runs.

Classic parking systems install compiled programs. build.ps1 runs
packaging/installer/compile_app.py on the staged ``app`` folder: split-module
parts become ``.partc`` files, every other module a ``.pyc`` next to where its
source was, and only the Alembic migrations stay as source.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.core import parts

ROOT = Path(__file__).resolve().parents[1]


def test_part_code_prefers_source(tmp_path):
    part = tmp_path / "01_part.py"
    part.write_text("VALUE = 41 + 1\n", encoding="utf-8")
    ns: dict = {}
    exec(parts.part_code(part), ns, ns)
    assert ns["VALUE"] == 42


def test_part_code_loads_the_compiled_form_without_source(tmp_path):
    part = tmp_path / "20_frames"
    part.write_text("def answer():\n    return 'compiled'\n", encoding="utf-8")
    parts.compile_part(part, display_name="app/x/20_frames")
    part.unlink()
    ns: dict = {}
    exec(parts.part_code(part), ns, ns)
    assert ns["answer"]() == "compiled"
    assert parts.part_names(tmp_path, "*") == ["20_frames"]


def test_compiled_part_for_another_python_is_refused_clearly(tmp_path):
    part = tmp_path / "01_part.py"
    part.write_text("X = 1\n", encoding="utf-8")
    compiled = parts.compile_part(part)
    part.unlink()
    data = bytearray(compiled.read_bytes())
    data[0:4] = b"\x00\x00\r\n"
    compiled.write_bytes(bytes(data))
    with pytest.raises(ImportError, match="another Python version"):
        parts.part_code(part)


def test_missing_part_names_both_forms(tmp_path):
    with pytest.raises(FileNotFoundError, match="neither source"):
        parts.part_code(tmp_path / "99_missing.py")


def test_compiled_copy_of_the_app_imports_and_has_no_source(tmp_path):
    """Compile a copy exactly as the build does, then import it in a fresh process."""
    sys.path.insert(0, str(ROOT / "packaging" / "installer"))
    try:
        import compile_app
    finally:
        sys.path.remove(str(ROOT / "packaging" / "installer"))

    release = tmp_path / "release"
    shutil.copytree(ROOT / "app", release / "app",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "mock_services"))
    part_count, module_count = compile_app.compile_app(release / "app")
    assert part_count >= 40 and module_count >= 150

    left = [p for p in (release / "app").rglob("*.py") if "alembic" not in p.parts]
    assert left == [], left[:5]
    assert list((release / "app" / "api" / "runtime_parts").glob("*.py.partc"))

    probe = (
        "import sys, importlib\n"
        f"sys.path.insert(0, {str(release)!r})\n"
        "for m in ['app.api_main', 'app.site_service', 'app.media_service', 'app.recognition_worker',\n"
        "          'app.services.media_gateway', 'app.services.captures', 'app.services.alpr',\n"
        "          'app.services.simulation', 'app.application.entry_lane', 'app.application.exit_lane',\n"
        "          'app.services.mobile_payments', 'app.services.receipt_jobs', 'app.release_tool']:\n"
        "    mod = importlib.import_module(m)\n"
        "    assert str(getattr(mod, '__file__', '') or '').find('release') >= 0 or m in ('app.recognition_worker',\n"
        "           'app.services.media_gateway', 'app.services.captures', 'app.services.alpr', 'app.services.simulation'), m\n"
        "import app.api_main as api\n"
        "assert hasattr(api, 'entry_fallback') and hasattr(api, '_persist_capture_event')\n"
        "from app.migrations.runner import head_revision\n"
        "assert head_revision()\n"
        "print('ok', api.__file__)\n"
    )
    env = {**os.environ, "SMARTPARK_LATENCY_TRACE": "0", "SMARTPARK_HOME": str(tmp_path / "home"),
           "SMARTPARK_DATA_DIR": str(tmp_path / "data"), "QT_QPA_PLATFORM": "offscreen"}
    env.setdefault("SMARTPARK_ENV_FILE", str(tmp_path / "empty.env"))
    (tmp_path / "empty.env").write_text("", encoding="utf-8")
    done = subprocess.run([sys.executable, "-c", probe], cwd=str(tmp_path), env=env,
                          capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stderr[-3000:]
    assert "ok" in done.stdout and str(release) in done.stdout
    assert importlib.util.MAGIC_NUMBER  # same interpreter compiled and loaded it
