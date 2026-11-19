"""Calibration window: each rule has an on/off switch that is loaded and saved."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.desktop import calibration  # noqa: E402

_APP = QApplication.instance() or QApplication([])


def test_rule_switches_follow_the_saved_calibration_and_are_sent_on_save(monkeypatch):
    monkeypatch.setattr(calibration.api, "can", lambda permission: True, raising=False)
    monkeypatch.setattr(calibration.CalibrationWindow, "load", lambda self: None)
    window = calibration.CalibrationWindow(None, cameras=[])
    try:
        # Saved before the switches existed: defaults (lines off, the rest on).
        window._show_config({"calibration": {"enabled": True, "version": 3}})
        assert window.rule_checks["start_line"].isChecked() is False
        assert window.rule_checks["end_line"].isChecked() is False
        assert window.rule_checks["zone"].isChecked() is True
        window._show_config({"calibration": {"enabled": True, "version": 4,
                                             "enforce": {"zone": False, "start_line": True}}})
        assert window.rule_checks["zone"].isChecked() is False
        assert window.rule_checks["start_line"].isChecked() is True
        window.rule_checks["picture_quality"].setChecked(False)
        rules = window._payload()["enforce"]
        assert rules == {"zone": False, "start_line": True, "end_line": False, "plate_size": True,
                         "detector": True, "picture_quality": False, "recognition": True}
    finally:
        window._dirty = False          # closing would otherwise ask to discard changes
        window.close()


def test_desktop_rule_list_matches_the_site_server():
    from app.services import capture_calibration as cc

    assert [rule for rule, _ in calibration.RULE_LABELS] == list(cc.RULES)
    assert calibration.DEFAULT_RULES == cc.DEFAULT_ENFORCE
