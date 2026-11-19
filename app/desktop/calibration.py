"""Per-camera capture calibration window.

Live picture with the camera's capture zone (rectangle or polygon), trigger
line, the detector's plate boxes with their pixel sizes, capture
eligibility, the frame chosen for OCR and the latest read. Every camera is
calibrated on its own; nothing is copied between cameras.

Test mode reads and shows plates without storing them: no parking session,
no barrier. It switches itself off after the chosen minutes.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QScrollArea, QSpinBox, QSplitter, QVBoxLayout, QWidget,
)

from .api import api
from .common import Worker, _stop_thread, run_task
from .frame_mailbox import FrameOrderGuard
from .streams import MjpegStream
from .video import VideoCanvas

ZONE_COLOR = QColor(255, 196, 0)
LINE_COLOR = QColor(0, 200, 255)
OK_COLOR = QColor(0, 220, 90)
NO_COLOR = QColor(235, 70, 60)


def runtime_api():
    resolver = getattr(api, "runtime_client", None)
    return resolver() if callable(resolver) else api


class CalibrationCanvas(VideoCanvas):
    """Live picture plus editable zone / trigger line and read-only plate boxes."""

    def __init__(self, parent=None):
        super().__init__("Waiting for live video…", parent)
        self.zone: list[list[float]] = []
        self.line: dict | None = None
        self.end_line: dict | None = None
        self.plates: list[dict] = []
        self.mode = "idle"             # idle | rect | polygon | line
        self.editable = True
        self._drag = None              # ("vertex", i) | ("zone", start, original) | ("rect", start) | ("line",)
        self.on_changed = lambda: None
        self.setMouseTracking(True)

    # mapping between widget pixels and normalised picture coordinates
    def _to_norm(self, pos):
        point = self.normalized_point(pos)
        return None if point is None else [round(point[0], 4), round(point[1], 4)]

    def _to_widget(self, x, y):
        rect = self.image_rect()
        return QPointF(rect.x() + x * rect.width(), rect.y() + y * rect.height())

    def set_mode(self, mode):
        self.mode = mode
        if mode == "polygon":
            self.zone = []
        self.update()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if not self.editable:
            return
        point = self._to_norm(event.pos())
        if point is None:
            return
        if self.mode == "rect":
            self._drag = ("rect", point)
            self.zone = [point, point, point, point]
        elif self.mode == "polygon":
            self.zone.append(point)
            self.on_changed()
        elif self.mode == "line":
            self.line = {"y": point[1], "side": (self.line or {}).get("side", "below")}
            self._drag = ("line",)
            self.on_changed()
        elif self.mode == "end":
            self.end_line = {"y": point[1]}
            self._drag = ("end",)
            self.on_changed()
        else:
            hit = self._vertex_at(event.pos())
            if hit is not None:
                self._drag = ("vertex", hit)
            elif self.zone and self._inside_zone(point):
                self._drag = ("zone", point, [list(p) for p in self.zone])
            elif self.line and abs(self._to_widget(0, self.line["y"]).y() - event.pos().y()) < 8:
                self._drag = ("line",)
            elif self.end_line and abs(self._to_widget(0, self.end_line["y"]).y() - event.pos().y()) < 8:
                self._drag = ("end",)
        self.update()

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if not self._drag:
            return
        point = self._to_norm(event.pos())
        if point is None:
            return
        kind = self._drag[0]
        if kind == "rect":
            x1, y1 = self._drag[1]
            x2, y2 = point
            left, right = sorted((x1, x2))
            top, bottom = sorted((y1, y2))
            self.zone = [[left, top], [right, top], [right, bottom], [left, bottom]]
        elif kind == "vertex":
            self.zone[self._drag[1]] = point
        elif kind == "zone":
            start, original = self._drag[1], self._drag[2]
            dx, dy = point[0] - start[0], point[1] - start[1]
            dx = max(-min(p[0] for p in original), min(dx, 1 - max(p[0] for p in original)))
            dy = max(-min(p[1] for p in original), min(dy, 1 - max(p[1] for p in original)))
            self.zone = [[round(p[0] + dx, 4), round(p[1] + dy, 4)] for p in original]
        elif kind == "line" and self.line is not None:
            self.line["y"] = point[1]
        elif kind == "end" and self.end_line is not None:
            self.end_line["y"] = point[1]
        self.update()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self._drag:
            if self._drag[0] in {"rect", "line", "end"}:
                self.mode = "idle"
            self._drag = None
            self.on_changed()
        self.update()

    def _vertex_at(self, pos):
        for i, (x, y) in enumerate(self.zone):
            p = self._to_widget(x, y)
            if abs(p.x() - pos.x()) <= 8 and abs(p.y() - pos.y()) <= 8:
                return i
        return None

    def _inside_zone(self, point):
        from app.services.capture_calibration import point_in_polygon

        return len(self.zone) >= 3 and point_in_polygon(point[0], point[1], self.zone)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.pixmap().isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.image_rect()
        if self.zone:
            polygon = QPolygonF([self._to_widget(x, y) for x, y in self.zone])
            fill = QColor(ZONE_COLOR)
            fill.setAlpha(40)
            painter.setBrush(fill)
            painter.setPen(QPen(ZONE_COLOR, 2))
            if len(self.zone) >= 3:
                painter.drawPolygon(polygon)
            else:
                painter.drawPolyline(polygon)
            painter.setBrush(ZONE_COLOR)
            for x, y in self.zone:
                p = self._to_widget(x, y)
                painter.drawEllipse(p, 5, 5)
        if self.line:
            y = self._to_widget(0, self.line["y"]).y()
            painter.setPen(QPen(LINE_COLOR, 2, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            painter.setFont(QFont("Sans Serif", 9))
            side = "read below this line" if self.line.get("side", "below") == "below" else "read above this line"
            painter.drawText(QPointF(rect.left() + 6, y - 4), f"Start line · {side}")
        if self.end_line:
            y = self._to_widget(0, self.end_line["y"]).y()
            painter.setPen(QPen(NO_COLOR, 2, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            painter.setFont(QFont("Sans Serif", 9))
            painter.drawText(QPointF(rect.left() + 6, y - 4), "End line · no reading past here")
        painter.setFont(QFont("Sans Serif", 9, QFont.Weight.Bold))
        for plate in self.plates:
            box = plate.get("box") or {}
            try:
                fw, fh = float(box["image_width"]), float(box["image_height"])
                x1, y1, x2, y2 = (float(box[k]) / (fw if k[0] == "x" else fh) for k in ("x1", "y1", "x2", "y2"))
            except (KeyError, TypeError, ValueError, ZeroDivisionError):
                continue
            a, b = self._to_widget(x1, y1), self._to_widget(x2, y2)
            color = OK_COLOR if plate.get("eligible") else NO_COLOR
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(color, 2))
            painter.drawRect(QRectF(a, b))
            label = f"{plate.get('plate_width_px', 0):.0f}×{plate.get('plate_height_px', 0):.0f}px"
            painter.drawText(QPointF(a.x(), max(rect.top() + 12, a.y() - 4)), label)
        painter.end()


class CalibrationWindow(QDialog):
    def __init__(self, camera=None, cameras=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Capture calibration")
        self.resize(1280, 760)
        self.cameras = list(cameras or [])
        self.camera = camera
        self.config = {}
        self._dirty = False
        self._stream = None
        self._order = FrameOrderGuard()
        self._live_busy = False
        self._snapshot_at = None
        self.can_edit = api.can("cameras.manage")

        root = QVBoxLayout(self)
        top = QHBoxLayout()
        self.picker = QComboBox()
        for cam in self.cameras or ([camera] if camera else []):
            self.picker.addItem(f"{cam.get('name') or 'Camera'}  ·  {str(cam.get('lane_direction') or '').title()}", cam.get("id"))
        if camera:
            idx = self.picker.findData(camera.get("id"))
            if idx >= 0:
                self.picker.setCurrentIndex(idx)
        self.picker.currentIndexChanged.connect(self._camera_changed)
        top.addWidget(QLabel("Camera"))
        top.addWidget(self.picker, 1)
        self.header = QLabel("")
        self.header.setWordWrap(True)
        top.addWidget(self.header, 3)
        root.addLayout(top)

        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget(); lv = QVBoxLayout(left); lv.setContentsMargins(0, 0, 0, 0)
        self.canvas = CalibrationCanvas()
        self.canvas.on_changed = self._geometry_changed
        lv.addWidget(self.canvas, 1)
        tools = QHBoxLayout()
        self.rect_btn = QPushButton("Draw rectangle"); self.rect_btn.clicked.connect(lambda: self._tool("rect"))
        self.poly_btn = QPushButton("Draw polygon"); self.poly_btn.clicked.connect(lambda: self._tool("polygon"))
        self.poly_done = QPushButton("Finish polygon"); self.poly_done.clicked.connect(lambda: self._tool("idle"))
        self.line_btn = QPushButton("Place start line"); self.line_btn.clicked.connect(lambda: self._tool("line"))
        self.end_btn = QPushButton("Place end line"); self.end_btn.clicked.connect(lambda: self._tool("end"))
        self.end_btn.setToolTip("Reading stops past this line, so a car moving out is not read again.")
        self.clear_end = QPushButton("Remove end line"); self.clear_end.clicked.connect(self._remove_end_line)
        self.line_side = QComboBox(); self.line_side.addItem("Read below the line", "below"); self.line_side.addItem("Read above the line", "above")
        self.line_side.currentIndexChanged.connect(self._side_changed)
        self.clear_line = QPushButton("Remove line"); self.clear_line.clicked.connect(self._remove_line)
        for w in (self.rect_btn, self.poly_btn, self.poly_done, self.line_btn, self.line_side, self.clear_line,
                  self.end_btn, self.clear_end):
            tools.addWidget(w)
        tools.addStretch()
        lv.addLayout(tools)
        self.tool_hint = QLabel("Drag a corner to move it, drag inside the zone to move it all.")
        self.tool_hint.setObjectName("muted")
        lv.addWidget(self.tool_hint)
        split.addWidget(left)

        right = QWidget(); rv = QVBoxLayout(right)
        settings_box = QGroupBox("This camera's capture conditions")
        form = QFormLayout(settings_box)
        self.enabled = QCheckBox("Use the capture zone and limits below")
        self.enabled.setToolTip("Off = uncalibrated: the whole picture, no size or quality limits.")
        form.addRow(self.enabled)
        self.min_w = QSpinBox(); self.min_w.setRange(0, 1000); self.min_w.setSuffix(" px")
        self.min_h = QSpinBox(); self.min_h.setRange(0, 600); self.min_h.setSuffix(" px")
        self.min_det = QDoubleSpinBox(); self.min_det.setRange(0, 1); self.min_det.setSingleStep(0.05); self.min_det.setDecimals(2)
        self.min_ocr = QDoubleSpinBox(); self.min_ocr.setRange(0, 1); self.min_ocr.setSingleStep(0.05); self.min_ocr.setDecimals(2)
        self.min_sharp = QDoubleSpinBox(); self.min_sharp.setRange(0, 5000); self.min_sharp.setSingleStep(10); self.min_sharp.setDecimals(0)
        self.min_bright = QSpinBox(); self.min_bright.setRange(0, 255)
        self.max_bright = QSpinBox(); self.max_bright.setRange(0, 255)
        self.max_clip = QDoubleSpinBox(); self.max_clip.setRange(0, 1); self.max_clip.setSingleStep(0.05); self.max_clip.setDecimals(2)
        self.frames = QSpinBox(); self.frames.setRange(1, 10)
        self.window_s = QDoubleSpinBox(); self.window_s.setRange(0.1, 5.0); self.window_s.setSingleStep(0.1); self.window_s.setSuffix(" s")
        form.addRow("Minimum plate width", self.min_w)
        form.addRow("Minimum plate height", self.min_h)
        form.addRow("Minimum detector confidence", self.min_det)
        form.addRow("Minimum recognition confidence", self.min_ocr)
        form.addRow("Minimum sharpness", self.min_sharp)
        form.addRow("Brightness from", self.min_bright)
        form.addRow("Brightness to", self.max_bright)
        form.addRow("Most glare / black allowed", self.max_clip)
        form.addRow("Best of up to", self.frames)
        form.addRow("…within", self.window_s)
        for widget in (self.enabled, self.min_w, self.min_h, self.min_det, self.min_ocr, self.min_sharp,
                       self.min_bright, self.max_bright, self.max_clip, self.frames, self.window_s):
            signal = getattr(widget, "valueChanged", None) or getattr(widget, "toggled")
            signal.connect(self._mark_dirty)
        rv.addWidget(settings_box)
        buttons = QHBoxLayout()
        self.save_btn = QPushButton("Save for this camera"); self.save_btn.clicked.connect(self.save)
        self.revert_btn = QPushButton("Revert"); self.revert_btn.setObjectName("secondary"); self.revert_btn.clicked.connect(self.load)
        self.reset_btn = QPushButton("Reset to uncalibrated"); self.reset_btn.setObjectName("secondary"); self.reset_btn.clicked.connect(self.reset_calibration)
        for w in (self.save_btn, self.revert_btn, self.reset_btn):
            buttons.addWidget(w)
        rv.addLayout(buttons)

        test_box = QGroupBox("Test")
        tv = QVBoxLayout(test_box)
        row = QHBoxLayout()
        self.test_btn = QPushButton("Start test mode"); self.test_btn.clicked.connect(self.toggle_test)
        self.test_minutes = QSpinBox(); self.test_minutes.setRange(1, 240); self.test_minutes.setValue(30); self.test_minutes.setSuffix(" min")
        row.addWidget(self.test_btn); row.addWidget(QLabel("for")); row.addWidget(self.test_minutes); row.addStretch()
        tv.addLayout(row)
        self.test_note = QLabel("Test mode reads plates and shows them here only: no parking session, no barrier.")
        self.test_note.setWordWrap(True)
        tv.addWidget(self.test_note)
        rv.addWidget(test_box)

        live_box = QGroupBox("Now")
        lb = QVBoxLayout(live_box)
        self.live_text = QLabel("—")
        self.live_text.setWordWrap(True)
        self.live_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lb.addWidget(self.live_text)
        self.snapshot = QLabel("No frame chosen yet")
        self.snapshot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.snapshot.setMinimumHeight(150)
        self.snapshot.setFrameShape(QFrame.Shape.StyledPanel)
        lb.addWidget(QLabel("Frame chosen for OCR"))
        lb.addWidget(self.snapshot)
        self.read_text = QLabel("Latest read: —")
        self.read_text.setStyleSheet("font-size:16px;font-weight:700")
        self.read_text.setWordWrap(True)
        lb.addWidget(self.read_text)
        rv.addWidget(live_box, 1)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(right)
        split.addWidget(scroll)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        root.addWidget(split, 1)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        for widget in (self.rect_btn, self.poly_btn, self.poly_done, self.line_btn, self.line_side, self.clear_line,
                       self.end_btn, self.clear_end,
                       self.save_btn, self.revert_btn, self.reset_btn, self.test_btn, self.enabled, self.min_w, self.min_h,
                       self.min_det, self.min_ocr, self.min_sharp, self.min_bright, self.max_bright, self.max_clip,
                       self.frames, self.window_s, self.test_minutes):
            widget.setEnabled(self.can_edit)
        self.canvas.editable = self.can_edit
        if not self.can_edit:
            self.status.setText("View only: changing calibration needs the camera management permission.")

        self._poll = QTimer(self)
        self._poll.setInterval(400)
        self._poll.timeout.connect(self._poll_live)
        self._camera_changed()

    # ------------------------------------------------------------ camera --
    def camera_id(self):
        return self.picker.currentData()

    def _camera_changed(self, *_):
        if self._dirty and QMessageBox.question(self, "Capture calibration", "Discard unsaved changes for the previous camera?") != QMessageBox.StandardButton.Yes:
            return
        self._dirty = False
        self._order.reset()
        self._snapshot_at = None
        self.snapshot.setText("No frame chosen yet"); self.snapshot.setPixmap(QPixmap())
        self._start_stream()
        self.load()
        self._poll.start()

    def _start_stream(self):
        _stop_thread(self._stream)
        self._stream = None
        cid = self.camera_id()
        if cid is None:
            return
        stream = MjpegStream(cid)
        stream.frame.connect(self._frame)
        stream.failed.connect(lambda error: self.canvas.setText(f"Live video: {error}"))
        self._stream = stream
        stream.start()

    def _frame(self):
        stream = self.sender()
        if stream is None or stream is not self._stream:
            return
        jpeg, seq = stream.mailbox.take_with_seq()
        if not jpeg or not self._order.accept(jpeg, source="camera", seq=seq):
            return
        pix = QPixmap()
        if pix.loadFromData(jpeg):
            self.canvas.setPixmap(pix)

    # ------------------------------------------------------------ config --
    def load(self):
        cid = self.camera_id()
        if cid is None:
            return
        self.status.setText("Loading this camera's calibration…")
        run_task(self, lambda: runtime_api().get(f"/cameras/{cid}/calibration"), self._show_config,
                 buttons=self.revert_btn, busy_text="Loading…", on_error=lambda m, _e: self.status.setText(m))

    def _show_config(self, data):
        data = data or {}
        cfg = dict(data.get("calibration") or {})
        self.config = cfg
        widgets = (self.enabled, self.min_w, self.min_h, self.min_det, self.min_ocr, self.min_sharp,
                   self.min_bright, self.max_bright, self.max_clip, self.frames, self.window_s)
        for widget in widgets:
            widget.blockSignals(True)
        self.enabled.setChecked(bool(cfg.get("enabled")))
        self.min_w.setValue(int(cfg.get("min_plate_width_px") or 0))
        self.min_h.setValue(int(cfg.get("min_plate_height_px") or 0))
        self.min_det.setValue(float(cfg.get("min_detection_confidence") or 0))
        self.min_ocr.setValue(float(cfg.get("min_ocr_confidence") or 0))
        self.min_sharp.setValue(float(cfg.get("min_sharpness") or 0))
        self.min_bright.setValue(int(cfg.get("min_brightness") or 0))
        self.max_bright.setValue(int(cfg.get("max_brightness") if cfg.get("max_brightness") is not None else 255))
        self.max_clip.setValue(float(cfg.get("max_clipped_fraction") if cfg.get("max_clipped_fraction") is not None else 1))
        self.frames.setValue(int(cfg.get("candidate_frames") or 3))
        self.window_s.setValue(float(cfg.get("candidate_seconds") or 0.8))
        for widget in widgets:
            widget.blockSignals(False)
        self.canvas.zone = [list(p) for p in (cfg.get("zone") or [])]
        self.canvas.line = dict(cfg["trigger_line"]) if cfg.get("trigger_line") else None
        self.canvas.end_line = dict(cfg["end_line"]) if cfg.get("end_line") else None
        side = (self.canvas.line or {}).get("side", "below")
        self.line_side.blockSignals(True)
        self.line_side.setCurrentIndex(max(0, self.line_side.findData(side)))
        self.line_side.blockSignals(False)
        self.canvas.update()
        self._dirty = False
        self._show_header(data.get("test_mode") or {})
        self.status.setText("")

    def _show_header(self, test_mode):
        cfg = self.config
        where = f"Gate {cfg.get('gate_id') or '—'} · lane {cfg.get('lane_id') or '—'} · {str(cfg.get('direction') or '').title()}"
        state = (f"Calibrated, version {cfg.get('version')}" if cfg.get("enabled")
                 else "Uncalibrated: whole picture, no size or quality limits")
        if cfg.get("updated_at"):
            state += f" · saved {str(cfg['updated_at'])[:16].replace('T', ' ')}" + (f" by {cfg['updated_by']}" if cfg.get("updated_by") else "")
        if test_mode.get("enabled"):
            state += f" · TEST MODE until {str(test_mode.get('until') or '')[11:16]} UTC"
        self.header.setText(f"{where}\n{state}")
        self.test_btn.setText("Stop test mode" if test_mode.get("enabled") else "Start test mode")
        self._test_on = bool(test_mode.get("enabled"))

    def _payload(self):
        return {
            "enabled": self.enabled.isChecked(),
            "zone": self.canvas.zone if len(self.canvas.zone) >= 3 else [],
            "trigger_line": self.canvas.line,
            "end_line": self.canvas.end_line,
            "min_plate_width_px": self.min_w.value(),
            "min_plate_height_px": self.min_h.value(),
            "min_detection_confidence": self.min_det.value(),
            "min_ocr_confidence": self.min_ocr.value(),
            "min_sharpness": self.min_sharp.value(),
            "min_brightness": self.min_bright.value(),
            "max_brightness": self.max_bright.value(),
            "max_clipped_fraction": self.max_clip.value(),
            "candidate_frames": self.frames.value(),
            "candidate_seconds": self.window_s.value(),
            # Plate sizes are set on this live picture; camera snapshots of
            # another size are scaled to it when they are checked.
            "reference_width": (self.canvas.pixmap().width() if not self.canvas.pixmap().isNull()
                                else int(self.config.get("reference_width") or 0)),
            "version": self.config.get("version"),
        }

    def save(self):
        cid = self.camera_id()
        if cid is None:
            return
        payload = self._payload()
        if payload["enabled"] and not payload["zone"]:
            if QMessageBox.question(self, "Capture calibration", "No capture zone is drawn, so the whole picture counts. Save anyway?") != QMessageBox.StandardButton.Yes:
                return
        self.status.setText("Saving…")

        def done(data):
            self._show_config(data)
            self.status.setText(f"Saved for this camera only (version {(data or {}).get('calibration', {}).get('version')}). "
                                "Recognition uses it within a few seconds.")
        run_task(self, lambda: runtime_api().put(f"/cameras/{cid}/calibration", payload), done,
                 buttons=self.save_btn, busy_text="Saving…", on_error=lambda m, _e: self.status.setText(m))

    def reset_calibration(self):
        cid = self.camera_id()
        if cid is None:
            return
        if QMessageBox.question(self, "Capture calibration", "Remove this camera's calibration? It goes back to the whole picture with no size or quality limits.") != QMessageBox.StandardButton.Yes:
            return
        run_task(self, lambda: runtime_api().delete(f"/cameras/{cid}/calibration"),
                 lambda _d: (self.load(), self.status.setText("This camera is uncalibrated again.")),
                 buttons=self.reset_btn, busy_text="Resetting…", on_error=lambda m, _e: self.status.setText(m))

    def toggle_test(self):
        cid = self.camera_id()
        if cid is None:
            return
        enabled = not getattr(self, "_test_on", False)
        if enabled and QMessageBox.question(
            self, "Test mode",
            "While test mode is on this camera's reads are only shown here: no parking session is created "
            "and its barrier is not opened by recognition. Start?") != QMessageBox.StandardButton.Yes:
            return
        body = {"enabled": enabled, "minutes": self.test_minutes.value()}
        run_task(self, lambda: runtime_api().put(f"/cameras/{cid}/calibration/test-mode", body),
                 lambda status: (self._show_header(status or {}),
                                 self.status.setText("Test mode on." if (status or {}).get("enabled") else "Test mode off: normal operation.")),
                 buttons=self.test_btn, busy_text="…", on_error=lambda m, _e: self.status.setText(m))

    # -------------------------------------------------------------- edit --
    def _tool(self, mode):
        self.canvas.set_mode(mode)
        hints = {
            "rect": "Drag a rectangle over the area where plates are close enough to read.",
            "polygon": "Click each corner of the capture area, then Finish polygon.",
            "line": "Click where reading starts: the plate must cross this line first; drag to adjust.",
            "end": "Click where reading ends: plates past this line are never read (a car moving out).",
            "idle": "Drag a corner to move it, drag inside the zone to move it all.",
        }
        self.tool_hint.setText(hints.get(mode, ""))
        if mode == "idle":
            self._geometry_changed()

    def _side_changed(self, *_):
        if self.canvas.line is not None:
            self.canvas.line["side"] = self.line_side.currentData()
            self.canvas.update()
            self._mark_dirty()

    def _remove_end_line(self):
        self.canvas.end_line = None
        self.canvas.update()
        self._mark_dirty()

    def _remove_line(self):
        self.canvas.line = None
        self.canvas.update()
        self._mark_dirty()

    def _geometry_changed(self):
        if self.canvas.line is not None:
            self.canvas.line["side"] = self.line_side.currentData()
        self._mark_dirty()

    def _mark_dirty(self, *_):
        self._dirty = True
        self.status.setText("Unsaved changes for this camera.")

    # -------------------------------------------------------------- live --
    def _poll_live(self):
        cid = self.camera_id()
        if cid is None or self._live_busy or not self.isVisible():
            return
        self._live_busy = True
        worker = Worker(lambda: runtime_api().get(f"/cameras/{cid}/calibration/live", timeout=5))
        worker.done.connect(lambda data: self._show_live(cid, data))
        worker.failed.connect(lambda message: self.live_text.setText(message))
        worker.finished.connect(lambda: setattr(self, "_live_busy", False))
        self._live_worker = worker
        worker.start()

    def _show_live(self, cid, data):
        if cid != self.camera_id():
            return
        data = data or {}
        state = data.get("state") or {}
        self._show_header({**(data.get("test_mode") or {})}) if not self._dirty else None
        plates = state.get("plates") or []
        self.canvas.plates = plates
        self.canvas.update()
        phase = {
            "far": "Plate seen, not eligible yet", "collecting": "Eligible: choosing the best frame",
            "ready": "Frame chosen, reading", "held": "Read done for this car", "absent": "Lane empty",
            "missing": "Lane empty", "new_vehicle": "Next car",
        }.get(str(state.get("phase") or ""), str(state.get("phase") or "No recognition data yet"))
        lines = [phase]
        if not state:
            lines = ["No recognition data for this camera yet. The detector reports here once the camera's lane is running recognition."]
        for plate in plates[:3]:
            q = plate.get("quality") or {}
            mark = "✔ eligible" if plate.get("eligible") else "✘ " + "; ".join(plate.get("reasons") or [])
            lines.append(
                f"Plate {plate.get('plate_width_px', 0):.0f}×{plate.get('plate_height_px', 0):.0f}px "
                f"({100 * float(plate.get('relative_plate_width') or 0):.1f}% of width), "
                f"detector {float(plate.get('detection_confidence') or 0):.2f}"
                + (f", sharpness {q.get('sharpness', 0):.0f}, brightness {q.get('brightness', 0):.0f}" if q else "")
                + f" — {mark}")
        lines.append("Plate sizes are pixels on this camera's picture, a relative distance cue, not metres.")
        self.live_text.setText("\n".join(lines))
        rejected = state.get("last_rejected") or {}
        if rejected:
            lines.append(f"Not stored (outside calibration): {rejected.get('plate') or 'a vehicle'} — "
                         + "; ".join(rejected.get("reasons") or []))
            self.live_text.setText("\n".join(lines))
        read = state.get("last_read") or {}
        if read:
            conf = float(read.get("confidence") or 0)
            tag = " (test, not stored)" if read.get("test_mode") else ""
            low = "" if read.get("meets_min_confidence", True) else " — below this camera's minimum"
            self.read_text.setText(f"Latest read: {read.get('plate') or '—'}  {conf:.0%}{tag}{low}")
        selected = state.get("selected") or {}
        if selected.get("at") and selected.get("at") != self._snapshot_at and data.get("has_snapshot"):
            self._snapshot_at = selected.get("at")
            worker = Worker(lambda: runtime_api().get_bytes(f"/cameras/{cid}/calibration/snapshot.jpg", timeout=5))
            worker.done.connect(self._show_snapshot)
            self._snap_worker = worker
            worker.start()

    def _show_snapshot(self, jpeg):
        pix = QPixmap()
        if pix.loadFromData(jpeg or b""):
            self.snapshot.setPixmap(pix.scaled(self.snapshot.width() or 320, 180, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation))

    def closeEvent(self, event):
        if self._dirty and self.can_edit:
            if QMessageBox.question(self, "Capture calibration", "Close without saving this camera's changes?") != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self._poll.stop()
        _stop_thread(self._stream)
        self._stream = None
        super().closeEvent(event)
