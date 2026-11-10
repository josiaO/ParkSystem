"""Regression coverage for the split desktop entrypoint."""


def test_desktop_launch_resolves_split_main_entrypoint():
    from app.desktop.launch import main as launch_main
    from app.desktop.main import MainWindow, main as desktop_main

    assert callable(launch_main)
    assert callable(desktop_main)
    assert MainWindow.__name__ == "MainWindow"
