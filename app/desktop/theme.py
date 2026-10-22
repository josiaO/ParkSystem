"""Presentation tokens for the native operator desktop; no service dependencies."""

from dataclasses import dataclass

from PySide6.QtGui import QColor, QPalette


@dataclass(frozen=True)
class Colors:
    workspace: str
    surface: str
    alternate: str
    text: str
    muted: str
    border: str
    accent: str
    selected_text: str
    focus: str


PALETTES = {
    "Light": Colors("#ecebe7", "#fafaf8", "#f0f1f3", "#182638", "#475467", "#adb3bc", "#244a79", "#ffffff", "#005fcc"),
    "Dark": Colors("#141d26", "#1e2b36", "#263643", "#edf3f7", "#b4c5d2", "#63798b", "#93dece", "#102b26", "#84bcff"),
    "High contrast": Colors("#000000", "#000000", "#151515", "#ffffff", "#ffffff", "#ffffff", "#ffff00", "#000000", "#00ffff"),
}
APPEARANCES = ("System", "Light", "Dark", "High contrast")


def stylesheet(colors: Colors) -> str:
    return f"""
QWidget {{ color:{colors.text}; }}
QMainWindow, QDialog, QWidget#workspace {{ background:{colors.workspace}; }}
QFrame#sidebar, QFrame#pageHeader, QFrame#card {{ background:{colors.surface}; border:1px solid {colors.border}; }}
QFrame#card {{ border-radius:4px; }}
QFrame#plateEvidence {{ background:#111b27; border:1px solid #8a9aaa; }}
QPushButton[compact="true"] {{ padding:2px 6px; border-radius:1px; }}
QLabel#brand {{ font-weight:700; }}
QLabel#muted, QLabel#pageDescription {{ color:{colors.muted}; }}
QLabel#pageTitle {{ font-weight:700; }}
QPushButton {{ background:{colors.surface}; border:1px solid {colors.border}; border-radius:3px; padding:6px 10px; }}
QPushButton:hover, QToolButton:hover {{ background:{colors.alternate}; }}
QPushButton:pressed {{ background:{colors.border}; }}
QPushButton[primary="true"], QPushButton:default {{ background:{colors.accent}; color:{colors.selected_text}; border-color:{colors.accent}; font-weight:600; }}
QPushButton:disabled, QToolButton:disabled {{ color:{colors.muted}; background:{colors.alternate}; }}
QPushButton:focus, QToolButton:focus, QCheckBox:focus, QSlider:focus, QListWidget:focus {{ border:2px solid {colors.focus}; }}
QLineEdit, QComboBox, QAbstractSpinBox, QPlainTextEdit, QTextEdit {{ background:{colors.surface}; color:{colors.text}; border:1px solid {colors.border}; border-radius:3px; padding:5px 7px; selection-background-color:{colors.accent}; selection-color:{colors.selected_text}; }}
QLineEdit:focus, QComboBox:focus, QAbstractSpinBox:focus, QPlainTextEdit:focus {{ border:2px solid {colors.focus}; }}
QComboBox QAbstractItemView {{ background:{colors.surface}; color:{colors.text}; selection-background-color:{colors.accent}; selection-color:{colors.selected_text}; }}
QListWidget#navigation {{ background:{colors.surface}; border:2px solid transparent; padding:4px; outline:0; }}
QListWidget#navigation::item {{ padding:7px 8px; margin:1px 0; border-radius:3px; }}
QListWidget#navigation::item:hover {{ background:{colors.alternate}; }}
QListWidget#navigation::item:selected {{ background:{colors.accent}; color:{colors.selected_text}; }}
QListWidget#navigation::item:focus {{ border:1px solid {colors.focus}; }}
QTableView {{ background:{colors.surface}; alternate-background-color:{colors.alternate}; border:1px solid {colors.border}; gridline-color:{colors.border}; selection-background-color:{colors.accent}; selection-color:{colors.selected_text}; }}
QHeaderView::section {{ background:{colors.alternate}; color:{colors.text}; padding:7px; border:0; border-right:1px solid {colors.border}; border-bottom:1px solid {colors.border}; font-weight:600; }}
QTableView::item {{ padding:3px; }}
QTableView::item:focus {{ border:2px solid {colors.focus}; }}
QTabWidget::pane {{ border:1px solid {colors.border}; background:{colors.surface}; }}
QTabBar::tab {{ background:{colors.alternate}; color:{colors.text}; padding:7px 14px; border:1px solid {colors.border}; }}
QTabBar::tab:selected {{ background:{colors.surface}; border-bottom:3px solid {colors.accent}; font-weight:600; }}
QTabBar::tab:focus {{ border:2px solid {colors.focus}; }}
QMenuBar, QMenu, QToolBar, QStatusBar {{ background:{colors.surface}; color:{colors.text}; }}
QMenu::item:selected, QMenuBar::item:selected {{ background:{colors.accent}; color:{colors.selected_text}; }}
QToolBar {{ border:0; border-bottom:1px solid {colors.border}; spacing:6px; padding:4px; }}
QToolButton {{ padding:5px 8px; border:1px solid transparent; }}
QSplitter::handle {{ background:{colors.border}; }}
QScrollArea {{ border:0; background:transparent; }}
QGroupBox {{ border:1px solid {colors.border}; border-radius:3px; margin-top:12px; padding-top:10px; }}
QGroupBox::title {{ subcontrol-origin:margin; padding:0 5px; }}
QLabel#video {{ background:#070e16; color:#d0dee9; border:1px solid {colors.border}; border-radius:3px; padding:6px; }}
QToolTip {{ background:{colors.surface}; color:{colors.text}; border:1px solid {colors.border}; padding:5px; }}
"""


def apply_appearance(application, name: str):
    if not hasattr(application, "_desktop_system_palette"):
        application._desktop_system_palette = QPalette(application.palette())
    if name == "System":
        application.setStyleSheet("")
        application.setPalette(application._desktop_system_palette)
        return
    colors = PALETTES[name]
    palette = QPalette(application._desktop_system_palette)
    for role, color in (
        (QPalette.ColorRole.Window, colors.workspace),
        (QPalette.ColorRole.Base, colors.surface),
        (QPalette.ColorRole.AlternateBase, colors.alternate),
        (QPalette.ColorRole.WindowText, colors.text),
        (QPalette.ColorRole.Text, colors.text),
        (QPalette.ColorRole.Button, colors.surface),
        (QPalette.ColorRole.ButtonText, colors.text),
        (QPalette.ColorRole.Highlight, colors.accent),
        (QPalette.ColorRole.HighlightedText, colors.selected_text),
        (QPalette.ColorRole.PlaceholderText, colors.muted),
    ):
        palette.setColor(role, QColor(color))
    application.setPalette(palette)
    application.setStyleSheet(stylesheet(colors))


LIGHT = stylesheet(PALETTES["Light"])
DARK = stylesheet(PALETTES["Dark"])
