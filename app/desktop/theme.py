# Tokens aligned with app/web/index.html (ui.html reference) — teal accent, light shell.

LIGHT = """
QWidget { background:#F2F4F6; color:#161C24; font-size:13px; }
QFrame#card { background:#FFFFFF; border:1px solid #E2E6EC; border-radius:10px; }
QPushButton {
  background:#0E7C72; color:#FFFFFF; padding:8px 14px; border-radius:6px; border:none; font-weight:600;
}
QPushButton:hover { background:#0B6A61; }
QPushButton:disabled { background:#C9D1DB; color:#545E6C; }
QPushButton#secondary, QPushButton[cssClass="secondary"] {
  background:#FFFFFF; color:#161C24; border:1px solid #C9D1DB;
}
QPushButton#secondary:hover { background:#F7F9FB; }
QLineEdit, QComboBox, QSpinBox {
  background:#FFFFFF; border:1px solid #C9D1DB; border-radius:6px; padding:7px; color:#161C24;
}
QLineEdit:focus, QComboBox:focus { border:1px solid #0E7C72; }
QTableWidget { background:#FFFFFF; border:1px solid #E2E6EC; gridline-color:#E2E6EC; border-radius:10px; }
QPlainTextEdit { background:#FFFFFF; border:1px solid #E2E6EC; border-radius:6px; padding:8px; color:#545E6C; }
QHeaderView::section {
  background:#FFFFFF; color:#545E6C; padding:8px 10px; border:none;
  border-bottom:1px solid #E2E6EC; font-weight:700; font-size:11px;
}
QListWidget {
  background:#FFFFFF; color:#545E6C; border:none; border-right:1px solid #E2E6EC; padding:8px;
}
QListWidget::item { padding:10px 12px; border-radius:6px; margin:1px 4px; font-weight:600; }
QListWidget::item:hover { background:#EDF1F5; color:#161C24; }
QListWidget::item:selected { background:rgba(14,124,114,0.12); color:#0E7C72; }
QLabel#video { background:#070B10; color:#8A94A2; border-radius:10px; padding:8px; }
QLabel#muted { color:#545E6C; }
QTabWidget::pane { border:1px solid #E2E6EC; background:#F2F4F6; border-radius:8px; }
QTabBar::tab {
  background:#FFFFFF; color:#545E6C; padding:8px 16px; border-radius:6px; margin-right:4px;
  border:1px solid #E2E6EC; font-weight:600;
}
QTabBar::tab:selected { background:#0E7C72; color:#FFFFFF; border-color:#0E7C72; }
QDialog { background:#F2F4F6; }
QMessageBox { background:#FFFFFF; }
"""

DARK = """
QWidget { background:#0D1117; color:#E7EDF3; font-size:13px; }
QFrame#card { background:#151B22; border:1px solid #242E39; border-radius:10px; }
QPushButton {
  background:#2FBFAD; color:#04211D; padding:8px 14px; border-radius:6px; border:none; font-weight:600;
}
QPushButton:hover { background:#4ACEBD; }
QPushButton:disabled { background:#33404E; color:#667180; }
QPushButton#secondary, QPushButton[cssClass="secondary"] {
  background:#151B22; color:#E7EDF3; border:1px solid #33404E;
}
QPushButton#secondary:hover { background:#1A222B; }
QLineEdit, QComboBox, QSpinBox {
  background:#151B22; color:#E7EDF3; border:1px solid #33404E; border-radius:6px; padding:7px;
}
QLineEdit:focus, QComboBox:focus { border:1px solid #2FBFAD; }
QTableWidget { background:#151B22; color:#E7EDF3; border:1px solid #242E39; gridline-color:#242E39; border-radius:10px; }
QPlainTextEdit { background:#151B22; color:#9AA5B1; border:1px solid #242E39; border-radius:6px; padding:8px; }
QHeaderView::section {
  background:#151B22; color:#9AA5B1; padding:8px 10px; border:none;
  border-bottom:1px solid #242E39; font-weight:700; font-size:11px;
}
QListWidget {
  background:#151B22; color:#9AA5B1; border:none; border-right:1px solid #242E39; padding:8px;
}
QListWidget::item { padding:10px 12px; border-radius:6px; margin:1px 4px; font-weight:600; }
QListWidget::item:hover { background:#212B36; color:#E7EDF3; }
QListWidget::item:selected { background:rgba(47,191,173,0.16); color:#2FBFAD; }
QLabel#video { background:#020617; color:#667180; border-radius:10px; padding:8px; }
QLabel#muted { color:#9AA5B1; }
QTabWidget::pane { border:1px solid #242E39; background:#0D1117; border-radius:8px; }
QTabBar::tab {
  background:#1A222B; color:#9AA5B1; padding:8px 16px; border-radius:6px; margin-right:4px;
  border:1px solid #242E39; font-weight:600;
}
QTabBar::tab:selected { background:#2FBFAD; color:#04211D; border-color:#2FBFAD; }
QDialog { background:#0D1117; }
QMessageBox { background:#151B22; }
"""
