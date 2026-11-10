from __future__ import annotations

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
        menu.addAction(add_act(
            "Repair / reconfigure deployment",
            "Ctrl+Shift+D",
            self._reconfigure_deployment,
            "Correct the saved Site Server, node, or database settings",
        ))
        menu.addSeparator()
        help_action=add_act("Keyboard shortcuts", ["F1", "Ctrl+/"], self._shortcut_help)
        menu.addAction(help_action)
        self.finish_shell(refresh_action, help_action)

    def _reconfigure_deployment(self):
        from app.deployment import load_deployment_config
        from app.desktop.api import configure_base_url
        from app.desktop.setup import SetupWizard

        current = load_deployment_config()
        wizard = SetupWizard(current, parent=self, role_locked=current.role)
        if wizard.exec() != QDialog.DialogCode.Accepted:
            return
        updated = load_deployment_config()
        configure_base_url()
        try:
            if updated.runs_local_gate_runtime:
                from app.desktop.launch import restart_background_services

                restart_background_services(config=updated)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Deployment saved but runtime could not restart",
                f"The new configuration was saved, but local services did not restart.\n\n{exc}\n\n"
                "Close and reopen SmartPark Edge after correcting the configuration.",
            )
            return
        QMessageBox.information(
            self,
            "Deployment updated",
            "The deployment configuration was saved and local services restarted. SmartPark Edge will close; reopen it to sign in with the repaired configuration.",
        )
        QApplication.instance().quit()
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
            "Ctrl+Shift+D    Repair / reconfigure deployment\n"
            "F8        Open only the highlighted camera or armed gate side\n"
            "F9        Close only the highlighted camera or armed gate side\n"
            "1 / 2     Select live camera 1 or 2, or gate entry / exit\n"
            "F1        This help",
        )
