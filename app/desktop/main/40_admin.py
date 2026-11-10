from __future__ import annotations

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
