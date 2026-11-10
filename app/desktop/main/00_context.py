from __future__ import annotations

import json

import os

from pathlib import Path

import sys

import time

import traceback

import httpx

from PySide6.QtCore import QDate, Qt, QSize, QThread, QTime, QTimer, Signal

from PySide6.QtGui import QAction, QColor, QFont, QGuiApplication, QIcon, QImage, QKeySequence, QPainter, QPen, QPixmap, QShortcut, QTextDocument

from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDateEdit, QDialog, QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QStackedWidget, QTabWidget, QTableWidget, QTableWidgetItem, QTimeEdit, QVBoxLayout, QWidget, QInputDialog, QGroupBox
)

from app.services.live_pair import camera_label, lane_options, pair_lane_cameras

from app.desktop.api import api, stream_http_error

from app.desktop.desk import ReportsPage, health_sentences

from app.desktop.theme import APPEARANCES, apply_appearance

from app.desktop.presentation import configure_table, label_for, page_viewport, prepare_page

from app.desktop.shell import DesktopShell

from app.desktop.common import (Worker, _stop_thread, action_label, available_screen, fit_window_to_screen,
                     is_technician, deployment_kind, source_label, money_label, method_label)

from app.branding import PRODUCT_NAME, PRODUCT_TAGLINE

def _qr_png_from_sources(qr_url="", qr_payload=""):
    """Load the ticket QR from the API, or draw it locally if that image is blocked."""
    png = b""
    if qr_url:
        try:
            png = api.get_bytes(qr_url, timeout=8)
        except Exception:
            png = b""
    if not png.startswith(b"\x89PNG"):
        png = b""
    if not png:
        from app.infrastructure.hardware.printers import qr_png_bytes
        payload = (qr_payload or "").strip()
        if not payload and qr_url:
            path = str(qr_url).split("?")[0]
            if path.endswith("/qr.png"):
                path = path[: -len("/qr.png")]
            payload = f"{api.base_url}{path}" if path.startswith("/") else path
        png = qr_png_bytes(payload)
    return png if png.startswith(b"\x89PNG") else b""

def _receipt_print_html(body, qr_png=b""):
    from html import escape
    import base64
    safe = escape(body or "").replace("\n", "<br>\n")
    qr = ""
    if qr_png and qr_png.startswith(b"\x89PNG"):
        uri = "data:image/png;base64," + base64.b64encode(qr_png).decode("ascii")
        qr = (
            '<p style="text-align:center;margin:16px 0">'
            f'<img src="{uri}" width="200" height="200" alt="QR" '
            'style="border:1px solid #ccc;padding:8px;background:#fff"></p>'
            '<p style="text-align:center;font-size:12px">Scan this QR at the kiosk if the camera cannot read the plate.</p>'
        )
    return (
        "<html><head><meta charset='utf-8'></head>"
        "<body style='font:14px/1.45 ui-monospace,monospace;padding:16px;max-width:420px'>"
        f"<div>{safe}</div>{qr}</body></html>"
    )

def show_printable_receipt(parent, body, path="", qr_url="", qr_payload=""):
    dlg=QDialog(parent)
    dlg.setWindowTitle("Parking receipt")
    dlg.setMinimumSize(420, 640)
    layout=QVBoxLayout(dlg)
    text=QPlainTextEdit(); text.setReadOnly(True)
    text.setPlainText(body or "Parking receipt")
    layout.addWidget(text, 1)
    qr_png=_qr_png_from_sources(qr_url, qr_payload)
    if qr_png:
        pix = QPixmap(); pix.loadFromData(qr_png)
        if not pix.isNull():
            qr_label = QLabel(); qr_label.setAlignment(Qt.AlignCenter)
            qr_label.setMinimumHeight(220)
            qr_label.setPixmap(pix.scaled(220, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            layout.addWidget(qr_label)
            tip = QLabel("Scan this QR at the kiosk if the camera cannot read the plate.")
            tip.setWordWrap(True); tip.setAlignment(Qt.AlignCenter); layout.addWidget(tip)
    if path:
        hint=QLabel(f"Printer-ready file: {path}"); hint.setWordWrap(True); layout.addWidget(hint)
    row=QHBoxLayout()
    print_btn=QPushButton("Print")
    close_btn=QPushButton("Close")
    row.addWidget(print_btn); row.addWidget(close_btn); row.addStretch()
    layout.addLayout(row)

    def do_print():
        html=_receipt_print_html(body, qr_png)
        try:
            from PySide6.QtPrintSupport import QPrintDialog, QPrinter
            printer=QPrinter()
            dialog=QPrintDialog(printer, dlg)
            if dialog.exec()==QDialog.DialogCode.Accepted:
                doc=QTextDocument(); doc.setHtml(html)
                doc.print_(printer)
                return
        except Exception:
            pass
        target=path
        if not target or not str(target).endswith(".html"):
            folder=os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp"
            target=os.path.join(folder, "smartpark-receipt.html")
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(html)
        try:
            if os.name=="nt":
                os.startfile(target, "print")
            else:
                import subprocess
                subprocess.Popen(["xdg-open", target])
        except Exception as exc:
            QMessageBox.information(dlg, "Receipt", f"Receipt is ready at:\n{target}\n\n{exc}")

    print_btn.clicked.connect(do_print)
    close_btn.clicked.connect(dlg.accept)
    dlg.exec()

from app.desktop.streams import MjpegStream, pop_latest_mjpeg, _pop_raw_jpegs

from app.desktop.live_pane import CameraLivePane

from app.desktop.video import VideoCanvas as ClickLabel

from app.desktop.live_cameras import CameraDialog, Cameras

def _iso_date(text: str, end: bool = False) -> str | None:
    raw=(text or "")[:10]
    if len(raw) < 10 or raw[4] != "-":
        return None
    return f"{raw}T{'23:59:59' if end else '00:00:00'}Z"
