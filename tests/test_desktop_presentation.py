"""Headless UI checks. All site access is replaced by explicit fixtures."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QFormLayout, QLabel, QLineEdit,
    QScrollArea, QTableWidget, QToolBar, QVBoxLayout, QWidget,
)

from app.desktop import common, desk, live_cameras, live_pane, main
from app.desktop.presentation import configure_table, label_for, page_viewport, prepare_page
from app.desktop.shell import DesktopShell
from app.desktop.theme import APPEARANCES, PALETTES


class FixtureApi:
    modules = {"profile": "PARKING_PRO", "enabled": [], "onboarding_completed": True}

    def __init__(self):
        self.requests = []

    def can(self, permission):
        return permission in {"dashboard.view", "settings.view", "payments.create"}

    def nav_page(self, name):
        return name in {"dashboard", "cameras", "sessions", "reports", "settings"}

    def nav_label(self, name, fallback):
        return fallback

    def get(self, path, **kwargs):
        self.requests.append(path)
        if path == "/dashboard":
            return {
                "cameras": 4, "sdk_connected": 4, "vehicles_inside": 24,
                "entries_today": 87, "exits_today": 63, "revenue_today": 126000, "currency": "TZS",
                "unpaid_active": 3, "subscribers_inside": 8,
                "alerts": ["Preview data only — no hardware connected."],
                "lanes": [{"label": "North entrance", "camera": "Online", "live_video": "Available", "plate_recognition": "Ready", "barrier": "Closed"}],
            }
        if path == "/backup":
            return {"offline_due": False, "cloud_due": False, "config": {}}
        if path == "/sessions":
            return [
                {"id": index, "plate": plate, "parker_kind": "CASUAL", "status": "ACTIVE", "receipt_status": "Printed", "entry_time": "2026-10-19T09:15:00", "amount_due": 2000, "amount_paid": 0, "currency": "TZS", "gate_id": 1}
                for index, plate in enumerate(("T 123 ABC", "T 456 DEF", "T 789 GHI"), 1)
            ]
        raise AssertionError(f"Unexpected fixture request: {path}")

    def post(self, *args, **kwargs):
        raise AssertionError("UI preview must never issue a command")


class InlineWorker(QObject):
    done = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, function):
        super().__init__()
        self.function = function

    def start(self):
        try:
            self.done.emit(self.function())
        finally:
            self.finished.emit()


@pytest.fixture(scope="module")
def application():
    application = QApplication.instance() or QApplication([])
    yield application


def test_example_camera_import_requires_admin_and_confirmation(fixture_ui, monkeypatch):
    page = live_cameras.Cameras()
    assert page.seed_button.isHidden()
    page.seed_site()
    monkeypatch.setattr(live_cameras.api, "can", lambda permission: True)
    calls = []
    monkeypatch.setattr(live_cameras.api, "seed_site", lambda: calls.append("seed") or {"created": [], "skipped": []}, raising=False)
    monkeypatch.setattr(page, "refresh", lambda: calls.append("refresh"))
    monkeypatch.setattr(live_cameras.QMessageBox, "information", lambda *args: None)
    monkeypatch.setattr(live_cameras.QMessageBox, "question", lambda *args: live_cameras.QMessageBox.StandardButton.No)
    page.seed_site()
    assert calls == []
    monkeypatch.setattr(live_cameras.QMessageBox, "question", lambda *args: live_cameras.QMessageBox.StandardButton.Yes)
    page.seed_site()
    assert calls == ["seed", "refresh"]
    page.close()


def test_last_evidence_loads_without_reviving_a_departed_plate(fixture_ui, monkeypatch):
    pane = live_pane.CameraLivePane()
    pane.camera={"id": 901, "lane_direction": "ENTRY"}
    requests=[]
    painted=[]
    monkeypatch.setattr(live_pane.api, "get_bytes", lambda path, **kwargs: requests.append(path) or b"jpeg", raising=False)
    monkeypatch.setattr(pane, "_set_pixmap", lambda label, jpeg, *args: painted.append(label) or True)
    payload={"clear_last_car": True, "vehicle_present": False, "evidence": {
        "plate": "T123ABC", "snapshot_url": "/media/snapshots/last.jpg", "crop_url": "/media/crops/last.jpg"}}
    pane._show_alpr(payload)
    pane._show_alpr(payload)
    assert requests == ["/media/snapshots/last.jpg", "/media/crops/last.jpg"]
    assert painted == [pane.last_snap, pane.crop]
    assert pane.plate.text() == "—"
    assert pane._held_car is None
    pane.close()


def test_old_evidence_response_cannot_replace_newer_capture(fixture_ui, monkeypatch):
    class DeferredWorker(InlineWorker):
        def start(self):
            pass
    monkeypatch.setattr(live_pane, "Worker", DeferredWorker)
    pane=live_pane.CameraLivePane()
    pane.camera={"id": 901}
    painted=[]
    monkeypatch.setattr(pane, "_set_pixmap", lambda label, jpeg: painted.append(jpeg) or True)
    pane._load_evidence(pane.crop, "/media/crops/old.jpg")
    old=pane._workers[-1]
    pane._load_evidence(pane.crop, "/media/crops/new.jpg")
    new=pane._workers[-1]
    new.done.emit(b"new")
    old.done.emit(b"old")
    assert painted == [b"new"]
    pane._live_gen += 1
    new.done.emit(b"previous generation")
    assert painted == [b"new"]
    old.finished.emit()
    new.finished.emit()
    pane.close()


def test_mjpeg_burst_does_not_hold_the_last_frame_until_another_network_chunk(application, monkeypatch):
    from app.desktop import streams
    seen=[]
    first=b"\xff\xd8first\xff\xd9"
    second=b"\xff\xd8second\xff\xd9"
    class Response:
        status_code=200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def iter_bytes(self):
            yield first
            yield second
            assert seen == [first, second]
    class Client:
        def __init__(self, **kwargs):
            pass
        def stream(self, *args, **kwargs):
            return Response()
        def close(self):
            pass
    monkeypatch.setattr(streams.httpx, "Client", Client)
    monkeypatch.setattr(streams.time, "monotonic", lambda: 10.0)
    reader=streams.MjpegStream(901)
    reader.frame.connect(lambda: seen.append(reader.mailbox.take()))
    reader.run()
    assert seen == [first, second]


@pytest.fixture
def fixture_ui(application, monkeypatch, tmp_path):
    font = QFont(application.font())
    font.setPointSize(10)
    application.setFont(font)
    settings = QSettings(str(tmp_path / "display.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr("app.desktop.shell.QSettings", lambda *args: settings)
    fixture_api = FixtureApi()
    monkeypatch.setattr(main, "api", fixture_api)
    monkeypatch.setattr(desk, "api", fixture_api)
    monkeypatch.setattr(main, "Worker", InlineWorker)
    for module in (common, live_cameras, live_pane):
        monkeypatch.setattr(module, "api", fixture_api)
        monkeypatch.setattr(module, "Worker", InlineWorker)
    monkeypatch.setattr(main.Cameras, "showEvent", QWidget.showEvent)
    monkeypatch.setattr(main.Cameras, "hideEvent", QWidget.hideEvent)
    monkeypatch.setattr(main.Cameras, "_on_tab", lambda *args: None)
    yield fixture_api, settings
    for window in application.topLevelWidgets():
        window.close()
        window.deleteLater()
    application.processEvents()


def test_navigation_filter_preserves_lazy_page_indexes(application, fixture_ui):
    fixture_api, settings = fixture_ui
    window = main.MainWindow()
    assert not fixture_api.requests
    assert all(page is None for page in window.pages)
    reports_index = next(index for index in range(window.nav.count()) if window.nav.item(index).text() == "Reports")
    window.show()
    window.page_search.setFocus()
    QTest.keyClicks(window.page_search, "reports")
    assert not window.nav.item(reports_index).isHidden()
    assert window.nav.item(0).isHidden()
    QTest.keyClick(window.page_search, Qt.Key.Key_Return)
    assert window.stack.currentIndex() == reports_index
    assert isinstance(window.pages[reports_index], desk.ReportsPage)
    assert isinstance(window.stack.currentWidget(), QScrollArea)
    assert window.page_title.text() == "Reports"
    assert all(page is None for index, page in enumerate(window.pages) if index != reports_index)
    window.page_search.setText("no such page")
    assert "No matching pages" in window.navigation_result.text()
    QTest.keyClick(window.page_search, Qt.Key.Key_Escape)
    assert all(not window.nav.item(index).isHidden() for index in range(window.nav.count()))
    assert fixture_api.requests == ["/backup"]


def test_shared_toolbar_action_uses_existing_refresh_dispatch(application, fixture_ui, monkeypatch):
    window = main.MainWindow()
    calls = []
    page = QWidget()
    page.refresh = lambda: calls.append("refresh")
    window._makers[0] = lambda: page
    window.nav.setCurrentRow(0)
    monkeypatch.setattr(window, "_text_editing", lambda: False)
    toolbar = window.findChild(QToolBar, "workspaceCommands")
    refresh = next(action for action in toolbar.actions() if action.text() == "Refresh")
    menu = window.menuBar().actions()[0].menu()
    assert refresh in menu.actions()
    refresh.trigger()
    assert calls == ["refresh"]
    assert not fixture_ui[0].requests


def test_keyboard_navigation_and_local_theme_sync(application, fixture_ui):
    window = main.MainWindow()
    window.show()
    window.activateWindow()
    window.nav.setFocus()
    application.processEvents()
    QTest.keyClick(window, Qt.Key.Key_K, Qt.KeyboardModifier.ControlModifier)
    assert window.page_search.hasFocus()
    QTest.keyClicks(window.page_search, "settings")
    QTest.keyClick(window.page_search, Qt.Key.Key_Return)
    page = window._current_page()
    assert isinstance(page, main.SettingsPage)
    appearance = next(combo for combo in page.findChildren(main.QComboBox) if combo.count() == len(APPEARANCES) and combo.itemText(0) == "System")
    window.apply_theme("Dark")
    assert appearance.currentText() == "Dark"
    appearance.setCurrentText("High contrast")
    assert window.appearance == "High contrast"
    assert window.page_title.font().pointSize() == 16
    assert not fixture_ui[0].requests


def test_login_has_persistent_labels_and_default_action(application, fixture_ui, monkeypatch):
    monkeypatch.setattr(main.Login, "_prefill", lambda self: None)
    dialog = main.Login()
    assert dialog.user.accessibleName() == "Username"
    assert dialog.pwd.accessibleName() == "Password"
    assert dialog.pwd.echoMode() == QLineEdit.EchoMode.Password
    labels = dialog.findChildren(QLabel)
    assert any(label.buddy() is dialog.user for label in labels)
    assert any(label.buddy() is dialog.pwd for label in labels)
    assert any(button.isDefault() for button in dialog.findChildren(main.QPushButton))
    assert not fixture_ui[0].requests


def test_camera_evidence_positions_and_compact_manual_controls(application, fixture_ui):
    pane = main.CameraLivePane("Entry")
    layout = QWidget.layout(pane)
    pane.resize(640, 600)
    pane.show()
    application.processEvents()
    assert not hasattr(pane, "controls_toggle")
    assert pane.open_btn.isVisible()
    assert pane.close_btn.isVisible()
    assert pane.open_btn.height() < 40
    assert pane.open_btn.y() < pane.video.y()
    assert pane.last_snap.isVisible()
    assert pane.last_snap.mapTo(pane, pane.last_snap.rect().topLeft()).y() > pane.video.geometry().bottom()
    assert pane.crop.isVisible()
    assert pane.crop_panel.parentWidget() is pane.video
    assert pane.crop_panel.geometry().right() >= pane.video.width()-10
    assert pane.crop_panel.geometry().bottom() >= pane.video.height()-10
    assert pane.video.height() > pane.height()*0.65
    assert pane.zoom.accessibleName() == "Entry detection zone zoom"
    assert not pane._snap_timer.isActive()
    assert not pane._alpr_timer.isActive()
    assert not fixture_ui[0].requests


def test_text_zoom_keeps_user_resized_columns(application, fixture_ui):
    window = main.MainWindow()
    index = next(index for index in range(window.nav.count()) if window.nav.item(index).text() == "Sessions")
    window.nav.setCurrentRow(index)
    table = window.pages[index].table
    table.setColumnWidth(0, 240)
    window._set_text_size(14)
    window.apply_theme("Dark")
    assert table.columnWidth(0) == 240
    assert table.verticalHeader().defaultSectionSize() >= table.fontMetrics().height() + 14


def test_gate_selection_in_devices_applies_when_returning_to_live(application, fixture_ui, monkeypatch):
    page = main.Cameras()
    page.rows = [
        {"id": 41, "name": "West arrival", "gate_id": 8, "lane_direction": "ENTRY"},
        {"id": 52, "name": "West departure", "gate_id": 8, "lane_direction": "EXIT"},
        {"id": 63, "name": "East arrival", "gate_id": 19, "lane_direction": "ENTRY"},
        {"id": 74, "name": "East departure", "gate_id": 19, "lane_direction": "EXIT"},
    ]
    monkeypatch.setattr(page, "_live_visible", lambda: False)
    page.lane.addItem("West", 8)
    page.lane.addItem("East", 19)
    page.lane.setCurrentIndex(1)
    assert page._pair_from_lane_pending
    for pane in (page.pane_a, page.pane_b):
        monkeypatch.setattr(pane, "set_camera", lambda camera, target=pane: setattr(target, "camera", camera))
    monkeypatch.setattr(page, "_live_visible", lambda: True)
    page._start_pair()
    assert page.pane_a.camera_id() == 63
    assert page.pane_b.camera_id() == 74
    assert not page.tabs.widget(0).isAncestorOf(page.view_tools)
    assert page.tabs.widget(1).isAncestorOf(page.assign_node)
    assert not fixture_ui[0].requests


def test_video_canvas_resizes_original_frame_and_maps_detection_coordinates(application):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QPixmap
    from app.desktop.video import VideoCanvas
    canvas = VideoCanvas()
    frame = QPixmap(1920, 1080)
    frame.fill(QColor("#204060"))
    canvas.setPixmap(frame)
    canvas.resize(640, 480)
    rect = canvas.image_rect()
    assert rect.width() == 640
    assert rect.height() == 360
    assert canvas.normalized_point(QPoint(320, 240)) == pytest.approx((0.5, 0.5), abs=0.003)
    canvas.resize(960, 540)
    assert canvas.image_rect().size().width() == 960
    assert canvas.pixmap().size().width() == 1920
    canvas.resize(640, 480)
    canvas.set_fill_view(True)
    assert canvas.image_rect().height() == 480
    assert canvas.image_rect().width() > 640
    assert canvas.normalized_point(QPoint(320, 240)) == pytest.approx((0.5, 0.5), abs=0.003)


def test_focus_workspace_can_restore_navigation(application, fixture_ui):
    window = main.MainWindow()
    window.show()
    window.focus_view.setChecked(True)
    assert window.sidebar.isHidden()
    assert window.page_header.isHidden()
    window._focus_navigation()
    assert not window.sidebar.isHidden()
    assert not window.page_header.isHidden()
    window.menu_visibility.setChecked(True)
    assert window.menuBar().isHidden()
    window._focus_navigation()
    assert not window.menuBar().isHidden()


def test_top_navigation_keeps_overflow_pages_accessible(application, fixture_ui):
    window = main.MainWindow()
    for index in range(20):
        window.add_page(f"Additional workspace {index}", QWidget)
    window.resize(800, 600)
    window.show()
    application.processEvents()
    assert window.nav.horizontalScrollBar().maximum() > 0
    window.nav.setCurrentRow(window.nav.count() - 1)
    application.processEvents()
    assert window.nav.visualItemRect(window.nav.currentItem()).intersects(window.nav.viewport().rect())
    window.navigation_visibility.setChecked(True)
    window._focus_navigation()
    assert not window.sidebar.isHidden()
    assert window.page_search.hasFocus()


def test_top_navigation_has_one_always_reachable_hide_show_button(application, fixture_ui):
    window = main.MainWindow()
    window.resize(800, 600)
    window.show()
    application.processEvents()
    assert window.sidebar.width() == window.stack.width()
    assert window.nav.flow() == window.nav.Flow.LeftToRight
    assert not window.nav.isWrapping()
    index = next(index for index in range(window.nav.count()) if window.nav.item(index).text() == "Live Gates")
    window.nav.setCurrentRow(index)
    application.processEvents()
    assert window.sidebar.geometry().bottom() + 1 == window.stack.mapTo(window.workspace_root, window.stack.rect().topLeft()).y()
    QTest.mouseClick(window.navigation_button, Qt.MouseButton.LeftButton)
    assert window.sidebar.isHidden()
    assert window.navigation_button.isVisible()
    assert window.navigation_button.text() == "Show navigation"
    QTest.mouseClick(window.navigation_button, Qt.MouseButton.LeftButton)
    assert not window.sidebar.isHidden()
    window.focus_view.setChecked(True)
    assert window.navigation_button.isVisible()
    QTest.mouseClick(window.navigation_button, Qt.MouseButton.LeftButton)
    assert not window.focus_view.isChecked()
    assert not window.sidebar.isHidden()


@pytest.mark.parametrize("failure", ["eof", "timeout"])
def test_live_reader_reports_closed_and_stalled_streams(application, monkeypatch, failure):
    import httpx
    from app.desktop import streams
    failures = []
    timeout_values = []

    class Response:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def iter_bytes(self):
            yield b"\xff\xd8first\xff\xd9"
            if failure == "timeout":
                raise httpx.ReadTimeout("camera stalled")

    class Client:
        def __init__(self, timeout):
            timeout_values.append(timeout.read)

        def stream(self, *args, **kwargs):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(streams.httpx, "Client", Client)
    reader = streams.MjpegStream(1)
    reader.failed.connect(failures.append)
    reader.run()
    assert timeout_values == [8.0]
    assert len(failures) == 1
    assert reader.mailbox.take() == b"\xff\xd8first\xff\xd9"


def test_display_readers_have_independent_mailboxes(application, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from app.desktop import streams

    class Response:
        status_code = 200

        def __init__(self, url):
            self.url = url

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def iter_bytes(self):
            yield b"\xff\xd8" + self.url.encode() + b"\xff\xd9"

    class Client:
        def __init__(self, **kwargs):
            pass

        def stream(self, method, url, **kwargs):
            return Response(url)

        def close(self):
            pass

    monkeypatch.setattr(streams.httpx, "Client", Client)
    readers = [streams.MjpegStream(camera_id) for camera_id in (1, 2, 3, 4)]
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda reader: reader.run(), readers))
    for camera_id, reader in enumerate(readers, 1):
        assert f"/cameras/{camera_id}/live.mjpeg".encode() in reader.mailbox.take()


def test_display_preferences_and_palette_are_local(application, fixture_ui):
    fixture_api, settings = fixture_ui
    window = main.MainWindow()
    for appearance in APPEARANCES:
        window.apply_theme(appearance)
        assert settings.value("appearance") == appearance
        if appearance != "System":
            assert application.palette().color(QPalette.ColorRole.Text) == QColor(PALETTES[appearance].text)
    window._set_text_size(14)
    assert QApplication.font().pointSize() == 14
    assert window.page_title.font().pointSize() == 20
    window._set_text_size(100)
    assert window.text_size == 18
    window._set_text_size(0)
    assert window.text_size == 10
    window.close()
    assert settings.contains("geometry")
    assert not settings.contains("splitter")
    assert not fixture_api.requests


def test_forms_expose_labels_and_tables_are_read_only(application):
    page = QWidget()
    form = QFormLayout(page)
    field = QLineEdit()
    form.addRow("&Camera name", field)
    table = QTableWidget(1, 3)
    form.addRow(table)
    prepare_page(page, "Cameras")
    assert form.labelForField(field).buddy() is field
    assert field.accessibleName() == "Camera name"
    assert form.rowWrapPolicy() == QFormLayout.RowWrapPolicy.WrapLongRows
    assert table.accessibleName() == "Cameras records"
    assert table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    assert table.alternatingRowColors()
    assert not table.isSortingEnabled()
    assert table.horizontalHeader().defaultSectionSize() >= 140
    buddy = label_for("&Visit", field)
    assert buddy.buddy() is field


def test_viewport_keeps_large_content_reachable(application):
    page = QWidget()
    layout = QVBoxLayout(page)
    large = QLineEdit()
    large.setMinimumSize(1300, 900)
    layout.addWidget(large)
    viewport = page_viewport(page, "Large page")
    viewport.resize(800, 600)
    viewport.show()
    application.processEvents()
    assert viewport.horizontalScrollBar().maximum() > 0
    assert viewport.verticalScrollBar().maximum() > 0
    viewport.close()


def luminance(color):
    channels = [int(color[offset:offset + 2], 16) / 255 for offset in (1, 3, 5)]
    linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
    return sum(channel * weight for channel, weight in zip(linear, (0.2126, 0.7152, 0.0722)))


@pytest.mark.parametrize("name", PALETTES)
def test_theme_text_contrast(name):
    colors = PALETTES[name]
    for foreground, background in (
        (colors.text, colors.surface), (colors.muted, colors.surface),
        (colors.muted, colors.workspace), (colors.selected_text, colors.accent),
    ):
        light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
        assert (light + 0.05) / (dark + 0.05) >= 4.5


def test_render_operator_workspaces(application, fixture_ui, tmp_path):
    output = Path(os.environ.get("SMARTPARK_UI_PREVIEW_DIR", tmp_path / "previews"))
    output.mkdir(parents=True, exist_ok=True)
    window = main.MainWindow()
    marker = QLabel("PREVIEW · fixture data · no engine connected")
    window.statusBar().addPermanentWidget(marker)
    for title, appearance, size in (
        ("Dashboard", "Light", (1280, 800)),
        ("Live Gates", "Light", (1280, 900)),
        ("Sessions", "Light", (1024, 768)),
        ("Reports", "Dark", (1280, 900)),
        ("Settings", "High contrast", (1024, 768)),
    ):
        window.apply_theme(appearance)
        window.resize(*size)
        index = next(index for index in range(window.nav.count()) if window.nav.item(index).text() == title)
        window.nav.setCurrentRow(index)
        window.show()
        application.processEvents()
        application.processEvents()
        page = window.pages[index]
        assert page.accessibleName() == title
        assert window.width() == size[0]
        filename = f"{title.lower().replace(' ', '-')}-{appearance.lower().replace(' ', '-')}.png"
        assert window.grab().save(str(output / filename))
    assert set(fixture_ui[0].requests) <= {"/dashboard", "/backup", "/sessions"}
    window.close()
