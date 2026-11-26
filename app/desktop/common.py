"""Shared desktop tasks and formatting; no camera lifecycle ownership."""
from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QThread, Signal
from PySide6.QtGui import QGuiApplication
from app.branding import PRODUCT_NAME
from .api import api, friendly_error
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
        return f"Camera + {PRODUCT_NAME}"
    if "fast" in text or "local" in text:
        return f"{PRODUCT_NAME} AI"
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
    """Run one blocking call (network, database, file) off the UI thread.

    ``failed`` carries a plain sentence: "Can't reach the Site Server…" when
    there was no answer, "The Site Server refused: …" when it said no.
    ``error`` is the original exception for callers that branch on it.
    """
    done=Signal(object)
    failed=Signal(str)
    def __init__(self, fn):
        super().__init__(); self.fn=fn; self.error=None
    def run(self):
        try: self.done.emit(self.fn())
        except Exception as e:
            self.error=e
            self.failed.emit(friendly_error(e))


# Tests drive page methods without a running Qt event loop. With this set,
# run_task calls the work and its callbacks inline, in order.
TASKS_INLINE = False

_live_tasks: set = set()


def _set_busy(widgets, busy, busy_text):
    for widget in widgets:
        if widget is None:
            continue
        try:
            if busy:
                widget._idle_text = widget.text() if hasattr(widget, "text") else None
                widget.setEnabled(False)
                if busy_text and hasattr(widget, "setText"):
                    widget.setText(busy_text)
            else:
                widget.setEnabled(True)
                idle = getattr(widget, "_idle_text", None)
                if idle is not None and hasattr(widget, "setText"):
                    widget.setText(idle)
        except RuntimeError:
            pass  # widget already deleted (page closed while working)


def show_status(owner, text, ms=8000):
    """Show a short result in the main window's status bar, if there is one."""
    # Settings and Camera calibration keep the main window in ``self.window``,
    # which hides QWidget.window(). Calling it raised "'MainWindow' object is
    # not callable" after every save there and closed the desktop app, so
    # the setting was saved but the app crashed before it could say so.
    window = getattr(owner, "window", None)
    try:
        if callable(window) and not hasattr(window, "statusBar"):
            window = window()
    except RuntimeError:
        return
    bar = getattr(window, "statusBar", None)
    if callable(bar):
        try:
            bar().showMessage(str(text), ms)
        except RuntimeError:
            pass


def run_task(owner, fn, on_done=None, *, buttons=(), busy_text="Working…", title="",
             on_error=None, status=None):
    """Do ``fn`` off the UI thread with visible feedback.

    While it runs the given buttons are disabled and show ``busy_text`` and
    the status bar says ``status``; afterwards the buttons come back,
    ``on_done(result)`` runs on the UI thread, and any failure is shown in
    plain words (``on_error(message, exc)`` overrides the default dialog).
    """
    buttons = tuple(b for b in (buttons if isinstance(buttons, (list, tuple)) else (buttons,)) if b is not None)

    def finish_ok(result):
        _set_busy(buttons, False, None)
        if on_done is not None:
            on_done(result)

    def finish_error(message, exc):
        _set_busy(buttons, False, None)
        if on_error is not None:
            on_error(message, exc)
            return
        from PySide6.QtWidgets import QMessageBox, QWidget
        parent = owner if isinstance(owner, QWidget) else None
        QMessageBox.warning(parent, title or PRODUCT_NAME, message)

    if TASKS_INLINE:
        _set_busy(buttons, True, busy_text)
        try:
            result = fn()
        except Exception as exc:
            finish_error(friendly_error(exc), exc)
            return None
        finish_ok(result)
        return None

    _set_busy(buttons, True, busy_text)
    if status:
        show_status(owner, status)
    worker = Worker(fn)
    worker.done.connect(finish_ok)
    worker.failed.connect(lambda message, w=worker: finish_error(message, getattr(w, "error", None)))
    _live_tasks.add(worker)
    worker.finished.connect(lambda w=worker: _live_tasks.discard(w))
    worker.start()
    return worker


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
