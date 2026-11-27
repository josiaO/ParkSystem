"""Two-line plates are read, calibration refusals are counted as such, and
saving a setting does not crash the desktop app."""

from __future__ import annotations

from types import SimpleNamespace


def _box(w, h, x=900, y=700):
    return SimpleNamespace(x1=x, y1=y, x2=x + w, y2=y + h)


def test_two_line_plate_box_is_plate_shaped():
    from app.services.alpr import plate_box_ok

    # A square Tanzanian plate measured on a 1920 x 1080 snapshot: 88 x 80.
    assert plate_box_ok(_box(88, 80), 1920, 1080)
    # One-line plates still pass; a tall sliver still does not.
    assert plate_box_ok(_box(276, 112), 1920, 1080)
    assert not plate_box_ok(_box(40, 80), 1920, 1080)


def test_two_line_plate_is_not_refused_when_stored():
    from app.services.captures import _bbox_aspect
    from app.services.captures import MIN_PLATE_ASPECT

    assert _bbox_aspect({"x1": 900, "y1": 700, "x2": 988, "y2": 780}) >= MIN_PLATE_ASPECT


def test_calibration_refusal_is_not_counted_as_an_empty_picture():
    from app.services import event_outcomes

    refused = {"ok": True, "plates": [], "best": None, "calibration_refused": True,
               "detail": "no plate inside this camera's calibration"}
    assert event_outcomes.classify(refused) == "calibration_refused"
    assert "calibration_refused" in event_outcomes.KEEP_IMAGE_FOR
    empty = {"ok": True, "plates": [], "best": None, "detail": "no plate in the detection zone"}
    assert event_outcomes.classify(empty) == "no_plate_box"


def test_status_message_on_a_page_that_stores_the_main_window():
    """Settings and Camera calibration keep the main window in ``self.window``."""
    from app.desktop.common import show_status

    shown = []

    class Bar:
        def showMessage(self, text, ms):
            shown.append(text)

    class MainWindow:                       # like QMainWindow: not callable
        def statusBar(self):
            return Bar()

    page = SimpleNamespace(window=MainWindow())
    show_status(page, "Recognition settings saved.")
    assert shown == ["Recognition settings saved."]

    class Widget:                           # ordinary widget: window() is a method
        def window(self):
            return MainWindow()

    show_status(Widget(), "Saved.")
    assert shown[-1] == "Saved."
