"""Native window chrome and local display preferences, with no API imports."""

from PySide6.QtCore import QEvent, QSettings, QSize, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListView, QMainWindow, QSizePolicy, QStackedWidget, QStyle, QToolBar, QToolButton,
    QVBoxLayout, QWidget,
)

from .presentation import prepare_page
from .theme import APPEARANCES, apply_appearance


PAGE_DESCRIPTIONS = {
    "Dashboard": "Site overview, lane condition, and items needing attention.",
    "Live Gates": "Monitor cameras and inspect a vehicle. Manual commands apply to one selected side only.",
    "Sessions": "Find a visit, review its evidence, and manage the operator workflow.",
    "Vehicles": "Maintain the site's registered vehicle directory.",
    "Reports": "Review activity, export records, and manage backups.",
    "Settings": "Local appearance and site configuration. Display preferences stay on this computer.",
    "System Health": "Inspect service and device information reported by the site.",
    "Detections": "Inspect recognition evidence and detection history.",
    "Payments": "Review recorded payments.",
    "Gates": "Inspect gate devices and select a side before a manual command.",
    "Users & Roles": "Manage operator accounts and their assigned access.",
    "Tariffs & Schedules": "Review the site's tariffs and charging schedules.",
}


class DesktopShell(QMainWindow):
    appearanceChanged = Signal(str)

    def __init__(self, settings=None):
        super().__init__()
        self.display_settings = settings if settings is not None else QSettings("SmartPark", "OperatorDesktop")
        self.appearance = self.display_settings.value("appearance", "Light")
        if self.appearance not in APPEARANCES:
            self.appearance = "Light"
        try:
            self.text_size = max(10, min(18, int(self.display_settings.value("textSize", 10))))
        except (TypeError, ValueError):
            self.text_size = 10
        self._appearance_actions = {}
        self._build_workspace()
        self.setMinimumSize(800, 600)
        self.resize(1280, 800)
        geometry = self.display_settings.value("geometry")
        self.restored_geometry = False
        if geometry:
            self.restored_geometry = self.restoreGeometry(geometry)
        self._set_text_size(self.text_size)
        self.apply_theme(self.appearance)

    def _build_workspace(self):
        self.workspace_root = QWidget()
        workspace_layout = QVBoxLayout(self.workspace_root)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)
        self.setCentralWidget(self.workspace_root)
        sidebar = QFrame()
        self.sidebar = sidebar
        sidebar.setObjectName("sidebar")
        sidebar.setFixedHeight(68)
        navigation = QHBoxLayout(sidebar)
        navigation.setContentsMargins(6, 4, 6, 4)
        navigation.setSpacing(6)
        self.page_search = QLineEdit()
        self.page_search.setPlaceholderText("Find a page · Ctrl+K")
        self.page_search.setClearButtonEnabled(True)
        self.page_search.setFixedWidth(180)
        self.page_search.setAccessibleName("Find a workspace page")
        self.page_search.installEventFilter(self)
        navigation.addWidget(self.page_search)
        self.nav = QListWidget()
        self.nav.setObjectName("navigation")
        self.nav.setAccessibleName("Workspace pages")
        self.nav.setAccessibleDescription("Arrow keys select a page. Ctrl+K filters page names. Enter in the filter opens the first match.")
        self.nav.setFlow(QListView.Flow.LeftToRight)
        self.nav.setWrapping(False)
        self.nav.setResizeMode(QListView.ResizeMode.Adjust)
        self.nav.setHorizontalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        navigation.addWidget(self.nav, 1)
        self.navigation_result = QLabel()
        self.navigation_result.setObjectName("muted")
        self.navigation_result.setWordWrap(True)
        self.navigation_result.hide()
        self.page_search.textChanged.connect(self._filter_navigation)
        workspace = QWidget()
        workspace.setObjectName("workspace")
        content = QVBoxLayout(workspace)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        header = QFrame()
        self.page_header = header
        header.setObjectName("pageHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(18, 14, 18, 14)
        header_layout.setSpacing(4)
        self.page_title = QLabel("Workspace")
        self.page_title.setObjectName("pageTitle")
        self.page_description = QLabel("Choose a page from Navigate.")
        self.page_description.setObjectName("pageDescription")
        self.page_description.setWordWrap(True)
        header_layout.addWidget(self.page_title)
        header_layout.addWidget(self.page_description)
        content.addWidget(header)
        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        content.addWidget(self.stack, 1)
        workspace_layout.addWidget(sidebar)
        workspace_layout.addWidget(workspace, 1)
        self.statusBar().setSizeGripEnabled(True)
        self.workspace_status = QLabel("Local operator workspace")
        self.statusBar().addPermanentWidget(self.workspace_status)
        self.navigation_visibility = QAction("Hide navigation", self)
        self.navigation_visibility.setCheckable(True)
        self.navigation_visibility.toggled.connect(self._set_navigation_hidden)
        self.navigation_button = QToolButton()
        self.navigation_button.setDefaultAction(self.navigation_visibility)
        self.navigation_button.setAccessibleName("Hide or show top navigation")
        self.statusBar().addPermanentWidget(self.navigation_button)

    def _set_navigation_hidden(self, hidden):
        self.sidebar.setVisible(not hidden)
        self.navigation_visibility.setText("Show navigation" if hidden else "Hide navigation")
        if not hidden and hasattr(self, "focus_view") and self.focus_view.isChecked():
            self.focus_view.setChecked(False)

    def finish_shell(self, refresh_action: QAction, help_action: QAction):
        workspace_menu = self.menuBar().addMenu("&Workspace")
        find_page = QAction("Find a page", self)
        find_page.setShortcut(QKeySequence("Ctrl+K"))
        self.addAction(find_page)
        find_page.triggered.connect(self._focus_navigation)
        workspace_menu.addAction(find_page)
        workspace_menu.addSeparator()
        close = QAction("Close window", self)
        close.setShortcut(QKeySequence.StandardKey.Quit)
        close.triggered.connect(self.close)
        workspace_menu.addAction(close)
        view = self.menuBar().addMenu("&View")
        self.focus_view = QAction("Focus live workspace", self)
        self.focus_view.setCheckable(True)
        self.focus_view.setShortcut(QKeySequence("F11"))
        self.addAction(self.focus_view)
        self.focus_view.toggled.connect(self._set_focus_view)
        view.addAction(self.focus_view)
        self.menu_visibility = QAction("Hide menu bar", self)
        self.menu_visibility.setCheckable(True)
        self.menu_visibility.setShortcut(QKeySequence("Ctrl+M"))
        self.menu_visibility.toggled.connect(lambda hidden: self.menuBar().setVisible(not hidden))
        self.addAction(self.menu_visibility)
        view.addAction(self.menu_visibility)
        appearance = view.addMenu("Appearance")
        group = QActionGroup(self)
        group.setExclusive(True)
        for name in APPEARANCES:
            action = QAction(name, self)
            action.setCheckable(True)
            action.setChecked(name == self.appearance)
            action.triggered.connect(lambda checked=False, value=name: self.apply_theme(value))
            group.addAction(action)
            appearance.addAction(action)
            self._appearance_actions[name] = action
        for title, keys, change in (
            ("Larger text", ["Ctrl++", "Ctrl+="], 1),
            ("Smaller text", ["Ctrl+-"], -1),
            ("Reset text size", ["Ctrl+0"], 0),
        ):
            action = QAction(title, self)
            action.setShortcuts([QKeySequence(key) for key in keys])
            action.triggered.connect(lambda checked=False, delta=change: self._set_text_size(self.text_size + delta if delta else 10))
            view.addAction(action)
        toolbar = QToolBar("Workspace commands", self)
        toolbar.setObjectName("workspaceCommands")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(16, 16))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        refresh_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        toolbar.addAction(refresh_action)
        toolbar.addSeparator()
        toolbar.addAction(find_page)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        toolbar.addAction(help_action)
        self.addToolBar(toolbar)
        self.workspace_toolbar = toolbar

    def _set_focus_view(self, enabled):
        self.navigation_visibility.setChecked(enabled)
        current = self.stack.currentWidget()
        page = current.widget() if hasattr(current, "widget") else current
        self.page_header.setVisible(not enabled and not bool(page and page.property("videoWorkspace")))
        self.workspace_toolbar.setVisible(not enabled)
        self.workspace_status.setText("Focused workspace · F11 restores navigation" if enabled else "Local operator workspace")

    def _focus_navigation(self):
        self.focus_view.setChecked(False)
        self.navigation_visibility.setChecked(False)
        self.menu_visibility.setChecked(False)
        self.page_search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.page_search.selectAll()

    def _filter_navigation(self, text):
        visible = 0
        for index in range(self.nav.count()):
            item = self.nav.item(index)
            item.setHidden(text.casefold() not in item.text().casefold())
            visible += not item.isHidden()
        self.navigation_result.setText((f"{visible} matching pages" if visible else "No matching pages. Clear the filter to show all.") if text else "F1 · Keyboard shortcuts")

    def eventFilter(self, watched, event):
        if watched is self.page_search and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Down):
                for index in range(self.nav.count()):
                    if not self.nav.item(index).isHidden():
                        self.nav.setCurrentRow(index)
                        self.nav.setFocus()
                        break
                return True
            if event.key() == Qt.Key.Key_Escape:
                self.page_search.clear()
                self.nav.setFocus()
                return True
        return super().eventFilter(watched, event)

    def show_page_context(self, index):
        item = self.nav.item(index)
        if item is None:
            return
        self.page_title.setText(item.text())
        current = self.stack.currentWidget()
        page = current.widget() if hasattr(current, "widget") else current
        self.page_header.setVisible(not self.focus_view.isChecked() and not bool(page and page.property("videoWorkspace")))
        self.page_description.setText(PAGE_DESCRIPTIONS.get(item.text(), "Use the controls below to work with this page."))
        self.workspace_status.setText(f"{item.text()}  ·  F1 for help")
        self.statusBar().showMessage("Ready")

    def apply_theme(self, name):
        if name not in APPEARANCES:
            return
        self.appearance = name
        apply_appearance(QApplication.instance(), name)
        self._set_text_size(self.text_size)
        self.display_settings.setValue("appearance", name)
        if name in self._appearance_actions:
            self._appearance_actions[name].setChecked(True)
        self.appearanceChanged.emit(name)

    def _set_text_size(self, size):
        self.text_size = max(10, min(18, int(size)))
        font = QFont(QApplication.font())
        font.setPointSize(self.text_size)
        QApplication.setFont(font)
        self.sidebar.setFixedHeight(self.fontMetrics().height() + 46)
        heading_font = QFont(font)
        heading_font.setPointSize(self.text_size + 6)
        heading_font.setBold(True)
        self.page_title.setFont(heading_font)
        for page in getattr(self, "pages", []):
            if page is not None:
                prepare_page(page, page.accessibleName())
        self.display_settings.setValue("textSize", self.text_size)

    def closeEvent(self, event):
        self.display_settings.setValue("geometry", self.saveGeometry())
        super().closeEvent(event)
