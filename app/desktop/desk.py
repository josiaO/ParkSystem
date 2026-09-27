"""Desktop reports, backup, and plain-language health.

The browser desk already exposes these. This module is the same operator path
for the Windows desktop client.
"""

from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from .api import api


REPORTS = (
    ("overview", "Overview"),
    ("payments", "Payments"),
    ("outstanding", "Cars still inside or owing"),
    ("daily", "Takings by day"),
    ("operators", "Cash by operator"),
    ("accuracy", "Plate reading accuracy"),
    ("exceptions", "Manual actions and corrections"),
    ("seasons", "Season tickets"),
)


def health_sentences(details: dict | None, live: dict | None = None) -> str:
    details = details or {}
    live = live or {}
    status = str(details.get("status") or details.get("state") or live.get("state") or "ok")
    lines = [f"The site is {status.replace('_', ' ')}."]
    hvx = details.get("hvx_host") or {}
    if hvx.get("ok"):
        lines.append("The camera host that talks to HVX cameras is running.")
    elif hvx.get("required") is False or hvx.get("supported") is False:
        lines.append("This computer does not run the Windows HVX camera host. IP cameras can still be used.")
    elif details.get("hvx_host"):
        lines.append("The HVX camera host is not responding. Parking can continue on cameras that do not need it.")
    modules = (details.get("modules") or {}).get("components") or details.get("modules") or {}
    if isinstance(modules, dict):
        for key, item in modules.items():
            if key in {"components", "profile", "enabled_modules"}:
                continue
            state = ""
            if isinstance(item, dict):
                state = str(item.get("state") or item.get("status") or "")
            elif isinstance(item, str):
                state = item
            if not state:
                continue
            label = str(key).replace("_", " ")
            lower = state.lower()
            if "disabled" in lower or lower in {"n/a", "neutral"}:
                lines.append(f"{label} is turned off. That is normal when you are not using it.")
            elif any(word in lower for word in ("ok", "ready", "healthy")):
                lines.append(f"{label} is working.")
            else:
                lines.append(f"{label} needs attention ({state}).")
    if len(lines) == 1:
        lines.append("No extra warnings.")
    return "\n".join(lines)


def format_sheet(sheet: dict | None) -> str:
    if not sheet:
        return "That report is not in this pack."
    lines = [str(sheet.get("title") or "Report"), ""]
    for section in sheet.get("sections") or []:
        lines.append(str(section.get("title") or ""))
        for row in section.get("rows") or []:
            lines.append(f"  {row.get('label')}: {row.get('value')}")
        lines.append("")
    columns = sheet.get("columns") or []
    if columns:
        lines.append(" | ".join(str(column.get("label") or "") for column in columns))
        rows = sheet.get("rows") or []
        if not rows:
            lines.append("Nothing in this period.")
        for row in rows:
            lines.append(" | ".join(str(row.get(column.get("key"), "")) for column in columns))
    return "\n".join(lines).strip() + "\n"


def print_text(parent, title: str, body: str) -> None:
    try:
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        printer = QPrinter()
        dialog = QPrintDialog(printer, parent)
        dialog.setWindowTitle(title)
        if dialog.exec():
            doc = QTextDocument()
            doc.setPlainText(body or "")
            doc.print_(printer)
            return
    except Exception as exc:
        QMessageBox.warning(parent, title, f"Printing is not available on this computer.\n\n{exc}")


class ReportsPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel("Reports")
        title.setStyleSheet("font-size:24px;font-weight:700")
        layout.addWidget(title)
        note = QLabel("Print or download the report a cashier, a supervisor, or an auditor needs. Plate accuracy counts stored reads. It does not change when a gate opens.")
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        self.kind = QComboBox()
        for key, label in REPORTS:
            self.kind.addItem(label, key)
        self.start = QLineEdit(QDate.currentDate().toString("yyyy-MM-dd"))
        self.end = QLineEdit(QDate.currentDate().toString("yyyy-MM-dd"))
        show = QPushButton("Show report")
        show.clicked.connect(self.show_report)
        print_one = QPushButton("Print this report")
        print_one.clicked.connect(self.print_current)
        print_all = QPushButton("Print all")
        print_all.clicked.connect(self.print_pack)
        download = QPushButton("Download this report")
        download.clicked.connect(self.download)
        for widget in (
            QLabel("Report"), self.kind, QLabel("From"), self.start, QLabel("To"), self.end,
            show, print_one, print_all, download,
        ):
            row.addWidget(widget)
        row.addStretch()
        layout.addLayout(row)
        self.body = QPlainTextEdit()
        self.body.setReadOnly(True)
        layout.addWidget(self.body, 1)
        backup_title = QLabel("Backup")
        backup_title.setStyleSheet("font-size:18px;font-weight:700")
        layout.addWidget(backup_title)
        self.backup_status = QLabel("Checking backup…")
        self.backup_status.setWordWrap(True)
        layout.addWidget(self.backup_status)
        form = QFormLayout()
        self.days = QLineEdit("7")
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://backup.example/smartpark")
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText("Leave blank to keep the saved token")
        self.hours = QLineEdit("24")
        self.enabled = QComboBox()
        self.enabled.addItem("Off", False)
        self.enabled.addItem("On", True)
        form.addRow("Remind me to save a file every (days)", self.days)
        form.addRow("Cloud address", self.url)
        form.addRow("Cloud token", self.token)
        form.addRow("Cloud every (hours)", self.hours)
        form.addRow("Cloud backup", self.enabled)
        layout.addLayout(form)
        actions = QHBoxLayout()
        save = QPushButton("Save backup schedule")
        save.clicked.connect(self.save_backup)
        offline = QPushButton("Download offline backup")
        offline.clicked.connect(self.download_backup)
        cloud = QPushButton("Run cloud backup now")
        cloud.clicked.connect(self.run_cloud)
        snooze = QPushButton("Remind me tomorrow")
        snooze.clicked.connect(self.snooze)
        manage = api.can("settings.manage")
        for button in (save, offline, cloud):
            button.setVisible(manage)
            actions.addWidget(button)
        actions.addWidget(snooze)
        actions.addStretch()
        layout.addLayout(actions)
        self.pack = None
        self._load_backup()

    def _range(self) -> str:
        start = self.start.text().strip()
        end = self.end.text().strip()
        bits = []
        if start:
            bits.append(f"start={start}")
        if end:
            bits.append(f"end={end}")
        return ("?" + "&".join(bits)) if bits else ""

    def show_report(self):
        try:
            self.pack = api.get(f"/reports/summary{self._range()}", timeout=20)
        except Exception as exc:
            QMessageBox.critical(self, "Reports", str(exc))
            return
        kind = self.kind.currentData()
        sheet = next((item for item in (self.pack.get("reports") or []) if item.get("id") == kind), None)
        self.body.setPlainText(format_sheet(sheet))

    def print_current(self):
        if not self.body.toPlainText().strip():
            QMessageBox.information(self, "Reports", "Show a report first.")
            return
        print_text(self, "SmartPark report", self.body.toPlainText())

    def print_pack(self):
        sheets = (self.pack or {}).get("reports") or []
        if not sheets:
            QMessageBox.information(self, "Reports", "Show a report first, then print all.")
            return
        print_text(self, "SmartPark audit pack", "\n\n".join(format_sheet(sheet) for sheet in sheets))

    def download(self):
        kind = self.kind.currentData() or "payments"
        query = self._range()
        joiner = "&" if query else "?"
        try:
            data = api.get_bytes(f"/reports/export.csv{query}{joiner}kind={kind}", timeout=20)
        except Exception as exc:
            QMessageBox.critical(self, "Reports", str(exc))
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save report", f"smartpark-{kind}.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "wb") as handle:
            handle.write(data)
        QMessageBox.information(self, "Reports", f"Saved {path}")

    def _apply_backup(self, status: dict):
        status = status or {}
        self.backup_status.setText(f"{status.get('offline_message') or ''} {status.get('cloud_message') or ''}".strip())
        self.days.setText(str(status.get("reminder_days") or 7))
        self.url.setText(status.get("cloud_url") or "")
        self.hours.setText(str(status.get("cloud_interval_hours") or 24))
        self.enabled.setCurrentIndex(1 if status.get("cloud_enabled") else 0)

    def _load_backup(self):
        try:
            self._apply_backup(api.get("/backup"))
        except Exception as exc:
            self.backup_status.setText(str(exc))

    def save_backup(self):
        payload = {
            "reminder_days": int(self.days.text() or "7"),
            "cloud_url": self.url.text().strip(),
            "cloud_interval_hours": int(self.hours.text() or "24"),
            "cloud_enabled": self.enabled.currentIndex() == 1,
        }
        if self.token.text():
            payload["cloud_token"] = self.token.text()
        try:
            self._apply_backup(api.patch("/backup", payload))
            self.token.clear()
        except Exception as exc:
            QMessageBox.critical(self, "Backup", str(exc))

    def download_backup(self):
        try:
            data = api.get_bytes("/backup/download", timeout=60)
        except Exception as exc:
            QMessageBox.critical(self, "Backup", str(exc))
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save offline backup", "smartpark-backup.sql", "SQL (*.sql)")
        if not path:
            return
        with open(path, "wb") as handle:
            handle.write(data)
        self._load_backup()
        QMessageBox.information(self, "Backup", f"Saved {path}")

    def run_cloud(self):
        try:
            self._apply_backup(api.post("/backup/cloud", {}, timeout=60))
        except Exception as exc:
            QMessageBox.critical(self, "Backup", str(exc))

    def snooze(self):
        try:
            self._apply_backup(api.post("/backup/snooze", {}))
        except Exception as exc:
            QMessageBox.critical(self, "Backup", str(exc))
