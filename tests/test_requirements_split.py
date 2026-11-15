"""Phase 6.5: runtime/dev requirement files stay consistent with the lockfile."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _lines(name):
    return [line.strip() for line in (ROOT / name).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")]


def test_runtime_pins_are_exactly_the_lockfile_pins():
    lock = set(_lines("requirements.txt"))
    for line in _lines("requirements-runtime.txt"):
        assert line in lock, f"{line} is not pinned identically in requirements.txt"


def test_dev_requirements_include_runtime_and_test_tools():
    dev = _lines("requirements-dev.txt")
    assert dev[0] == "-r requirements-runtime.txt"
    assert {"pytest", "pytest-asyncio"} <= {line.split(">=")[0] for line in dev}
