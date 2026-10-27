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

from .api import api, stream_http_error
from .desk import ReportsPage, health_sentences
from .theme import APPEARANCES, apply_appearance
from .presentation import configure_table, label_for, page_viewport, prepare_page
from .shell import DesktopShell


from .common import (Worker, _stop_thread, action_label, available_screen, fit_window_to_screen,
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


from .streams import MjpegStream, pop_latest_mjpeg, _pop_raw_jpegs


class Login(QDialog):
    def __init__(self):
        super().__init__(); self.setWindowTitle(f"{PRODUCT_NAME} — Sign In")
        self.setMinimumWidth(360); self.setMaximumWidth(460)
        l=QVBoxLayout(self); l.setContentsMargins(28,28,28,28); l.setSpacing(8)
        brand=QLabel(PRODUCT_NAME); brand.setStyleSheet("font-size:18px;font-weight:700;letter-spacing:-0.2px")
        tag=QLabel(PRODUCT_TAGLINE)
        tag.setObjectName("muted")
        title=QLabel("Sign in"); title.setStyleSheet("font-size:22px;font-weight:700;margin-top:10px")
        self.sub=QLabel("Sign in with the first-run admin password shown at setup")
        self.sub.setObjectName("muted"); self.sub.setWordWrap(True)
        self.user=QLineEdit("admin"); self.user.setPlaceholderText("Username")
        self.pwd=QLineEdit(); self.pwd.setPlaceholderText("Password"); self.pwd.setEchoMode(QLineEdit.Password)
        btn=QPushButton("&Sign in"); btn.clicked.connect(self.login)
        btn.setDefault(True); btn.setProperty("primary", True)
        l.addWidget(brand); l.addWidget(tag); l.addWidget(title); l.addWidget(self.sub)
        l.addSpacing(8)
        l.addWidget(label_for("&Username", self.user)); l.addWidget(self.user)
        l.addWidget(label_for("&Password", self.pwd)); l.addWidget(self.pwd)
        l.addSpacing(6); l.addWidget(btn)
        self.user.setFocus()
        fit_window_to_screen(self, (420, 420), min_size=(360, 360))
        QTimer.singleShot(0, self._prefill)
    def _prefill(self):
        try:
            import httpx
            setup=httpx.get(f"{api.base_url}/auth/setup", timeout=3).json()
            if setup.get("username"): self.user.setText(setup["username"])
            if setup.get("password"):
                self.pwd.setText(setup["password"])
            else:
                self.pwd.clear()
            if setup.get("hint"): self.sub.setText(setup["hint"])
        except Exception:
            pass
    def login(self):
        def is_connection_failure(exc) -> bool:
            text = str(exc).lower()
            return isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)) or any(
                marker in text for marker in ("winerror 10061", "connection refused", "connecterror")
            )

        try:
            # The wizard may have just replaced deployment.json. Refresh the
            # endpoint immediately before the first authentication request.
            from .api import configure_base_url

            configure_base_url()
            api.login(self.user.text().strip(), self.pwd.text())
            self.accept()
            return
        except Exception as e:
            if is_connection_failure(e):
                try:
                    from app.deployment import load_deployment_config
                    from app.desktop.launch import ensure_background_services, wait_for_api

                    config = load_deployment_config()
                    if config.is_server:
                        # Safe to call again: the launcher verifies the API
                        # health endpoint and uses the Site Service lock.
                        ensure_background_services(config=config)
                    else:
                        wait_for_api(timeout=20.0, base_url=api.base_url)
                    configure_base_url()
                    api.login(self.user.text().strip(), self.pwd.text())
                    self.accept()
                    return
                except Exception as retry_error:
                    e = retry_error
            text=str(e)
            if "401" in text or "Invalid username" in text:
                text = (
                    "Invalid username or password.\n\n"
                    "admin / first-run password only works on a fresh database. "
                    "This PC already has an admin account. "
                    "Reset it with: python -m app.cli reset-admin"
                )
            elif "Connection" in text or "ConnectError" in text or "8760" in text:
                text = f"Cannot reach the {PRODUCT_NAME} Site Server at {api.base_url}. Check the connection or open deployment configuration."
            QMessageBox.critical(self,"Sign in failed",text)


from .live_pane import CameraLivePane
from .video import VideoCanvas as ClickLabel


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
        cap=QLabel(label); cap.setObjectName("muted")
        box.addWidget(val); box.addWidget(cap)
        prepare_page(frame, label)
        return frame, val
    def refresh(self):
        w=Worker(lambda: api.get("/dashboard"))
        w.done.connect(self._apply)
        w.failed.connect(lambda e: self.alert.setText(f"Unable to load dashboard: {e}"))
        self._keep(w); w.start()
    def _apply(self, data):
        data=data or {}
        stats=self._dashboard_stats(data)
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
    def _dashboard_stats(self, data):
        kind=deployment_kind()
        online=data.get("sdk_connected", 0)
        cameras=data.get("cameras", 0)
        if kind=="lpr":
            return [
                ("Cameras online", online),
                ("Cameras configured", cameras),
                ("Registered vehicles", data.get("registered_plates", 0)),
            ]
        if kind=="security":
            return [
                ("Cameras online", online),
                ("Cameras configured", cameras),
                ("Active notices", len(data.get("alerts") or [])),
            ]
        if kind=="access":
            return [
                ("Registered vehicles", data.get("registered_plates", 0)),
                ("Cameras online", online),
                ("Devices configured", cameras),
            ]
        return [
            ("Vehicles inside", data.get("vehicles_inside", 0)),
            ("Entries today", data.get("entries_today", 0)),
            ("Exits today", data.get("exits_today", 0)),
            ("Revenue today", data.get("revenue_today_label") or money_label(data.get("revenue_today"), data.get("currency"))),
            ("Unpaid sessions", data.get("unpaid_active", 0)),
            ("Subscribers inside", data.get("subscribers_inside", 0)),
        ]
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


from .live_cameras import CameraDialog, Cameras


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
        note=QLabel("Manual commands apply to one selected camera side, never both barriers. Select a configured gate, press 1 for entry or 2 for exit, then F8 / F9.")
        note.setWordWrap(True); l.addWidget(note)
        self.table=QTableWidget(0,6); self.table.setHorizontalHeaderLabels(["ID","Lane","Mode","Enabled","Sides (camera / controller / display)","Action"])
        configure_table(self.table); l.addWidget(self.table, 1)
        self.shortcut_hint=QLabel("Select a lane, then 1 = entry, 2 = exit. F8 / F9 pulse that side only.")
        self.shortcut_hint.setWordWrap(True); l.addWidget(self.shortcut_hint)
        self._armed_side=None
        row=QHBoxLayout()
        add=QPushButton(action_label("Add Gate", "Ctrl+N")); add.clicked.connect(self.add_gate); add.setVisible(api.can("gates.manage")); add.setToolTip("Add Gate (Ctrl+N)")
        edit=QPushButton(action_label("Edit", "Ctrl+E")); edit.clicked.connect(self.edit_gate); edit.setVisible(api.can("gates.manage")); edit.setToolTip("Edit (Ctrl+E)")
        delete=QPushButton(action_label("Delete", "Del")); delete.clicked.connect(self.delete_gate); delete.setVisible(api.can("gates.manage")); delete.setToolTip("Delete (Del)")
        led=QPushButton("LED text"); led.clicked.connect(self.write_led); led.setVisible(api.can("gates.open"))
        row.addWidget(add); row.addWidget(edit); row.addWidget(delete); row.addWidget(led); row.addStretch(); l.addLayout(row); self.rows=[]; self.refresh()
        sc1=QShortcut(QKeySequence("1"), self); sc1.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut); sc1.activated.connect(lambda: self.arm_side("ENTRY"))
        sc2=QShortcut(QKeySequence("2"), self); sc2.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut); sc2.activated.connect(lambda: self.arm_side("EXIT"))
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
                b.clicked.connect(lambda _,gid=g["id"],s=side: self._open_and_arm(gid,s,"open"))
                hl.addWidget(b)
                cbtn=QPushButton("Close entry" if side=="ENTRY" else "Close exit")
                cbtn.clicked.connect(lambda _,gid=g["id"],s=side: self._open_and_arm(gid,s,"close"))
                hl.addWidget(cbtn)
            self.table.setCellWidget(r,5,cell)
    def selected_gate(self):
        row=self.table.currentRow()
        if row<0 or row>=len(self.rows): return None
        return self.rows[row]
    def arm_side(self, side):
        self._armed_side=side
        gate=self.selected_gate()
        name=(gate or {}).get("name") or "this lane"
        label="entry" if side=="ENTRY" else "exit"
        self.shortcut_hint.setText(f"{name} {label} is armed. F8 opens it, F9 closes it.")
    def shortcut_side(self):
        gate=self.selected_gate()
        if not gate:
            return None, None
        sides=[]
        seen=set()
        for cam in (gate.get("cameras") or []):
            s=(cam.get("lane_direction") or cam.get("side") or "").upper()
            if s in {"ENTRY","EXIT"} and s not in seen:
                seen.add(s); sides.append(s)
        if self._armed_side in sides:
            return gate, self._armed_side
        if len(sides)==1:
            return gate, sides[0]
        return gate, None
    def _open_and_arm(self, gid, side, action):
        self._armed_side=side
        self.arm_side(side)
        self.command_gate(gid, side, action)
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
        self.command_gate(gid, side, "open")
    def command_gate(self,gid,side,action="open"):
        verb="close" if action=="close" else "open"
        label="entry" if side=="ENTRY" else "exit"
        title=f"{'Close' if verb=='close' else 'Open'} this side"
        prompt=f"{'Close' if verb=='close' else 'Pulse'} only this lane's {label} barrier (not the other side)?"
        if QMessageBox.question(self,title,prompt)!=QMessageBox.Yes: return
        reason,ok=QInputDialog.getText(self,title,"Reason", text=f"manual {verb}")
        if ok and reason:
            try: QMessageBox.information(self,"Barrier",str(api.post(f"/gates/{gid}/open",{"reason":reason,"side":side,"action":verb}, timeout=20)))
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
        add=QPushButton(action_label("Add User", "Ctrl+N")); add.clicked.connect(self.add_user); add.setVisible(api.can("users.manage")); add.setToolTip("Add User (Ctrl+N)")
        edit=QPushButton(action_label("Edit", "Ctrl+E")); edit.clicked.connect(self.edit_user); edit.setVisible(api.can("users.manage")); edit.setToolTip("Edit (Ctrl+E)")
        delete=QPushButton(action_label("Delete", "Del")); delete.clicked.connect(self.delete_user); delete.setVisible(api.can("users.manage")); delete.setToolTip("Delete (Del)")
        refresh=QPushButton(action_label("Refresh", "F5")); refresh.clicked.connect(self.refresh); refresh.setToolTip("Refresh (F5)")
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
        find.addWidget(label_for("&Find visit", self.query)); find.addWidget(self.query, 1); find.addWidget(find_btn); l.addLayout(find)
        card=QFrame(); card.setObjectName("card"); card_l=QHBoxLayout(card)
        photos=QVBoxLayout()
        self.photo=QLabel("No entry photo stored."); self.photo.setMinimumSize(200, 140); self.photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.photo.setObjectName("video"); self.photo.setAccessibleName("Selected visit entry photograph")
        self.crop=QLabel(""); self.crop.setMinimumHeight(80); self.crop.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.crop.setObjectName("video"); self.crop.setAccessibleName("Selected visit plate crop")
        photos.addWidget(self.photo); photos.addWidget(self.crop)
        detail=QVBoxLayout()
        self.kiosk_plate=QLabel("—"); self.kiosk_plate.setStyleSheet("font-size:28px;font-weight:700;letter-spacing:2px")
        self.kiosk_stay=QLabel("Scan a receipt or pick a session.")
        self.kiosk_stay.setWordWrap(True)
        self.kiosk_due=QLabel(""); self.kiosk_due.setStyleSheet("font-size:18px;font-weight:700")
        self.kiosk_note=QLabel(""); self.kiosk_note.setWordWrap(True)
        self.correct=QLineEdit(); self.correct.setPlaceholderText("Correct plate")
        actions=QVBoxLayout()
        save_plate=QPushButton("Save corrected plate"); save_plate.clicked.connect(self.correct_plate)
        self.pay_btn=QPushButton("Record payment"); self.pay_btn.clicked.connect(self.pay_visit); self.pay_btn.setEnabled(False)
        self.mobile_btn=QPushButton("Pay with mobile on this computer"); self.mobile_btn.clicked.connect(self.pay_mobile); self.mobile_btn.setEnabled(False)
        can_pay=api.can("payments.create") or api.can("kiosk.use")
        self.pay_btn.setVisible(can_pay)
        self.mobile_btn.setVisible(can_pay)
        actions.addWidget(save_plate); actions.addWidget(self.pay_btn); actions.addWidget(self.mobile_btn)
        detail.addWidget(self.kiosk_plate); detail.addWidget(self.kiosk_stay); detail.addWidget(self.kiosk_due); detail.addWidget(self.kiosk_note)
        detail.addWidget(label_for("&Correct plate", self.correct)); detail.addWidget(self.correct); detail.addLayout(actions)
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
                money_label(s.get("amount_due"), s.get("currency")),
                money_label(s.get("amount_paid"), s.get("currency")),
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
        qr_payload=(issued or {}).get("qr_payload") or (issued or {}).get("public_url") or ""
        if not body:
            try:
                slip=api.get(f"/sessions/{s['id']}/receipt")
                body=slip.get("body_text") or ""
                path=(slip.get("payload") or {}).get("path") or path
                qr_payload=qr_payload or slip.get("qr_payload") or ""
                if not qr_url and slip.get("qr_url"):
                    qr_url=slip.get("qr_url")
            except Exception:
                pass
        show_printable_receipt(self, body, path, qr_url=qr_url, qr_payload=qr_payload)
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
                method_label(p.get("method")),
                money_label(p.get("amount"), p.get("currency")),
                p.get("status") or "",
                p.get("provider_id") or "",
            ]
            for c,val in enumerate(vals): self.table.setItem(r,c,QTableWidgetItem(str(val)))
        self.table.setColumnHidden(5, not is_technician())


class Vehicles(QWidget):
    def __init__(self):
        super().__init__(); l=QVBoxLayout(self)
        title=QLabel("Registered vehicles"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        note=QLabel("Registered vehicles and access plans. A matching plate can be allowed through when gate access is enabled.")
        note.setWordWrap(True); l.addWidget(note)
        self.table=QTableWidget(0,7); self.table.setHorizontalHeaderLabels(["Plate","Owner","Plan","Auto-open","Enabled","From","Until"])
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        configure_table(self.table); l.addWidget(self.table, 1)
        bulk_note=QLabel("Register many, one plate per line: plate, owner, start date, end date")
        l.addWidget(bulk_note)
        self.bulk=QPlainTextEdit(); self.bulk.setPlaceholderText("ABC1234, Owner, 2026-09-01, 2026-10-01"); self.bulk.setMaximumHeight(90)
        l.addWidget(self.bulk)
        row=QHBoxLayout()
        manage=api.can("subscribers.manage")
        add=QPushButton(action_label("Register plate", "Ctrl+N")); add.clicked.connect(self.add); add.setVisible(manage); add.setToolTip("Register plate (Ctrl+N)")
        bulk=QPushButton("Register these plates"); bulk.clicked.connect(self.add_bulk); bulk.setVisible(manage)
        edit=QPushButton(action_label("Edit", "Ctrl+E")); edit.clicked.connect(self.edit); edit.setVisible(manage); edit.setToolTip("Edit (Ctrl+E)")
        delete=QPushButton(action_label("Delete", "Del")); delete.clicked.connect(self.delete); delete.setVisible(manage); delete.setToolTip("Delete (Del)")
        delete_many=QPushButton(action_label("Delete selected", "Del")); delete_many.clicked.connect(self.delete_selected); delete_many.setVisible(manage); delete_many.setToolTip("Delete selected (Del)")
        refresh=QPushButton(action_label("Refresh", "F5")); refresh.clicked.connect(self.refresh); refresh.setToolTip("Refresh (F5)")
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
        title=QLabel("Tariffs & Schedules"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        note=QLabel("Day and night rates for this site. Times and amounts are normal fields — save them here.")
        note.setWordWrap(True); l.addWidget(note)
        form=QFormLayout()
        self.currency=QLineEdit()
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
        self.currency.setText(editor.get("currency") or data.get("currency") or "")
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
        warn=QLabel("Technician tools: camera connection, media streaming, recognition, gate I/O, and logs."); warn.setWordWrap(True); l.addWidget(warn)
        self.info=QPlainTextEdit(); self.info.setReadOnly(True); self.info.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.info.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        l.addWidget(self.info, 1)
        row=QHBoxLayout()
        b=QPushButton("Check HVX SDK Host"); b.clicked.connect(self.check)
        a=QPushButton("Check recognition"); a.clicked.connect(self.check_alpr)
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
        title=QLabel("Testing & Simulation"); title.setStyleSheet("font-size:24px;font-weight:700"); l.addWidget(title)
        note=QLabel("Practice entry and exit without live cameras. Registered vehicles follow the same access rules as the live site.")
        note.setWordWrap(True); l.addWidget(note)
        form=QFormLayout()
        self.gate=QComboBox()
        self.plate=QLineEdit(); self.plate.setPlaceholderText("ABC 1234")
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
        if best.get("plate"): parts.append(f"Recognition: {best.get('plate')} ({int(round((best.get('confidence') or 0)*100))}%)")
        parts.append(json.dumps({k:v for k,v in data.items() if k not in {"alpr","receipt"}}, indent=2, default=str))
        self.out.setPlainText("\n\n".join(parts))
        crop=(
            best.get("crop_url")
            or sess.get("crop_url")
            or (data.get("capture") or {}).get("crop_url")
            or alpr.get("annotated_url")
            or sess.get("snapshot_url")
        )
        if crop:
            w=Worker(lambda url=crop: api.get_bytes(url, timeout=8))
            w.done.connect(lambda jpeg: self._pix(jpeg)); self._keep(w); w.start()
        if str(data.get("action") or "").upper() == "ENTRY" and (data.get("receipt") or data.get("qr_url") or sess.get("public_token")):
            qr_url=data.get("qr_url") or ""
            token=sess.get("public_token") or data.get("public_token") or ""
            if not qr_url and token:
                qr_url=f"/p/{token}/qr.png"
            show_printable_receipt(
                self,
                data.get("receipt") or "",
                ((data.get("print") or {}).get("path") or ""),
                qr_url=qr_url,
                qr_payload=data.get("qr_payload") or data.get("public_url") or sess.get("qr_payload") or "",
            )
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
        l1.addWidget(QLabel("What do you want to use this site for?"))
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
        l2.addWidget(QLabel("How is this site laid out?"))
        self.topo_preset = QComboBox()
        self.topo_preset.addItem("1 entry / 1 exit", "1in1out")
        self.topo_preset.addItem("One bidirectional lane", "bidirectional")
        self.topo_preset.addItem("No gates", "lpr_only")
        self.topo_preset.addItem("Multiple lanes — keep current", "keep")
        l2.addWidget(self.topo_preset)
        form2 = QFormLayout()
        self.site_name = QLineEdit("Default Site")
        self.site_tz = QLineEdit("UTC")
        self.site_cur = QComboBox()
        for code, label in (
            ("USD", "US Dollar (USD)"),
            ("EUR", "Euro (EUR)"),
            ("GBP", "British Pound (GBP)"),
            ("KES", "Kenyan Shilling (KES)"),
            ("TZS", "Tanzanian Shilling (TZS)"),
            ("AED", "UAE Dirham (AED)"),
        ):
            self.site_cur.addItem(label, code)
        self.site_lang = QComboBox()
        for code, label in (("en", "English"), ("sw", "Kiswahili"), ("ar", "Arabic"), ("fr", "French"), ("pt", "Portuguese")):
            self.site_lang.addItem(label, code)
        form2.addRow("Site name", self.site_name)
        form2.addRow("Timezone", self.site_tz)
        form2.addRow("Currency", self.site_cur)
        form2.addRow("Language", self.site_lang)
        l2.addLayout(form2)
        self.stack.addWidget(p2)

        # 3 hardware
        p3 = QWidget(); l3 = QVBoxLayout(p3)
        l3.addWidget(QLabel("Add cameras now, or skip and add them later under Devices."))
        self.hw_info = QPlainTextEdit(); self.hw_info.setReadOnly(True)
        l3.addWidget(self.hw_info)
        disc = QPushButton("Discover cameras on LAN")
        disc.clicked.connect(self._discover)
        l3.addWidget(disc)
        self.stack.addWidget(p3)

        # 4 recognition
        p4 = QWidget(); l4 = QVBoxLayout(p4)
        l4.addWidget(QLabel("How should plates be read?"))
        self.rec_mode = QComboBox()
        for mid, label in [
            ("NATIVE_ONLY", "Use camera recognition"),
            ("FASTALPR_ONLY", f"Use {PRODUCT_NAME} AI recognition"),
            ("HYBRID", "Use both"),
            ("VIDEO_ONLY", "Video only"),
        ]:
            self.rec_mode.addItem(label, mid)
        self.rec_mode.setCurrentIndex(2)
        l4.addWidget(self.rec_mode)
        self.stack.addWidget(p4)

        # 5 modules
        p5 = QWidget(); l5 = QVBoxLayout(p5)
        l5.addWidget(QLabel("Optional features. Disabled features disappear from navigation."))
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
            self.hw_info.setPlainText(f"{n} camera(s) found.\nOpen Devices to add and connect them.")
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
                idx = self.site_cur.findData(site["currency"])
                if idx < 0:
                    self.site_cur.addItem(str(site["currency"]), site["currency"])
                    idx = self.site_cur.findData(site["currency"])
                if idx >= 0:
                    self.site_cur.setCurrentIndex(idx)
            if site.get("language"):
                idx = self.site_lang.findData(site["language"])
                if idx >= 0:
                    self.site_lang.setCurrentIndex(idx)
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
                "currency": self.site_cur.currentData() or "USD",
                "language": self.site_lang.currentData() or "en",
                "locale": self.site_lang.currentData() or "en",
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
    """Recent plate reads. Engine files stay in the technician view."""

    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        title = QLabel("Detections")
        title.setStyleSheet("font-size:24px;font-weight:700")
        root.addWidget(title)
        intro = QLabel("Recent plate reads from this site. Camera and model details stay in Hardware Lab.")
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        root.addWidget(intro)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Time", "Plate", "Camera", "Lane", "Confidence"])
        configure_table(self.table)
        root.addWidget(self.table, 1)
        self.card = QLabel("")
        self.card.setWordWrap(True)
        self.card.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.card.setVisible(is_technician())
        root.addWidget(self.card)
        row = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.load)
        pack = QPushButton("Apply model pack…")
        pack.setObjectName("secondary")
        pack.clicked.connect(self.apply_pack)
        pack.setVisible(is_technician())
        row.addWidget(refresh)
        row.addWidget(pack)
        row.addStretch()
        root.addLayout(row)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

    def showEvent(self, event):
        super().showEvent(event)
        self.load()

    def load(self):
        try:
            rows = api.get("/captures?limit=50") or []
        except Exception as exc:
            self.status.setText(f"Detections could not be loaded. {exc}")
            rows = []
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            conf = row.get("confidence")
            pct = ""
            if conf is not None:
                pct = f"{int(round(float(conf) * 100 if float(conf) <= 1 else float(conf)))}%"
            vals = [
                str(row.get("created_at") or "")[:19].replace("T", " "),
                row.get("plate") or "—",
                row.get("camera_id") if row.get("camera_id") is not None else "—",
                row.get("lane_direction") or "—",
                pct or "—",
            ]
            for c, val in enumerate(vals):
                self.table.setItem(r, c, QTableWidgetItem(str(val)))
        if not rows:
            self.status.setText("No detections yet. Detected vehicles will appear here automatically.")
        elif not is_technician():
            self.status.setText("")
        if not is_technician():
            return
        try:
            data = api.get("/recognition/engine")
        except Exception as exc:
            self.card.setText(str(exc))
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
        self.status.setText("Technician recognition details are below the detection list.")

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
        combo=QComboBox(); combo.addItems(APPEARANCES); combo.setCurrentText(window.appearance)
        combo.currentTextChanged.connect(self.change)
        window.appearanceChanged.connect(lambda name: self._sync_appearance(combo, name))
        form.addRow("Appearance", combo)
        self.timezone=QLineEdit("UTC")
        self.currency=QLineEdit()
        self.language=QComboBox(); self.language.addItems(["en","sw","ar","fr","pt"])
        self.plate_validation=QComboBox(); self.plate_validation.addItems(["NONE","TZ","KE","ZA","AE"])
        self.public_base_url=QLineEdit()
        self.public_base_url.setPlaceholderText("http://smartpark-server:8760")
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
    def _sync_appearance(self, combo, name):
        previous = combo.blockSignals(True)
        combo.setCurrentText(name)
        combo.blockSignals(previous)
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
        webbrowser.open(api.base_url + "/")


class MainWindow(DesktopShell):
    def __init__(self):
        super().__init__()
        import platform
        system = platform.system() or "desktop"
        self.setWindowTitle(f"{PRODUCT_NAME}  ·  {system}")
        self.pages=[]
        self._makers=[]
        if api.nav_page("dashboard"):
            self.add_page(api.nav_label("dashboard", "Dashboard"), Dashboard)
        if api.nav_page("health"):
            self.add_page(api.nav_label("health", "System Health"), SystemHealth)
        if api.nav_page("cameras"):
            self.add_page(api.nav_label("cameras", "Live Gates"), Cameras)
        if api.nav_page("plates"):
            self.add_page(api.nav_label("plates", "Detections"), PlateEnginePage)
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
            self.add_page(api.nav_label("fees", "Tariffs & Schedules"), Fees)
        if api.nav_page("reports"):
            self.add_page(api.nav_label("reports", "Reports"), ReportsPage)
        if api.nav_page("gates"):
            self.add_page(api.nav_label("gates", "Gates"), Gates)
        if api.nav_page("users"):
            self.add_page(api.nav_label("users", "Users & Roles"), Users)
        if api.nav_page("settings") or api.can("settings.view") or api.can("dashboard.view"):
            self.add_page(api.nav_label("settings", "Settings"), lambda: SettingsPage(self))
        if api.nav_page("hardware"):
            self.add_page(api.nav_label("hardware", "Hardware Lab"), Hardware)
        if api.nav_page("sim"):
            self.add_page(api.nav_label("sim", "Testing & Simulation"), SimPage)
        self.nav.currentRowChanged.connect(self._show_page)
        self._filter_navigation("")
        self.statusBar().showMessage("Choose a workspace page")
        self._install_shortcuts()
        # Do not setGeometry() to the full screen rect. On Windows the frame is
        # taller than the client area, Qt retries, and the window grows forever.
    def closeEvent(self, event):
        for page in self.pages:
            if page is None: continue
            fn=getattr(page, "shutdown", None)
            if callable(fn):
                fn()
        super().closeEvent(event)
    def add_page(self, name, factory):
        self.nav.addItem(name)
        self.nav.item(self.nav.count() - 1).setToolTip(name)
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
            self.stack.insertWidget(index, page_viewport(page, self.nav.item(index).text()))
            old.deleteLater()
            self.pages[index]=page
        self.stack.setCurrentIndex(index)
        self.show_page_context(index)
    def _current_page(self):
        idx=self.stack.currentIndex()
        if 0<=idx<len(self.pages):
            return self.pages[idx]
        return None
    def _text_editing(self):
        w=QApplication.focusWidget()
        return isinstance(w, (QLineEdit, QPlainTextEdit, QSpinBox, QDateEdit, QTimeEdit))
    def _install_shortcuts(self):
        def add_act(title, keys, slot, tip=""):
            act=QAction(title, self)
            seqs=keys if isinstance(keys, (list, tuple)) else [keys]
            act.setShortcuts([QKeySequence(k) for k in seqs])
            act.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            if tip:
                act.setStatusTip(tip)
            act.triggered.connect(slot)
            self.addAction(act)
            return act
        menu=self.menuBar().addMenu("&Actions")
        menu.addAction(add_act("Add", "Ctrl+N", self._shortcut_add, "Add camera, gate, vehicle, or user"))
        menu.addAction(add_act("Edit", "Ctrl+E", self._shortcut_edit, "Edit the selected row"))
        menu.addAction(add_act("Delete", ["Delete", "Ctrl+Backspace"], self._shortcut_delete, "Delete the selected row"))
        menu.addSeparator()
        menu.addAction(add_act("Open gate", "F8", lambda: self._shortcut_barrier("open"), "Open the selected barrier"))
        menu.addAction(add_act("Close gate", "F9", lambda: self._shortcut_barrier("close"), "Close the selected barrier"))
        refresh_action=add_act("Refresh", ["F5", "Ctrl+R"], self._shortcut_refresh, "Reload this page")
        menu.addAction(refresh_action)
        menu.addSeparator()
        help_action=add_act("Keyboard shortcuts", ["F1", "Ctrl+/"], self._shortcut_help)
        menu.addAction(help_action)
        self.finish_shell(refresh_action, help_action)
    def _call_page(self, names):
        page=self._current_page()
        if page is None:
            return False
        for name in names:
            fn=getattr(page, name, None)
            if callable(fn):
                fn()
                return True
        return False
    def _shortcut_add(self):
        if self._text_editing():
            return
        if not self._call_page(("add_camera", "add_gate", "add_user", "add")):
            QMessageBox.information(self, "Add", "Open Cameras, Gates, Vehicles, or Users to add.")
    def _shortcut_edit(self):
        if self._text_editing():
            return
        if not self._call_page(("edit_camera", "edit_gate", "edit_user", "edit")):
            QMessageBox.information(self, "Edit", "Select a row on Cameras, Gates, Vehicles, or Users.")
    def _shortcut_delete(self):
        if self._text_editing():
            return
        if not self._call_page(("delete_selected", "delete_camera", "delete_gate", "delete_user", "delete")):
            QMessageBox.information(self, "Delete", "Select a row on Cameras, Gates, Vehicles, or Users.")
    def _shortcut_refresh(self):
        if self._text_editing():
            return
        self._call_page(("refresh",))
    def _shortcut_barrier(self, action):
        if self._text_editing():
            return
        page=self._current_page()
        if isinstance(page, Cameras):
            if page._live_visible():
                pane=page.shortcut_pane()
                if pane is None:
                    QMessageBox.information(self, "Barrier", "Click a live camera first, or press 1 / 2. F8 and F9 pulse that side only — never both.")
                    return
                pane.command_barrier(action)
                return
            page.command_barrier(action)
            return
        if isinstance(page, Gates):
            gate, side=page.shortcut_side()
            if not gate:
                QMessageBox.information(self, "Barrier", "Select a gate row first.")
                return
            if not side:
                QMessageBox.information(self, "Barrier", "This lane has two sides. Press 1 for entry or 2 for exit, then F8 / F9.")
                return
            page.command_gate(gate["id"], side, action)
            return
        QMessageBox.information(self, "Barrier", "Open Live Gates or Gates, then select one side.")
    def _shortcut_help(self):
        QMessageBox.information(
            self,
            "Keyboard shortcuts",
            "Ctrl+K    Find a workspace page\n"
            "Ctrl++ / Ctrl+-    Resize text (Ctrl+0 to reset)\n"
            "Ctrl+N    Add camera, gate, vehicle, or user\n"
            "Ctrl+E    Edit the selected row\n"
            "Delete    Delete the selected row\n"
            "F5        Refresh this page\n"
            "F11       Focus workspace / restore navigation\n"
            "Ctrl+M    Hide / restore menu bar\n"
            "F8        Open only the highlighted camera or armed gate side\n"
            "F9        Close only the highlighted camera or armed gate side\n"
            "1 / 2     Select live camera 1 or 2, or gate entry / exit\n"
            "F1        This help",
        )


def main():
    app=QApplication(sys.argv); app.setApplicationName(PRODUCT_NAME)
    assets = Path(__file__).resolve().parents[1] / "assets"
    icon = assets / "zirp.ico"
    if not icon.is_file():
        icon = assets / "zirp-logo.png"
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))
    font = QFont()
    font.setPointSize(10)
    app.setFont(font)
    apply_appearance(app, "Light")
    from app.deployment import OPERATOR_CLIENT, ensure_legacy_config_saved, load_deployment_config
    from .api import configure_base_url
    config = ensure_legacy_config_saved()
    if not config.configured:
        from .setup import SetupWizard
        wizard = SetupWizard(config)
        if wizard.exec() != QDialog.DialogCode.Accepted:
            return 0
        config = load_deployment_config()
    configure_base_url()
    if config.role != OPERATOR_CLIENT:
        try:
            from app.desktop.launch import ensure_background_services
            ensure_background_services(config=config)
        except Exception as exc:
            QMessageBox.critical(None, PRODUCT_NAME, f"The {PRODUCT_NAME} Site Server could not start.\n\n{exc}")
            return 1
    else:
        from app.desktop.launch import disable_background_services

        disable_background_services()
        while True:
            try:
                import httpx
                response = httpx.get(f"{api.base_url}/health/live", timeout=3)
                response.raise_for_status()
                identity = httpx.get(f"{api.base_url}/deployment/info", timeout=3)
                identity.raise_for_status()
                identity_body = identity.json()
                if config.paired_server_id:
                    if identity_body.get("server_installation_id", identity_body.get("installation_id")) != config.paired_server_id:
                        raise RuntimeError("Server identity changed. Open deployment configuration and verify the Site Server.")
                elif config.server_id and identity_body.get("server_id") != config.server_id:
                    # Compatibility with v1 client metadata, where server_id
                    # was the server's public site identity.
                    raise RuntimeError("Server identity changed. Open deployment configuration and verify the Site Server.")
                if config.paired_site_id and identity_body.get("site_id", identity_body.get("server_id")) != config.paired_site_id:
                    raise RuntimeError("Site identity changed. Open deployment configuration and verify the Site Server.")
                elif not config.paired_server_id and config.installation_id and identity_body.get("installation_id") != config.installation_id:
                    # Compatibility with v1 clients that stored the server
                    # installation ID in installation_id.
                    raise RuntimeError("Site identity changed. Open deployment configuration and verify the Site Server.")
                break
            except Exception as exc:
                prompt = QMessageBox(None)
                prompt.setIcon(QMessageBox.Icon.Warning)
                prompt.setWindowTitle(f"{PRODUCT_NAME} Operator Workstation")
                prompt.setText(f"{PRODUCT_NAME} Site Server unavailable")
                prompt.setInformativeText(f"Server: {api.base_url}\n\n{exc}")
                retry = prompt.addButton("Retry", QMessageBox.ButtonRole.AcceptRole)
                change = prompt.addButton("Change Server", QMessageBox.ButtonRole.ActionRole)
                prompt.addButton("Exit", QMessageBox.ButtonRole.RejectRole)
                prompt.exec()
                if prompt.clickedButton() is retry:
                    continue
                if prompt.clickedButton() is change:
                    from .setup import SetupWizard

                    wizard = SetupWizard(config)
                    if wizard.exec() == QDialog.DialogCode.Accepted:
                        config = load_deployment_config()
                        configure_base_url()
                        continue
                return 1
    login=Login()
    if login.exec()!=QDialog.Accepted: return 0
    w=MainWindow()
    if w.restored_geometry:
        w.show()
    else:
        w.showMaximized()
    if w.nav.count():
        w.nav.setCurrentRow(0)
        w._show_page(0)
    return app.exec()


if __name__ == "__main__": raise SystemExit(main())
