from __future__ import annotations

import json
import os
import sys
import time
import traceback
import httpx
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen, QPixmap, QTextDocument
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QInputDialog
)

from .api import api, BASE
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


def show_printable_receipt(parent, body, path=""):
    dlg=QDialog(parent)
    dlg.setWindowTitle("Parking receipt")
    dlg.setMinimumSize(420, 420)
    layout=QVBoxLayout(dlg)
    text=QPlainTextEdit(); text.setReadOnly(True); text.setPlainText(body or "")
    layout.addWidget(text, 1)
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
    """Read /live.mjpeg and emit JPEG frames. Snapshot polling is only a fallback."""
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
                chunks=response.iter_bytes()
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
                        buf = buf[-120_000:]
                    while True:
                        start=buf.find(b"\xff\xd8")
                        end=buf.find(b"\xff\xd9", start+2) if start>=0 else -1
                        if start<0 or end<0:
                            if start>0:
                                buf=buf[start:]
                            break
                        pending=buf[start:end+2]
                        buf=buf[end+2:]
                    now=time.monotonic()
                    if pending is not None and (now-last_emit) >= 0.03:
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


class Login(QDialog):
    def __init__(self):
        super().__init__(); self.setWindowTitle("SmartPark Edge — Sign In")
        self.setMinimumWidth(320); self.setMaximumWidth(460)
        l=QVBoxLayout(self); l.setContentsMargins(20,20,20,20)
        title=QLabel("SmartPark Edge"); title.setStyleSheet("font-size:26px;font-weight:700")
        self.sub=QLabel("Sign in as admin / SmartPark1!")
        self.sub.setWordWrap(True)
        self.user=QLineEdit("admin"); self.user.setPlaceholderText("Username")
        self.pwd=QLineEdit("SmartPark1!"); self.pwd.setPlaceholderText("Password"); self.pwd.setEchoMode(QLineEdit.Password)
        btn=QPushButton("Sign In"); btn.clicked.connect(self.login)
        l.addWidget(title); l.addWidget(self.sub); l.addSpacing(15); l.addWidget(self.user); l.addWidget(self.pwd); l.addWidget(btn)
        fit_window_to_screen(self, (390, 280), min_size=(320, 220))
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
                    "admin / SmartPark1! only works on a fresh database. "
                    "This PC already has an admin account. "
                    "Reset it with: python -m app.cli reset-admin"
                )
            elif "Connection" in text or "ConnectError" in text or "8760" in text:
                text = "Cannot reach the API at http://127.0.0.1:8760. Start SmartPark with python -m app.desktop.launch"
            QMessageBox.critical(self,"Sign in failed",text)


class Lanes(QWidget):
    def __init__(self):
        super().__init__(); l=QVBoxLayout(self)
        title=QLabel("Live Gates"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        note=QLabel("Car snapshots only — the still taken when a vehicle is read at each gate. Moving live video is on the Cameras tab. Add a gate, then attach cameras (entry/exit) to grow the site.")
        note.setWordWrap(True); l.addWidget(note)
        row=QHBoxLayout(); refresh=QPushButton("Refresh"); refresh.clicked.connect(self.refresh)
        row.addWidget(refresh); row.addStretch(); l.addLayout(row)
        self.board=QWidget(); self.grid=QGridLayout(self.board); self.grid.setContentsMargins(0,0,0,0)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(self.board)
        l.addWidget(scroll, 3)
        self.recent=QPlainTextEdit(); self.recent.setReadOnly(True); l.addWidget(self.recent, 1)
        self._workers=[]; self._panes={}
        self._event_timer=QTimer(self); self._event_timer.setInterval(2000); self._event_timer.timeout.connect(self._tick_events)
    def hideEvent(self, event):
        self._event_timer.stop()
        super().hideEvent(event)
    def showEvent(self, event):
        super().showEvent(event)
        if not self._event_timer.isActive():
            self._event_timer.start()
        self._tick_events()
    def shutdown(self):
        self._event_timer.stop()
    def _keep(self, worker):
        self._workers.append(worker)
        worker.finished.connect(lambda w=worker: self._workers.remove(w) if w in self._workers else None)
    def refresh(self):
        self._tick_events()
    def _tick_events(self):
        w=Worker(lambda: api.get("/lanes/overview", timeout=12))
        w.done.connect(self._show_overview); w.failed.connect(lambda e: self.recent.setPlainText(str(e))); self._keep(w); w.start()
    def _show_overview(self, data):
        lanes=(data or {}).get("lanes") or []
        seen=set(); recent_lines=[]; index=0
        for lane in lanes:
            gate=lane.get("gate") or {}
            gid=gate.get("id")
            for side in lane.get("sides") or []:
                label=f"{gate.get('name') or 'Gate'} {(side.get('side') or '').title()}"
                key=f"{gid}:{side.get('side')}:{((side.get('camera') or {}).get('id'))}"
                seen.add(key)
                pane=self._panes.get(key)
                if pane is None:
                    pane=LanePane(label)
                    self._panes[key]=pane
                self.grid.addWidget(pane, index//2, index%2)
                index+=1
                pane.apply_event(side)
            for item in lane.get("recent") or []:
                when=(item.get("created_at") or "")[:19].replace("T"," ")
                recent_lines.append(f"{when}  {gate.get('name')}  {item.get('lane_direction')}  {item.get('plate') or '—'}  {item.get('characters') or ''}")
        for key, pane in list(self._panes.items()):
            if key not in seen:
                self.grid.removeWidget(pane); pane.deleteLater(); self._panes.pop(key, None)
        self.recent.setPlainText("\n".join(recent_lines[:40]) or "No car snapshots yet. Connect the cameras and wait for a vehicle.")


class LanePane(QFrame):
    def __init__(self, title):
        super().__init__(); self.setObjectName("card")
        l=QVBoxLayout(self)
        head=QLabel(title); head.setStyleSheet("font-size:18px;font-weight:700"); l.addWidget(head)
        self.snap=QLabel("No snapshot yet"); self.snap.setObjectName("video"); self.snap.setAlignment(Qt.AlignmentFlag.AlignCenter); self.snap.setMinimumHeight(180)
        self.crop=QLabel("Plate crop"); self.crop.setObjectName("video"); self.crop.setAlignment(Qt.AlignmentFlag.AlignCenter); self.crop.setMinimumHeight(70)
        self.plate=QLabel("—"); self.plate.setAlignment(Qt.AlignmentFlag.AlignCenter); self.plate.setStyleSheet("font-size:28px;font-weight:700;letter-spacing:6px")
        self.meta=QLabel("No capture yet"); self.meta.setWordWrap(True)
        l.addWidget(self.snap, 3); l.addWidget(QLabel("Cropped plate")); l.addWidget(self.crop, 1); l.addWidget(self.plate); l.addWidget(self.meta)
        self._last_image=None
    def apply_event(self, payload):
        payload=payload or {}
        cam=payload.get("camera") or {}
        last=payload.get("last") or {}
        plate=last.get("plate") or "—"
        chars=last.get("characters") or (" ".join(list(plate)) if plate not in {"", "—"} else "—")
        self.plate.setText(chars)
        name=cam.get("name") or "camera"
        self.meta.setText(f"{name}  ·  {last.get('plate_raw') or plate}  ·  {int(round((last.get('confidence') or 0)*100))}%")
        image_id=last.get("image_id") or last.get("id") or last.get("snapshot_url")
        if last.get("snapshot_url") and image_id != self._last_image:
            self._last_image=image_id
            w=Worker(lambda url=last["snapshot_url"]: api.get_bytes(url, timeout=8))
            w.done.connect(lambda jpeg: self._pix(self.snap, jpeg)); self._keep_local(w); w.start()
            if last.get("crop_url"):
                w=Worker(lambda url=last["crop_url"]: api.get_bytes(url, timeout=8))
                w.done.connect(lambda jpeg: self._pix(self.crop, jpeg)); self._keep_local(w); w.start()
    def _keep_local(self, worker):
        parent=self.parent()
        while parent is not None and not hasattr(parent, "_keep"):
            parent=parent.parent()
        if parent is not None:
            parent._keep(worker)
    def _pix(self, label, jpeg):
        image=QImage.fromData(jpeg)
        if image.isNull(): return
        pix=QPixmap.fromImage(image)
        label.setPixmap(pix.scaled(label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation))


class Dashboard(QWidget):
    def __init__(self):
        super().__init__(); self.layout=QVBoxLayout(self)
        title=QLabel("Overview"); title.setStyleSheet("font-size:24px;font-weight:700")
        self.layout.addWidget(title)
        self.grid=QGridLayout(); self.layout.addLayout(self.grid)
        self.alert=QLabel(""); self.alert.setWordWrap(True); self.layout.addWidget(self.alert)
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
            ("Revenue today", f"TZS {int(data.get('revenue_today') or 0):,}"),
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
        alerts=data.get("alerts") or []
        self.alert.setText("  ·  ".join(alerts) if alerts else "No hardware alerts.")


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
            ("hvx", "hvx — this site (NetSDK)"),
            ("rtsp", "rtsp — media extra (no SDK login)"),
            ("onvif", "onvif — not implemented"),
            ("simulated", "simulated — no hardware"),
        ):
            self.adapter.addItem(label, key)
        self.rtsp=QLineEdit()
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
            idx=self.gate.findData(camera.get("gate_id")); 
            if idx>=0: self.gate.setCurrentIndex(idx)
        for label,w in [("Name",self.name),("Camera IP",self.ip),("HVX SDK port",self.port),("Username",self.username),("Password",self.password),("Side",self.direction),("Lane",self.gate),("Adapter",self.adapter),("Controller IP (Board*)",self.controller),("Display IP (IpAddr*)",self.display),("RTSP URL (optional)",self.rtsp)]: form.addRow(label,w)
        save=QPushButton("Save Camera"); save.clicked.connect(self.accept); form.addRow(save)
    def payload(self):
        data={"name":self.name.text().strip(),"ip_address":self.ip.text().strip(),"sdk_port":int(self.port.text()),"username":self.username.text(),"lane_direction":self.direction.currentText(),"adapter_id":self.adapter.currentData(),"controller_ip":self.controller.text().strip(),"display_ip":self.display.text().strip(),"rtsp_url":self.rtsp.text().strip(),"gate_id":self.gate.currentData()}
        if self.password.text() or not self.camera:
            data["password"]=self.password.text()
        return data


class Cameras(QWidget):
    def __init__(self):
        super().__init__(); l=QVBoxLayout(self)
        row=QVBoxLayout(); heading=QHBoxLayout()
        title=QLabel("Cameras"); title.setStyleSheet("font-size:24px;font-weight:700")
        heading.addWidget(title); heading.addStretch(); row.addLayout(heading)
        tools=QHBoxLayout()
        add=QPushButton("Add Camera"); add.clicked.connect(self.add_camera); add.setVisible(api.can("cameras.manage"))
        seed=QPushButton("Add site cameras"); seed.clicked.connect(self.seed_site); seed.setVisible(api.can("cameras.manage"))
        discover=QPushButton("Discover"); discover.clicked.connect(self.discover)
        connect_all=QPushButton("Connect all"); connect_all.clicked.connect(self.connect_all)
        edit=QPushButton("Edit"); edit.clicked.connect(self.edit_camera); edit.setVisible(api.can("cameras.manage"))
        delete=QPushButton("Delete"); delete.clicked.connect(self.delete_camera); delete.setVisible(api.can("cameras.manage"))
        refresh=QPushButton("Refresh"); refresh.clicked.connect(self.refresh)
        for w in (add, seed, discover, connect_all, edit, delete, refresh): tools.addWidget(w)
        tools.addStretch(); row.addLayout(tools); l.addLayout(row)
        hint=QLabel("Live view is the moving SDK video stream, not the last car still. Add Camera or Add Gate anytime — default adapter is HVX. Connect all logs in camera IPs on port 30000.")
        hint.setWordWrap(True); l.addWidget(hint)
        self.table=QTableWidget(0,10); self.table.setHorizontalHeaderLabels(["ID","Name","Lane","Side","Camera","Controller","Display","Status","SDK","Error"])
        configure_table(self.table); l.addWidget(self.table, 1)
        self.rows=[]
        self.table.itemSelectionChanged.connect(self._on_select)
        live=QHBoxLayout()
        self.video=QLabel("Select a camera to open live view.")
        self.video.setObjectName("video")
        self.video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video.setMinimumHeight(200)
        self.video.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.plate_info=QLabel("These cameras read plates themselves after Connect all. FastALPR is a second, local OCR.")
        self.plate_info.setWordWrap(True)
        self.crop=QLabel()
        self.crop.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.crop.setMinimumWidth(180)
        self.crop.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        right=QVBoxLayout(); right.addWidget(self.plate_info); right.addWidget(self.crop, 1)
        live.addWidget(self.video, 3); live.addLayout(right, 2); l.addLayout(live, 1)
        actions=QHBoxLayout();
        self.connect_btn=QPushButton("SDK Connect"); self.connect_btn.clicked.connect(self.sdk_connect)
        self.probe_btn=QPushButton("Probe video"); self.probe_btn.clicked.connect(self.rtsp_probe)
        self.alpr_btn=QPushButton("FastALPR"); self.alpr_btn.clicked.connect(self.fastalpr)
        self.disconnect_btn=QPushButton("SDK Disconnect"); self.disconnect_btn.clicked.connect(self.sdk_disconnect)
        self.open_side_btn=QPushButton("Open this side"); self.open_side_btn.clicked.connect(self.open_this_side)
        self.snap_btn=QPushButton("Capture snapshot"); self.snap_btn.clicked.connect(self.capture_snapshot)
        actions.addWidget(self.connect_btn); actions.addWidget(self.probe_btn); actions.addWidget(self.alpr_btn); actions.addWidget(self.snap_btn); actions.addWidget(self.disconnect_btn); actions.addWidget(self.open_side_btn); actions.addStretch(); l.addLayout(actions)
        self._workers=[]
        self._snap_busy=False
        self._alpr_busy=False
        self._last_jpeg=b""
        self._last_overlay=None
        self._mjpeg=None
        self._snap_timer=QTimer(self); self._snap_timer.setInterval(250); self._snap_timer.timeout.connect(self._tick_snapshot)
        self._alpr_timer=QTimer(self); self._alpr_timer.setInterval(2000); self._alpr_timer.timeout.connect(self._tick_alpr)
        self._ready=False
        self._paint_busy=False
        self._shown_jpeg=b""
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
    def selected_camera(self):
        row=self.table.currentRow()
        if row<0 or row>=len(self.rows): return None
        return self.rows[row]
    def seed_site(self):
        w=Worker(api.seed_site); w.done.connect(lambda data:(QMessageBox.information(self,"Site cameras",f"Added {len(data.get('created') or [])} camera(s)."),self.refresh())); w.failed.connect(lambda e:QMessageBox.critical(self,"Site cameras",e)); self._keep(w); w.start()
    def discover(self):
        w=Worker(lambda: api.get("/cameras/discover", timeout=20)); w.done.connect(self._show_discover); w.failed.connect(lambda e:QMessageBox.critical(self,"Discover",e)); self._keep(w); w.start()
    def _show_discover(self, data):
        rows=data.get("cameras") or []
        text="\n".join(f"{r['ip_address']}  {r['name']}  {'reachable' if r.get('reachable') else 'no TCP'}  {'added' if r.get('already_added') else 'new'}" for r in rows) or "No cameras listed."
        QMessageBox.information(self,"Discover",text[:2000])
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
        self.refresh(); self._start_live()
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
        if isinstance(data, dict) and (data.get("plates") or data.get("annotated_url")):
            self._show_alpr(data)
        else:
            QMessageBox.information(self,title,str(data)[:1200])
        self._start_live()
    def sdk_connect(self): self._run(lambda cid: api.post(f"/cameras/{cid}/sdk/connect", timeout=25),"SDK Connect")
    def sdk_disconnect(self): self._run(lambda cid: api.post(f"/cameras/{cid}/sdk/disconnect"),"SDK Disconnect")
    def rtsp_probe(self): self._run(lambda cid: api.post(f"/cameras/{cid}/rtsp/probe"),"RTSP Probe")
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
    def _on_select(self):
        self._last_jpeg=b""; self._last_overlay=None; self._start_live()
    def hideEvent(self, event):
        self._stop_mjpeg(); self._snap_timer.stop(); self._alpr_timer.stop()
        super().hideEvent(event)
    def showEvent(self, event):
        super().showEvent(event)
        if not self._ready:
            self._ready=True
            self.refresh()
        self._start_live()
    def shutdown(self):
        self._snap_timer.stop(); self._alpr_timer.stop(); self._stop_mjpeg()
    def _stop_mjpeg(self):
        stream=self._mjpeg
        self._mjpeg=None
        _stop_thread(stream)
    def _start_live(self):
        cid=self.selected_id()
        if cid is None:
            self._stop_mjpeg(); self._snap_timer.stop(); self._alpr_timer.stop(); return
        if self._mjpeg is not None and self._mjpeg.camera_id==cid and self._mjpeg.isRunning():
            if not self._alpr_timer.isActive(): self._alpr_timer.start()
            return
        self._stop_mjpeg()
        self._snap_timer.stop()
        stream=MjpegStream(cid)
        stream.frame.connect(self._show_frame)
        stream.failed.connect(self._mjpeg_fail)
        self._mjpeg=stream
        stream.start()
        if not self._alpr_timer.isActive(): self._alpr_timer.start()
        self._tick_alpr()
    def _mjpeg_fail(self, err):
        self._live_fail(err)
        if self.selected_id() is not None and not self._snap_timer.isActive():
            self._snap_timer.start()
            self._tick_snapshot()
    def _set_pixmap(self, label, jpeg, overlay=None):
        image=QImage.fromData(jpeg)
        if image.isNull(): return False
        if overlay and label is self.video:
            image=self._paint_overlay(image, overlay)
        pix=QPixmap.fromImage(image)
        label.setPixmap(pix.scaled(label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation))
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
        cid=self.selected_id()
        if cid is None or self._snap_busy: return
        self._snap_busy=True
        w=Worker(lambda: api.get_bytes(f"/cameras/{cid}/snapshot.jpg", timeout=8))
        w.done.connect(self._show_frame); w.failed.connect(self._live_fail); w.finished.connect(lambda: setattr(self,"_snap_busy",False)); self._keep(w); w.start()
    def _show_frame(self, jpeg):
        if self._paint_busy or jpeg == self._shown_jpeg:
            return
        self._paint_busy=True
        try:
            self._last_jpeg=jpeg
            self._shown_jpeg=jpeg
            if not self._set_pixmap(self.video, jpeg, self._last_overlay):
                self.video.setText("Waiting for a JPEG frame")
        finally:
            self._paint_busy=False
    def _live_fail(self, err):
        text=str(err or "")
        if "409" in text or "ffmpeg" in text.lower() or "ffprobe" in text.lower():
            self.video.setText("Waiting for a camera JPEG.\nSDK login can succeed without RTSP.\nIf another SDK client is open, close it and click SDK Connect again.")
            return
        self.video.setText(text)
    def _tick_alpr(self):
        cid=self.selected_id()
        if cid is None or self._alpr_busy: return
        self._alpr_busy=True
        w=Worker(lambda: api.get(f"/cameras/{cid}/plates", timeout=8))
        w.done.connect(self._show_alpr); w.failed.connect(lambda e: self.plate_info.setText(e)); w.finished.connect(lambda: setattr(self,"_alpr_busy",False)); self._keep(w); w.start()
    def _show_alpr(self, data):
        payload=data if isinstance(data, dict) else {}
        alpr=payload.get("alpr") if "alpr" in payload else payload
        native=payload.get("native") or {}
        fusion=payload.get("fusion") or {}
        resolved=payload.get("resolved_plate") or fusion.get("resolved_plate") or native.get("plate") or ""
        self._last_overlay=payload.get("overlay") or native.get("bbox")
        if isinstance(self._last_overlay, dict) and "x1" in self._last_overlay:
            if "image_width" not in self._last_overlay:
                self._last_overlay={**self._last_overlay, "label": resolved or native.get("plate") or "", "image_width": native.get("image_width") or 0, "image_height": native.get("image_height") or 0}
            if self._last_jpeg:
                self._set_pixmap(self.video, self._last_jpeg, self._last_overlay)
        if not isinstance(alpr, dict):
            alpr={}
        plates=alpr.get("plates") or []
        src=payload.get("live_source") or ""
        fps=payload.get("live_fps")
        live_bit=f"{src} {fps:g} fps".strip() if fps else src
        if resolved:
            method=fusion.get("method") or ("NATIVE" if native.get("plate") else "")
            self.plate_info.setText(f"{resolved}   ·   {method}" + (f"   ·   {live_bit}" if live_bit else ""))
        elif native.get("plate"):
            self.plate_info.setText(f"{native.get('plate')}   ·   NATIVE" + (f"   ·   {live_bit}" if live_bit else ""))
        else:
            waiting="Waiting for the camera to read a plate. Close any other SDK client if live video works but plates never arrive."
            self.plate_info.setText((f"Live {live_bit}. " if live_bit else "") + waiting)
        best=alpr.get("best") or (plates[0] if plates else None)
        crop=(best or {}).get("crop_url") or alpr.get("annotated_url")
        if crop:
            w=Worker(lambda: api.get_bytes(crop, timeout=8))
            w.done.connect(lambda jpeg: self._set_pixmap(self.crop, jpeg)); self._keep(w); w.start()


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


class VehicleDialog(QDialog):
    def __init__(self, vehicle=None, plans=None):
        super().__init__(); self.setWindowTitle("Edit vehicle" if vehicle else "Register plate")
        form=QFormLayout(self)
        self.plate=QLineEdit(); self.owner=QLineEdit(); self.plan=QComboBox(); self.enabled=QComboBox(); self.enabled.addItems(["Yes","No"]); self.notes=QLineEdit()
        for p in plans or []: self.plan.addItem(p["name"], p["id"])
        if vehicle:
            self.plate.setText(vehicle.get("plate") or ""); self.owner.setText(vehicle.get("owner_name") or "")
            idx=self.plan.findData(vehicle.get("plan_id"));
            if idx>=0: self.plan.setCurrentIndex(idx)
            self.enabled.setCurrentText("Yes" if vehicle.get("enabled") else "No")
            self.notes.setText(vehicle.get("notes") or "")
        form.addRow("Plate", self.plate); form.addRow("Owner", self.owner); form.addRow("Plan", self.plan)
        form.addRow("Enabled", self.enabled); form.addRow("Notes", self.notes)
        save=QPushButton("Save"); save.clicked.connect(self.accept); form.addRow(save)
    def payload(self):
        return {
            "plate": self.plate.text().strip(), "owner_name": self.owner.text().strip(),
            "plan_id": self.plan.currentData(), "enabled": self.enabled.currentText()=="Yes",
            "notes": self.notes.text().strip(),
        }


class Sessions(QWidget):
    def __init__(self):
        super().__init__(); l=QVBoxLayout(self)
        title=QLabel("Parking sessions"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        note=QLabel("Plate-first sessions. A vehicle can exit at a different gate from the one it entered.")
        note.setWordWrap(True); l.addWidget(note)
        self.table=QTableWidget(0,8); self.table.setHorizontalHeaderLabels(["Plate","Kind","Status","Receipt","Entry","Due","Paid","Gate"])
        configure_table(self.table); l.addWidget(self.table, 1)
        row=QHBoxLayout()
        pay=QPushButton("Record kiosk payment"); pay.clicked.connect(self.pay); pay.setVisible(api.can("payments.create"))
        receipt=QPushButton("Show / print receipt"); receipt.clicked.connect(self.print_receipt)
        refresh=QPushButton("Refresh"); refresh.clicked.connect(self.refresh)
        row.addWidget(pay); row.addWidget(receipt); row.addWidget(refresh); row.addStretch(); l.addLayout(row)
        self.rows=[]; self.refresh()
    def refresh(self):
        try: self.rows=api.get("/sessions")
        except Exception as e: QMessageBox.warning(self,"Sessions",str(e)); return
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
        if not body:
            try:
                slip=api.get(f"/sessions/{s['id']}/receipt")
                body=slip.get("body_text") or ""
                path=(slip.get("payload") or {}).get("path") or path
            except Exception:
                pass
        show_printable_receipt(self, body, path)
        self.refresh()
    def pay(self):
        s=self.selected()
        if not s: QMessageBox.information(self,"Payment","Select a session first."); return
        if QMessageBox.question(self,"Record payment",f"Record kiosk payment for {s.get('plate')}?")!=QMessageBox.Yes: return
        try:
            api.post(f"/sessions/{s['id']}/pay", {"method": "KIOSK_CASH"})
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self,"Payment",str(e))


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
        note=QLabel("Season, VIP, staff, and tenant plates open the gate automatically when the camera reads them.")
        note.setWordWrap(True); l.addWidget(note)
        self.table=QTableWidget(0,6); self.table.setHorizontalHeaderLabels(["Plate","Owner","Plan","Auto-open","Enabled","Until"])
        configure_table(self.table); l.addWidget(self.table, 1)
        row=QHBoxLayout()
        add=QPushButton("Register plate"); add.clicked.connect(self.add); add.setVisible(api.can("subscribers.manage"))
        edit=QPushButton("Edit"); edit.clicked.connect(self.edit); edit.setVisible(api.can("subscribers.manage"))
        delete=QPushButton("Delete"); delete.clicked.connect(self.delete); delete.setVisible(api.can("subscribers.manage"))
        refresh=QPushButton("Refresh"); refresh.clicked.connect(self.refresh)
        row.addWidget(add); row.addWidget(edit); row.addWidget(delete); row.addWidget(refresh); row.addStretch(); l.addLayout(row)
        self.rows=[]; self.refresh()
    def refresh(self):
        try: self.rows=api.get("/vehicles")
        except Exception as e: QMessageBox.warning(self,"Vehicles",str(e)); return
        self.table.setRowCount(len(self.rows))
        for r,v in enumerate(self.rows):
            vals=[v["plate"], v.get("owner_name") or "—", v.get("plan_name") or "—", "Yes" if v.get("auto_open") else "No", "Yes" if v.get("enabled") else "No", (v.get("valid_until") or "—")[:10]]
            for c,val in enumerate(vals): self.table.setItem(r,c,QTableWidgetItem(str(val)))
    def selected(self):
        row=self.table.currentRow()
        if row<0 or row>=len(self.rows): return None
        return self.rows[row]
    def add(self):
        d=VehicleDialog(plans=api.get("/access-plans"))
        if d.exec():
            try: api.post("/vehicles", d.payload()); self.refresh()
            except Exception as e: QMessageBox.critical(self,"Register plate",str(e))
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


class Fees(QWidget):
    def __init__(self):
        super().__init__(); l=QVBoxLayout(self)
        title=QLabel("Tariffs"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        note=QLabel("Current site tariff. Change rates in configuration — do not edit program constants.")
        note.setWordWrap(True); l.addWidget(note)
        form=QFormLayout()
        self.entry=QLineEdit(); self.exit=QLineEdit()
        from datetime import datetime, timezone, timedelta
        now=datetime.now(timezone.utc)
        self.entry.setText((now-timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S"))
        self.exit.setText(now.strftime("%Y-%m-%dT%H:%M:%S"))
        form.addRow("Entry (UTC)", self.entry); form.addRow("Exit (UTC)", self.exit)
        l.addLayout(form)
        quote=QPushButton("Quote Car1 fee"); quote.clicked.connect(self.quote); l.addWidget(quote)
        self.out=QPlainTextEdit(); self.out.setReadOnly(True); l.addWidget(self.out, 1)
        self.load_tariff()
    def load_tariff(self):
        try: data=api.get("/fees/tariff")
        except Exception as e: self.out.setPlainText(str(e)); return
        self.out.setPlainText(json.dumps(data, indent=2, default=str))
    def quote(self):
        try:
            data=api.post("/fees/quote",{"entry_time":self.entry.text().strip(),"exit_time":self.exit.text().strip(),"car_type":"Car1"})
            self.out.setPlainText(json.dumps(data, indent=2, default=str))
        except Exception as e:
            QMessageBox.critical(self,"Fee",str(e))


class SystemHealth(QWidget):
    def __init__(self):
        super().__init__()
        l=QVBoxLayout(self)
        title=QLabel("System Health"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        note=QLabel("Technician view. Parking stays up when one camera or the HVX host is degraded.")
        note.setWordWrap(True); l.addWidget(note)
        self.state=QLabel("…"); self.state.setStyleSheet("font-size:18px;font-weight:700"); l.addWidget(self.state)
        self.info=QPlainTextEdit(); self.info.setReadOnly(True); l.addWidget(self.info, 1)
        row=QHBoxLayout(); refresh=QPushButton("Refresh"); refresh.clicked.connect(self.refresh)
        row.addWidget(refresh); row.addStretch(); l.addLayout(row)
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
        self.info.setPlainText(json.dumps(data, indent=2, default=str))


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
        row.addWidget(b); row.addWidget(a); row.addStretch(); l.addLayout(row)
    def check_alpr(self):
        try:
            data=api.get("/alpr/status")
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


class SettingsPage(QWidget):
    def __init__(self, window):
        super().__init__(); self.window=window; l=QVBoxLayout(self)
        title=QLabel("Settings"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        form=QFormLayout()
        combo=QComboBox(); combo.addItems(["Light","Dark"]); combo.currentTextChanged.connect(self.change)
        form.addRow("Appearance", combo)
        l.addLayout(form)
        if api.can("simulation.run"):
            park=QLabel("Parking rules (simulation and live plates share this)."); park.setWordWrap(True); l.addWidget(park)
            self.receipt=QCheckBox("Receipt must be taken before the entry barrier opens")
            self.policy=QComboBox(); self.policy.addItems(["REQUIRE_TAKEN_BEFORE_OPEN","PRINT_AND_OPEN","PRINT_OPTIONAL","OFF"])
            self.pay=QCheckBox("Exit stays closed until the session is paid")
            self.prompt=QLineEdit()
            self.printer=QComboBox(); self.printer.setEditable(False)
            printer_note=QLabel("USB A4 printer: plug it in, pick it here, Save. A detected car prints then the gate opens.")
            printer_note.setWordWrap(True)
            l.addWidget(self.receipt); pf=QFormLayout(); pf.addRow("Receipt policy", self.policy); pf.addRow("Pay prompt", self.prompt); pf.addRow("USB / A4 printer", self.printer); l.addLayout(pf)
            l.addWidget(self.pay); l.addWidget(printer_note)
            row=QHBoxLayout()
            save=QPushButton("Save parking rules"); save.clicked.connect(self.save_parking)
            test=QPushButton("Print test page"); test.clicked.connect(self.test_printer)
            row.addWidget(save); row.addWidget(test); row.addStretch(); l.addLayout(row)
            self.park_status=QLabel(""); self.park_status.setWordWrap(True); l.addWidget(self.park_status)
        web=QPushButton("Open web UI"); web.clicked.connect(self.open_web); l.addWidget(web)
        l.addStretch()
    def showEvent(self, event):
        super().showEvent(event)
        if api.can("simulation.run") and not getattr(self, "_loaded", False):
            self._loaded=True
            self.load_parking()
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
            self.park_status.setText("Saved. Entry prints on that printer, then the gate opens." if name else "Saved. Receipts are stored as files until you pick a printer.")
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
        super().__init__(); self.setWindowTitle("SmartPark Edge")
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
        self.add_page("Dashboard", Dashboard)
        if api.can("hardware.view") or api.can("dashboard.view"):
            self.add_page("System Health", SystemHealth)
        if api.can("cameras.view"): self.add_page("Live Gates", Lanes)
        if api.can("sessions.view") or api.can("fees.view"): self.add_page("Sessions", Sessions)
        if api.can("subscribers.view"): self.add_page("Vehicles", Vehicles)
        if api.can("payments.view") or api.can("fees.view"): self.add_page("Payments", Payments)
        if api.can("fees.view"): self.add_page("Tariffs", Fees)
        if api.can("cameras.view"): self.add_page("Cameras", Cameras)
        if api.can("gates.view"): self.add_page("Gates", Gates)
        if api.can("users.view"): self.add_page("Users", Users)
        self.add_page("Settings", lambda: SettingsPage(self))
        if api.can("hardware.view"): self.add_page("Hardware Lab", Hardware)
        if api.can("simulation.run"): self.add_page("Simulation", SimPage)
        self.nav.currentRowChanged.connect(self._show_page)
        self.apply_theme("Light")
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
