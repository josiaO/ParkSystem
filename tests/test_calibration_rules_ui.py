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
        assert rules == {"zone": False, "zone_before": True, "zone_after": True, "start_line": True,
                         "end_line": False, "plate_size": True,
                         "detector": True, "picture_quality": False, "recognition": True}
        # The zone before / after switches come from the saved calibration too.
        window._show_config({"calibration": {"enabled": True, "version": 5, "enforce": {"zone_before": False}}})
        assert window.rule_checks["zone_before"].isChecked() is False
        assert window.rule_checks["zone_after"].isChecked() is True
    finally:
        window._dirty = False          # closing would otherwise ask to discard changes
        window.close()


def test_desktop_rule_list_matches_the_site_server():
    from app.services import capture_calibration as cc

    assert [rule for rule, _ in calibration.RULE_LABELS] == list(cc.RULES)
    assert calibration.DEFAULT_RULES == cc.DEFAULT_ENFORCE


def _quiet_window(monkeypatch):
    monkeypatch.setattr(calibration.api, "can", lambda permission: True, raising=False)
    monkeypatch.setattr(calibration.CalibrationWindow, "load", lambda self: None)
    monkeypatch.setattr(calibration.CalibrationWindow, "_start_stream", lambda self: None)


def test_calibration_settings_open_in_their_own_minimizable_window(monkeypatch):
    from PySide6.QtCore import Qt

    _quiet_window(monkeypatch)
    window = calibration.CalibrationWindow(None, cameras=[])
    try:
        flags = window.windowFlags()
        assert flags & Qt.WindowType.WindowMinimizeButtonHint
        assert flags & Qt.WindowType.WindowMaximizeButtonHint
        assert not window.isModal()
        # Save stays in view: it is not inside the scrolling settings column.
        from PySide6.QtWidgets import QScrollArea
        scroll = window.findChild(QScrollArea)
        assert not scroll.widget().isAncestorOf(window.save_btn)
        # Short rule names, the full explanation on pointing.
        assert window.rule_checks["zone_before"].text() == "Not in the zone yet"
        assert "start line" in window.rule_checks["zone_before"].toolTip()
    finally:
        window._dirty = False
        window.close()


def test_one_calibration_window_is_shared_and_switches_camera(monkeypatch):
    _quiet_window(monkeypatch)
    cameras = [{"id": 1, "name": "1# Entry", "lane_direction": "ENTRY"},
               {"id": 2, "name": "1# Exit", "lane_direction": "EXIT"}]
    calibration._open_window = None
    first = calibration.open_calibration(1, cameras=cameras)
    try:
        assert first.camera_id() == 1
        again = calibration.open_calibration(2, cameras=cameras)     # e.g. from the other Live Gates tile
        assert again is first and first.camera_id() == 2
    finally:
        first._dirty = False
        first.close()
        calibration._open_window = None


def test_escape_asks_before_dropping_unsaved_changes(monkeypatch):
    _quiet_window(monkeypatch)
    asked = []
    monkeypatch.setattr(calibration.QMessageBox, "question",
                        lambda *a, **k: asked.append(1) or calibration.QMessageBox.StandardButton.No)
    window = calibration.CalibrationWindow(None, cameras=[])
    window.show()
    window._dirty = True
    window.reject()                                   # Escape
    assert asked and window.isVisible()
    window._dirty = False
    window.close()
    assert not window.isVisible()


def test_calibration_window_fits_a_scaled_full_hd_screen(monkeypatch):
    """1920 x 1080 at 125% is 1536 logical pixels wide; the window was wider."""
    _quiet_window(monkeypatch)
    window = calibration.CalibrationWindow(None, cameras=[])
    try:
        # Pixel widths depend on the fonts installed, so check the layout:
        # zone tools and line tools are on separate rows.
        window.resize(1400, 800); window.show(); _APP.processEvents()
        assert window.rect_btn.y() != window.line_btn.y()
        assert window.line_btn.y() == window.end_btn.y()
        assert window.line_side.sizeAdjustPolicy() == calibration.QComboBox.SizeAdjustPolicy.AdjustToContents
    finally:
        window._dirty = False
        window.close()
