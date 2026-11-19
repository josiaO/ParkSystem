"""Per-camera display lifecycle and recognition evidence controller."""
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt, QSize, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QImageReader, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QInputDialog, QMessageBox
from app.services.live_pair import camera_label
from .api import api
from .common import Worker, _stop_thread, is_technician, source_label
from .streams import MjpegStream
from .frame_mailbox import FrameOrderGuard
from .live_pane_ui import build_live_pane
from .video import VideoCanvas


class CameraLivePane(QFrame):
    """One live camera: video on top, last-car stills and plate details below."""
    armed=Signal(object)
    def __init__(self, slot_title="Camera"):
        super().__init__()
        self.setObjectName("card")
        self.slot_title=slot_title
        self.camera=None
        self._all=[]
        build_live_pane(self, slot_title)
        self._workers=[]
        self._snap_busy=False
        self._alpr_busy=False
        self._last_jpeg=b""
        self._last_overlay=None
        self._mjpeg=None
        self._live_gen=0
        self._mjpeg_retry_ms=1000
        self._snap_timer=QTimer(self); self._snap_timer.setInterval(200); self._snap_timer.timeout.connect(self._tick_snapshot)
        self._alpr_timer=QTimer(self); self._alpr_timer.setInterval(2000); self._alpr_timer.timeout.connect(self._tick_alpr)
        self._paint_busy=False
        self._shown_jpeg=b""
        self._pending_live=b""
        self._order=FrameOrderGuard()
        self._held_car=None
        self._evidence_requests={}
        self._evidence_loaded={}
        # Set while Live Gates is out of sight but the stream is kept open
        # (short grace period): frames are kept, not decoded or painted.
        self._paused=False
        self._watching=None
        # Read-only view of this camera's capture calibration (edited in
        # Settings): zone, trigger line, and the detector's plate boxes.
        self._calib={"config": {}, "plates": [], "phase": ""}
        self._calib_busy=False
        self._calib_config_at=0.0
        self._calib_timer=QTimer(self); self._calib_timer.setInterval(700); self._calib_timer.timeout.connect(self._tick_calibration)

    def _runtime_api(self):
        resolver = getattr(api, "runtime_client", None)
        return resolver() if callable(resolver) else api
    def _on_video(self):
        self.armed.emit(self)
    def mousePressEvent(self, event):
        self.armed.emit(self)
        super().mousePressEvent(event)
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
        self.armed.emit(self)
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
        self.view_title.setText(str((camera or {}).get("name") or f"{self.slot_title} · Choose camera"))
        self._sync_picker()
        if not same:
            self._held_car=None
            self._evidence_requests.clear()
            self._evidence_loaded.clear()
            self._last_overlay=None
            self._last_jpeg=b""
            self._shown_jpeg=b""
            self._pending_live=b""
            self._order.reset()
            self.plate.setText("—")
            self.last_snap.clear()
            self.crop.clear()
        if not camera:
            self.status.setText("Click this view or the list to choose a camera.")
            self.details.setText("Any added camera can go on the left or the right.")
            self.plate.setText("—")
            self.decision.setText("")
            self.stop_live()
            self.video.setText("Click to choose a camera")
            return
        if same and ((self._mjpeg is not None and self._mjpeg.isRunning()) or self._snap_timer.isActive()):
            if not self._alpr_timer.isActive(): self._alpr_timer.start()
            return
        self.start_live()
    def set_paused(self, paused):
        """Out of sight: keep the connection, skip decoding; back: paint at once."""
        paused=bool(paused)
        if paused == self._paused:
            return
        self._paused=paused
        if not paused:
            self._flush_live_frame()
            if self._alpr_timer.isActive():
                self._tick_alpr()
    def stop_live(self):
        self._paused=False
        self._live_gen += 1
        self._snap_timer.stop(); self._alpr_timer.stop(); self._calib_timer.stop(); self._stop_mjpeg()
        self._watching=None
    def shutdown(self):
        self.stop_live()
    def start_live(self):
        cid=self.camera_id()
        if cid is None:
            self.stop_live(); return
        if self._watching==cid and self._mjpeg is not None and self._mjpeg.isRunning():
            if not self._alpr_timer.isActive(): self._alpr_timer.start()
            return
        self._live_gen += 1
        self._snap_timer.stop()
        self._stop_mjpeg()
        self._watching=cid
        self.status.setText("Opening live view…")
        stream=MjpegStream(cid)
        stream.frame.connect(self._consume_live_frame)
        stream.failed.connect(self._mjpeg_fail)
        self._mjpeg=stream
        stream.start()
        if not self._alpr_timer.isActive(): self._alpr_timer.start()
        self._calib={"config": {}, "plates": [], "phase": ""}
        self._calib_config_at=0.0
        if not self._calib_timer.isActive(): self._calib_timer.start()
        self._tick_alpr()
    def _stop_mjpeg(self):
        stream=self._mjpeg
        self._mjpeg=None
        _stop_thread(stream)
    def _mjpeg_fail(self, err):
        sender=self.sender()
        if sender is not None and sender is not self._mjpeg:
            return
        self._live_fail(err)
        # Stay on the MJPEG stream. snapshot.jpg grabs one FFmpeg frame per
        # request, so polling it as live video restarts a decoder every tick.
        if self.camera_id() is None:
            return
        self._snap_timer.stop()
        gen = self._live_gen
        text=str(err or "").lower()
        reset = any(token in text for token in ("10054", "forcibly closed", "connection reset", "connectionreset", "winerror"))
        if reset:
            delay = 250
            self._mjpeg_retry_ms = 1000
        else:
            delay = self._mjpeg_retry_ms
            self._mjpeg_retry_ms = min(8000, max(1000, delay * 2))
        self.status.setText("Reconnecting live view…")
        QTimer.singleShot(delay, lambda g=gen: self._retry_mjpeg(g))
    def _retry_mjpeg(self, gen):
        if gen != self._live_gen or self.camera_id() is None:
            return
        if self._mjpeg is not None and self._mjpeg.isRunning():
            QTimer.singleShot(250, lambda: self._retry_mjpeg(gen))
            return
        self.start_live()
    def _set_pixmap(self, label, jpeg, overlay=None):
        target = self._display_target(label)
        image = self._decode_live_image(jpeg, target)
        if image.isNull(): return False
        if overlay and label is self.video and self.overlays_toggle.isChecked():
            image=self._paint_overlay(image, overlay)
        if label is self.video and self.overlays_toggle.isChecked():
            image=self._paint_calibration(image)
        pix=QPixmap.fromImage(image)
        if isinstance(label, VideoCanvas):
            label.setPixmap(pix)
            return True
        box=target
        label.setPixmap(pix.scaled(box, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation))
        return True

    def _display_target(self, label):
        """Return the largest useful decode size for this widget.

        QImageReader can decode directly at this size. Decoding a 1920px QY
        frame only to immediately paint it into a 900px widget wastes most of
        the GUI thread's time and makes the next frame wait behind it.
        """
        box = label.contentsRect().size()
        max_h = label.maximumHeight()
        if max_h and 0 < max_h < 16777215:
            box.setHeight(min(box.height() or max_h, max_h))
        if box.width() < 16 or box.height() < 16:
            box = QSize(max(label.width(), 480), max_h if max_h and max_h < 16777215 else 360)
        return box

    @staticmethod
    def _decode_live_image(jpeg, target):
        buffer = QBuffer()
        buffer.setData(QByteArray(jpeg))
        if buffer.open(QIODevice.OpenModeFlag.ReadOnly):
            reader = QImageReader(buffer)
            reader.setAutoTransform(True)
            source = reader.size()
            if source.isValid() and target.isValid():
                scaled = source.scaled(target, Qt.AspectRatioMode.KeepAspectRatio)
                if scaled.isValid() and (scaled.width() < source.width() or scaled.height() < source.height()):
                    reader.setScaledSize(scaled)
            image = reader.read()
            if not image.isNull():
                return image
        return QImage.fromData(jpeg)
    def _tick_calibration(self):
        """Fetch the camera's calibration (every 10 s) and live plate boxes."""
        import time as _time
        cid=self.camera_id()
        if cid is None or self._calib_busy or not self.isVisible() or not self.overlays_toggle.isChecked():
            return
        self._calib_busy=True
        need_config=_time.monotonic() - self._calib_config_at > 10
        generation=self._live_gen
        def fetch():
            api_=self._runtime_api()
            live=api_.get(f"/cameras/{cid}/calibration/live", timeout=4)
            config=api_.get(f"/cameras/{cid}/calibration", timeout=4) if need_config else None
            return live, config
        def done(result):
            if cid != self.camera_id() or generation != self._live_gen:
                return
            live, config=result
            state=(live or {}).get("state") or {}
            self._calib["plates"]=state.get("plates") or []
            self._calib["phase"]=str(state.get("phase") or "")
            self._calib["test_mode"]=bool(((live or {}).get("test_mode") or {}).get("enabled"))
            if config is not None:
                self._calib["config"]=(config or {}).get("calibration") or {}
                self._calib_config_at=_time.monotonic()
        w=Worker(fetch)
        w.done.connect(done)
        w.finished.connect(lambda: setattr(self, "_calib_busy", False))
        self._keep(w); w.start()
    def _paint_calibration(self, image):
        """Zone (yellow), trigger line (blue), plate boxes (green = will be read, red = not)."""
        calib=getattr(self, "_calib", None) or {}
        config=calib.get("config") or {}
        width, height = image.width(), image.height()
        painted=image.copy()
        painter=QPainter(painted)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen_w=max(2, width // 320)
        zone=config.get("zone") or []
        if config.get("enabled") and len(zone) >= 3:
            from PySide6.QtCore import QPointF
            from PySide6.QtGui import QPolygonF
            fill=QColor(255, 196, 0, 30)
            painter.setBrush(fill)
            painter.setPen(QPen(QColor(255, 196, 0), pen_w))
            painter.drawPolygon(QPolygonF([QPointF(x * width, y * height) for x, y in zone]))
            painter.setBrush(QColor(0, 0, 0, 0))
        rules=config.get("enforce") or {}
        painter.setFont(QFont("Sans Serif", max(8, width // 90)))
        line=config.get("trigger_line") if config.get("enabled") else None
        if line:
            y=int(float(line.get("y") or 0) * height)
            painter.setPen(QPen(QColor(0, 200, 255), pen_w, Qt.PenStyle.DashLine))
            painter.drawLine(0, y, width, y)
            painter.drawText(6, max(12, y - 4), "Start" + ("" if rules.get("start_line") else " (does not refuse)"))
        end=config.get("end_line") if config.get("enabled") else None
        if end:
            y=int(float(end.get("y") or 0) * height)
            painter.setPen(QPen(QColor(235, 70, 60), pen_w, Qt.PenStyle.DashLine))
            painter.drawLine(0, y, width, y)
            painter.drawText(6, max(12, y - 4), "End" + ("" if rules.get("end_line") else " (does not refuse)"))
        painter.setFont(QFont("Sans Serif", max(9, width // 70), QFont.Weight.Bold))
        for plate in calib.get("plates") or []:
            box=plate.get("box") or {}
            try:
                fw=float(box["image_width"]); fh=float(box["image_height"])
                x1=int(float(box["x1"]) / fw * width); y1=int(float(box["y1"]) / fh * height)
                x2=int(float(box["x2"]) / fw * width); y2=int(float(box["y2"]) / fh * height)
            except (KeyError, TypeError, ValueError, ZeroDivisionError):
                continue
            color=QColor(0, 220, 90) if plate.get("eligible") else QColor(235, 70, 60)
            painter.setPen(QPen(color, pen_w))
            painter.drawRect(x1, y1, max(1, x2 - x1), max(1, y2 - y1))
            painter.drawText(x1, max(12, y1 - 4), f"{float(plate.get('plate_width_px') or 0):.0f}px")
        if config:
            text="Calibrated v%s" % config.get("version") if config.get("enabled") else "Not calibrated"
            if calib.get("test_mode"):
                text += " · TEST MODE"
            painter.setPen(QPen(QColor(255, 255, 255)))
            painter.drawText(8, height - 8, text)
        painter.end()
        return painted
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
        w=Worker(lambda: self._runtime_api().get_bytes(f"/cameras/{cid}/snapshot.jpg", timeout=3))
        w.done.connect(self._queue_live_frame); w.failed.connect(self._live_fail); w.finished.connect(lambda: setattr(self,"_snap_busy",False)); self._keep(w); w.start()
    def _consume_live_frame(self):
        stream = self.sender()
        # A queued signal may arrive after teardown, when both references are None.
        if stream is None or stream is not self._mjpeg:
            return
        jpeg, seq = stream.mailbox.take_with_seq()
        if jpeg and seq is not None:
            self._queue_live_frame(jpeg, seq)
        elif jpeg:
            self._queue_live_frame(jpeg)
    def _queue_live_frame(self, jpeg, seq=None):
        self._pending_live=jpeg
        self._pending_seq=seq
        if not self._paint_busy and not self._paused:
            self._flush_live_frame()
    def _flush_live_frame(self):
        jpeg=self._pending_live
        if not jpeg or jpeg==self._shown_jpeg:
            return
        # Both paths (this PC's HVX host, and the Site Server relay) carry
        # the camera's own frame number, so a frame older than the one on
        # screen is refused even when it arrives through the other path.
        if not self._order.accept(jpeg, source="camera", seq=getattr(self, "_pending_seq", None)):
            # An older picture than the one on screen (fallback between the
            # lane PC's SDK host and the server relay, or a late frame).
            # Painting it makes the camera clock run backwards.
            self._pending_live=b""
            return
        self._paint_busy=True
        try:
            self._last_jpeg=jpeg
            self._shown_jpeg=jpeg
            if not self._set_pixmap(self.video, jpeg, self._last_overlay):
                self.video.setText("Waiting for a JPEG frame")
            else:
                self.status.setText("Live")
                self._mjpeg_retry_ms = 1000
        finally:
            self._paint_busy=False
        if self._pending_live and self._pending_live != jpeg:
            QTimer.singleShot(0, self._flush_live_frame)
    def _live_fail(self, err):
        text=str(err or "")
        if "409" in text or "ffmpeg" in text.lower() or "ffprobe" in text.lower() or "no live video" in text.lower():
            if is_technician():
                self.video.setText("Waiting for a camera JPEG.\nHVX: SDK login on port 30000. Generic IP: HTTP snapshot or RTSP + FastALPR.")
            else:
                self.video.setText("Waiting for the first frame.\nPlate recognition can continue while this picture reconnects.")
            self.status.setText("Waiting for live video")
            return
        self.status.setText(text)
        self.video.setText(text)
    def _tick_alpr(self):
        cid=self.camera_id()
        if cid is None or self._alpr_busy or self._paused: return
        self._alpr_busy=True
        generation=self._live_gen
        w=Worker(lambda: self._runtime_api().get(f"/cameras/{cid}/plates", timeout=8))
        w.done.connect(lambda data: self._show_alpr(data) if cid == self.camera_id() and generation == self._live_gen else None)
        w.failed.connect(lambda error: self.status.setText(error) if cid == self.camera_id() and generation == self._live_gen else None)
        w.finished.connect(lambda: setattr(self,"_alpr_busy",False)); self._keep(w); w.start()
    def _show_alpr(self, data):
        payload=data if isinstance(data, dict) else {}
        previous_overlay = self._last_overlay
        if payload.get("clear_last_car"):
            self._held_car=None
            self._last_overlay=None
        last=payload.get("last_car") or payload.get("capture") or {}
        if last.get("snapshot_url") or last.get("crop_url") or last.get("plate"):
            self._held_car=last
        shown=self._held_car or last
        fusion=payload.get("fusion") or {}
        native=payload.get("native") or {}
        resolved=payload.get("resolved_plate") or fusion.get("resolved_plate") or shown.get("plate") or native.get("plate") or ""
        stored=shown.get("bbox") if isinstance(shown.get("bbox"), dict) else None
        next_overlay=payload.get("overlay") or native.get("bbox") or stored
        self._last_overlay=next_overlay
        if isinstance(self._last_overlay, dict) and "x1" in self._last_overlay:
            width=int(self._last_overlay.get("image_width") or native.get("image_width") or (stored or {}).get("image_width") or 0)
            height=int(self._last_overlay.get("image_height") or native.get("image_height") or (stored or {}).get("image_height") or 0)
            self._last_overlay={**self._last_overlay, "label": self._last_overlay.get("label") or resolved or native.get("plate") or "", "image_width": width, "image_height": height}
            if self._last_jpeg and self._last_overlay != previous_overlay:
                self._set_pixmap(self.video, self._last_jpeg, self._last_overlay)
        elif self._last_jpeg and self._last_overlay != previous_overlay:
            # Clear an old box when the vehicle leaves without repainting the
            # live image every two-second ALPR poll.
            self._set_pixmap(self.video, self._last_jpeg, None)
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
            if is_technician():
                self.status.setText("Live" + ((" · " + " · ".join(live_bits)) if live_bits else ""))
            else:
                self.status.setText("Video is live.")
        elif payload.get("error"):
            self.status.setText(str(payload.get("error")) if is_technician() else "Video unavailable. The camera may still be reading plates.")
        conf=shown.get("confidence")
        pct=None
        if conf is not None:
            number=float(conf)
            pct=int(round(number*100 if number<=1 else number))
        conf_txt=f"{pct}%" if pct is not None else ""
        source=source_label(shown.get("source") or fusion.get("method") or "")
        side=shown.get("lane_direction") or (self.camera or {}).get("side") or (self.camera or {}).get("lane_direction") or ""
        when=str(shown.get("created_at") or "")[:19].replace("T"," ")
        held=bool(shown.get("pending_confirmation") or shown.get("needs_review") or fusion.get("needs_review"))
        low=pct is not None and pct < 80
        if plate:
            bits=[bit for bit in (when, side, source if is_technician() else "") if bit]
            self.details.setText("  ·  ".join(bits) or "Plate read")
            self.decision.setText("Check plate" if held or low else "Plate read")
            if conf_txt:
                self.plate.setText(f"{chars}    {conf_txt}")
            self.hold_label.setText("Confirm or correct this plate before the barrier decides." if held else "")
        else:
            mode=(payload.get("camera") or self.camera or {}).get("recognition_mode") or ""
            if mode == "NATIVE_ONLY":
                self.details.setText("Camera OCR selected. Choose FastALPR in Devices → Edit Camera for software recognition.")
            else:
                self.details.setText("FastALPR · waiting for a stopped plate in the detection zone.")
            self.decision.setText("")
            self.hold_label.setText("")
        error=(payload.get("recognition") or {}).get("last_error")
        if error:
            self.details.setText(f"Recognition: {error}")
        refused=payload.get("refused") or {}
        warning=str(payload.get("calibration_warning") or "")
        if refused:
            # The newest car was read but refused by this camera's calibration:
            # show that car, clearly marked, instead of an older stored car.
            reason=", ".join(refused.get("reasons") or []) or "outside calibration"
            self.decision.setText("NOT STORED")
            self.details.setText(f"{refused.get('plate') or 'Plate'} not stored: {reason}")
            self.hold_label.setText(warning)
            self._load_evidence(self.last_snap, refused.get("snapshot_url"))
            self._load_evidence(self.crop, refused.get("crop_url"))
            return
        if warning:
            self.hold_label.setText(warning)
        evidence=payload.get("evidence") or shown
        self._load_evidence(self.last_snap, evidence.get("snapshot_url"))
        self._load_evidence(self.crop, evidence.get("crop_url"))
    def _load_evidence(self, label, path):
        if not path:
            return
        key=(self.camera_id(), self._live_gen, path)
        loaded=self._evidence_loaded.get(label)
        if (loaded and (loaded[0], loaded[2]) == (key[0], key[2])) or self._evidence_requests.get(label) == key:
            return
        self._evidence_requests[label]=key
        worker=Worker(lambda: self._runtime_api().get_bytes(path, timeout=8))
        def current():
            return key[:2] == (self.camera_id(), self._live_gen) and self._evidence_requests.get(label) == key
        def loaded(jpeg):
            if current() and self._set_pixmap(label, jpeg):
                self._evidence_loaded[label]=key
        def failed(error):
            if current():
                self.details.setText(f"Evidence unavailable: {error}")
        def finished():
            if self._evidence_requests.get(label) == key:
                self._evidence_requests.pop(label, None)
        worker.done.connect(loaded)
        worker.failed.connect(failed)
        worker.finished.connect(finished)
        self._keep(worker)
        worker.start()
    def open_this_side(self):
        self.command_barrier("open")
    def close_this_side(self):
        self.command_barrier("close")
    def command_barrier(self, action="open"):
        cam=self.camera
        verb="close" if action=="close" else "open"
        title="Close this side" if verb=="close" else "Open this side"
        if not cam:
            QMessageBox.information(self,title,"No camera on this side."); return
        side=cam.get("side") or cam.get("lane_direction") or "this side"
        prompt=f"{'Close' if verb=='close' else 'Pulse'} only {cam.get('name') or side} — not the other side of this lane?"
        if QMessageBox.question(self,title,prompt)!=QMessageBox.Yes: return
        reason,ok=QInputDialog.getText(self,title,"Reason", text=f"manual {verb}")
        if ok and reason:
            try: QMessageBox.information(self,"Barrier",str(self._runtime_api().post(f"/cameras/{cam['id']}/barrier/open",{"reason":reason,"action":verb}, timeout=20)))
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
            data=self._runtime_api().post(f"/cameras/{cam['id']}/plate-corrections", body, timeout=20)
            QMessageBox.information(self,"Plate",str((data or {}).get("message") or data))
            self._tick_alpr()
        except Exception as e:
            QMessageBox.critical(self,"Correct plate",str(e))
