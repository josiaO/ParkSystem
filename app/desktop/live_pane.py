"""Per-camera display lifecycle and recognition evidence controller."""
from PySide6.QtCore import Qt, QSize, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QInputDialog, QMessageBox
from app.services.live_pair import camera_label
from .api import api
from .common import Worker, _stop_thread, is_technician, source_label
from .streams import MjpegStream
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
        self._held_car=None
        self._evidence_requests={}
        self._evidence_loaded={}
        self._watching=None
        self._zone=(0.06, 0.18, 0.94, 0.92)
        self._zone_edit=False
        self._zone_drag=None
    def _on_video(self):
        if self._zone_edit:
            return
        self.armed.emit(self)
    def _toggle_zone(self):
        self._zone_edit=not self._zone_edit
        if self._zone_edit:
            self.overlays_toggle.setChecked(True)
        self.zone_btn.setText("Done drawing" if self._zone_edit else "Set detection zone")
        self.video.setText("Drag a box on the picture. The plate is read from that crop." if self._zone_edit and not self._last_jpeg else self.video.text())
        if self._last_jpeg:
            self._set_pixmap(self.video, self._last_jpeg, self._last_overlay)
    def _zoom_changed(self, value):
        self.zoom_label.setText(f"Zoom {value/10:.1f}")
        if self._last_jpeg:
            self._set_pixmap(self.video, self._last_jpeg, self._last_overlay)
    def _load_zone(self, camera):
        framing=(camera or {}).get("framing") or {}
        roi=str(framing.get("detect_roi") or "")
        parts=[part.strip() for part in roi.split(",")]
        self._zone=(0.06, 0.18, 0.94, 0.92)
        if len(parts)==4:
            try:
                vals=tuple(float(part) for part in parts)
            except ValueError:
                vals=None
            if vals and vals[2]-vals[0] >= 0.08 and vals[3]-vals[1] >= 0.08:
                self._zone=vals
        zoom=float(framing.get("detect_zoom") or 1)
        self.zoom.blockSignals(True)
        self.zoom.setValue(int(round(max(1.0, min(4.0, zoom))*10)))
        self.zoom.blockSignals(False)
        self.zoom_label.setText(f"Zoom {self.zoom.value()/10:.1f}")
    def _norm_at(self, pos):
        return self.video.normalized_point(pos)
    def _zone_press(self, pos):
        if not self._zone_edit:
            return
        point=self._norm_at(pos)
        if point is None:
            return
        self._zone_drag=point
        self._zone=(point[0], point[1], point[0], point[1])
    def _zone_move(self, pos):
        if not self._zone_edit or self._zone_drag is None:
            return
        point=self._norm_at(pos)
        if point is None:
            return
        x1,y1=self._zone_drag
        x2,y2=point
        self._zone=(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        if self._last_jpeg:
            self._set_pixmap(self.video, self._last_jpeg, self._last_overlay)
    def _zone_release(self, pos):
        if not self._zone_edit:
            return
        self._zone_move(pos)
        self._zone_drag=None
    def _save_zone(self):
        cid=self.camera_id()
        if cid is None:
            self.status.setText("Choose a camera before saving the zone.")
            return
        x1,y1,x2,y2=self._zone
        if (x2-x1) < 0.08 or (y2-y1) < 0.08:
            self.status.setText("Draw a larger box. The zone needs to cover the plate.")
            return
        roi=f"{x1:.4f},{y1:.4f},{x2:.4f},{y2:.4f}"
        zoom=self.zoom.value()/10
        try:
            data=api.put(f"/cameras/{cid}/framing", {"detect_roi": roi, "detect_zoom": zoom})
        except Exception as exc:
            self.status.setText(str(exc))
            return
        framing=(data or {}).get("framing") or {}
        if self.camera is not None:
            self.camera["framing"]=framing
        self._zone_edit=False
        self.zone_btn.setText("Set detection zone")
        self.status.setText("Zone saved. The live gate crops the plate from this box, then reads that crop.")
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
            self.plate.setText("—")
            self.last_snap.clear()
            self.crop.clear()
            self._load_zone(camera)
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
    def stop_live(self):
        self._live_gen += 1
        self._snap_timer.stop(); self._alpr_timer.stop(); self._stop_mjpeg()
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
        image=QImage.fromData(jpeg)
        if image.isNull(): return False
        if label is self.video and self.overlays_toggle.isChecked():
            image=self._paint_zone(image)
        if overlay and label is self.video and self.overlays_toggle.isChecked():
            image=self._paint_overlay(image, overlay)
        pix=QPixmap.fromImage(image)
        if isinstance(label, VideoCanvas):
            label.setPixmap(pix)
            return True
        box=label.contentsRect().size()
        max_h=label.maximumHeight()
        if max_h and 0 < max_h < 16777215:
            box.setHeight(min(box.height() or max_h, max_h))
        if box.width() < 16 or box.height() < 16:
            box=QSize(max(label.width(), 480), max_h if max_h and max_h < 16777215 else 360)
        label.setPixmap(pix.scaled(box, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation))
        return True
    def _paint_zone(self, image):
        zone=getattr(self, "_zone", None)
        if not zone:
            return image
        x1, y1, x2, y2 = zone
        width, height = image.width(), image.height()
        ax1, ay1 = int(x1 * width), int(y1 * height)
        ax2, ay2 = int(x2 * width), int(y2 * height)
        painted=image.copy()
        painter=QPainter(painted)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(255, 196, 0), max(2, width // 240)))
        painter.drawRect(ax1, ay1, max(1, ax2 - ax1), max(1, ay2 - ay1))
        zoom=self.zoom.value() / 10 if hasattr(self, "zoom") else 1
        if zoom > 1.01 and ax2 > ax1 and ay2 > ay1:
            cx, cy = (ax1 + ax2) / 2, (ay1 + ay2) / 2
            zw, zh = max(8, (ax2 - ax1) / zoom), max(8, (ay2 - ay1) / zoom)
            painter.setPen(QPen(QColor(255, 196, 0), 1, Qt.PenStyle.DashLine))
            painter.drawRect(int(cx - zw / 2), int(cy - zh / 2), int(zw), int(zh))
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
        w=Worker(lambda: api.get_bytes(f"/cameras/{cid}/snapshot.jpg", timeout=3))
        w.done.connect(self._queue_live_frame); w.failed.connect(self._live_fail); w.finished.connect(lambda: setattr(self,"_snap_busy",False)); self._keep(w); w.start()
    def _consume_live_frame(self):
        stream = self.sender()
        # A queued signal may arrive after teardown, when both references are None.
        if stream is None or stream is not self._mjpeg:
            return
        jpeg = stream.mailbox.take()
        if jpeg:
            self._queue_live_frame(jpeg)
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
        if cid is None or self._alpr_busy: return
        self._alpr_busy=True
        generation=self._live_gen
        w=Worker(lambda: api.get(f"/cameras/{cid}/plates", timeout=8))
        w.done.connect(lambda data: self._show_alpr(data) if cid == self.camera_id() and generation == self._live_gen else None)
        w.failed.connect(lambda error: self.status.setText(error) if cid == self.camera_id() and generation == self._live_gen else None)
        w.finished.connect(lambda: setattr(self,"_alpr_busy",False)); self._keep(w); w.start()
    def _show_alpr(self, data):
        payload=data if isinstance(data, dict) else {}
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
        self._last_overlay=payload.get("overlay") or native.get("bbox") or stored
        if isinstance(self._last_overlay, dict) and "x1" in self._last_overlay:
            width=int(self._last_overlay.get("image_width") or native.get("image_width") or (stored or {}).get("image_width") or 0)
            height=int(self._last_overlay.get("image_height") or native.get("image_height") or (stored or {}).get("image_height") or 0)
            self._last_overlay={**self._last_overlay, "label": self._last_overlay.get("label") or resolved or native.get("plate") or "", "image_width": width, "image_height": height}
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
        evidence=payload.get("evidence") or shown
        self._load_evidence(self.last_snap, evidence.get("snapshot_url"))
        self._load_evidence(self.crop, evidence.get("crop_url"))
    def _load_evidence(self, label, path):
        if not path:
            return
        key=(self.camera_id(), self._live_gen, path)
        if self._evidence_loaded.get(label) == key or self._evidence_requests.get(label) == key:
            return
        self._evidence_requests[label]=key
        worker=Worker(lambda: api.get_bytes(path, timeout=8))
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
            try: QMessageBox.information(self,"Barrier",str(api.post(f"/cameras/{cam['id']}/barrier/open",{"reason":reason,"action":verb}, timeout=20)))
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
