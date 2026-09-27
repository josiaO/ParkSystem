from __future__ import annotations

import json
import os
import sys
import time
import traceback
import httpx
from PySide6.QtCore import QDate, Qt, QSize, QThread, QTime, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen, QPixmap, QTextDocument
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDateEdit, QDialog, QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QStackedWidget, QTabWidget, QTableWidget, QTableWidgetItem, QTimeEdit, QVBoxLayout, QWidget, QInputDialog
)

from app.services.live_pair import camera_label, lane_options, pair_lane_cameras

from .api import api, BASE
from .desk import ReportsPage, health_sentences
from .theme import DARK, LIGHT


def available_screen():
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return None
    return screen.availableGeometry()


def fit_window_to_screen(window, preferred=(1120, 720), min_size=(720, 480)):
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


def configure_table(table: QTableWidget):
    table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
    table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
    table.setWordWrap(False)
    table.verticalHeader().setVisible(False)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    header.setStretchLastSection(True)


class Worker(QThread):
    done=Signal(object)
    failed=Signal(str)
    def __init__(self, fn): super().__init__(); self.fn=fn
    def run(self):
        try: self.done.emit(self.fn())
        except Exception as e: self.failed.emit(str(e))


def _stop_thread(thread, wait_ms=3000):
    """Stop a QThread without aborting the process if the camera stream is slow."""
    if thread is None:
        return
    try:
        thread.stop()
    except Exception:
        pass
    if thread.isRunning() and not thread.wait(wait_ms):
        thread.terminate()
        thread.wait(400)


def show_printable_receipt(parent, body, path="", qr_url=""):
    dlg=QDialog(parent)
    dlg.setWindowTitle("Parking receipt")
    dlg.setMinimumSize(420, 520)
    layout=QVBoxLayout(dlg)
    text=QPlainTextEdit(); text.setReadOnly(True); text.setPlainText(body or "")
    layout.addWidget(text, 1)
    if qr_url:
        try:
            png = api.get_bytes(qr_url, timeout=8)
            pix = QPixmap(); pix.loadFromData(png)
            if not pix.isNull():
                qr_label = QLabel(); qr_label.setAlignment(Qt.AlignCenter)
                qr_label.setPixmap(pix.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                layout.addWidget(qr_label)
                tip = QLabel("Scan to pay on your phone, or use the code at the kiosk.")
                tip.setWordWrap(True); tip.setAlignment(Qt.AlignCenter); layout.addWidget(tip)
        except Exception:
            pass
    if path:
        hint=QLabel(f"Printer-ready file: {path}"); hint.setWordWrap(True); layout.addWidget(hint)
    row=QHBoxLayout()
    print_btn=QPushButton("Print")
    close_btn=QPushButton("Close")
    row.addWidget(print_btn); row.addWidget(close_btn); row.addStretch()
    layout.addLayout(row)

    def do_print():
        try:
            from PySide6.QtPrintSupport import QPrintDialog, QPrinter
            printer=QPrinter()
            dialog=QPrintDialog(printer, dlg)
            if dialog.exec()==QDialog.DialogCode.Accepted:
                doc=QTextDocument(); doc.setPlainText(body or "")
                doc.print_(printer)
                return
        except Exception:
            pass
        target=path
        if not target:
            folder=os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp"
            target=os.path.join(folder, "smartpark-receipt.txt")
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(body or "")
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


class MjpegStream(QThread):
    """Read /live.mjpeg and emit only the newest JPEG. Old frames in the pipe are dropped."""
    frame=Signal(bytes)
    failed=Signal(str)
    def __init__(self, camera_id):
        super().__init__()
        self.camera_id=camera_id
        self._stop=False
        self._client=None
    def stop(self):
        self._stop=True
        client=self._client
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
    def run(self):
        client=httpx.Client(timeout=httpx.Timeout(connect=5.0, read=None, write=5.0, pool=5.0))
        self._client=client
        try:
            with client.stream(
                "GET",
                f"{BASE}/cameras/{self.camera_id}/live.mjpeg",
                headers=api._headers(),
            ) as response:
                if response.status_code >= 400:
                    if not self._stop:
                        self.failed.emit(response.text or str(response.status_code))
                    return
                buf=b""
                last_emit=0.0
                pending=None
                chunks=response.iter_bytes(65536)
                while not self._stop:
                    try:
                        chunk=next(chunks)
                    except StopIteration:
                        break
                    except Exception as e:
                        if self._stop:
                            return
                        if isinstance(e, httpx.ReadTimeout):
                            continue
                        raise
                    buf += chunk
                    if len(buf) > 2_500_000:
                        start=buf.rfind(b"\xff\xd8")
                        buf = buf[start:] if start>=0 else buf[-120_000:]
                    latest, buf = pop_latest_mjpeg(buf)
                    if latest is not None:
                        pending=latest
                    now=time.monotonic()
                    if pending is not None and (now-last_emit) >= 0.025:
                        self.frame.emit(pending)
                        pending=None
                        last_emit=now
                if pending is not None and not self._stop:
                    self.frame.emit(pending)
        except Exception as e:
            if not self._stop:
                self.failed.emit(str(e))
        finally:
            self._client=None
            try:
                client.close()
            except Exception:
                pass


def pop_latest_mjpeg(buf: bytes) -> tuple[bytes | None, bytes]:
    """Pull complete MJPEG parts from buf; keep only the newest JPEG."""
    latest = None
    boundary = b"--smartparkframe"
    while True:
        mark = buf.find(boundary)
        if mark < 0:
            jpeg, rest = _pop_raw_jpegs(buf)
            if jpeg:
                latest = jpeg
            return latest, rest
        header_end = buf.find(b"\r\n\r\n", mark)
        if header_end < 0:
            return latest, buf[mark:]
        headers = buf[mark:header_end]
        body = buf[header_end + 4:]
        length = None
        for line in headers.split(b"\r\n"):
            if line.lower().startswith(b"content-length:"):
                try:
                    length = int(line.split(b":", 1)[1].strip())
                except ValueError:
                    length = None
                break
        if length is None:
            jpeg, rest = _pop_raw_jpegs(body)
            if jpeg:
                latest = jpeg
            return latest, rest
        if len(body) < length:
            return latest, buf[mark:]
        latest = body[:length]
        buf = body[length:]
        if buf.startswith(b"\r\n"):
            buf = buf[2:]


def _pop_raw_jpegs(buf: bytes) -> tuple[bytes | None, bytes]:
    latest = None
    while True:
        start = buf.find(b"\xff\xd8")
        if start < 0:
            return latest, (buf[-1:] if buf.endswith(b"\xff") else b"")
        end = buf.find(b"\xff\xd9", start + 2)
        if end < 0:
            return latest, buf[start:]
        latest = buf[start:end + 2]
        buf = buf[end + 2:]


class Login(QDialog):
    def __init__(self):
        super().__init__(); self.setWindowTitle("SmartPark Edge — Sign In")
        self.setMinimumWidth(360); self.setMaximumWidth(460)
        l=QVBoxLayout(self); l.setContentsMargins(28,28,28,28); l.setSpacing(8)
        brand=QLabel("SmartPark Edge"); brand.setStyleSheet("font-size:18px;font-weight:700;letter-spacing:-0.2px")
        tag=QLabel("Vehicle intelligence · edge platform")
        tag.setStyleSheet("font-size:10px;font-weight:600;color:#8A94A2;letter-spacing:0.08em;text-transform:uppercase")
        title=QLabel("Sign in"); title.setStyleSheet("font-size:22px;font-weight:700;margin-top:10px")
        self.sub=QLabel("Sign in with the first-run admin password shown at setup")
        self.sub.setObjectName("muted"); self.sub.setWordWrap(True)
        self.user=QLineEdit("admin"); self.user.setPlaceholderText("Username")
        self.pwd=QLineEdit(); self.pwd.setPlaceholderText("Password"); self.pwd.setEchoMode(QLineEdit.Password)
        btn=QPushButton("Sign in"); btn.clicked.connect(self.login)
        l.addWidget(brand); l.addWidget(tag); l.addWidget(title); l.addWidget(self.sub)
        l.addSpacing(8); l.addWidget(self.user); l.addWidget(self.pwd); l.addSpacing(6); l.addWidget(btn)
        fit_window_to_screen(self, (400, 320), min_size=(340, 260))
        QTimer.singleShot(0, self._prefill)
    def _prefill(self):
        try:
            import httpx
            setup=httpx.get(f"{BASE}/auth/setup", timeout=3).json()
            if setup.get("username"): self.user.setText(setup["username"])
            if setup.get("password"):
                self.pwd.setText(setup["password"])
            else:
                self.pwd.clear()
            if setup.get("hint"): self.sub.setText(setup["hint"])
        except Exception:
            pass
    def login(self):
        try:
            api.login(self.user.text().strip(), self.pwd.text())
            self.accept()
        except Exception as e:
            text=str(e)
            if "401" in text or "Invalid username" in text:
                text = (
                    "Invalid username or password.\n\n"
                    "admin / first-run password only works on a fresh database. "
                    "This PC already has an admin account. "
                    "Reset it with: python -m app.cli reset-admin"
                )
            elif "Connection" in text or "ConnectError" in text or "8760" in text:
                text = "Cannot reach the API at http://127.0.0.1:8760. Start SmartPark with python -m app.desktop.launch"
            QMessageBox.critical(self,"Sign in failed",text)


class ClickLabel(QLabel):
    clicked=Signal()
    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class CameraLivePane(QFrame):
    """One live camera: video on top, last-car stills and plate details below."""
    def __init__(self, slot_title="Camera"):
        super().__init__()
        self.setObjectName("card")
        self.slot_title=slot_title
        self.camera=None
        self._all=[]
        l=QVBoxLayout(self)
        self.picker=QComboBox()
        self.picker.addItem("Choose camera…", None)
        self.picker.currentIndexChanged.connect(self._picked)
        l.addWidget(self.picker)
        self.video=ClickLabel("Click to choose a camera.")
        self.video.setObjectName("video")
        self.video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video.setMinimumHeight(280)
        self.video.setMaximumHeight(480)
        self.video.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.video.clicked.connect(self.picker.showPopup)
        l.addWidget(self.video, 3)
        self.status=QLabel("Click this view or the list to choose a camera.")
        self.status.setWordWrap(True)
        l.addWidget(self.status)
        stills=QHBoxLayout()
        snap_col=QVBoxLayout(); snap_col.addWidget(QLabel("Snapshot"))
        self.last_snap=QLabel("Waiting for a car")
        self.last_snap.setObjectName("video")
        self.last_snap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.last_snap.setMinimumHeight(80)
        self.last_snap.setMaximumHeight(110)
        snap_col.addWidget(self.last_snap)
        crop_col=QVBoxLayout(); crop_col.addWidget(QLabel("Cropped plate"))
        self.crop=QLabel("—")
        self.crop.setObjectName("video")
        self.crop.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.crop.setMinimumHeight(80)
        self.crop.setMaximumHeight(110)
        crop_col.addWidget(self.crop)
        stills.addLayout(snap_col, 1); stills.addLayout(crop_col, 1)
        l.addLayout(stills)
        self.plate=QLabel("—"); self.plate.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plate.setStyleSheet("font-size:22px;font-weight:700;letter-spacing:4px")
        l.addWidget(self.plate)
        self.details=QLabel("No car yet. Connect all on the IPs tab, then wait for a vehicle.")
        self.details.setWordWrap(True)
        l.addWidget(self.details)
        self.open_btn=QPushButton("Open this side"); self.open_btn.clicked.connect(self.open_this_side)
        l.addWidget(self.open_btn)
        self.correct_btn=QPushButton("Correct plate")
        self.correct_btn.clicked.connect(self.correct_plate)
        l.addWidget(self.correct_btn)
        self.hold_label=QLabel("")
        self.hold_label.setWordWrap(True)
        l.addWidget(self.hold_label)
        self._workers=[]
        self._snap_busy=False
        self._alpr_busy=False
        self._last_jpeg=b""
        self._last_overlay=None
        self._mjpeg=None
        self._snap_timer=QTimer(self); self._snap_timer.setInterval(200); self._snap_timer.timeout.connect(self._tick_snapshot)
        self._alpr_timer=QTimer(self); self._alpr_timer.setInterval(2000); self._alpr_timer.timeout.connect(self._tick_alpr)
        self._paint_busy=False
        self._shown_jpeg=b""
        self._pending_live=b""
        self._held_car=None
        self._watching=None
    def fill_cameras(self, rows):
        self._all=list(rows or [])
        current=self.camera_id()
        self.picker.blockSignals(True)
        self.picker.clear()
        self.picker.addItem("Choose camera…", None)
        for cam in self._all:
            self.picker.addItem(camera_label(cam), cam.get("id"))
        if current is not None:
            idx=self.picker.findData(current)
            if idx>=0: self.picker.setCurrentIndex(idx)
        self.picker.blockSignals(False)
    def _picked(self, _index=None):
        cid=self.picker.currentData()
        cam=next((c for c in self._all if c.get("id")==cid), None)
        self.set_camera(cam)
    def _sync_picker(self):
        cid=self.camera_id()
        self.picker.blockSignals(True)
        idx=self.picker.findData(cid) if cid is not None else 0
        if idx>=0: self.picker.setCurrentIndex(idx)
        else: self.picker.setCurrentIndex(0)
        self.picker.blockSignals(False)
    def _keep(self, worker):
        self._workers.append(worker)
        worker.finished.connect(lambda w=worker: self._workers.remove(w) if w in self._workers else None)
    def camera_id(self):
        return None if not self.camera else self.camera.get("id")
    def set_camera(self, camera):
        cid=(camera or {}).get("id") if camera else None
        same=self.camera and cid and self.camera.get("id")==cid
        self.camera=camera
        self._sync_picker()
        if not camera:
            self.status.setText("Click this view or the list to choose a camera.")
            self.details.setText("Any added camera can go on the left or the right.")
            self.plate.setText("—")
            self.stop_live()
            self.video.setText("Click to choose a camera")
            return
        if same and self._snap_timer.isActive():
            if not self._alpr_timer.isActive(): self._alpr_timer.start()
            return
        self.start_live()
    def stop_live(self):
        self._snap_timer.stop(); self._alpr_timer.stop(); self._stop_mjpeg()
        watching=self._watching
        self._watching=None
        if watching is not None:
            try: api.post(f"/cameras/{watching}/live/unwatch", {}, timeout=4)
            except Exception: pass
    def shutdown(self):
        self.stop_live()
    def start_live(self):
        cid=self.camera_id()
        if cid is None:
            self.stop_live(); return
        if self._watching==cid and self._snap_timer.isActive():
            if not self._alpr_timer.isActive(): self._alpr_timer.start()
            return
        self._stop_mjpeg()
        if self._watching not in {None, cid}:
            try: api.post(f"/cameras/{self._watching}/live/unwatch", {}, timeout=4)
            except Exception: pass
        self._watching=cid
        self.status.setText("Opening live view…")
        try: api.post(f"/cameras/{cid}/live/watch", {}, timeout=8)
        except Exception: pass
        self._snap_timer.setInterval(40)
        if not self._snap_timer.isActive(): self._snap_timer.start()
        self._tick_snapshot()
        if not self._alpr_timer.isActive(): self._alpr_timer.start()
        self._tick_alpr()
    def _stop_mjpeg(self):
        stream=self._mjpeg
        self._mjpeg=None
        _stop_thread(stream)
    def _mjpeg_fail(self, err):
        self._live_fail(err)
        if self.camera_id() is not None and not self._snap_timer.isActive():
            self._snap_timer.start()
            self._tick_snapshot()
    def _set_pixmap(self, label, jpeg, overlay=None):
        image=QImage.fromData(jpeg)
        if image.isNull(): return False
        if overlay and label is self.video:
            image=self._paint_overlay(image, overlay)
        pix=QPixmap.fromImage(image)
        box=label.contentsRect().size()
        max_h=label.maximumHeight()
        if max_h and 0 < max_h < 16777215:
            box.setHeight(min(box.height() or max_h, max_h))
        if box.width() < 16 or box.height() < 16:
            box=QSize(max(label.width(), 480), max_h if max_h and max_h < 16777215 else 360)
        label.setPixmap(pix.scaled(box, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation))
        return True
    def _paint_overlay(self, image, overlay):
        src_w=int(overlay.get("image_width") or 0) or image.width()
        src_h=int(overlay.get("image_height") or 0) or image.height()
        sx=image.width()/src_w if src_w else 1
        sy=image.height()/src_h if src_h else 1
        x1,y1=int(overlay["x1"]*sx), int(overlay["y1"]*sy)
        x2,y2=int(overlay["x2"]*sx), int(overlay["y2"]*sy)
        painted=image.copy()
        painter=QPainter(painted)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(0, 220, 90), max(2, painted.width()//240)))
        painter.drawRect(x1, y1, max(1, x2-x1), max(1, y2-y1))
        label=str(overlay.get("label") or "")
        if label:
            painter.setFont(QFont("Sans Serif", max(10, painted.width()//48)))
            painter.setPen(QPen(QColor(0, 220, 90)))
            painter.drawText(x1, max(12, y1-6), label)
        painter.end()
        return painted
    def _tick_snapshot(self):
        cid=self.camera_id()
        if cid is None or self._snap_busy: return
        self._snap_busy=True
        w=Worker(lambda: api.get_bytes(f"/cameras/{cid}/snapshot.jpg", timeout=3))
        w.done.connect(self._queue_live_frame); w.failed.connect(self._live_fail); w.finished.connect(lambda: setattr(self,"_snap_busy",False)); self._keep(w); w.start()
    def _queue_live_frame(self, jpeg):
        self._pending_live=jpeg
        if not self._paint_busy:
            self._flush_live_frame()
    def _flush_live_frame(self):
        jpeg=self._pending_live
        if not jpeg or jpeg==self._shown_jpeg:
            return
        self._paint_busy=True
        try:
            self._last_jpeg=jpeg
            self._shown_jpeg=jpeg
            if not self._set_pixmap(self.video, jpeg, self._last_overlay):
                self.video.setText("Waiting for a JPEG frame")
            else:
                self.status.setText("Live")
        finally:
            self._paint_busy=False
        if self._pending_live and self._pending_live != jpeg:
            QTimer.singleShot(0, self._flush_live_frame)
    def _live_fail(self, err):
        text=str(err or "")
        if "409" in text or "ffmpeg" in text.lower() or "ffprobe" in text.lower():
            self.video.setText("Waiting for a camera JPEG.\nHVX: SDK login on port 30000. Generic IP: HTTP snapshot or RTSP + FastALPR.")
            self.status.setText("Waiting for live video")
            return
        self.status.setText(text)
        self.video.setText(text)
    def _tick_alpr(self):
        cid=self.camera_id()
        if cid is None or self._alpr_busy: return
        self._alpr_busy=True
        w=Worker(lambda: api.get(f"/cameras/{cid}/plates", timeout=8))
        w.done.connect(self._show_alpr); w.failed.connect(lambda e: self.status.setText(e)); w.finished.connect(lambda: setattr(self,"_alpr_busy",False)); self._keep(w); w.start()
    def _show_alpr(self, data):
        payload=data if isinstance(data, dict) else {}
        last=payload.get("last_car") or payload.get("capture") or {}
        if last.get("snapshot_url") or last.get("crop_url") or last.get("plate"):
            self._held_car=last
        shown=self._held_car or last
        fusion=payload.get("fusion") or {}
        native=payload.get("native") or {}
        resolved=payload.get("resolved_plate") or fusion.get("resolved_plate") or shown.get("plate") or native.get("plate") or ""
        self._last_overlay=payload.get("overlay") or native.get("bbox")
        if isinstance(self._last_overlay, dict) and "x1" in self._last_overlay:
            if "image_width" not in self._last_overlay:
                self._last_overlay={**self._last_overlay, "label": resolved or native.get("plate") or "", "image_width": native.get("image_width") or 0, "image_height": native.get("image_height") or 0}
            if self._last_jpeg:
                self._set_pixmap(self.video, self._last_jpeg, self._last_overlay)
        plate=resolved or shown.get("plate") or shown.get("plate_raw") or ""
        chars=shown.get("characters") or (" ".join(list(plate)) if plate else "—")
        self.plate.setText(chars)
        src=payload.get("live_source") or ""
        fps=payload.get("live_fps")
        age=payload.get("live_frame_age_ms")
        live_bits=[]
        if src: live_bits.append(str(src))
        if fps: live_bits.append(f"{fps:g} fps")
        if age is not None: live_bits.append(f"{int(round(age))} ms")
        if payload.get("live"):
            self.status.setText("Live" + ((" · " + " · ".join(live_bits)) if live_bits else ""))
        elif payload.get("error"):
            self.status.setText(str(payload.get("error")))
        conf=shown.get("confidence")
        conf_txt=f"{int(round(conf*100))}%" if conf is not None else "—"
        source=shown.get("source") or fusion.get("method") or "—"
        side=shown.get("lane_direction") or (self.camera or {}).get("side") or (self.camera or {}).get("lane_direction") or "—"
        when=str(shown.get("created_at") or "")[:19].replace("T"," ") or "—"
        if plate:
            decision = "held for confirmation" if (shown.get("pending_confirmation") or shown.get("needs_review") or fusion.get("needs_review")) else "auto-accepted"
            self.details.setText(f"Time {when}  ·  {side}  ·  {conf_txt}  ·  {source}  ·  {decision}")
            self.hold_label.setText("Waiting: confirm or correct this plate before the gate auto-decides." if decision.startswith("held") else "")
        else:
            self.details.setText("No car yet. Connect all on the IPs tab, then wait for a vehicle.")
            self.hold_label.setText("")
        snap=shown.get("snapshot_url")
        if snap:
            w=Worker(lambda: api.get_bytes(snap, timeout=8))
            w.done.connect(lambda jpeg: self._set_pixmap(self.last_snap, jpeg)); self._keep(w); w.start()
        crop=shown.get("crop_url")
        if crop:
            w=Worker(lambda: api.get_bytes(crop, timeout=8))
            w.done.connect(lambda jpeg: self._set_pixmap(self.crop, jpeg)); self._keep(w); w.start()
    def open_this_side(self):
        cam=self.camera
        if not cam:
            QMessageBox.information(self,"Open this side","No camera on this side."); return
        side=cam.get("side") or cam.get("lane_direction") or "this side"
        if QMessageBox.question(self,"Open this side",f"Pulse only {cam.get('name') or side} — not the other side of this lane?")!=QMessageBox.Yes: return
        reason,ok=QInputDialog.getText(self,"Open this side","Reason", text="manual open")
        if ok and reason:
            try: QMessageBox.information(self,"Barrier",str(api.post(f"/cameras/{cam['id']}/barrier/open",{"reason":reason}, timeout=20)))
            except Exception as e: QMessageBox.critical(self,"Barrier",str(e))

    def correct_plate(self):
        cam=self.camera
        if not cam:
            QMessageBox.information(self,"Correct plate","No camera on this side."); return
        shown=self._held_car or {}
        current=str(shown.get("plate") or "")
        text,ok=QInputDialog.getText(self,"Correct plate","Plate (leave as-is to confirm)", text=current)
        if not ok:
            return
        try:
            body={"plate": text.strip() or current, "capture_id": shown.get("id"), "confirm": True}
            data=api.post(f"/cameras/{cam['id']}/plate-corrections", body, timeout=20)
            QMessageBox.information(self,"Plate",str((data or {}).get("message") or data))
            self._tick_alpr()
        except Exception as e:
            QMessageBox.critical(self,"Correct plate",str(e))


class Dashboard(QWidget):
    def __init__(self):
        super().__init__(); self.layout=QVBoxLayout(self)
        title=QLabel("Overview"); title.setStyleSheet("font-size:24px;font-weight:700")
        self.layout.addWidget(title)
        self.grid=QGridLayout(); self.layout.addLayout(self.grid)
        self.alert=QLabel(""); self.alert.setWordWrap(True); self.layout.addWidget(self.alert)
        self.backup=QLabel(""); self.backup.setWordWrap(True); self.layout.addWidget(self.backup)
        backup_row=QHBoxLayout()
        self.open_reports=QPushButton("Open reports"); self.open_reports.clicked.connect(self._open_reports); self.open_reports.setVisible(False)
        self.snooze_backup=QPushButton("Remind me tomorrow"); self.snooze_backup.clicked.connect(self._snooze_backup); self.snooze_backup.setVisible(False)
        backup_row.addWidget(self.open_reports); backup_row.addWidget(self.snooze_backup); backup_row.addStretch()
        self.layout.addLayout(backup_row)
        self.layout.addStretch()
        self._cards=[]
        self._workers=[]
        QTimer.singleShot(0, self.refresh)
    def _keep(self, worker):
        self._workers.append(worker)
        worker.finished.connect(lambda w=worker: self._workers.remove(w) if w in self._workers else None)
    def _card(self, label, value):
        frame=QFrame(); frame.setObjectName("card")
        box=QVBoxLayout(frame)
        val=QLabel(str(value)); val.setStyleSheet("font-size:28px;font-weight:700")
        cap=QLabel(label); cap.setStyleSheet("color:#5b6b82")
        box.addWidget(val); box.addWidget(cap)
        return frame, val
    def refresh(self):
        w=Worker(lambda: api.get("/dashboard"))
        w.done.connect(self._apply)
        w.failed.connect(lambda e: self.alert.setText(f"Unable to load dashboard: {e}"))
        self._keep(w); w.start()
    def _apply(self, data):
        data=data or {}
        stats=[
            ("Vehicles inside", data.get("vehicles_inside", 0)),
            ("Entries today", data.get("entries_today", 0)),
            ("Exits today", data.get("exits_today", 0)),
            ("Revenue today", data.get("revenue_today_label") or data.get("revenue_today") or 0),
            ("Unpaid active", data.get("unpaid_active", 0)),
            ("Subscribers inside", data.get("subscribers_inside", 0)),
        ]
        while self.grid.count():
            item=self.grid.takeAt(0)
            w=item.widget()
            if w is not None:
                w.deleteLater()
        for i,(label,value) in enumerate(stats):
            frame,_=self._card(label, value)
            self.grid.addWidget(frame, i//3, i%3)
        for i,lane in enumerate(data.get("lanes") or []):
            text=(
                f"{lane.get('label') or lane.get('name') or ''}\n"
                f"Camera: {lane.get('camera')}\n"
                f"Live Video: {lane.get('live_video')}\n"
                f"Plate Recognition: {lane.get('plate_recognition')}\n"
                f"Barrier: {lane.get('barrier')}"
            )
            frame=QFrame(); frame.setObjectName("card")
            box=QVBoxLayout(frame)
            cap=QLabel(text); cap.setWordWrap(True)
            box.addWidget(cap)
            self.grid.addWidget(frame, 2 + i//2, i%2)
        alerts=data.get("alerts") or []
        self.alert.setText("  ·  ".join(alerts) if alerts else "No hardware alerts.")
        self._load_backup()
    def _load_backup(self):
        try:
            status=api.get("/backup")
        except Exception:
            self.backup.setText("")
            self.open_reports.setVisible(False)
            self.snooze_backup.setVisible(False)
            return
        due=bool(status.get("offline_due") or status.get("cloud_due"))
        bits=[]
        if status.get("offline_due"):
            bits.append(status.get("offline_message") or "")
        if status.get("cloud_due"):
            bits.append(status.get("cloud_message") or "Cloud backup is due.")
        self.backup.setText(" ".join(bit for bit in bits if bit))
        self.open_reports.setVisible(due)
        self.snooze_backup.setVisible(due)
    def _open_reports(self):
        window=self.window()
        nav=getattr(window, "nav", None)
        if nav is None:
            return
        for i in range(nav.count()):
            if "report" in nav.item(i).text().lower():
                nav.setCurrentRow(i)
                return
    def _snooze_backup(self):
        try:
            api.post("/backup/snooze", {})
        except Exception as exc:
            QMessageBox.warning(self, "Backup", str(exc))
            return
        self._load_backup()


class CameraDialog(QDialog):
    def __init__(self, camera=None):
        super().__init__(); self.camera=camera; self.setWindowTitle("Edit Camera" if camera else "Add Camera")
        self.setMinimumWidth(360); self.setMaximumWidth(520)
        form=QFormLayout(self)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.name=QLineEdit(); self.ip=QLineEdit(); self.port=QLineEdit("30000"); self.username=QLineEdit("admin")
        self.password=QLineEdit(); self.password.setEchoMode(QLineEdit.Password)
        if camera: self.password.setPlaceholderText("Leave blank to keep current password")
        else: self.password.setText("admin")
        self.direction=QComboBox(); self.direction.addItems(["ENTRY","EXIT"])
        self.adapter=QComboBox()
        for key, label in (
            ("hvx", "hvx — this site (NetSDK + onboard ALPR)"),
            ("rtsp", "rtsp — generic IP + FastALPR"),
            ("dahua", "dahua — IP camera + FastALPR"),
            ("hikvision", "hikvision — IP camera + FastALPR"),
            ("onvif", "onvif — not implemented"),
            ("simulated", "simulated — no hardware"),
        ):
            self.adapter.addItem(label, key)
        self.rtsp=QLineEdit()
        self.rtsp.setPlaceholderText("leave blank to auto-try Dahua/Hikvision paths")
        self.ffmpeg_profile=QComboBox(); self.ffmpeg_profile.addItems(["LOW_LATENCY_LAN","COMPATIBLE","LOSSY_NETWORK","VENDOR_SPECIAL"])
        self.transport=QComboBox(); self.transport.addItems(["TCP","UDP","AUTO"])
        self.recognition=QComboBox(); self.recognition.addItem("Default for adapter", "")
        for key in ("NATIVE_ONLY","FASTALPR_ONLY","HYBRID"):
            self.recognition.addItem(key, key)
        self.controller=QLineEdit(); self.display=QLineEdit()
        self.gate=QComboBox(); self.gate.addItem("None", None)
        try:
            for g in api.get("/gates"): self.gate.addItem(g["name"], g["id"])
        except Exception:
            pass
        if camera:
            self.name.setText(camera["name"]); self.ip.setText(camera["ip_address"]); self.port.setText(str(camera["sdk_port"]))
            self.username.setText(camera["username"]); self.direction.setCurrentText(camera["lane_direction"]); self.rtsp.setText(camera.get("rtsp_url") or "")
            self.controller.setText(camera.get("controller_ip") or "")
            self.display.setText(camera.get("display_ip") or "")
            if camera.get("adapter_id"):
                idx=self.adapter.findData(str(camera.get("adapter_id")))
                if idx>=0: self.adapter.setCurrentIndex(idx)
            if camera.get("ffmpeg_profile"):
                idx=self.ffmpeg_profile.findText(str(camera.get("ffmpeg_profile")))
                if idx>=0: self.ffmpeg_profile.setCurrentIndex(idx)
            if camera.get("rtsp_transport"):
                idx=self.transport.findText(str(camera.get("rtsp_transport")))
                if idx>=0: self.transport.setCurrentIndex(idx)
            if camera.get("recognition_mode"):
                idx=self.recognition.findData(str(camera.get("recognition_mode")))
                if idx>=0: self.recognition.setCurrentIndex(idx)
            idx=self.gate.findData(camera.get("gate_id")); 
            if idx>=0: self.gate.setCurrentIndex(idx)
        for label,w in [("Name",self.name),("Camera IP",self.ip),("HVX SDK port",self.port),("Username",self.username),("Password",self.password),("Side",self.direction),("Lane",self.gate),("Adapter",self.adapter),("Recognition",self.recognition),("Controller IP (Board*)",self.controller),("Display IP (IpAddr*)",self.display),("RTSP URL (optional, auto-tried if blank)",self.rtsp),("FFmpeg profile",self.ffmpeg_profile),("RTSP transport",self.transport)]: form.addRow(label,w)
        save=QPushButton("Save Camera"); save.clicked.connect(self.accept); form.addRow(save)
    def payload(self):
        data={"name":self.name.text().strip(),"ip_address":self.ip.text().strip(),"sdk_port":int(self.port.text()),"username":self.username.text(),"lane_direction":self.direction.currentText(),"adapter_id":self.adapter.currentData(),"recognition_mode":self.recognition.currentData() or "","controller_ip":self.controller.text().strip(),"display_ip":self.display.text().strip(),"rtsp_url":self.rtsp.text().strip(),"ffmpeg_profile":self.ffmpeg_profile.currentText(),"rtsp_transport":self.transport.currentText(),"gate_id":self.gate.currentData()}
        if self.password.text() or not self.camera:
            data["password"]=self.password.text()
        return data


class Cameras(QWidget):
    def __init__(self):
        super().__init__(); l=QVBoxLayout(self)
        title=QLabel("Live Gates"); title.setStyleSheet("font-size:24px;font-weight:700")
        l.addWidget(title)
        hint=QLabel("Show 1 camera, 2 cameras, or every camera. A camera that is not on this screen still reads plates and fills its lane. Leaving this page only stops the picture, not recognition.")
        hint.setWordWrap(True); l.addWidget(hint)
        self.tabs=QTabWidget()
        live=QWidget(); live_l=QVBoxLayout(live)
        lane_row=QHBoxLayout()
        lane_row.addWidget(QLabel("Show"))
        self.layout_mode=QComboBox()
        self.layout_mode.addItems(["1 camera", "2 cameras", "All cameras"])
        self.layout_mode.setCurrentIndex(1)
        self.layout_mode.currentIndexChanged.connect(self._on_layout)
        lane_row.addWidget(self.layout_mode)
        lane_row.addWidget(QLabel("Lane preset"))
        self.lane=QComboBox(); self.lane.currentIndexChanged.connect(self._lane_changed)
        lane_row.addWidget(self.lane, 1)
        fill_lane=QPushButton("Fill both from lane"); fill_lane.clicked.connect(lambda: self._start_pair(True))
        lane_row.addWidget(fill_lane)
        refresh_live=QPushButton("Refresh live"); refresh_live.clicked.connect(lambda: self._start_pair(False))
        lane_row.addWidget(refresh_live)
        live_l.addLayout(lane_row)
        self.live_grid=QGridLayout()
        self.pane_a=CameraLivePane("Left")
        self.pane_b=CameraLivePane("Right")
        self.extra_panes=[]
        self.live_grid.addWidget(self.pane_a, 0, 0)
        self.live_grid.addWidget(self.pane_b, 0, 1)
        live_host=QWidget(); live_host.setLayout(self.live_grid)
        live_scroll=QScrollArea(); live_scroll.setWidgetResizable(True); live_scroll.setWidget(live_host)
        live_l.addWidget(live_scroll, 1)

        ips=QWidget(); ips_l=QVBoxLayout(ips)
        tools=QHBoxLayout()
        add=QPushButton("Add Camera"); add.clicked.connect(self.add_camera); add.setVisible(api.can("cameras.manage"))
        seed=QPushButton("Add site cameras"); seed.clicked.connect(self.seed_site); seed.setVisible(api.can("cameras.manage"))
        discover=QPushButton("Discover"); discover.clicked.connect(self.discover)
        onboard=QPushButton("Onboard wizard"); onboard.clicked.connect(self.onboard); onboard.setVisible(api.can("cameras.manage"))
        connect_all=QPushButton("Connect all"); connect_all.clicked.connect(self.connect_all)
        edit=QPushButton("Edit"); edit.clicked.connect(self.edit_camera); edit.setVisible(api.can("cameras.manage"))
        delete=QPushButton("Delete"); delete.clicked.connect(self.delete_camera); delete.setVisible(api.can("cameras.manage"))
        refresh=QPushButton("Refresh"); refresh.clicked.connect(self.refresh)
        for w in (add, seed, discover, onboard, connect_all, edit, delete, refresh): tools.addWidget(w)
        tools.addStretch(); ips_l.addLayout(tools)
        ips_hint=QLabel("Discover, Connect all, and camera IPs live here. Select a row for Connect, Probe, FastALPR, or Capture snapshot.")
        ips_hint.setWordWrap(True); ips_l.addWidget(ips_hint)
        self.table=QTableWidget(0,10); self.table.setHorizontalHeaderLabels(["ID","Name","Lane","Side","Camera","Controller","Display","Status","SDK","Error"])
        configure_table(self.table); ips_l.addWidget(self.table, 1)
        self.stream_info=QLabel("Stream profiles appear after Connect. Live and FastALPR share one gateway producer.")
        self.stream_info.setWordWrap(True); ips_l.addWidget(self.stream_info)
        actions=QHBoxLayout()
        self.connect_btn=QPushButton("Connect"); self.connect_btn.clicked.connect(self.sdk_connect)
        self.probe_btn=QPushButton("Probe video"); self.probe_btn.clicked.connect(self.rtsp_probe)
        self.onvif_btn=QPushButton("ONVIF profiles"); self.onvif_btn.clicked.connect(self.onvif_discover)
        self.alpr_btn=QPushButton("FastALPR"); self.alpr_btn.clicked.connect(self.fastalpr)
        self.disconnect_btn=QPushButton("SDK Disconnect"); self.disconnect_btn.clicked.connect(self.sdk_disconnect)
        self.open_side_btn=QPushButton("Open this side"); self.open_side_btn.clicked.connect(self.open_this_side)
        self.snap_btn=QPushButton("Capture snapshot"); self.snap_btn.clicked.connect(self.capture_snapshot)
        for w in (self.connect_btn, self.probe_btn, self.onvif_btn, self.alpr_btn, self.snap_btn, self.disconnect_btn, self.open_side_btn):
            actions.addWidget(w)
        actions.addStretch(); ips_l.addLayout(actions)

        self.tabs.addTab(live, "Live")
        self.tabs.addTab(ips, "IPs")
        self.tabs.currentChanged.connect(self._on_tab)
        l.addWidget(self.tabs, 1)
        self.rows=[]
        self.table.itemSelectionChanged.connect(self._on_select)
        self._workers=[]
        self._ready=False
        if not hasattr(self, "extra_panes"):
            self.extra_panes=[]
    def selected_id(self):
        row=self.table.currentRow()
        if row<0: return None
        return int(self.table.item(row,0).text())
    def refresh(self):
        try: rows=api.get("/cameras")
        except Exception as e: QMessageBox.warning(self,"Cameras",str(e)); return
        self.rows=rows
        self.table.setRowCount(len(rows))
        for r,c in enumerate(rows):
            vals=[
                c["id"], c["name"],
                c.get("lane_name") or c.get("gate_name") or "—",
                c.get("side") or c.get("lane_direction") or "—",
                c.get("ip_address") or "—",
                c.get("controller_ip") or "—",
                c.get("display_ip") or "—",
                c["status"],
                "handle="+str(c["sdk_handle"]) if c["sdk_handle"] is not None else "—",
                (c.get("last_error") or "—")[:80],
            ]
            for col,v in enumerate(vals): self.table.setItem(r,col,QTableWidgetItem(str(v)))
        self._fill_lanes()
        self._maybe_start_pair()
    def selected_camera(self):
        row=self.table.currentRow()
        if row<0 or row>=len(self.rows): return None
        return self.rows[row]
    def seed_site(self):
        w=Worker(api.seed_site); w.done.connect(lambda data:(QMessageBox.information(self,"Site cameras",f"Added {len(data.get('created') or [])} camera(s)."),self.refresh())); w.failed.connect(lambda e:QMessageBox.critical(self,"Site cameras",e)); self._keep(w); w.start()
    def discover(self):
        w=Worker(lambda: api.get("/cameras/discover?scan_lan=true", timeout=45)); w.done.connect(self._show_discover); w.failed.connect(lambda e:QMessageBox.critical(self,"Discover",e)); self._keep(w); w.start()
    def onboard(self):
        ip, ok = QInputDialog.getText(self, "Onboard camera", "Camera IP")
        if not ok or not str(ip).strip():
            return
        payload={"ip_address": str(ip).strip(), "username": "admin", "password": "admin"}
        w=Worker(lambda: api.post("/cameras/onboard/probe", payload, timeout=20))
        w.done.connect(self._show_onboard); w.failed.connect(lambda e:QMessageBox.critical(self,"Onboard",e)); self._keep(w); w.start()
    def _show_onboard(self, data):
        data=data or {}
        QMessageBox.information(self, "Onboard", json.dumps({k: data.get(k) for k in ("ok","recommended_adapter","camera_type","recognition_mode","capabilities","note") if k in data}, indent=2))
        dlg=CameraDialog()
        dlg.ip.setText(str((data.get("ip") or "")))
        if data.get("recommended_adapter"):
            idx=dlg.adapter.findData(str(data.get("recommended_adapter")))
            if idx>=0: dlg.adapter.setCurrentIndex(idx)
        if data.get("recognition_mode"):
            idx=dlg.recognition.findData(str(data.get("recognition_mode")))
            if idx>=0: dlg.recognition.setCurrentIndex(idx)
        if dlg.exec()==QDialog.DialogCode.Accepted and api.can("cameras.manage"):
            w=Worker(lambda: api.post("/cameras", dlg.payload())); w.done.connect(lambda _: self.refresh()); w.failed.connect(lambda e:QMessageBox.critical(self,"Add Camera",e)); self._keep(w); w.start()
    def _show_discover(self, data):
        rows=data.get("cameras") or []
        lines=[
            f"{r.get('ip_address')}  {r.get('kind') or r.get('adapter_id') or 'hvx'}  "
            f"{'reachable' if r.get('reachable') else 'no'}  "
            f"{'added' if r.get('already_added') else 'new'}  {r.get('note') or ''}"
            for r in rows
        ] or ["No cameras listed."]
        ipcams=[r for r in rows if (r.get("adapter_id") or "hvx") != "hvx" and r.get("reachable")]
        QMessageBox.information(self,"Discover","\n".join(lines)[:1800])
        if not ipcams: return
        if QMessageBox.question(self,"IP cameras",f"Add and connect {len(ipcams)} web/RTSP camera(s)? HVX cameras stay on NetSDK.")!=QMessageBox.Yes: return
        user,ok=QInputDialog.getText(self,"IP cameras","Camera username", text="admin")
        if not ok: return
        password,ok=QInputDialog.getText(self,"IP cameras","Camera password", text="admin", echo=QLineEdit.Password)
        if not ok: return
        payload={
            "username": user.strip() or "admin",
            "password": password,
            "connect": True,
            "cameras": [
                {
                    "ip_address": r["ip_address"],
                    "adapter_id": r.get("adapter_id") or "rtsp",
                    "name": r.get("name"),
                    "lane_direction": r.get("lane_direction") or "ENTRY",
                }
                for r in ipcams
            ],
        }
        w=Worker(lambda: api.post("/cameras/import-discovered", payload, timeout=60))
        w.done.connect(lambda body: (
            QMessageBox.information(self,"IP cameras", f"Added {len(body.get('created') or [])}. Connected {sum(1 for x in (body.get('connected') or []) if x.get('status')=='VIDEO_CONNECTED')}. HVX unchanged."),
            self.refresh(),
            self._maybe_start_pair(),
        ))
        w.failed.connect(lambda e: QMessageBox.critical(self,"IP cameras", e))
        self._keep(w); w.start()
    def connect_all(self):
        w=Worker(api.connect_all)
        w.done.connect(self._after_connect_all)
        w.failed.connect(lambda e:QMessageBox.critical(self,"Connect all",e))
        self._keep(w); w.start()
    def _after_connect_all(self, data):
        data=data or {}
        lines=[f"Connected {data.get('connected') or 0} / {data.get('attempted') or 0}"]
        skipped=data.get("skipped") or 0
        if skipped:
            lines.append(f"Skipped {skipped} unreachable camera(s).")
        for item in data.get("results") or []:
            err=item.get("last_error") or (item.get("sdk_result") or {}).get("error")
            if err:
                lines.append(f"{item.get('name') or item.get('id')}: {err}")
        QMessageBox.information(self,"Connect all","\n".join(lines)[:2000])
        self.refresh(); self._maybe_start_pair()
    def add_camera(self):
        d=CameraDialog()
        if d.exec():
            try: api.post("/cameras",d.payload()); self.refresh()
            except Exception as e: QMessageBox.critical(self,"Add camera",str(e))
    def edit_camera(self):
        cam=self.selected_camera()
        if not cam: QMessageBox.information(self,"Edit camera","Select a camera first."); return
        d=CameraDialog(cam)
        if d.exec():
            try: api.patch(f"/cameras/{cam['id']}",d.payload()); self.refresh()
            except Exception as e: QMessageBox.critical(self,"Edit camera",str(e))
    def delete_camera(self):
        cam=self.selected_camera()
        if not cam: QMessageBox.information(self,"Delete camera","Select a camera first."); return
        if QMessageBox.question(self,"Delete camera",f"Delete {cam['name']}?")!=QMessageBox.Yes: return
        try: api.delete(f"/cameras/{cam['id']}"); self.refresh()
        except Exception as e: QMessageBox.critical(self,"Delete camera",str(e))
    def _run(self, fn, title):
        cid=self.selected_id()
        if cid is None: QMessageBox.information(self,title,"Select a camera first."); return
        w=Worker(lambda: fn(cid)); w.done.connect(lambda data:(self._after_connect(data,title),self.refresh())); w.failed.connect(lambda e:QMessageBox.critical(self,title,e)); self._keep(w); w.start()
    def _after_connect(self, data, title):
        QMessageBox.information(self,title,str(data)[:1200])
        self._maybe_start_pair()
        cid=self.selected_id()
        if cid is not None: self._load_streams(cid)
    def sdk_connect(self): self._run(lambda cid: api.post(f"/cameras/{cid}/sdk/connect", timeout=25),"Connect")
    def sdk_disconnect(self): self._run(lambda cid: api.post(f"/cameras/{cid}/sdk/disconnect"),"SDK Disconnect")
    def rtsp_probe(self): self._run(lambda cid: api.post(f"/cameras/{cid}/rtsp/probe"),"RTSP Probe")
    def onvif_discover(self): self._run(lambda cid: api.post(f"/cameras/{cid}/onvif/discover", timeout=20),"ONVIF profiles")
    def fastalpr(self): self._run(lambda cid: api.post(f"/cameras/{cid}/alpr/recognize", timeout=30),"FastALPR")
    def capture_snapshot(self): self._run(lambda cid: api.post(f"/cameras/{cid}/snapshot/capture", timeout=12),"Snapshot")
    def open_this_side(self):
        cam=self.selected_camera()
        if not cam: QMessageBox.information(self,"Open this side","Select 1# Entry, 1# Exit, 2# Entry, or 2# Exit first."); return
        side=cam.get("side") or cam.get("lane_direction") or "this side"
        if QMessageBox.question(self,"Open this side",f"Pulse only {cam.get('name') or side} — not the other side of this lane?")!=QMessageBox.Yes: return
        reason,ok=QInputDialog.getText(self,"Open this side","Reason", text="manual open")
        if ok and reason:
            try: QMessageBox.information(self,"Barrier",str(api.post(f"/cameras/{cam['id']}/barrier/open",{"reason":reason}, timeout=20)))
            except Exception as e: QMessageBox.critical(self,"Barrier",str(e))
    def _keep(self, worker):
        self._workers.append(worker)
        worker.finished.connect(lambda w=worker: self._workers.remove(w) if w in self._workers else None)
    def _live_visible(self):
        return self.isVisible() and self.tabs.currentIndex()==0
    def _fill_lanes(self):
        previous=self.lane.currentText() if self.lane.count() else ""
        self.lane.blockSignals(True)
        self.lane.clear()
        for gid, name in lane_options(self.rows):
            self.lane.addItem(name, gid)
        idx=self.lane.findText(previous) if previous else -1
        if idx>=0:
            self.lane.setCurrentIndex(idx)
        self.lane.blockSignals(False)
    def _lane_changed(self):
        self._start_pair(True)
    def _all_panes(self):
        return [self.pane_a, self.pane_b, *getattr(self, "extra_panes", [])]
    def _stop_panes(self):
        for pane in self._all_panes():
            pane.stop_live()
    def _on_layout(self):
        self._sync_layout()
        self._start_pair(False)
    def _sync_layout(self):
        mode=self.layout_mode.currentIndex() if hasattr(self, "layout_mode") else 1
        self.pane_b.setVisible(mode != 0)
        if mode == 0:
            self.pane_b.stop_live()
        needed=max(0, len(self.rows) - 2) if mode == 2 else 0
        while len(self.extra_panes) < needed:
            pane=CameraLivePane(f"Camera {len(self.extra_panes)+3}")
            self.extra_panes.append(pane)
            index=len(self.extra_panes) + 1
            self.live_grid.addWidget(pane, index // 2, index % 2)
        for i, pane in enumerate(self.extra_panes):
            show=i < needed
            pane.setVisible(show)
            if not show:
                pane.stop_live()
    def _on_tab(self, index):
        if index==0:
            self._start_pair(False)
        else:
            self._stop_panes()
    def _maybe_start_pair(self):
        if self._live_visible():
            self._start_pair(False)
        else:
            self._stop_panes()
    def _start_pair(self, from_lane=False):
        if not self._live_visible():
            self._stop_panes(); return
        self._sync_layout()
        mode=self.layout_mode.currentIndex() if hasattr(self, "layout_mode") else 1
        if mode == 2:
            visible=[self.pane_a, self.pane_b] + [pane for pane in self.extra_panes if pane.isVisible()]
            for pane in visible:
                pane.fill_cameras(self.rows)
            for pane, cam in zip(visible, self.rows):
                pane.set_camera(cam)
            for pane in visible[len(self.rows):]:
                pane.set_camera(None)
            return
        self.pane_a.fill_cameras(self.rows)
        self.pane_b.fill_cameras(self.rows)
        if from_lane:
            left, right=pair_lane_cameras(self.rows, self.lane.currentData())
            self.pane_a.set_camera(left)
            if mode != 0:
                self.pane_b.set_camera(right)
            return
        if self.pane_a.camera_id() is None and self.pane_b.camera_id() is None and self.rows:
            self.pane_a.set_camera(self.rows[0])
            if mode != 0:
                self.pane_b.set_camera(self.rows[1] if len(self.rows)>1 else None)
            return
        self.pane_a.start_live()
        if mode != 0:
            self.pane_b.start_live()
    def _on_select(self):
        cid=self.selected_id()
        if cid is not None:
            self._load_streams(cid)
    def hideEvent(self, event):
        self._stop_panes()
        super().hideEvent(event)
    def showEvent(self, event):
        super().showEvent(event)
        if not self._ready:
            self._ready=True
            self.refresh()
        else:
            self._maybe_start_pair()
    def shutdown(self):
        for pane in self._all_panes():
            pane.shutdown()
    def _load_streams(self, cid):
        s=Worker(lambda: api.get(f"/cameras/{cid}/streams", timeout=8))
        s.done.connect(self._show_streams); self._keep(s); s.start()
    def _show_streams(self, data):
        payload=data if isinstance(data, dict) else {}
        profiles=payload.get("stream_profiles") or {}
        media=payload.get("media") or {}
        lines=[]
        for role in ("MAIN","SUB","LIVE","DETECT","EVIDENCE"):
            row=profiles.get(role) or {}
            if not row: continue
            bits=[role]
            if row.get("codec"): bits.append(str(row.get("codec")).upper())
            if row.get("width") and row.get("height"): bits.append(f"{row.get('width')}x{row.get('height')}")
            if row.get("fps"): bits.append(f"{row.get('fps')} FPS")
            if row.get("gop"): bits.append(f"GOP {row.get('gop')}")
            if row.get("transport"): bits.append(str(row.get("transport")))
            if row.get("source"): bits.append(f"Source {row.get('source')}")
            if row.get("ai_fps"): bits.append(f"AI {row.get('ai_fps')} FPS")
            lines.append(" ".join(str(b) for b in bits))
        age=[]
        if media.get("live_frame_age_ms") is not None: age.append(f"live {int(round(media.get('live_frame_age_ms')))} ms")
        if media.get("ai_frame_age_ms") is not None: age.append(f"AI {int(round(media.get('ai_frame_age_ms')))} ms")
        if media.get("connection_state"): age.append(str(media.get("connection_state")))
        warns=payload.get("warnings") or media.get("warnings") or []
        text="\n".join(lines) or "No stream profiles yet. Probe video or ONVIF after Connect."
        if age: text += "\n" + " · ".join(age)
        if warns: text += "\n" + "; ".join(str(w) for w in warns)
        self.stream_info.setText(text)


class GateDialog(QDialog):
    def __init__(self, gate=None):
        super().__init__(); self.setWindowTitle("Edit Gate" if gate else "Add Gate")
        self.setMinimumWidth(320); self.setMaximumWidth(480)
        form=QFormLayout(self)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.name=QLineEdit(); self.mode=QComboBox(); self.mode.addItems(["COMMISSIONING","SHADOW","PRODUCTION","MAINTENANCE"])
        self.enabled=QComboBox(); self.enabled.addItems(["Yes","No"])
        if gate:
            self.name.setText(gate["name"]); self.mode.setCurrentText(gate["mode"]); self.enabled.setCurrentText("Yes" if gate["enabled"] else "No")
        form.addRow("Name", self.name); form.addRow("Mode", self.mode); form.addRow("Enabled", self.enabled)
        save=QPushButton("Save Gate"); save.clicked.connect(self.accept); form.addRow(save)
    def payload(self):
        return {"name":self.name.text().strip(),"mode":self.mode.currentText(),"enabled":self.enabled.currentText()=="Yes"}


class UserDialog(QDialog):
    def __init__(self, user=None):
        super().__init__(); self.user=user; self.setWindowTitle("Edit User" if user else "Add User")
        self.setMinimumWidth(360); self.setMaximumWidth(520)
        form=QFormLayout(self)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.username=QLineEdit(); self.full_name=QLineEdit()
        self.password=QLineEdit(); self.password.setEchoMode(QLineEdit.Password)
        self.status=QComboBox(); self.status.addItems(["ACTIVE","LOCKED","DISABLED"])
        self.role_boxes=[]
        roles_box=QWidget(); roles_l=QVBoxLayout(roles_box); roles_l.setContentsMargins(0,0,0,0)
        try: roles=api.get("/roles")
        except Exception: roles=[{"name":"Operator"},{"name":"Admin"}]
        selected=set(user["roles"] if user else ["Operator"])
        for role in roles:
            box=QCheckBox(role["name"]); box.setChecked(role["name"] in selected); self.role_boxes.append(box); roles_l.addWidget(box)
        if user:
            self.username.setText(user["username"]); self.username.setReadOnly(True)
            self.full_name.setText(user.get("full_name") or ""); self.status.setCurrentText(user["status"])
            self.password.setPlaceholderText("Leave blank to keep current password")
        for label,w in [("Username",self.username),("Full name",self.full_name),("Password",self.password),("Status",self.status),("Roles",roles_box)]: form.addRow(label,w)
        save=QPushButton("Save User"); save.clicked.connect(self.accept); form.addRow(save)
    def payload(self):
        data={"full_name":self.full_name.text().strip(),"status":self.status.currentText(),"roles":[b.text() for b in self.role_boxes if b.isChecked()]}
        if self.password.text() or not self.user:
            data["password"]=self.password.text()
        if not self.user:
            data["username"]=self.username.text().strip()
        return data


class Gates(QWidget):
    def __init__(self):
        super().__init__(); l=QVBoxLayout(self)
        title=QLabel("Gates"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        note=QLabel("Open barrier is per side: 1# Entry, 1# Exit, 2# Entry, or 2# Exit. It does not pulse both barriers on a numbered lane. GPIO + Board TCP + LED UDP.")
        note.setWordWrap(True); l.addWidget(note)
        self.table=QTableWidget(0,6); self.table.setHorizontalHeaderLabels(["ID","Lane","Mode","Enabled","Sides (camera / controller / display)","Action"])
        configure_table(self.table); l.addWidget(self.table, 1)
        row=QHBoxLayout()
        add=QPushButton("Add Gate"); add.clicked.connect(self.add_gate); add.setVisible(api.can("gates.manage"))
        edit=QPushButton("Edit"); edit.clicked.connect(self.edit_gate); edit.setVisible(api.can("gates.manage"))
        delete=QPushButton("Delete"); delete.clicked.connect(self.delete_gate); delete.setVisible(api.can("gates.manage"))
        led=QPushButton("LED text"); led.clicked.connect(self.write_led); led.setVisible(api.can("gates.open"))
        row.addWidget(add); row.addWidget(edit); row.addWidget(delete); row.addWidget(led); row.addStretch(); l.addLayout(row); self.rows=[]; self.refresh()
    def refresh(self):
        try: rows=api.get("/gates")
        except Exception: rows=[]
        self.rows=rows
        self.table.setRowCount(len(rows))
        for r,g in enumerate(rows):
            cams=g.get("cameras") or []
            summary="; ".join(
                f'{row.get("side") or row.get("lane_direction")}: cam {row.get("ip_address")} / ctrl {row.get("controller_ip") or "—"} / disp {row.get("display_ip") or "—"}'
                for row in cams
            ) or "—"
            for c,v in enumerate([g["id"],g["name"],g["mode"],"Yes" if g["enabled"] else "No", summary]): self.table.setItem(r,c,QTableWidgetItem(str(v)))
            cell=QWidget(); hl=QHBoxLayout(cell); hl.setContentsMargins(0,0,0,0)
            seen=set()
            for cam in cams:
                side=(cam.get("lane_direction") or cam.get("side") or "").upper()
                if side not in {"ENTRY","EXIT"} or side in seen:
                    continue
                seen.add(side)
                b=QPushButton("Open entry" if side=="ENTRY" else "Open exit")
                b.clicked.connect(lambda _,gid=g["id"],s=side: self.open_gate(gid,s))
                hl.addWidget(b)
            self.table.setCellWidget(r,5,cell)
    def selected_gate(self):
        row=self.table.currentRow()
        if row<0 or row>=len(self.rows): return None
        return self.rows[row]
    def add_gate(self):
        d=GateDialog()
        if d.exec():
            try: api.post("/gates",d.payload()); self.refresh()
            except Exception as e: QMessageBox.critical(self,"Gate",str(e))
    def edit_gate(self):
        gate=self.selected_gate()
        if not gate: QMessageBox.information(self,"Edit gate","Select a gate first."); return
        d=GateDialog(gate)
        if d.exec():
            try: api.patch(f"/gates/{gate['id']}",d.payload()); self.refresh()
            except Exception as e: QMessageBox.critical(self,"Edit gate",str(e))
    def delete_gate(self):
        gate=self.selected_gate()
        if not gate: QMessageBox.information(self,"Delete gate","Select a gate first."); return
        if QMessageBox.question(self,"Delete gate",f"Delete {gate['name']}?")!=QMessageBox.Yes: return
        try: api.delete(f"/gates/{gate['id']}"); self.refresh()
        except Exception as e: QMessageBox.critical(self,"Delete gate",str(e))
    def open_gate(self,gid,side):
        label="entry" if side=="ENTRY" else "exit"
        if QMessageBox.question(self,"Open this side",f"Pulse only this lane's {label} barrier (not the other side)?")!=QMessageBox.Yes: return
        reason,ok=QInputDialog.getText(self,"Open this side","Reason", text="manual open")
        if ok and reason:
            try: QMessageBox.information(self,"Barrier",str(api.post(f"/gates/{gid}/open",{"reason":reason,"side":side}, timeout=20)))
            except Exception as e: QMessageBox.critical(self,"Barrier",str(e))
    def write_led(self):
        gate=self.selected_gate()
        if not gate: QMessageBox.information(self,"LED","Select a lane first."); return
        cams=gate.get("cameras") or []
        if not cams: QMessageBox.information(self,"LED","No cameras on this lane."); return
        text,ok=QInputDialog.getText(self,"LED text","Message", text="WELCOME")
        if not ok or not text: return
        try:
            first=cams[0]
            QMessageBox.information(self,"LED",str(api.post(f"/cameras/{first['id']}/led",{"text":text})))
        except Exception as e: QMessageBox.critical(self,"LED",str(e))


class Users(QWidget):
    def __init__(self):
        super().__init__(); l=QVBoxLayout(self)
        title=QLabel("Users"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        self.table=QTableWidget(0,5); self.table.setHorizontalHeaderLabels(["ID","Username","Name","Status","Roles"])
        configure_table(self.table); l.addWidget(self.table, 1)
        row=QHBoxLayout()
        add=QPushButton("Add User"); add.clicked.connect(self.add_user); add.setVisible(api.can("users.manage"))
        edit=QPushButton("Edit"); edit.clicked.connect(self.edit_user); edit.setVisible(api.can("users.manage"))
        delete=QPushButton("Delete"); delete.clicked.connect(self.delete_user); delete.setVisible(api.can("users.manage"))
        refresh=QPushButton("Refresh"); refresh.clicked.connect(self.refresh)
        row.addWidget(add); row.addWidget(edit); row.addWidget(delete); row.addWidget(refresh); row.addStretch(); l.addLayout(row); self.rows=[]; self.refresh()
    def refresh(self):
        try: rows=api.get("/users")
        except Exception as e: QMessageBox.warning(self,"Users",str(e)); return
        self.rows=rows
        self.table.setRowCount(len(rows))
        for r,u in enumerate(rows):
            for c,v in enumerate([u["id"],u["username"],u.get("full_name") or "—",u["status"],", ".join(u["roles"])]):
                self.table.setItem(r,c,QTableWidgetItem(str(v)))
    def selected_user(self):
        row=self.table.currentRow()
        if row<0 or row>=len(self.rows): return None
        return self.rows[row]
    def add_user(self):
        d=UserDialog()
        if d.exec():
            try: api.post("/users",d.payload()); self.refresh()
            except Exception as e: QMessageBox.critical(self,"Add user",str(e))
    def edit_user(self):
        user=self.selected_user()
        if not user: QMessageBox.information(self,"Edit user","Select a user first."); return
        d=UserDialog(user)
        if d.exec():
            try: api.patch(f"/users/{user['id']}",d.payload()); self.refresh()
            except Exception as e: QMessageBox.critical(self,"Edit user",str(e))
    def delete_user(self):
        user=self.selected_user()
        if not user: QMessageBox.information(self,"Delete user","Select a user first."); return
        if QMessageBox.question(self,"Delete user",f"Delete {user['username']}?")!=QMessageBox.Yes: return
        try: api.delete(f"/users/{user['id']}"); self.refresh()
        except Exception as e: QMessageBox.critical(self,"Delete user",str(e))


def _iso_date(text: str, end: bool = False) -> str | None:
    raw=(text or "")[:10]
    if len(raw) < 10 or raw[4] != "-":
        return None
    return f"{raw}T{'23:59:59' if end else '00:00:00'}Z"


class VehicleDialog(QDialog):
    def __init__(self, vehicle=None, plans=None):
        super().__init__(); self.setWindowTitle("Edit vehicle" if vehicle else "Register plate")
        form=QFormLayout(self)
        self.plate=QLineEdit(); self.owner=QLineEdit(); self.plan=QComboBox(); self.enabled=QComboBox(); self.enabled.addItems(["Yes","No"]); self.notes=QLineEdit()
        self.use_from=QCheckBox("Starts on")
        self.valid_from=QDateEdit(QDate.currentDate()); self.valid_from.setCalendarPopup(True); self.valid_from.setDisplayFormat("yyyy-MM-dd")
        self.use_until=QCheckBox("Ends on")
        self.valid_until=QDateEdit(QDate.currentDate()); self.valid_until.setCalendarPopup(True); self.valid_until.setDisplayFormat("yyyy-MM-dd")
        for p in plans or []: self.plan.addItem(p["name"], p["id"])
        if vehicle:
            self.plate.setText(vehicle.get("plate") or ""); self.owner.setText(vehicle.get("owner_name") or "")
            idx=self.plan.findData(vehicle.get("plan_id"));
            if idx>=0: self.plan.setCurrentIndex(idx)
            self.enabled.setCurrentText("Yes" if vehicle.get("enabled") else "No")
            self.notes.setText(vehicle.get("notes") or "")
            start=_iso_date(str(vehicle.get("valid_from") or ""))
            finish=_iso_date(str(vehicle.get("valid_until") or ""), end=True)
            if start:
                self.use_from.setChecked(True)
                self.valid_from.setDate(QDate.fromString(start[:10], "yyyy-MM-dd"))
            if finish:
                self.use_until.setChecked(True)
                self.valid_until.setDate(QDate.fromString(finish[:10], "yyyy-MM-dd"))
        form.addRow("Plate", self.plate); form.addRow("Owner", self.owner); form.addRow("Plan", self.plan)
        form.addRow("Enabled", self.enabled); form.addRow("Notes", self.notes)
        from_row=QHBoxLayout(); from_row.addWidget(self.use_from); from_row.addWidget(self.valid_from)
        start_today=QPushButton("Start today"); start_today.clicked.connect(lambda: (self.use_from.setChecked(True), self.valid_from.setDate(QDate.currentDate())))
        from_row.addWidget(start_today)
        until_row=QHBoxLayout(); until_row.addWidget(self.use_until); until_row.addWidget(self.valid_until)
        end_today=QPushButton("End today"); end_today.clicked.connect(lambda: (self.use_until.setChecked(True), self.valid_until.setDate(QDate.currentDate())))
        until_row.addWidget(end_today)
        form.addRow("Season start", from_row); form.addRow("Season end", until_row)
        save=QPushButton("Save"); save.clicked.connect(self.accept); form.addRow(save)
    def payload(self):
        return {
            "plate": self.plate.text().strip(), "owner_name": self.owner.text().strip(),
            "plan_id": self.plan.currentData(), "enabled": self.enabled.currentText()=="Yes",
            "notes": self.notes.text().strip(),
            "valid_from": _iso_date(self.valid_from.date().toString("yyyy-MM-dd")) if self.use_from.isChecked() else None,
            "valid_until": _iso_date(self.valid_until.date().toString("yyyy-MM-dd"), end=True) if self.use_until.isChecked() else None,
        }


class Sessions(QWidget):
    def __init__(self):
        super().__init__(); l=QVBoxLayout(self)
        title=QLabel("Parking sessions"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        note=QLabel("Find a visit by scanning the receipt QR or typing the plate. Compare the photo and the time inside before taking money. Payment stays off when nothing is owed.")
        note.setWordWrap(True); l.addWidget(note)
        find=QHBoxLayout()
        self.query=QLineEdit(); self.query.setPlaceholderText("Scan QR, paste the receipt link, or type the plate")
        self.query.returnPressed.connect(self.lookup)
        find_btn=QPushButton("Find visit"); find_btn.clicked.connect(self.lookup)
        find.addWidget(self.query, 1); find.addWidget(find_btn); l.addLayout(find)
        card=QFrame(); card.setObjectName("card"); card_l=QHBoxLayout(card)
        photos=QVBoxLayout()
        self.photo=QLabel("No entry photo stored."); self.photo.setMinimumSize(240, 140); self.photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.crop=QLabel(""); self.crop.setMinimumHeight(80); self.crop.setAlignment(Qt.AlignmentFlag.AlignCenter)
        photos.addWidget(self.photo); photos.addWidget(self.crop)
        detail=QVBoxLayout()
        self.kiosk_plate=QLabel("—"); self.kiosk_plate.setStyleSheet("font-size:28px;font-weight:700;letter-spacing:2px")
        self.kiosk_stay=QLabel("Scan a receipt or pick a session.")
        self.kiosk_stay.setWordWrap(True)
        self.kiosk_due=QLabel(""); self.kiosk_due.setStyleSheet("font-size:18px;font-weight:700")
        self.kiosk_note=QLabel(""); self.kiosk_note.setWordWrap(True)
        self.correct=QLineEdit(); self.correct.setPlaceholderText("Correct plate")
        actions=QHBoxLayout()
        save_plate=QPushButton("Save corrected plate"); save_plate.clicked.connect(self.correct_plate)
        self.pay_btn=QPushButton("Record payment"); self.pay_btn.clicked.connect(self.pay_visit); self.pay_btn.setEnabled(False)
        self.mobile_btn=QPushButton("Pay with mobile on this computer"); self.mobile_btn.clicked.connect(self.pay_mobile); self.mobile_btn.setEnabled(False)
        can_pay=api.can("payments.create") or api.can("kiosk.use")
        self.pay_btn.setVisible(can_pay)
        self.mobile_btn.setVisible(can_pay)
        actions.addWidget(save_plate); actions.addWidget(self.pay_btn); actions.addWidget(self.mobile_btn); actions.addStretch()
        detail.addWidget(self.kiosk_plate); detail.addWidget(self.kiosk_stay); detail.addWidget(self.kiosk_due); detail.addWidget(self.kiosk_note)
        detail.addWidget(self.correct); detail.addLayout(actions)
        card_l.addLayout(photos, 1); card_l.addLayout(detail, 2)
        l.addWidget(card)
        self.table=QTableWidget(0,8); self.table.setHorizontalHeaderLabels(["Plate","Kind","Status","Receipt","Entry","Due","Paid","Gate"])
        configure_table(self.table); l.addWidget(self.table, 1)
        self.table.itemSelectionChanged.connect(self._on_row)
        row=QHBoxLayout()
        pay=QPushButton("Record kiosk payment"); pay.clicked.connect(self.pay); pay.setVisible(can_pay)
        receipt=QPushButton("Show / print receipt"); receipt.clicked.connect(self.print_receipt)
        refresh=QPushButton("Refresh"); refresh.clicked.connect(self.refresh)
        row.addWidget(pay); row.addWidget(receipt); row.addWidget(refresh); row.addStretch(); l.addLayout(row)
        self.rows=[]; self.visit=None; self.refresh()
    def _pixmap(self, label, path, empty):
        if not path:
            label.setPixmap(QPixmap()); label.setText(empty); return
        try:
            data=api.get_bytes(path, timeout=12)
            pix=QPixmap(); pix.loadFromData(data)
            if pix.isNull():
                label.setText(empty); return
            label.setText("")
            label.setPixmap(pix.scaled(320, 180, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        except Exception:
            label.setPixmap(QPixmap()); label.setText(empty)
    def _show_visit(self, data):
        self.visit=data or None
        if not data:
            self.kiosk_plate.setText("—")
            self.kiosk_stay.setText("No visit matches that QR code or plate.")
            self.kiosk_due.setText("")
            self.kiosk_note.setText("")
            self.pay_btn.setEnabled(False)
            self.mobile_btn.setEnabled(False)
            self._pixmap(self.photo, None, "No entry photo stored.")
            self._pixmap(self.crop, None, "")
            return
        self.kiosk_plate.setText(data.get("plate") or "—")
        inside="Still inside." if data.get("still_inside") else "Has left."
        entered=(data.get("entry_time") or "").replace("T", " ")[:16]
        self.kiosk_stay.setText(f"Time on site: {data.get('duration_label') or '—'} ({inside}) Entered {entered}.")
        remaining=int(float(data.get("amount_remaining") or 0))
        currency=data.get("currency") or "TZS"
        if data.get("payable"):
            self.kiosk_due.setText(f"To pay: {currency} {remaining:,}")
        else:
            self.kiosk_due.setText(data.get("pay_blocked_reason") or "Nothing to pay.")
        self.kiosk_note.setText(data.get("image_note") or "")
        self.correct.setText("" if data.get("image_matches_plate") is False else (data.get("plate") or ""))
        payable=bool(data.get("payable"))
        self.pay_btn.setEnabled(payable)
        self.mobile_btn.setEnabled(payable and bool(data.get("token")))
        self._pixmap(self.photo, data.get("snapshot_url"), "No entry photo stored.")
        self._pixmap(self.crop, data.get("crop_url"), "")
    def lookup(self):
        from urllib.parse import quote
        q=self.query.text().strip()
        if not q:
            QMessageBox.information(self, "Find visit", "Scan a QR code or type a plate."); return
        try:
            data=api.get(f"/sessions/lookup?q={quote(q, safe='')}", timeout=15)
        except Exception as exc:
            self._show_visit(None)
            self.kiosk_stay.setText(str(exc))
            return
        self._show_visit(data)
    def _on_row(self):
        if getattr(self, "_filling", False):
            return
        row=self.selected()
        if not row:
            return
        text=row.get("public_token") or row.get("plate") or ""
        if not text:
            return
        self.query.setText(text)
        self.lookup()
    def refresh(self):
        try: self.rows=api.get("/sessions")
        except Exception as e: QMessageBox.warning(self,"Sessions",str(e)); return
        self._filling=True
        self.table.setRowCount(len(self.rows))
        for r,s in enumerate(self.rows):
            vals=[
                s.get("plate") or "",
                s.get("parker_kind") or "CASUAL",
                s.get("status") or "",
                s.get("receipt_status") or "—",
                (s.get("entry_time") or "")[:19].replace("T"," "),
                f"{int(float(s.get('amount_due') or 0)):,}",
                f"{int(float(s.get('amount_paid') or 0)):,}",
                s.get("gate_id") or "—",
            ]
            for c,val in enumerate(vals): self.table.setItem(r,c,QTableWidgetItem(str(val)))
        self._filling=False
    def selected(self):
        row=self.table.currentRow()
        if row<0 or row>=len(self.rows): return None
        return self.rows[row]
    def print_receipt(self):
        s=self.selected()
        if not s: QMessageBox.information(self,"Receipt","Select a session first."); return
        try:
            issued=api.post(f"/sessions/{s['id']}/receipt", {}, timeout=15)
        except Exception as e:
            QMessageBox.critical(self,"Receipt",str(e)); return
        body=(issued or {}).get("receipt") or ""
        printed=(issued or {}).get("print") or {}
        record=(issued or {}).get("receipt_record") or {}
        path=printed.get("path") or (record.get("payload") or {}).get("path") or ""
        qr_url=(issued or {}).get("qr_url") or ""
        if not qr_url and (issued or {}).get("public_token"):
            qr_url=f"/p/{issued['public_token']}/qr.png"
        if not body:
            try:
                slip=api.get(f"/sessions/{s['id']}/receipt")
                body=slip.get("body_text") or ""
                path=(slip.get("payload") or {}).get("path") or path
            except Exception:
                pass
        show_printable_receipt(self, body, path, qr_url=qr_url)
        self.refresh()
    def correct_plate(self):
        visit=self.visit or {}
        session_id=visit.get("session_id")
        plate=self.correct.text().strip()
        if not session_id or not plate:
            QMessageBox.information(self, "Correct plate", "Find the visit and type the plate you can see."); return
        try:
            api.post(f"/sessions/{session_id}/correct-plate", {"plate": plate})
        except Exception as exc:
            QMessageBox.critical(self, "Correct plate", str(exc)); return
        self.query.setText(plate)
        self.lookup()
        self.refresh()
    def _settle(self, method):
        visit=self.visit or {}
        if not visit.get("payable"):
            QMessageBox.information(self, "Payment", visit.get("pay_blocked_reason") or "This vehicle does not have a fee to pay.")
            return
        token=visit.get("token")
        session_id=visit.get("session_id")
        plate=visit.get("plate") or ""
        if QMessageBox.question(self, "Record payment", f"Take payment for {plate}?") != QMessageBox.Yes:
            return
        try:
            if method == "KIOSK_CASH" and token:
                result=api.post(f"/p/{token}/kiosk-pay", {"method": "KIOSK_CASH"})
            elif method == "KIOSK_CASH" and session_id:
                result=api.post(f"/sessions/{session_id}/pay", {"method": "KIOSK_CASH"})
            elif token:
                result=api.post(f"/p/{token}/pay", {"method": "MOBILE_SIMULATED"})
            else:
                raise RuntimeError("This visit has no receipt code for phone payment.")
        except Exception as exc:
            QMessageBox.critical(self, "Payment", str(exc)); return
        if result.get("already_paid"):
            QMessageBox.information(self, "Payment", "Already settled.")
        else:
            QMessageBox.information(self, "Payment", "Payment recorded.")
        if "payable" in (result or {}):
            self._show_visit(result)
        self.refresh()
    def pay_visit(self):
        self._settle("KIOSK_CASH")
    def pay_mobile(self):
        self._settle("MOBILE_SIMULATED")
    def pay(self):
        s=self.selected()
        if s:
            self.query.setText(s.get("public_token") or s.get("plate") or "")
            self.lookup()
        if not (self.visit or {}).get("session_id") and s:
            self.visit={"session_id": s.get("id"), "plate": s.get("plate"), "token": s.get("public_token"), "payable": float(s.get("amount_due") or 0) > float(s.get("amount_paid") or 0)}
        self.pay_visit()


class Payments(QWidget):
    def __init__(self):
        super().__init__(); l=QVBoxLayout(self)
        title=QLabel("Payments"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        note=QLabel("Kiosk and mobile payments share one ledger. A phone success screen is not paid until a verified transaction exists.")
        note.setWordWrap(True); l.addWidget(note)
        self.table=QTableWidget(0,6); self.table.setHorizontalHeaderLabels(["When","Session","Method","Amount","Status","Provider"])
        configure_table(self.table); l.addWidget(self.table, 1)
        refresh=QPushButton("Refresh"); refresh.clicked.connect(self.refresh)
        row=QHBoxLayout(); row.addWidget(refresh); row.addStretch(); l.addLayout(row)
        self.refresh()
    def refresh(self):
        try: rows=api.get("/payments")
        except Exception as e: QMessageBox.warning(self,"Payments",str(e)); return
        self.table.setRowCount(len(rows))
        for r,p in enumerate(rows):
            vals=[
                (p.get("confirmed_at") or p.get("created_at") or "")[:19].replace("T"," "),
                p.get("session_id") or "—",
                p.get("method") or "",
                f"TZS {int(float(p.get('amount') or 0)):,}",
                p.get("status") or "",
                p.get("provider_id") or "",
            ]
            for c,val in enumerate(vals): self.table.setItem(r,c,QTableWidgetItem(str(val)))


class Vehicles(QWidget):
    def __init__(self):
        super().__init__(); l=QVBoxLayout(self)
        title=QLabel("Registered plates"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        note=QLabel("Season, VIP, staff, and tenant plates open the gate automatically when the camera reads them. Set a start and end date, or use today.")
        note.setWordWrap(True); l.addWidget(note)
        self.table=QTableWidget(0,7); self.table.setHorizontalHeaderLabels(["Plate","Owner","Plan","Auto-open","Enabled","From","Until"])
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        configure_table(self.table); l.addWidget(self.table, 1)
        bulk_note=QLabel("Register many, one plate per line: plate, owner, start date, end date")
        l.addWidget(bulk_note)
        self.bulk=QPlainTextEdit(); self.bulk.setPlaceholderText("T111AAA, Jane, 2026-09-01, 2026-10-01"); self.bulk.setMaximumHeight(90)
        l.addWidget(self.bulk)
        row=QHBoxLayout()
        manage=api.can("subscribers.manage")
        add=QPushButton("Register plate"); add.clicked.connect(self.add); add.setVisible(manage)
        bulk=QPushButton("Register these plates"); bulk.clicked.connect(self.add_bulk); bulk.setVisible(manage)
        edit=QPushButton("Edit"); edit.clicked.connect(self.edit); edit.setVisible(manage)
        delete=QPushButton("Delete"); delete.clicked.connect(self.delete); delete.setVisible(manage)
        delete_many=QPushButton("Delete selected"); delete_many.clicked.connect(self.delete_selected); delete_many.setVisible(manage)
        refresh=QPushButton("Refresh"); refresh.clicked.connect(self.refresh)
        row.addWidget(add); row.addWidget(bulk); row.addWidget(edit); row.addWidget(delete); row.addWidget(delete_many); row.addWidget(refresh); row.addStretch(); l.addLayout(row)
        self.rows=[]; self.refresh()
    def refresh(self):
        try: self.rows=api.get("/vehicles")
        except Exception as e: QMessageBox.warning(self,"Vehicles",str(e)); return
        self.table.setRowCount(len(self.rows))
        for r,v in enumerate(self.rows):
            vals=[
                v["plate"], v.get("owner_name") or "—", v.get("plan_name") or "—",
                "Yes" if v.get("auto_open") else "No", "Yes" if v.get("enabled") else "No",
                (v.get("valid_from") or "—")[:10], (v.get("valid_until") or "—")[:10],
            ]
            for c,val in enumerate(vals): self.table.setItem(r,c,QTableWidgetItem(str(val)))
    def selected(self):
        row=self.table.currentRow()
        if row<0 or row>=len(self.rows): return None
        return self.rows[row]
    def selected_ids(self):
        ids=[]
        for index in self.table.selectionModel().selectedRows():
            row=index.row()
            if 0<=row<len(self.rows):
                ids.append(self.rows[row]["id"])
        return ids
    def add(self):
        d=VehicleDialog(plans=api.get("/access-plans"))
        if d.exec():
            try: api.post("/vehicles", d.payload()); self.refresh()
            except Exception as e: QMessageBox.critical(self,"Register plate",str(e))
    def add_bulk(self):
        lines=[line.strip() for line in self.bulk.toPlainText().splitlines() if line.strip()]
        if not lines:
            QMessageBox.information(self, "Register plates", "Add one plate per line."); return
        vehicles=[]
        for line in lines:
            parts=[part.strip() for part in line.split(",")]
            plate=parts[0] if parts else ""
            owner=parts[1] if len(parts)>1 else ""
            start=parts[2] if len(parts)>2 else ""
            finish=parts[3] if len(parts)>3 else ""
            vehicles.append({
                "plate": plate,
                "owner_name": owner,
                "valid_from": _iso_date(start) if start else None,
                "valid_until": _iso_date(finish, end=True) if finish else None,
            })
        try:
            result=api.post("/vehicles/bulk", {"vehicles": vehicles})
        except Exception as exc:
            QMessageBox.critical(self, "Register plates", str(exc)); return
        failed="; ".join(item.get("error") or "" for item in (result.get("errors") or []) if item.get("error"))
        created=len(result.get("created") or [])
        self.bulk.clear()
        self.refresh()
        QMessageBox.information(self, "Register plates", f"Registered {created} plates. {failed}".strip())
    def edit(self):
        v=self.selected()
        if not v: QMessageBox.information(self,"Edit","Select a plate first."); return
        d=VehicleDialog(v, plans=api.get("/access-plans"))
        if d.exec():
            try: api.patch(f"/vehicles/{v['id']}", d.payload()); self.refresh()
            except Exception as e: QMessageBox.critical(self,"Edit",str(e))
    def delete(self):
        v=self.selected()
        if not v: return
        if QMessageBox.question(self,"Delete",f"Remove {v['plate']}?")!=QMessageBox.Yes: return
        try: api.delete(f"/vehicles/{v['id']}"); self.refresh()
        except Exception as e: QMessageBox.critical(self,"Delete",str(e))
    def delete_selected(self):
        ids=self.selected_ids()
        if not ids:
            QMessageBox.information(self, "Delete", "Select at least one plate."); return
        if QMessageBox.question(self, "Delete", f"Remove {len(ids)} registered plate(s)?")!=QMessageBox.Yes: return
        try: api.post("/vehicles/bulk-delete", {"ids": ids}); self.refresh()
        except Exception as e: QMessageBox.critical(self,"Delete",str(e))


class Fees(QWidget):
    def __init__(self):
        super().__init__(); l=QVBoxLayout(self)
        title=QLabel("Tariffs"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        note=QLabel("Day and night rates for this site. Times and amounts are normal fields — save them here.")
        note.setWordWrap(True); l.addWidget(note)
        form=QFormLayout()
        self.currency=QLineEdit("TZS")
        self.day_start=QTimeEdit(); self.day_start.setDisplayFormat("HH:mm")
        self.day_end=QTimeEdit(); self.day_end.setDisplayFormat("HH:mm")
        self.free_day=QSpinBox(); self.free_night=QSpinBox()
        self.day_block=QSpinBox(); self.night_block=QSpinBox()
        self.day_fee=QSpinBox(); self.night_fee=QSpinBox()
        self.day_max=QSpinBox(); self.night_max=QSpinBox(); self.daily=QSpinBox()
        for box in (self.free_day, self.free_night, self.day_fee, self.night_fee, self.day_max, self.night_max, self.daily):
            box.setRange(0, 10000000)
        for box in (self.day_block, self.night_block):
            box.setRange(1, 10080)
        form.addRow("Currency", self.currency)
        form.addRow("Day starts", self.day_start); form.addRow("Day ends", self.day_end)
        form.addRow("Free daytime (minutes)", self.free_day); form.addRow("Free night (minutes)", self.free_night)
        form.addRow("Day block (minutes)", self.day_block); form.addRow("Night block (minutes)", self.night_block)
        form.addRow("Fee per day block", self.day_fee); form.addRow("Fee per night block", self.night_fee)
        form.addRow("Day maximum", self.day_max); form.addRow("Night maximum", self.night_max)
        form.addRow("Fee per full day", self.daily)
        l.addLayout(form)
        actions=QHBoxLayout()
        save=QPushButton("Save tariff"); save.clicked.connect(self.save)
        save.setVisible(api.can("fees.manage") or api.can("settings.manage"))
        reload_btn=QPushButton("Reload"); reload_btn.clicked.connect(self.load_tariff)
        actions.addWidget(save); actions.addWidget(reload_btn); actions.addStretch(); l.addLayout(actions)
        quote_form=QFormLayout()
        self.entry=QLineEdit(); self.exit=QLineEdit()
        from datetime import datetime, timezone, timedelta
        now=datetime.now(timezone.utc)
        self.entry.setText((now-timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S"))
        self.exit.setText(now.strftime("%Y-%m-%dT%H:%M:%S"))
        quote_form.addRow("Entry (UTC)", self.entry); quote_form.addRow("Exit (UTC)", self.exit)
        l.addLayout(quote_form)
        quote=QPushButton("Quote Car1 fee"); quote.clicked.connect(self.quote); l.addWidget(quote)
        self.out=QLabel(""); self.out.setWordWrap(True); l.addWidget(self.out)
        l.addStretch()
        self.load_tariff()
    def _set_time(self, edit, value):
        parsed=QTime.fromString(str(value or "")[:5], "HH:mm")
        if parsed.isValid():
            edit.setTime(parsed)
    def load_tariff(self):
        try: data=api.get("/fees/tariff")
        except Exception as e: self.out.setText(str(e)); return
        editor=(data or {}).get("editor") or {}
        self.currency.setText(editor.get("currency") or data.get("currency") or "TZS")
        self._set_time(self.day_start, editor.get("day_start"))
        self._set_time(self.day_end, editor.get("day_end"))
        self.free_day.setValue(int(float(editor.get("free_day_minutes") or 0)))
        self.free_night.setValue(int(float(editor.get("free_night_minutes") or 0)))
        self.day_block.setValue(max(1, int(float(editor.get("day_block_minutes") or 1))))
        self.night_block.setValue(max(1, int(float(editor.get("night_block_minutes") or 1))))
        self.day_fee.setValue(int(editor.get("day_block_fee") or 0))
        self.night_fee.setValue(int(editor.get("night_block_fee") or 0))
        self.day_max.setValue(int(editor.get("day_max") or 0))
        self.night_max.setValue(int(editor.get("night_max") or 0))
        self.daily.setValue(int(editor.get("daily_wrap_fee") or 0))
        name=data.get("name") or "Tariff"
        self.out.setText(f"{name} · {self.currency.text()}. Day rate {self.day_fee.value()} per {self.day_block.value()} min.")
    def save(self):
        payload={
            "currency": self.currency.text().strip(),
            "day_start": self.day_start.time().toString("HH:mm"),
            "day_end": self.day_end.time().toString("HH:mm"),
            "free_day_minutes": self.free_day.value(),
            "free_night_minutes": self.free_night.value(),
            "day_block_minutes": self.day_block.value(),
            "night_block_minutes": self.night_block.value(),
            "day_block_fee": self.day_fee.value(),
            "night_block_fee": self.night_fee.value(),
            "day_max": self.day_max.value(),
            "night_max": self.night_max.value(),
            "daily_wrap_fee": self.daily.value(),
        }
        try:
            api.patch("/fees/tariff", payload)
        except Exception as exc:
            QMessageBox.critical(self, "Tariff", str(exc)); return
        self.load_tariff()
        QMessageBox.information(self, "Tariff", "Tariff saved.")
    def quote(self):
        try:
            data=api.post("/fees/quote",{"entry_time":self.entry.text().strip(),"exit_time":self.exit.text().strip(),"car_type":"Car1"})
        except Exception as e:
            QMessageBox.critical(self,"Fee",str(e)); return
        minutes=max(0, int(int(data.get("duration_seconds") or 0) / 60))
        due=int(data.get("due") or 0)
        currency=data.get("currency") or self.currency.text() or "TZS"
        self.out.setText(f"{currency} {due:,} for {minutes} min.")


class SystemHealth(QWidget):
    def __init__(self):
        super().__init__()
        l=QVBoxLayout(self)
        title=QLabel("System Health"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        note=QLabel("Parking stays up when one camera or the HVX host is degraded. The summary is in plain language.")
        note.setWordWrap(True); l.addWidget(note)
        self.state=QLabel("…"); self.state.setStyleSheet("font-size:18px;font-weight:700"); l.addWidget(self.state)
        self.summary=QLabel("…"); self.summary.setWordWrap(True); l.addWidget(self.summary)
        self.info=QPlainTextEdit(); self.info.setReadOnly(True); self.info.setVisible(False); l.addWidget(self.info, 1)
        row=QHBoxLayout(); refresh=QPushButton("Refresh"); refresh.clicked.connect(self.refresh)
        self.details_btn=QPushButton("Show technical details"); self.details_btn.clicked.connect(self._toggle_details)
        row.addWidget(refresh); row.addWidget(self.details_btn); row.addStretch(); l.addLayout(row)
        self._timer=QTimer(self); self._timer.setInterval(4000); self._timer.timeout.connect(self.refresh)
    def showEvent(self, event):
        super().showEvent(event)
        if not self._timer.isActive():
            self._timer.start()
        self.refresh()
    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)
    def shutdown(self):
        self._timer.stop()
    def refresh(self):
        try:
            live=api.get("/health/live")
        except Exception as e:
            self.state.setText("OFFLINE")
            self.info.setPlainText(str(e))
            return
        state=(live.get("state") or live.get("process", {}).get("state") or "UNKNOWN")
        try:
            data=api.get("/health/details")
        except Exception:
            try:
                data=api.get("/health/ready")
            except Exception as e:
                data={"error": str(e), "live": live}
        self.state.setText(str(data.get("state") or state))
        self.summary.setText(health_sentences(data, live))
        self.info.setPlainText(json.dumps(data, indent=2, default=str))
    def _toggle_details(self):
        show=not self.info.isVisible()
        self.info.setVisible(show)
        self.details_btn.setText("Hide technical details" if show else "Show technical details")


class Hardware(QWidget):
    def __init__(self):
        super().__init__(); l=QVBoxLayout(self)
        title=QLabel("Hardware Lab"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        warn=QLabel("Advanced integration diagnostics. The HVX vendor SDK requires a 32-bit Windows host process."); warn.setWordWrap(True); l.addWidget(warn)
        self.info=QPlainTextEdit(); self.info.setReadOnly(True); self.info.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.info.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        l.addWidget(self.info, 1)
        row=QHBoxLayout()
        b=QPushButton("Check HVX SDK Host"); b.clicked.connect(self.check)
        a=QPushButton("Check FastALPR"); a.clicked.connect(self.check_alpr)
        m=QPushButton("Check media gateway"); m.clicked.connect(self.check_media)
        d=QPushButton("Check decode path"); d.clicked.connect(self.check_decode)
        row.addWidget(b); row.addWidget(a); row.addWidget(m); row.addWidget(d); row.addStretch(); l.addLayout(row)
    def check_alpr(self):
        try:
            data=api.get("/alpr/status")
            self.info.setPlainText(json.dumps(data, indent=2, default=str))
        except Exception as e:
            self.info.setPlainText(str(e))
    def check_media(self):
        try:
            data=api.get("/media/gateway")
            self.info.setPlainText(json.dumps(data, indent=2, default=str))
        except Exception as e:
            self.info.setPlainText(str(e))
    def check_decode(self):
        try:
            data=api.get("/hardware/decode")
            self.info.setPlainText(json.dumps(data, indent=2, default=str))
        except Exception as e:
            self.info.setPlainText(str(e))
    def check(self):
        try:
            data=api.get("/hardware/hvx/info")
            self.info.setPlainText(json.dumps(data, indent=2, default=str))
        except Exception as e:
            self.info.setPlainText(str(e))
    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_ready", False):
            self._ready=True
            self.check()


class SimPage(QWidget):
    def __init__(self):
        super().__init__(); l=QVBoxLayout(self)
        title=QLabel("Simulation"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        note=QLabel("Does not need cameras. Choose a car photo, Upload as ENTRY — FastALPR on this PC reads the plate, then Receipt taken / Mark paid / Upload as EXIT.")
        note.setWordWrap(True); l.addWidget(note)
        form=QFormLayout()
        self.gate=QComboBox()
        self.plate=QLineEdit(); self.plate.setPlaceholderText("T453ETH")
        self.file_label=QLabel("No photo selected")
        pick=QPushButton("Choose car photo…"); pick.clicked.connect(self.pick_file)
        form.addRow("Lane", self.gate); form.addRow("Plate", self.plate); form.addRow("Photo", pick); form.addRow("", self.file_label)
        l.addLayout(form)
        self.preview=QLabel("Car photo"); self.preview.setObjectName("video"); self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter); self.preview.setMinimumHeight(140)
        l.addWidget(self.preview)
        row=QHBoxLayout()
        typed=QPushButton("Enter plate as ENTRY"); typed.clicked.connect(self.do_plate_entry)
        entry=QPushButton("Upload as ENTRY"); entry.clicked.connect(lambda: self.do_upload("ENTRY"))
        taken=QPushButton("Receipt taken (open barrier)"); taken.clicked.connect(self.do_taken)
        pay=QPushButton("Mark paid"); pay.clicked.connect(self.do_pay)
        exitb=QPushButton("Upload as EXIT"); exitb.clicked.connect(lambda: self.do_upload("EXIT"))
        for w in (typed, entry, taken, pay, exitb): row.addWidget(w)
        row.addStretch(); l.addLayout(row)
        self.out=QPlainTextEdit(); self.out.setReadOnly(True); l.addWidget(self.out, 1)
        self._sid=None; self._path=""; self._workers=[]
    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_ready", False):
            self._ready=True
            self.reload()
    def _keep(self, worker):
        self._workers.append(worker)
        worker.finished.connect(lambda w=worker: self._workers.remove(w) if w in self._workers else None)
    def reload(self):
        self.gate.clear()
        try:
            for g in api.get("/lanes"):
                self.gate.addItem(g["name"], g["id"])
        except Exception as e:
            self.out.setPlainText(str(e))
    def pick_file(self):
        path,_=QFileDialog.getOpenFileName(self,"Car photo","","Images (*.jpg *.jpeg *.png)")
        if not path: return
        self._path=path
        self.file_label.setText(path)
        image=QImage(path)
        if not image.isNull():
            self.preview.setPixmap(QPixmap.fromImage(image).scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
    def do_plate_entry(self):
        plate=self.plate.text().strip()
        if not plate:
            QMessageBox.information(self,"Simulation","Type a number plate first."); return
        if self.gate.currentData() is None:
            QMessageBox.information(self,"Simulation","Add a lane first."); return
        w=Worker(lambda: api.post("/sim/entry", {"plate": plate, "gate_id": self.gate.currentData(), "side": "ENTRY"}, timeout=20))
        w.done.connect(self._show_result); w.failed.connect(lambda e: self.out.setPlainText(str(e))); self._keep(w); w.start()
    def do_upload(self, side):
        if not self._path:
            QMessageBox.information(self,"Simulation","Choose a JPEG photo of the car first."); return
        if self.gate.currentData() is None:
            QMessageBox.information(self,"Simulation","Add site cameras so a lane exists, then try again."); return
        path=self._path; gate_id=self.gate.currentData()
        def send():
            with open(path, "rb") as fh:
                data=fh.read()
            name=path.replace("\\","/").rsplit("/",1)[-1]
            return api.post_file("/sim/capture", {"file": (name, data, "image/jpeg")}, {"gate_id": str(gate_id), "side": side}, timeout=40)
        w=Worker(send)
        w.done.connect(self._show_result); w.failed.connect(lambda e: self.out.setPlainText(str(e))); self._keep(w); w.start()
    def _show_result(self, data):
        data=data or {}
        sess=data.get("session") or {}
        if sess.get("id"): self._sid=sess.get("id")
        parts=[]
        if data.get("receipt"): parts.append(data["receipt"])
        if data.get("say"): parts.append(data["say"])
        if data.get("message"): parts.append(data["message"])
        alpr=data.get("alpr") or {}
        best=(alpr.get("best") or {})
        if best.get("plate"): parts.append(f"FastALPR: {best.get('plate')} ({int(round((best.get('confidence') or 0)*100))}%)")
        parts.append(json.dumps({k:v for k,v in data.items() if k not in {"alpr","receipt"}}, indent=2, default=str))
        self.out.setPlainText("\n\n".join(parts))
        crop=best.get("crop_url") or alpr.get("annotated_url")
        if crop:
            w=Worker(lambda url=crop: api.get_bytes(url, timeout=8))
            w.done.connect(lambda jpeg: self._pix(jpeg)); self._keep(w); w.start()
    def _pix(self, jpeg):
        image=QImage.fromData(jpeg)
        if image.isNull(): return
        self.preview.setPixmap(QPixmap.fromImage(image).scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
    def do_taken(self):
        if not self._sid:
            QMessageBox.information(self,"Simulation","Upload an ENTRY photo first."); return
        w=Worker(lambda: api.post(f"/sim/sessions/{self._sid}/receipt-taken", {}, timeout=20))
        w.done.connect(self._show_result); w.failed.connect(lambda e: self.out.setPlainText(str(e))); self._keep(w); w.start()
    def do_pay(self):
        if not self._sid:
            QMessageBox.information(self,"Simulation","Upload an ENTRY photo first."); return
        w=Worker(lambda: api.post(f"/sim/sessions/{self._sid}/pay", {}, timeout=20))
        w.done.connect(self._show_result); w.failed.connect(lambda e: self.out.setPlainText(str(e))); self._keep(w); w.start()


class OnboardingWizard(QWidget):
    """Full 8-step deployment setup (prompt §9), driven by /onboarding/*."""
    def __init__(self):
        super().__init__()
        self._status = {}
        self._step = 1
        root = QVBoxLayout(self)
        title = QLabel("Setup Wizard")
        title.setStyleSheet("font-size:24px;font-weight:700")
        root.addWidget(title)
        self.subtitle = QLabel("Configure this deployment in eight steps.")
        self.subtitle.setWordWrap(True)
        self.subtitle.setObjectName("muted")
        root.addWidget(self.subtitle)
        self.step_label = QLabel("Step 1 of 8")
        self.step_label.setStyleSheet("font-weight:700;color:#0E7C72")
        root.addWidget(self.step_label)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        # 1 purpose
        p1 = QWidget(); l1 = QVBoxLayout(p1)
        l1.addWidget(QLabel("What is this site for?"))
        self.use_case = QComboBox()
        for cid, label in [
            ("LPR", "License Plate Recognition"),
            ("SECURITY", "Security Monitoring"),
            ("ACCESS", "Vehicle Access Control"),
            ("PARKING", "Parking Management"),
            ("CUSTOM", "Custom"),
        ]:
            self.use_case.addItem(label, cid)
        l1.addWidget(self.use_case)
        self.stack.addWidget(p1)

        # 2 topology
        p2 = QWidget(); l2 = QVBoxLayout(p2)
        l2.addWidget(QLabel("Site topology preset"))
        self.topo_preset = QComboBox()
        self.topo_preset.addItem("1 entry / 1 exit", "1in1out")
        self.topo_preset.addItem("One bidirectional lane", "bidirectional")
        self.topo_preset.addItem("No gates (LPR / security)", "lpr_only")
        self.topo_preset.addItem("Keep current topology", "keep")
        l2.addWidget(self.topo_preset)
        form2 = QFormLayout()
        self.site_name = QLineEdit("Default Site")
        self.site_tz = QLineEdit("UTC")
        self.site_cur = QLineEdit("USD")
        form2.addRow("Site name", self.site_name)
        form2.addRow("Timezone", self.site_tz)
        form2.addRow("Currency", self.site_cur)
        l2.addLayout(form2)
        self.stack.addWidget(p2)

        # 3 hardware
        p3 = QWidget(); l3 = QVBoxLayout(p3)
        l3.addWidget(QLabel("Hardware — discover cameras or skip and commission later in Live Gates."))
        self.hw_info = QPlainTextEdit(); self.hw_info.setReadOnly(True)
        l3.addWidget(self.hw_info)
        disc = QPushButton("Discover cameras on LAN")
        disc.clicked.connect(self._discover)
        l3.addWidget(disc)
        self.stack.addWidget(p3)

        # 4 recognition
        p4 = QWidget(); l4 = QVBoxLayout(p4)
        l4.addWidget(QLabel("Default recognition mode for cameras"))
        self.rec_mode = QComboBox()
        for mid, label in [
            ("NATIVE_ONLY", "Native ALPR"),
            ("FASTALPR_ONLY", "SmartPark FastALPR"),
            ("HYBRID", "Hybrid"),
            ("VIDEO_ONLY", "Video only"),
        ]:
            self.rec_mode.addItem(label, mid)
        self.rec_mode.setCurrentIndex(2)
        l4.addWidget(self.rec_mode)
        self.stack.addWidget(p4)

        # 5 modules
        p5 = QWidget(); l5 = QVBoxLayout(p5)
        l5.addWidget(QLabel("Optional modules (disabled modules disappear from navigation)"))
        self.mod_list = QListWidget()
        self.mod_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        l5.addWidget(self.mod_list)
        self.stack.addWidget(p5)

        # 6 users
        p6 = QWidget(); l6 = QVBoxLayout(p6)
        l6.addWidget(QLabel("Optional: create an operator account (leave blank to skip)"))
        form6 = QFormLayout()
        self.new_user = QLineEdit(); self.new_full = QLineEdit()
        self.new_pass = QLineEdit(); self.new_pass.setEchoMode(QLineEdit.Password)
        self.new_role = QComboBox(); self.new_role.addItems(["Operator", "Admin", "Cashier", "Technician"])
        form6.addRow("Username", self.new_user)
        form6.addRow("Full name", self.new_full)
        form6.addRow("Password", self.new_pass)
        form6.addRow("Role", self.new_role)
        l6.addLayout(form6)
        self.stack.addWidget(p6)

        # 7 health
        p7 = QWidget(); l7 = QVBoxLayout(p7)
        l7.addWidget(QLabel("Module health — Disabled is neutral, not an error."))
        self.health_view = QPlainTextEdit(); self.health_view.setReadOnly(True)
        l7.addWidget(self.health_view)
        refresh = QPushButton("Refresh health")
        refresh.clicked.connect(self._load)
        l7.addWidget(refresh)
        self.stack.addWidget(p7)

        # 8 activate
        p8 = QWidget(); l8 = QVBoxLayout(p8)
        self.ready = QLabel("Ready to activate this deployment.")
        self.ready.setWordWrap(True)
        self.ready.setStyleSheet("font-size:16px;font-weight:600")
        l8.addWidget(self.ready)
        self.stack.addWidget(p8)

        nav = QHBoxLayout()
        self.back_btn = QPushButton("Back"); self.back_btn.clicked.connect(self._back)
        self.skip_btn = QPushButton("Skip step"); self.skip_btn.setObjectName("secondary"); self.skip_btn.clicked.connect(lambda: self._next(skip=True))
        self.next_btn = QPushButton("Continue"); self.next_btn.clicked.connect(lambda: self._next(skip=False))
        self.act_btn = QPushButton("Activate deployment"); self.act_btn.clicked.connect(self._activate)
        nav.addWidget(self.back_btn); nav.addStretch(); nav.addWidget(self.skip_btn); nav.addWidget(self.next_btn); nav.addWidget(self.act_btn)
        root.addLayout(nav)
        self.err = QLabel(""); self.err.setStyleSheet("color:#C0372E"); self.err.setWordWrap(True)
        root.addWidget(self.err)
        QTimer.singleShot(0, self._load)

    def _discover(self):
        try:
            data = api.get("/cameras/discover?scan_lan=true")
            cams = data.get("cameras") if isinstance(data, dict) else data
            n = len(cams) if isinstance(cams, list) else 0
            self.hw_info.setPlainText(f"{n} device(s) found.\nImport and connect them under Live Gates → IPs.")
        except Exception as e:
            self.hw_info.setPlainText(str(e))

    def _load(self):
        self.err.setText("")
        try:
            self._status = api.get("/onboarding/status")
            self._step = max(1, min(int(self._status.get("step") or 1), 8))
            uc = self._status.get("use_case")
            if uc:
                idx = self.use_case.findData(uc)
                if idx >= 0:
                    self.use_case.setCurrentIndex(idx)
            site = ((self._status.get("topology") or {}).get("site") or {})
            if site.get("name"):
                self.site_name.setText(site["name"])
            if site.get("timezone"):
                self.site_tz.setText(site["timezone"])
            if site.get("currency"):
                self.site_cur.setText(site["currency"])
            self.mod_list.clear()
            for row in self._status.get("optional_module_choices") or []:
                item = QListWidgetItem(f"{row.get('label')} — {row.get('description', '')}")
                item.setData(Qt.ItemDataRole.UserRole, row.get("id"))
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if row.get("enabled") else Qt.CheckState.Unchecked)
                self.mod_list.addItem(item)
            comps = ((self._status.get("health") or {}).get("components") or {})
            lines = [f"{k}: {v.get('state', '—')}" for k, v in comps.items()]
            self.health_view.setPlainText("\n".join(lines) or "No health data.")
            enabled = self._status.get("enabled_modules") or []
            self.ready.setText(
                f"Profile {self._status.get('profile') or '—'} · {len(enabled)} modules enabled.\n"
                + ", ".join(enabled)
            )
            counts = self._status.get("counts") or {}
            self.hw_info.setPlainText(
                f"Cameras: {counts.get('cameras', 0)} · Gates: {counts.get('gates', 0)} · Lanes: {counts.get('lanes', 0)}"
            )
            self._show_step()
        except Exception as e:
            self.err.setText(str(e))

    def _show_step(self):
        self.stack.setCurrentIndex(self._step - 1)
        self.step_label.setText(f"Step {self._step} of 8")
        self.back_btn.setEnabled(self._step > 1)
        self.skip_btn.setVisible(self._step not in (1, 8))
        self.next_btn.setVisible(self._step < 8)
        self.act_btn.setVisible(self._step >= 8)

    def _payload(self, next_step, *, activate=False, skip=False):
        body = {
            "step": next_step,
            "use_case": self.use_case.currentData(),
            "activate": activate,
            "skip": skip,
        }
        if self._step == 2 and not skip:
            body["site"] = {
                "name": self.site_name.text().strip(),
                "timezone": self.site_tz.text().strip() or "UTC",
                "currency": self.site_cur.text().strip() or "USD",
            }
            preset = self.topo_preset.currentData()
            if preset != "keep":
                body["topology"] = {"preset": preset}
        if self._step == 3 and not skip:
            body["hardware"] = {"reviewed": True}
        if self._step == 4 and not skip:
            body["recognition_mode"] = self.rec_mode.currentData()
        if self._step == 5 and not skip:
            selected = []
            for i in range(self.mod_list.count()):
                item = self.mod_list.item(i)
                if item.checkState() == Qt.CheckState.Checked:
                    selected.append(item.data(Qt.ItemDataRole.UserRole))
            body["optional_modules"] = selected
        if self._step == 6 and not skip:
            u = self.new_user.text().strip()
            p = self.new_pass.text()
            if u and p:
                body["user"] = {
                    "username": u,
                    "password": p,
                    "full_name": self.new_full.text().strip() or u,
                    "role": self.new_role.currentText(),
                }
        if self._step == 7:
            body["health_ok"] = True
        return body

    def _back(self):
        self._step = max(1, self._step - 1)
        self._show_step()

    def _next(self, skip=False):
        self.err.setText("")
        nxt = min(8, self._step + 1)
        try:
            api.post("/onboarding/step", self._payload(nxt, skip=skip))
            self._step = nxt
            self._load()
        except Exception as e:
            self.err.setText(str(e))

    def _activate(self):
        self.err.setText("")
        try:
            api.post("/onboarding/step", self._payload(8, activate=True))
            QMessageBox.information(self, "Activated", "Deployment activated. Restart navigation by signing out and back in if needed.")
            self._load()
        except Exception as e:
            self.err.setText(str(e))


class PlateEnginePage(QWidget):
    """ParkWatch-style reader: the camera snaps, FastALPR reads, the pack can be replaced."""

    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        title = QLabel("Plate Engine")
        title.setStyleSheet("font-size:24px;font-weight:700")
        root.addWidget(title)
        intro = QLabel(
            "Same split as ParkWatch. The lane camera saves the photo. "
            "FastALPR finds the plate and reads it. Tanzania is the country profile. "
            "Drop a new ONNX pack to retrain, or register another engine to change the library. "
            "This desktop runs on Windows and Linux."
        )
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        root.addWidget(intro)
        self.card = QLabel("")
        self.card.setWordWrap(True)
        self.card.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.card)
        row = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.load)
        pack = QPushButton("Apply model pack…")
        pack.setObjectName("secondary")
        pack.clicked.connect(self.apply_pack)
        row.addWidget(refresh)
        row.addWidget(pack)
        row.addStretch()
        root.addLayout(row)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        root.addStretch()

    def showEvent(self, event):
        super().showEvent(event)
        self.load()

    def load(self):
        try:
            data = api.get("/recognition/engine")
        except Exception as exc:
            self.status.setText(str(exc))
            return
        models = data.get("models") or {}
        training = data.get("training") or {}
        engines = ", ".join(row.get("id", "") for row in (data.get("engines") or []))
        lines = [
            f"Engine: {data.get('display_name')} ({data.get('id')}) {data.get('version')}",
            f"Installed: {'yes' if data.get('installed') else 'no'}    Loaded: {'yes' if data.get('loaded') else 'no'}",
            f"Country: {data.get('country')}    Contrast: {data.get('contrast_sensitivity')}",
            f"Detector: {models.get('detector_file')} ({'ready' if models.get('detector_ready') else 'missing'})",
            f"OCR: {models.get('ocr_file')} ({'ready' if models.get('ocr_ready') else 'missing'})",
            f"Model folder: {models.get('bundled_dir') or 'not installed'}",
            f"Registered engines: {engines or data.get('id')}",
            f"Corrections saved for retraining: {training.get('corrections', 0)}",
            str(training.get("retrain") or ""),
        ]
        self.card.setText("\n".join(lines))
        self.status.setText("Reading every lane photo in software.")

    def apply_pack(self):
        folder = QFileDialog.getExistingDirectory(self, "Model pack folder")
        if not folder:
            return
        try:
            result = api.post("/recognition/model-pack", {"directory": folder}, timeout=60)
        except Exception as exc:
            self.status.setText(str(exc))
            return
        self.status.setText(f"Installed to {result.get('installed_to')}. The next car uses the new weights.")
        self.load()


class SettingsPage(QWidget):
    def __init__(self, window):
        super().__init__(); self.window=window; l=QVBoxLayout(self)
        title=QLabel("Settings"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        form=QFormLayout()
        combo=QComboBox(); combo.addItems(["Light","Dark"]); combo.currentTextChanged.connect(self.change)
        form.addRow("Appearance", combo)
        self.timezone=QLineEdit("UTC")
        self.currency=QLineEdit()
        self.language=QComboBox(); self.language.addItems(["en","sw","ar","fr","pt"])
        self.plate_validation=QComboBox(); self.plate_validation.addItems(["NONE","TZ","KE","ZA","AE"])
        self.public_base_url=QLineEdit()
        self.public_base_url.setPlaceholderText("http://192.168.1.10:8760")
        form.addRow("Timezone (IANA)", self.timezone)
        form.addRow("Currency (ISO 4217)", self.currency)
        form.addRow("Language", self.language)
        form.addRow("Plate validation", self.plate_validation)
        form.addRow("Public receipt URL (QR scans)", self.public_base_url)
        site_save=QPushButton("Save site locale")
        site_save.clicked.connect(self.save_site)
        form.addRow("", site_save)
        self.site_status=QLabel("")
        form.addRow("", self.site_status)
        l.addLayout(form)
        if api.can("simulation.run"):
            park=QLabel("Parking rules (simulation and live plates share this)."); park.setWordWrap(True); l.addWidget(park)
            self.receipt=QCheckBox("Receipt must be taken before the entry barrier opens")
            self.policy=QComboBox(); self.policy.addItems(["REQUIRE_TAKEN_BEFORE_OPEN","PRINT_AND_OPEN","PRINT_OPTIONAL","OFF"])
            self.pay=QCheckBox("Exit stays closed until the session is paid")
            self.prompt=QLineEdit()
            self.printer=QComboBox(); self.printer.setEditable(False)
            printer_note=QLabel("Thermal receipt printer (58 mm / 80 mm USB roll): plug it in, pick it here, Save. A detected car prints a ticket, then the gate opens.")
            printer_note.setWordWrap(True)
            l.addWidget(self.receipt); pf=QFormLayout(); pf.addRow("Receipt policy", self.policy); pf.addRow("Pay prompt", self.prompt); pf.addRow("Thermal receipt printer", self.printer); l.addLayout(pf)
            l.addWidget(self.pay); l.addWidget(printer_note)
            row=QHBoxLayout()
            save=QPushButton("Save parking rules"); save.clicked.connect(self.save_parking)
            test=QPushButton("Print test ticket"); test.clicked.connect(self.test_printer)
            row.addWidget(save); row.addWidget(test); row.addStretch(); l.addLayout(row)
            self.park_status=QLabel(""); self.park_status.setWordWrap(True); l.addWidget(self.park_status)
        web=QPushButton("Open web UI"); web.clicked.connect(self.open_web); l.addWidget(web)
        l.addStretch()
    def showEvent(self, event):
        super().showEvent(event)
        if api.can("simulation.run") and not getattr(self, "_loaded", False):
            self._loaded=True
            self.load_parking()
            self.load_site()
    def load_site(self):
        try:
            data=api.get("/settings/site")
        except Exception as e:
            self.site_status.setText(str(e)); return
        self.timezone.setText(str(data.get("timezone") or "UTC"))
        self.currency.setText(str(data.get("currency") or ""))
        self.public_base_url.setText(str(data.get("public_base_url") or ""))
        idx=self.language.findText(str(data.get("language") or "en"))
        if idx>=0: self.language.setCurrentIndex(idx)
        idx=self.plate_validation.findText(str(data.get("plate_validation") or "NONE"))
        if idx>=0: self.plate_validation.setCurrentIndex(idx)
    def save_site(self):
        try:
            saved=api.patch("/settings/site",{
                "timezone": self.timezone.text().strip() or "UTC",
                "currency": self.currency.text().strip().upper(),
                "language": self.language.currentText(),
                "plate_validation": self.plate_validation.currentText(),
                "public_base_url": self.public_base_url.text().strip().rstrip("/"),
            })
            self.site_status.setText(f"Saved {saved.get('timezone')} / {saved.get('currency')}")
        except Exception as e:
            self.site_status.setText(str(e))
    def change(self,text): self.window.apply_theme(text)
    def load_parking(self):
        try:
            data=api.get("/settings/parking")
            status=api.get("/printers/status")
        except Exception as e:
            self.park_status.setText(str(e)); return
        self.receipt.setChecked(bool(data.get("receipt_required_before_open")))
        if hasattr(self, "policy"):
            self.policy.setCurrentText(str(data.get("receipt_policy") or "PRINT_AND_OPEN"))
        self.pay.setChecked(bool(data.get("exit_requires_payment")))
        self.prompt.setText(str(data.get("pay_prompt") or ""))
        self.printer.clear()
        self.printer.addItem("File only (no paper)", "")
        chosen=str(data.get("printer_name") or status.get("printer_name") or "")
        found=False
        for row in status.get("printers") or []:
            name=str(row.get("name") or "")
            if not name: continue
            label=name
            extras=[]
            if row.get("is_usb"): extras.append("USB")
            if row.get("is_default"): extras.append("default")
            if extras: label=f"{name}  ({', '.join(extras)})"
            self.printer.addItem(label, name)
            if name==chosen: found=True
        if chosen and not found:
            self.printer.addItem(chosen, chosen)
        idx=self.printer.findData(chosen)
        self.printer.setCurrentIndex(idx if idx>=0 else 0)
    def save_parking(self):
        try:
            name=self.printer.currentData() if hasattr(self, "printer") else ""
            saved=api.patch("/settings/parking",{
                "receipt_required_before_open": self.receipt.isChecked(),
                "receipt_policy": self.policy.currentText() if hasattr(self, "policy") else None,
                "exit_requires_payment": self.pay.isChecked(),
                "pay_prompt": self.prompt.text().strip(),
                "printer_adapter": "system" if name else "simulated",
                "printer_name": name or "",
            })
            self.park_status.setText("Saved. Entry prints a thermal ticket on that printer, then the gate opens." if name else "Saved. Receipts are stored as files until you pick a printer.")
            _ = saved
        except Exception as e:
            self.park_status.setText(str(e))
    def test_printer(self):
        try:
            self.save_parking()
            result=api.post("/printers/test", {}, timeout=20)
            self.park_status.setText(str((result or {}).get("message") or result))
        except Exception as e:
            self.park_status.setText(str(e))
    def open_web(self):
        import webbrowser
        webbrowser.open(BASE + "/")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        import platform
        system = platform.system() or "desktop"
        self.setWindowTitle(f"SmartPark  ·  {system}")
        central=QWidget(); self.setCentralWidget(central)
        root=QHBoxLayout(central); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        self.nav=QListWidget()
        avail=available_screen()
        nav_w=160 if avail is not None and avail.width()<1366 else 190
        self.nav.setFixedWidth(nav_w)
        self.stack=QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self.nav); root.addWidget(self.stack,1)
        self.pages=[]
        self._makers=[]
        if api.nav_page("dashboard"):
            self.add_page(api.nav_label("dashboard", "Dashboard"), Dashboard)
        if api.nav_page("health"):
            self.add_page(api.nav_label("health", "System Health"), SystemHealth)
        if api.nav_page("cameras"):
            self.add_page(api.nav_label("cameras", "Live Gates"), Cameras)
        if api.nav_page("plates"):
            self.add_page(api.nav_label("plates", "Plate Engine"), PlateEnginePage)
        if api.nav_page("onboarding") or (
            api.can("settings.manage") and not (api.modules or {}).get("onboarding_completed", True)
        ):
            self.add_page(api.nav_label("onboarding", "Setup Wizard"), OnboardingWizard)
        if api.nav_page("sessions"):
            self.add_page(api.nav_label("sessions", "Sessions"), Sessions)
        if api.nav_page("vehicles"):
            self.add_page(api.nav_label("vehicles", "Vehicles"), Vehicles)
        if api.nav_page("payments"):
            self.add_page(api.nav_label("payments", "Payments"), Payments)
        if api.nav_page("fees"):
            self.add_page(api.nav_label("fees", "Tariffs"), Fees)
        if api.nav_page("reports"):
            self.add_page(api.nav_label("reports", "Reports"), ReportsPage)
        if api.nav_page("gates"):
            self.add_page(api.nav_label("gates", "Gates"), Gates)
        if api.nav_page("users"):
            self.add_page(api.nav_label("users", "Users"), Users)
        if api.nav_page("settings") or api.can("settings.view") or api.can("dashboard.view"):
            self.add_page(api.nav_label("settings", "Settings"), lambda: SettingsPage(self))
        if api.nav_page("hardware"):
            self.add_page(api.nav_label("hardware", "Hardware Lab"), Hardware)
        if api.nav_page("sim"):
            self.add_page(api.nav_label("sim", "Simulation"), SimPage)
        self.nav.currentRowChanged.connect(self._show_page)
        self.apply_theme("Light")
        self.statusBar().showMessage("Camera snaps the photo. FastALPR reads the plate. Windows and Linux.")
        geom=available_screen()
        if geom is not None:
            self.setGeometry(geom)
        self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)
    def closeEvent(self, event):
        for page in self.pages:
            if page is None: continue
            fn=getattr(page, "shutdown", None)
            if callable(fn):
                fn()
        super().closeEvent(event)
    def add_page(self, name, factory):
        self.nav.addItem(name)
        self.stack.addWidget(QWidget())
        self._makers.append(factory)
        self.pages.append(None)
    def _show_page(self, index):
        if index < 0 or index >= len(self._makers):
            return
        if self.pages[index] is None:
            page=self._makers[index]()
            page.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            old=self.stack.widget(index)
            self.stack.removeWidget(old)
            self.stack.insertWidget(index, page)
            old.deleteLater()
            self.pages[index]=page
        self.stack.setCurrentIndex(index)
    def apply_theme(self,name): QApplication.instance().setStyleSheet(DARK if name=="Dark" else LIGHT)


def main():
    app=QApplication(sys.argv); app.setApplicationName("SmartPark Edge")
    app.setStyleSheet(LIGHT)
    try:
        from app.desktop.launch import ensure_background_services
        ensure_background_services()
    except Exception as exc:
        QMessageBox.critical(None, "SmartPark Edge", f"The local API did not start on http://127.0.0.1:8760\n\n{exc}")
        return 1
    login=Login()
    if login.exec()!=QDialog.Accepted: return 0
    w=MainWindow()
    w.showMaximized()
    if w.nav.count():
        w.nav.setCurrentRow(0)
        w._show_page(0)
    return app.exec()


if __name__ == "__main__": raise SystemExit(main())
