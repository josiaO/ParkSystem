from __future__ import annotations

class UserDialog(QDialog):
    def __init__(self, user=None, roles=None):
        super().__init__(); self.user=user; self.setWindowTitle("Edit User" if user else "Add User")
        self.setMinimumWidth(360); self.setMaximumWidth(520)
        form=QFormLayout(self)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.username=QLineEdit(); self.full_name=QLineEdit()
        self.password=QLineEdit(); self.password.setEchoMode(QLineEdit.Password)
        self.status=QComboBox(); self.status.addItems(["ACTIVE","LOCKED","DISABLED"])
        self.role_boxes=[]
        roles_box=QWidget(); roles_l=QVBoxLayout(roles_box); roles_l.setContentsMargins(0,0,0,0)
        roles=roles or [{"name":"Operator"},{"name":"Admin"}]
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
        self.add_btn=add; self.edit_btn=edit; self.refresh_btn=refresh
        row.addWidget(add); row.addWidget(edit); row.addWidget(delete); row.addWidget(refresh); row.addStretch(); l.addLayout(row); self.rows=[]
        self.status=QLabel(""); self.status.setWordWrap(True); l.addWidget(self.status)
        self._loaded=False
        if api.can("users.manage"):
            self.kiosks=KioskDevicesBox(); l.addWidget(self.kiosks)
    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded:
            self._loaded=True
            self.refresh()
            if hasattr(self, "kiosks"):
                self.kiosks.refresh()
    def refresh(self):
        self.status.setText("Loading users…")
        run_task(self, lambda: api.get("/users"), self._fill, buttons=self.refresh_btn, busy_text="Refreshing…",
                 on_error=lambda message, _e: self.status.setText(message))
    def _fill(self, rows):
        rows=rows or []
        self.status.setText("")
        # Kiosk service accounts are managed under Kiosk devices below.
        rows=[u for u in rows if not str(u.get("username") or "").startswith("kiosk-device:")]
        self.rows=rows
        self.table.setRowCount(len(rows))
        for r,u in enumerate(rows):
            for c,v in enumerate([u["id"],u["username"],u.get("full_name") or "—",u["status"],", ".join(u["roles"])]):
                self.table.setItem(r,c,QTableWidgetItem(str(v)))
    def selected_user(self):
        row=self.table.currentRow()
        if row<0 or row>=len(self.rows): return None
        return self.rows[row]
    def _saved(self, text):
        self.status.setText(text); show_status(self, text); self.refresh()
    def _with_roles(self, button, then):
        def fallback(_message, _exc):
            then(None)
        run_task(self, lambda: api.get("/roles"), then, buttons=button, busy_text="Opening…", on_error=fallback)
    def add_user(self):
        def open_dialog(roles):
            d=UserDialog(roles=roles)
            if d.exec():
                payload=d.payload()
                run_task(self, lambda: api.post("/users",payload), lambda _r: self._saved(f"User {payload.get('username')} added."),
                         buttons=self.add_btn, busy_text="Saving…", title="Add user")
        self._with_roles(self.add_btn, open_dialog)
    def edit_user(self):
        user=self.selected_user()
        if not user: QMessageBox.information(self,"Edit user","Select a user first."); return
        def open_dialog(roles):
            d=UserDialog(user, roles=roles)
            if d.exec():
                payload=d.payload(); uid=user['id']
                run_task(self, lambda: api.patch(f"/users/{uid}",payload), lambda _r: self._saved(f"User {user['username']} saved."),
                         buttons=self.edit_btn, busy_text="Saving…", title="Edit user")
        self._with_roles(self.edit_btn, open_dialog)
    def delete_user(self):
        user=self.selected_user()
        if not user: QMessageBox.information(self,"Delete user","Select a user first."); return
        if QMessageBox.question(self,"Delete user",f"Delete {user['username']}?")!=QMessageBox.Yes: return
        uid=user['id']
        run_task(self, lambda: api.delete(f"/users/{uid}"), lambda _r: self._saved(f"User {user['username']} deleted."), title="Delete user")


class KioskDevicesBox(QGroupBox):
    """Enrol and revoke kiosk PCs (revocable device credentials, Phase 2.3)."""

    def __init__(self):
        super().__init__("Kiosk devices")
        l=QVBoxLayout(self)
        note=QLabel("A kiosk PC signs in with its own device credential and stays signed in through a shift. "
                    "Revoke a lost or replaced kiosk here; it is signed out at once.")
        note.setWordWrap(True); note.setObjectName("muted"); l.addWidget(note)
        self.table=QTableWidget(0,5); self.table.setHorizontalHeaderLabels(["Device id","Name","Status","Last seen","Created"])
        configure_table(self.table); l.addWidget(self.table)
        row=QHBoxLayout()
        add=QPushButton("Enrol kiosk…"); add.clicked.connect(self.create_device)
        revoke=QPushButton("Revoke"); revoke.clicked.connect(self.revoke_device)
        refresh=QPushButton("Refresh"); refresh.clicked.connect(self.refresh)
        self.add_btn=add; self.revoke_btn=revoke; self.refresh_btn=refresh
        row.addWidget(add); row.addWidget(revoke); row.addWidget(refresh); row.addStretch(); l.addLayout(row)
        self.rows=[]

    def refresh(self):
        def failed(message, _exc):
            self.table.setRowCount(0); self.setTitle(f"Kiosk devices — {message}")
        run_task(self, lambda: api.get("/kiosk-devices"), self._fill, buttons=self.refresh_btn, busy_text="Refreshing…", on_error=failed)

    def _fill(self, rows):
        rows=rows or []
        self.setTitle("Kiosk devices")
        self.rows=rows
        self.table.setRowCount(len(rows))
        for r,d in enumerate(rows):
            values=[d.get("device_id"), d.get("name") or "—", d.get("status"),
                    (d.get("last_seen_at") or "never").replace("T"," ")[:16], (d.get("created_at") or "").replace("T"," ")[:16]]
            for c,v in enumerate(values):
                self.table.setItem(r,c,QTableWidgetItem(str(v)))

    def create_device(self):
        name, ok = QInputDialog.getText(self, "Enrol kiosk", "Kiosk name (for example 'Exit B kiosk'):")
        if not ok or not name.strip():
            return
        def done(created):
            self.refresh()
            self.show_credential(created or {})
        run_task(self, lambda: api.post("/kiosk-devices", {"name": name.strip()}), done,
                 buttons=self.add_btn, busy_text="Enrolling…", title="Enrol kiosk")

    def show_credential(self, created):
        d=QDialog(self); d.setWindowTitle("Kiosk credential — shown once")
        l=QVBoxLayout(d)
        info=QLabel("On the kiosk PC choose Sign in → Kiosk device… and enter these two values. "
                    "The credential is not shown again; revoke and enrol again if it is lost.")
        info.setWordWrap(True); l.addWidget(info)
        text=QPlainTextEdit(f"Device id: {created.get('device_id')}\nCredential: {created.get('credential')}")
        text.setReadOnly(True); l.addWidget(text)
        close=QPushButton("Done"); close.clicked.connect(d.accept); l.addWidget(close)
        d.exec()

    def revoke_device(self):
        row=self.table.currentRow()
        if row<0 or row>=len(self.rows):
            QMessageBox.information(self, "Revoke kiosk", "Select a kiosk first."); return
        device=self.rows[row]
        if QMessageBox.question(self, "Revoke kiosk",
                                f"Revoke {device.get('name')} ({device.get('device_id')})? It is signed out at once.") != QMessageBox.Yes:
            return
        did=device['id']
        run_task(self, lambda: api.post(f"/kiosk-devices/{did}/revoke"), lambda _r: self.refresh(),
                 buttons=self.revoke_btn, busy_text="Revoking…", title="Revoke kiosk")
