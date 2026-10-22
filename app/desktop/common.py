"""Shared desktop tasks and formatting; no camera lifecycle ownership."""
from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QThread, Signal
from PySide6.QtGui import QGuiApplication
from .api import api
from .presentation import prepare_page


def action_label(name: str, shortcut: str) -> str:
    return f"{name} ({shortcut})"


def available_screen():
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return None
    return screen.availableGeometry()


def fit_window_to_screen(window, preferred=(1120, 720), min_size=(720, 480)):
    prepare_page(window, window.windowTitle())
    avail = available_screen()
    if avail is None:
        window.resize(*preferred)
        return False
    margin = 24
    max_w = max(320, avail.width() - margin)
    max_h = max(240, avail.height() - margin)
    width = min(preferred[0], max_w)
    height = min(preferred[1], max_h)
    window.setMaximumSize(max_w, max_h)
    window.setMinimumSize(min(min_size[0], max_w), min(min_size[1], max_h))
    window.resize(width, height)
    window.move(avail.x() + (avail.width() - width) // 2, avail.y() + (avail.height() - height) // 2)
    return width >= max_w * 0.92 or height >= max_h * 0.92


def is_technician():
    return api.can("hardware.view")


def deployment_kind():
    profile = str((api.modules or {}).get("profile") or "")
    enabled = set((api.modules or {}).get("enabled") or [])
    if profile == "LPR_ONLY":
        return "lpr"
    if profile == "SECURITY":
        return "security"
    if profile == "ACCESS_CONTROL":
        return "access"
    if profile in {"PARKING_LITE", "PARKING_PRO", "ENTERPRISE"}:
        return "parking"
    if "parking.sessions" in enabled or "payments.core" in enabled:
        return "parking"
    if "security.watchlists" in enabled or "security.alerts" in enabled:
        return "security"
    if "access.gates" in enabled:
        return "access"
    if "recognition.alpr" in enabled:
        return "lpr"
    return "parking"


def source_label(source):
    text = str(source or "").lower()
    if not text or text == "—":
        return "—"
    if "operator" in text:
        return "Operator"
    if "hybrid" in text or "fusion" in text:
        return "Camera + SmartPark"
    if "fast" in text or "local" in text:
        return "SmartPark AI"
    if "native" in text or "camera" in text or "sdk" in text:
        return "Camera"
    return str(source) if is_technician() else "Recognition"


def money_label(amount, currency=""):
    try:
        number = float(amount or 0)
    except (TypeError, ValueError):
        number = 0
    text = f"{number:,.0f}" if number == int(number) else f"{number:,.2f}"
    cur = str(currency or "").strip()
    return f"{cur} {text}".strip()


def method_label(method):
    text = str(method or "").lower()
    if not text:
        return "—"
    if "cash" in text:
        return "Cash"
    if "card" in text:
        return "Card"
    if "mobile" in text or "mpesa" in text or "m-pesa" in text or "wallet" in text:
        return "Mobile Money"
    return str(method) if is_technician() else "Other"


class Worker(QThread):
    done=Signal(object)
    failed=Signal(str)
    def __init__(self, fn): super().__init__(); self.fn=fn
    def run(self):
        try: self.done.emit(self.fn())
        except Exception as e: self.failed.emit(str(e))


_retired_threads = set()
_shutdown_connected = False


def _finish_retired_threads():
    for thread in list(_retired_threads):
        thread.stop()
        thread.wait(14000)
        if not thread.isRunning():
            _retired_threads.discard(thread)


def _stop_thread(thread, wait_ms=0):
    """Retain stopping readers until they exit, without freezing or terminating Qt."""
    global _shutdown_connected
    if thread is None:
        return
    try:
        thread.stop()
    except Exception:
        pass
    if thread.isRunning() and not thread.wait(wait_ms):
        _retired_threads.add(thread)
        thread.finished.connect(lambda: _retired_threads.discard(thread))
        application = QCoreApplication.instance()
        if application is not None and not _shutdown_connected:
            application.aboutToQuit.connect(_finish_retired_threads)
            _shutdown_connected = True
        if not thread.isRunning():
            _retired_threads.discard(thread)
