from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock
from tools.hvx_sdk_host import check_runtime


def test_runtime_check_loads_matched_dlls_without_sdk_calls(tmp_path, monkeypatch):
    for name in check_runtime.DLLS:
        (tmp_path / name).write_bytes(b'MZ')
    loader = Mock(return_value=object())
    monkeypatch.setattr(check_runtime, 'os', SimpleNamespace(name='nt', add_dll_directory=lambda _: nullcontext()))
    monkeypatch.setattr(check_runtime, 'struct', SimpleNamespace(calcsize=lambda _: 4))
    monkeypatch.setattr(check_runtime, 'ctypes', SimpleNamespace(WinDLL=loader))
    assert check_runtime.check(tmp_path) == []
    assert loader.call_count == len(check_runtime.DLLS)


def test_loader_failure_identifies_legacy_runtime(tmp_path, monkeypatch):
    for name in check_runtime.DLLS:
        (tmp_path / name).write_bytes(b'MZ')
    monkeypatch.setattr(check_runtime, 'os', SimpleNamespace(name='nt', add_dll_directory=lambda _: nullcontext()))
    monkeypatch.setattr(check_runtime, 'struct', SimpleNamespace(calcsize=lambda _: 4))
    monkeypatch.setattr(check_runtime, 'ctypes', SimpleNamespace(WinDLL=Mock(side_effect=OSError('missing dependency'))))
    errors = check_runtime.check(tmp_path)
    assert 'MSVCR80.dll' in errors[-1]
    assert 'x86' in errors[-1]
