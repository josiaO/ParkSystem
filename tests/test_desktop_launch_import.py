"""Regression coverage for the split desktop entrypoint."""


def test_desktop_launch_resolves_split_main_entrypoint():
    from app.desktop.launch import main as launch_main
    from app.desktop.main import MainWindow, main as desktop_main

    assert callable(launch_main)
    assert callable(desktop_main)
    assert MainWindow.__name__ == "MainWindow"


def test_instance_lock_survives_a_pid_file_owned_by_another_account(tmp_path, monkeypatch):
    """The mutex is the lock; an unwritable PID file must not mean 'already open'."""
    import os
    import pathlib

    import pytest

    if os.name != "nt":
        pytest.skip("Windows mutex path")
    from app.services import runtime

    monkeypatch.delenv("SMARTPARK_SKIP_INSTANCE_LOCK", raising=False)
    monkeypatch.setattr(runtime, "data_dir", lambda: tmp_path)
    real = pathlib.Path.write_text

    def denied(self, *args, **kwargs):
        if self.name.endswith(".lock"):
            raise PermissionError("Access is denied")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "write_text", denied)

    def denied_open(*args, **kwargs):
        raise PermissionError("Access is denied")

    monkeypatch.setattr(runtime, "open", denied_open, raising=False)
    name = f"pytest-lock-{os.getpid()}"
    try:
        assert runtime.acquire_instance_lock(name) is True
    finally:
        runtime.release_instance_lock()
