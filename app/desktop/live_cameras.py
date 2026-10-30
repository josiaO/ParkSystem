"""Gate viewing, explicit node assignment, and camera device management."""
import json
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFormLayout, QGridLayout,
    QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from app.services.live_pair import lane_options, pair_lane_cameras, reconcile_slots
from .api import api
from .common import Worker, action_label, is_technician
from .presentation import configure_table, label_for
from .live_pane import CameraLivePane


def runtime_api():
    """Use this PC's local operational API for camera and gate hardware."""
    # Keep lightweight desktop fixtures and older operator clients compatible;
    # the production ApiClient always exposes the split runtime plane.
    resolver = getattr(api, "runtime_client", None)
    return resolver() if callable(resolver) else api

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
        self.direction=QComboBox()
        self.direction.addItem("Entry", "ENTRY")
        self.direction.addItem("Exit", "EXIT")
        self.direction.addItem("Bidirectional", "BOTH")
        self.adapter=QComboBox()
        for key, label in (
            ("hvx", "hvx"),
            ("rtsp", "rtsp"),
            ("dahua", "dahua"),
            ("hikvision", "hikvision"),
            ("onvif", "onvif"),
            ("simulated", "simulated"),
        ):
            self.adapter.addItem(label, key)
        self.rtsp=QLineEdit()
        self.rtsp.setPlaceholderText("Leave blank to discover")
        self.ffmpeg_profile=QComboBox(); self.ffmpeg_profile.addItems(["LOW_LATENCY_LAN","COMPATIBLE","LOSSY_NETWORK","VENDOR_SPECIAL"])
        self.transport=QComboBox(); self.transport.addItems(["TCP","UDP","AUTO"])
        self.recognition=QComboBox()
        self.recognition.addItem("Use the site default", "")
        for key, label in (
            ("NATIVE_ONLY", "Use camera recognition"),
            ("FASTALPR_ONLY", "Use FastALPR (read a plate crop)"),
            ("HYBRID", "Use both"),
            ("VIDEO_ONLY", "Video only"),
        ):
            self.recognition.addItem(label, key)
        self.controller=QLineEdit(); self.display=QLineEdit()
        self.gate=QComboBox(); self.gate.addItem("No gate — monitoring only", None)
        try:
            for g in runtime_api().get("/gates"): self.gate.addItem(g["name"], g["id"])
        except Exception:
            pass
        if camera:
            self.name.setText(camera["name"]); self.ip.setText(camera["ip_address"]); self.port.setText(str(camera["sdk_port"]))
            self.username.setText(camera["username"])
            dir_idx=self.direction.findData(str(camera.get("lane_direction") or "ENTRY"))
            if dir_idx>=0: self.direction.setCurrentIndex(dir_idx)
            self.rtsp.setText(camera.get("rtsp_url") or "")
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
        for label,w in [("Name",self.name),("Camera address",self.ip),("Username",self.username),("Password",self.password),("Direction",self.direction),("Gate",self.gate),("Recognition",self.recognition)]: form.addRow(label,w)
        advanced=QGroupBox("Advanced")
        advanced_form=QFormLayout(advanced)
        for label,w in [("SDK port",self.port),("Adapter",self.adapter),("Controller IP",self.controller),("Display IP",self.display),("RTSP URI",self.rtsp),("FFmpeg profile",self.ffmpeg_profile),("RTSP transport",self.transport)]:
            advanced_form.addRow(label,w)
        advanced.setVisible(is_technician())
        form.addRow(advanced)
        save=QPushButton("Save Camera"); save.clicked.connect(self.accept); form.addRow(save)
    def payload(self):
        data={"name":self.name.text().strip(),"ip_address":self.ip.text().strip(),"sdk_port":int(self.port.text() or "30000"),"username":self.username.text(),"lane_direction":self.direction.currentData() or "ENTRY","adapter_id":self.adapter.currentData(),"recognition_mode":self.recognition.currentData() or "","controller_ip":self.controller.text().strip(),"display_ip":self.display.text().strip(),"rtsp_url":self.rtsp.text().strip(),"ffmpeg_profile":self.ffmpeg_profile.currentText(),"rtsp_transport":self.transport.currentText(),"gate_id":self.gate.currentData()}
        if self.password.text() or not self.camera:
            data["password"]=self.password.text()
        return data


class Cameras(QWidget):
    def __init__(self):
        super().__init__(); l=QVBoxLayout(self)
        self.setProperty("videoWorkspace", True)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(0)
        self.tabs=QTabWidget()
        live=QWidget(); live_l=QVBoxLayout(live)
        lane_row=QGridLayout()
        self.layout_mode=QComboBox()
        self.layout_mode.addItems(["1 camera", "2 cameras", "All cameras"])
        self.layout_mode.setCurrentIndex(1)
        self.layout_mode.currentIndexChanged.connect(self._on_layout)
        lane_row.addWidget(label_for("&Show", self.layout_mode), 0, 0)
        lane_row.addWidget(self.layout_mode, 0, 1)
        self.lane=QComboBox(); self.lane.currentIndexChanged.connect(self._lane_changed)
        lane_row.addWidget(label_for("&Lane preset", self.lane), 0, 2)
        lane_row.addWidget(self.lane, 0, 3, 1, 2)
        lane_row.setColumnStretch(3, 1)
        fill_lane=QPushButton("Fill both from lane"); fill_lane.clicked.connect(lambda: self._start_pair(True))
        lane_row.addWidget(fill_lane, 1, 0, 1, 2)
        self.scope_hint=QLabel(""); self.scope_hint.setWordWrap(True)
        self.assign_node=QPushButton("Assign PC to this gate…")
        self.assign_node.setVisible(api.can("settings.manage"))
        self.assign_node.clicked.connect(self._assign_recognition_owner)
        lane_row.addWidget(self.assign_node, 1, 2, 1, 2)
        refresh_live=QPushButton(action_label("Refresh live", "F5")); refresh_live.clicked.connect(lambda: self._start_pair(False))
        lane_row.addWidget(refresh_live, 1, 4)
        self.view_tools=QWidget()
        self.view_tools.setLayout(lane_row)
        live_l.setContentsMargins(3, 3, 3, 3)
        self.live_grid=QGridLayout()
        self.live_grid.setColumnStretch(0, 1)
        self.live_grid.setColumnStretch(1, 1)
        self.pane_a=CameraLivePane("Left")
        self.pane_b=CameraLivePane("Right")
        self.extra_panes=[]
        self._armed_pane=None
        self.pane_a.armed.connect(self.arm_pane)
        self.pane_b.armed.connect(self.arm_pane)
        for i in range(1, 10):
            sc=QShortcut(QKeySequence(str(i)), live)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(lambda n=i: self.arm_visible(n))
        self.live_grid.addWidget(self.pane_a, 0, 0)
        self.live_grid.addWidget(self.pane_b, 0, 1)
        live_host=QWidget(); live_host.setLayout(self.live_grid)
        live_l.addWidget(live_host, 1)

        ips=QWidget(); ips_l=QVBoxLayout(ips)
        ips_l.addWidget(self.view_tools)
        ips_l.addWidget(self.scope_hint)
        tools=QGridLayout()
        add=QPushButton(action_label("Add Camera", "Ctrl+N")); add.clicked.connect(self.add_camera); add.setVisible(api.can("cameras.manage")); add.setToolTip("Add Camera (Ctrl+N)")
        discover=QPushButton("Discover"); discover.clicked.connect(self.discover); discover.setVisible(api.can("cameras.manage"))
        onboard=QPushButton("Onboard wizard"); onboard.clicked.connect(self.onboard); onboard.setVisible(api.can("cameras.manage"))
        connect_all=QPushButton("Connect all"); connect_all.clicked.connect(self.connect_all)
        edit=QPushButton(action_label("Edit", "Ctrl+E")); edit.clicked.connect(self.edit_camera); edit.setVisible(api.can("cameras.manage")); edit.setToolTip("Edit (Ctrl+E)")
        delete=QPushButton(action_label("Delete", "Del")); delete.clicked.connect(self.delete_camera); delete.setVisible(api.can("cameras.manage")); delete.setToolTip("Delete (Del)")
        refresh=QPushButton(action_label("Refresh", "F5")); refresh.clicked.connect(self.refresh); refresh.setToolTip("Refresh (F5)")
        self.seed_button=QPushButton("Load example cameras…")
        self.seed_button.setVisible(api.can("cameras.manage"))
        self.seed_button.clicked.connect(self.seed_site)
        for index, widget in enumerate((add, edit, delete, refresh, discover, onboard, connect_all, self.seed_button)):
            tools.addWidget(widget, index // 4, index % 4)
        ips_l.addLayout(tools)
        ips_hint=QLabel("Cameras on this site. Add one to start live monitoring and plate recognition.")
        ips_hint.setWordWrap(True); ips_l.addWidget(ips_hint)
        self.table=QTableWidget(0,10); self.table.setHorizontalHeaderLabels(["ID","Name","Location","Direction","Address","Controller","Display","Health","SDK","Detail"])
        configure_table(self.table); ips_l.addWidget(self.table, 1)
        self.empty_devices=QLabel("")
        self.empty_devices.setWordWrap(True)
        ips_l.addWidget(self.empty_devices)
        self.stream_info=QLabel("Stream profiles appear after Connect. Live and recognition share one gateway producer.")
        self.stream_info.setWordWrap(True)
        self.stream_info.setVisible(is_technician())
        ips_l.addWidget(self.stream_info)
        actions=QGridLayout()
        tech=is_technician()
        self.connect_btn=QPushButton("Connect"); self.connect_btn.clicked.connect(self.sdk_connect); self.connect_btn.setVisible(tech)
        self.probe_btn=QPushButton("Test Video"); self.probe_btn.clicked.connect(self.rtsp_probe); self.probe_btn.setVisible(tech)
        self.onvif_btn=QPushButton("Discover Streams"); self.onvif_btn.clicked.connect(self.onvif_discover); self.onvif_btn.setVisible(tech)
        self.alpr_btn=QPushButton("Test Recognition"); self.alpr_btn.clicked.connect(self.fastalpr); self.alpr_btn.setVisible(tech)
        self.disconnect_btn=QPushButton("Disconnect camera"); self.disconnect_btn.clicked.connect(self.sdk_disconnect); self.disconnect_btn.setVisible(tech)
        self.open_side_btn=QPushButton(action_label("Manual open", "F8")); self.open_side_btn.clicked.connect(self.open_this_side); self.open_side_btn.setToolTip("Open this barrier (F8)")
        self.close_side_btn=QPushButton(action_label("Manual close", "F9")); self.close_side_btn.clicked.connect(self.close_this_side); self.close_side_btn.setToolTip("Close this barrier (F9)")
        self.snap_btn=QPushButton("Capture snapshot"); self.snap_btn.clicked.connect(self.capture_snapshot)
        for index, widget in enumerate((self.connect_btn, self.probe_btn, self.onvif_btn, self.alpr_btn, self.snap_btn, self.disconnect_btn, self.open_side_btn, self.close_side_btn)):
            actions.addWidget(widget, index // 4, index % 4)
        ips_l.addLayout(actions)
        if not tech:
            for col in (0, 4, 5, 6, 8, 9):
                self.table.setColumnHidden(col, True)

        self.tabs.addTab(live, "Live")
        self.tabs.addTab(ips, "Devices")
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
        try: rows=runtime_api().get("/cameras")
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
        self.empty_devices.setText("" if rows else "No cameras configured. Add a camera to start live monitoring and plate recognition.")
        self._fill_lanes()
        self._maybe_start_pair()
    def selected_camera(self):
        row=self.table.currentRow()
        if row<0 or row>=len(self.rows): return None
        return self.rows[row]
    def seed_site(self):
        if not api.can("cameras.manage"):
            return
        answer=QMessageBox.question(self, "Load example cameras", "Add example gates and cameras as a setup shortcut? Review and edit their addresses and assignments before use. Existing cameras are preserved. This does not connect cameras or assign recognition to this PC.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        worker=Worker(runtime_api().seed_site)
        worker.done.connect(lambda result: (QMessageBox.information(self, "Example cameras", f"Added {len(result.get('created', []))} cameras; kept {len(result.get('skipped', []))} existing cameras. Review the setup before connecting."), self.refresh()))
        worker.failed.connect(lambda error: QMessageBox.critical(self, "Example cameras", error))
        self._keep(worker)
        worker.start()

    def discover(self):
        w=Worker(lambda: runtime_api().get("/cameras/discover?scan_lan=true", timeout=45)); w.done.connect(self._show_discover); w.failed.connect(lambda e:QMessageBox.critical(self,"Discover",e)); self._keep(w); w.start()
    def onboard(self):
        ip, ok = QInputDialog.getText(self, "Add Camera", "Camera address")
        if not ok or not str(ip).strip():
            return
        payload={"ip_address": str(ip).strip(), "username": "admin", "password": "admin"}
        w=Worker(lambda: runtime_api().post("/cameras/onboard/probe", payload, timeout=20))
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
            w=Worker(lambda: runtime_api().post("/cameras", dlg.payload())); w.done.connect(lambda _: self.refresh()); w.failed.connect(lambda e:QMessageBox.critical(self,"Add Camera",e)); self._keep(w); w.start()
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
        w=Worker(lambda: runtime_api().post("/cameras/import-discovered", payload, timeout=60))
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
            try: runtime_api().post("/cameras",d.payload()); self.refresh()
            except Exception as e: QMessageBox.critical(self,"Add camera",str(e))
    def edit_camera(self):
        cam=self.selected_camera()
        if not cam: QMessageBox.information(self,"Edit camera","Select a camera first."); return
        d=CameraDialog(cam)
        if d.exec():
            try: runtime_api().patch(f"/cameras/{cam['id']}",d.payload()); self.refresh()
            except Exception as e: QMessageBox.critical(self,"Edit camera",str(e))
    def delete_camera(self):
        cam=self.selected_camera()
        if not cam: QMessageBox.information(self,"Delete camera","Select a camera first."); return
        if QMessageBox.question(self,"Delete camera",f"Delete {cam['name']}?")!=QMessageBox.Yes: return
        try: runtime_api().delete(f"/cameras/{cam['id']}"); self.refresh()
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
    def sdk_connect(self): self._run(lambda cid: runtime_api().post(f"/cameras/{cid}/sdk/connect", timeout=25),"Connect")
    def sdk_disconnect(self):
        if QMessageBox.question(self, "Disconnect camera", "Disconnect this camera? Live video for it stops until someone connects it again.") != QMessageBox.Yes:
            return
        self._run(lambda cid: runtime_api().post(f"/cameras/{cid}/sdk/disconnect"), "Disconnect camera")
    def rtsp_probe(self): self._run(lambda cid: runtime_api().post(f"/cameras/{cid}/rtsp/probe"),"RTSP Probe")
    def onvif_discover(self): self._run(lambda cid: runtime_api().post(f"/cameras/{cid}/onvif/discover", timeout=20),"ONVIF profiles")
    def fastalpr(self): self._run(lambda cid: runtime_api().post(f"/cameras/{cid}/alpr/recognize", timeout=30),"FastALPR")
    def capture_snapshot(self): self._run(lambda cid: runtime_api().post(f"/cameras/{cid}/snapshot/capture", timeout=12),"Snapshot")
    def open_this_side(self):
        self.command_barrier("open")
    def close_this_side(self):
        self.command_barrier("close")
    def command_barrier(self, action="open"):
        cam=self.selected_camera()
        verb="close" if action=="close" else "open"
        title="Close this side" if verb=="close" else "Open this side"
        if not cam: QMessageBox.information(self,title,"Select a camera in Devices first."); return
        side=cam.get("side") or cam.get("lane_direction") or "this side"
        prompt=f"{'Close' if verb=='close' else 'Pulse'} only {cam.get('name') or side} — not the other side of this lane?"
        if QMessageBox.question(self,title,prompt)!=QMessageBox.Yes: return
        reason,ok=QInputDialog.getText(self,title,"Reason", text=f"manual {verb}")
        if ok and reason:
            try: QMessageBox.information(self,"Barrier",str(runtime_api().post(f"/cameras/{cam['id']}/barrier/open",{"reason":reason,"action":verb}, timeout=20)))
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
        elif self.lane.count() > 1:
            self.lane.setCurrentIndex(1)
        self.lane.blockSignals(False)
        self._refresh_recognition_scope()
    def _refresh_recognition_scope(self):
        def work():
            return runtime_api().get("/runtime/recognition-scope", timeout=8)
        w=Worker(work)
        w.done.connect(self._show_recognition_scope)
        w.failed.connect(lambda error: self.scope_hint.setText(f"Recognition status unavailable: {error}"))
        self._keep(w); w.start()
    def _assign_recognition_owner(self):
        gid=self.lane.currentData()
        if gid is None:
            QMessageBox.information(self, "Assign recognition", "Choose one gate, not All cameras.")
            return
        if QMessageBox.question(self, "Assign recognition", f"Assign this PC to {self.lane.currentText()} entry and exit only? Other gates will not be recognized on this PC.") != QMessageBox.Yes:
            return
        self.assign_node.setEnabled(False)
        worker=Worker(lambda: runtime_api().put("/runtime/recognition-owner", {"gate_id": gid}, timeout=8))
        worker.done.connect(self._show_recognition_scope)
        worker.failed.connect(lambda error: QMessageBox.critical(self, "Recognition assignment failed", error))
        worker.finished.connect(lambda: self.assign_node.setEnabled(True))
        self._keep(worker); worker.start()
    def _show_recognition_scope(self, data):
        body=data if isinstance(data, dict) else {}
        text=str(body.get("detail") or "")
        if hasattr(self, "scope_hint"):
            self.scope_hint.setText(text)
        self.assign_node.setEnabled(not body.get("pinned", False))
        if not getattr(self, "_owner_view_loaded", False) and body.get("gate_id") is not None:
            index=self.lane.findData(body["gate_id"])
            if index >= 0:
                self._owner_view_loaded=True
                self.lane.setCurrentIndex(index)
                self._start_pair(True)
    def _lane_changed(self):
        self._pair_from_lane_pending=True
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
            pane.armed.connect(self.arm_pane)
            self.extra_panes.append(pane)
            index=len(self.extra_panes) + 1
            self.live_grid.addWidget(pane, index // 2, index % 2)
        for i, pane in enumerate(self.extra_panes):
            show=i < needed
            pane.setVisible(show)
            if not show:
                pane.stop_live()
    def arm_pane(self, pane):
        self._armed_pane=pane
        for p in self._all_panes():
            if p is pane:
                p.setStyleSheet("CameraLivePane { border: 2px solid #0E7C72; }")
                p.target_chip.setText("Selected side")
            else:
                p.setStyleSheet("")
                p.target_chip.setText("")
    def arm_visible(self, n):
        panes=[p for p in self._all_panes() if p.isVisible()]
        if not (1 <= n <= len(panes)):
            return
        self.arm_pane(panes[n-1])
    def shortcut_pane(self):
        def usable(pane):
            return pane is not None and pane.isVisible() and pane.camera
        if usable(self._armed_pane):
            return self._armed_pane
        w=QApplication.focusWidget()
        for candidate in self._all_panes():
            if usable(candidate) and w is not None and (candidate is w or candidate.isAncestorOf(w)):
                self.arm_pane(candidate)
                return candidate
        return None
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
        from_lane=from_lane or getattr(self, "_pair_from_lane_pending", False)
        self._pair_from_lane_pending=False
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
        left, right=reconcile_slots(self.rows, self.pane_a.camera_id(), self.pane_b.camera_id(), self.lane.currentData())
        self.pane_a.set_camera(left)
        if mode != 0:
            self.pane_b.set_camera(right)
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
        s=Worker(lambda: runtime_api().get(f"/cameras/{cid}/streams", timeout=8))
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
