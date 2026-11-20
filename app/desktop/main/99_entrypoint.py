from __future__ import annotations


def run_with_progress(text, fn):
    """Run slow start-up work (start local services, reach the Site Server)
    on a worker thread while a small window says what is happening.

    Before this the desktop showed nothing at all for up to a minute while
    the local Site Service started. Returns fn()'s result or re-raises.
    """
    from PySide6.QtCore import QEventLoop
    from PySide6.QtWidgets import QProgressBar

    box=QDialog(None)
    box.setWindowTitle(PRODUCT_NAME)
    box.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
    layout=QVBoxLayout(box); layout.setContentsMargins(24,20,24,20)
    label=QLabel(text); label.setWordWrap(True); layout.addWidget(label)
    bar=QProgressBar(); bar.setRange(0, 0); bar.setTextVisible(False); layout.addWidget(bar)
    box.setMinimumWidth(380)
    outcome={}
    loop=QEventLoop()
    worker=Worker(fn)
    worker.done.connect(lambda value: outcome.update(value=value))
    worker.failed.connect(lambda _message: outcome.update(error=getattr(worker, "error", None) or RuntimeError(_message)))
    worker.finished.connect(loop.quit)
    box.show()
    worker.start()
    if not worker.isFinished():
        loop.exec()
    worker.wait()
    box.close()
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("value")


def _check_operator_server(config):
    """Operator Workstation: confirm the configured Site Server is up and is the paired one."""
    import httpx
    response = httpx.get(f"{api.base_url}/health/live", timeout=3, trust_env=False)
    response.raise_for_status()
    identity = httpx.get(f"{api.base_url}/deployment/info", timeout=3, trust_env=False)
    identity.raise_for_status()
    identity_body = identity.json()
    if config.paired_server_id:
        if identity_body.get("server_installation_id", identity_body.get("installation_id")) != config.paired_server_id:
            raise RuntimeError("Server identity changed. Open deployment configuration and verify the Site Server.")
    elif config.server_id and identity_body.get("server_id") != config.server_id:
        raise RuntimeError("Server identity changed. Open deployment configuration and verify the Site Server.")
    if config.paired_site_id and identity_body.get("site_id", identity_body.get("server_id")) != config.paired_site_id:
        raise RuntimeError("Site identity changed. Open deployment configuration and verify the Site Server.")
    elif not config.paired_server_id and config.installation_id and identity_body.get("installation_id") != config.installation_id:
        raise RuntimeError("Site identity changed. Open deployment configuration and verify the Site Server.")


def _apply_installer_station(config):
    """The installer's Kiosk role sets SMARTPARK_STATION=KIOSK; persist it once."""
    from dataclasses import replace

    from app.deployment import OPERATOR_CLIENT, STATION_KIOSK, save_deployment_config

    wanted = str(os.environ.get("SMARTPARK_STATION") or "").strip().upper()
    if wanted != STATION_KIOSK or config.station == STATION_KIOSK or config.role != OPERATOR_CLIENT:
        return config
    try:
        return save_deployment_config(replace(config, station=STATION_KIOSK))
    except Exception:
        return replace(config, station=STATION_KIOSK)


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
    from app.desktop.api import configure_base_url, configure_desktop_base_url
    config = ensure_legacy_config_saved()
    if not config.configured:
        from app.desktop.setup import SetupWizard
        role_lock = str(os.environ.get("SMARTPARK_ROLE_LOCKED") or "").upper() or None
        wizard = SetupWizard(config, role_locked=role_lock)
        if wizard.exec() != QDialog.DialogCode.Accepted:
            return 0
        config = load_deployment_config()
    configure_base_url()
    if config.role != OPERATOR_CLIENT:
        while True:
            try:
                from app.desktop.launch import ensure_background_services

                run_with_progress(f"Starting {PRODUCT_NAME} services on this computer…",
                                  lambda: ensure_background_services(config=config))
                break
            except Exception as exc:
                prompt = QMessageBox(None)
                prompt.setIcon(QMessageBox.Icon.Critical)
                prompt.setWindowTitle(f"{PRODUCT_NAME} startup failed")
                prompt.setText(f"The {PRODUCT_NAME} local service could not start.")
                prompt.setInformativeText(str(exc))
                repair = prompt.addButton("Repair deployment", QMessageBox.ButtonRole.AcceptRole)
                prompt.addButton("Exit", QMessageBox.ButtonRole.RejectRole)
                prompt.exec()
                if prompt.clickedButton() is not repair:
                    return 1
                from app.desktop.setup import SetupWizard

                wizard = SetupWizard(config, role_locked=config.role)
                if wizard.exec() != QDialog.DialogCode.Accepted:
                    return 1
                from app.deployment import load_deployment_config

                config = load_deployment_config()
                configure_base_url()
                try:
                    from app.desktop.launch import restart_background_services

                    run_with_progress(f"Restarting {PRODUCT_NAME} services…",
                                      lambda: restart_background_services(config=config))
                    break
                except Exception as repair_exc:
                    exc = repair_exc
                    continue
    else:
        from app.desktop.launch import disable_background_services

        disable_background_services()
        while True:
            try:
                run_with_progress("Connecting to the Site Server…", lambda: _check_operator_server(config))
                break
            except Exception as exc:
                prompt = QMessageBox(None)
                prompt.setIcon(QMessageBox.Icon.Warning)
                prompt.setWindowTitle(f"{PRODUCT_NAME} Operator Workstation")
                prompt.setText(f"{PRODUCT_NAME} Site Server unavailable")
                prompt.setInformativeText(f"Server: {api.base_url}\n\n{friendly_error(exc)}")
                retry = prompt.addButton("Retry", QMessageBox.ButtonRole.AcceptRole)
                change = prompt.addButton("Change Server", QMessageBox.ButtonRole.ActionRole)
                prompt.addButton("Exit", QMessageBox.ButtonRole.RejectRole)
                prompt.exec()
                if prompt.clickedButton() is retry:
                    continue
                if prompt.clickedButton() is change:
                    from app.desktop.setup import SetupWizard

                    wizard = SetupWizard(config)
                    if wizard.exec() == QDialog.DialogCode.Accepted:
                        config = load_deployment_config()
                        configure_base_url()
                        continue
                return 1
    configure_desktop_base_url()
    config = _apply_installer_station(config)
    login=Login(kiosk_station=config.is_kiosk)
    if login.exec()!=QDialog.Accepted: return 0
    w=MainWindow()
    try:
        from app.desktop import cpu_watch
        cpu_watch.start()          # logs what is busy when the desktop uses a lot of CPU
    except Exception:
        pass
    if config.is_kiosk:
        w.showFullScreen()   # driver-facing payment kiosk
    elif w.restored_geometry:
        w.show()
    else:
        w.showMaximized()
    if w.nav.count():
        w.nav.setCurrentRow(0)
        w._show_page(0)
    return app.exec()

if __name__ == "__main__": raise SystemExit(main())
