"""Cameras handed to an Edge Node can still be calibrated.

Field report (SERVER01 + Edge Node MANGESHO, 20 Nov 2026): after gate 1 was
assigned to the node, its cameras could not be calibrated anywhere. The Site
Server no longer runs them, so it has no live picture or plate boxes for them
(and refuses their video), and the node's desktop signs in with the Processing
Node account, which has cameras.manage but no Settings page, where the
calibration tab lived.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Camera, Gate, Node, NodeGateAssignment, Site

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        session.add(Site(id=1, name="Site", currency="TZS"))
        session.flush()
        session.add_all([Gate(id=1, name="1#", site_id=1), Gate(id=2, name="2#", site_id=1)])
        session.flush()
        session.add_all([
            Camera(id=1, name="1# Entry", ip_address="10.0.0.1", site_id=1, gate_id=1, lane_direction="ENTRY"),
            Camera(id=3, name="2# Entry", ip_address="10.0.0.3", site_id=1, gate_id=2, lane_direction="ENTRY"),
            Node(id=1, node_id="MANGESHO-1", site_id=1, name="Edge Node (MANGESHO)", node_type="EDGE_NODE",
                 status="ACTIVE", credential_hash="x", last_seen_at=datetime.now(timezone.utc)),
        ])
        session.flush()
        session.add(NodeGateAssignment(node_id=1, gate_id=1, enabled=True))
        session.commit()
        yield session
    engine.dispose()


def test_site_server_names_the_node_that_runs_the_camera(db, monkeypatch):
    from app.api import capture_calibration_routes as routes

    monkeypatch.setattr("app.services.node_scope.is_processing_node", lambda: False)
    monkeypatch.setattr("app.services.node_scope.camera_owned_by_edge_node",
                        lambda camera, db=None: int(camera.gate_id) == 1)
    assert routes._owning_edge_node(db, db.get(Camera, 1)) == "Edge Node (MANGESHO)"
    assert routes._owning_edge_node(db, db.get(Camera, 3)) == ""


def test_the_node_itself_is_never_told_to_go_elsewhere(db, monkeypatch):
    from app.api import capture_calibration_routes as routes

    monkeypatch.setattr("app.services.node_scope.is_processing_node", lambda: True)
    assert routes._owning_edge_node(db, db.get(Camera, 1)) == ""


def test_processing_node_account_gets_a_calibration_page():
    window = (ROOT / "app" / "desktop" / "main" / "80_window.py").read_text(encoding="utf-8")
    assert 'elif api.can("cameras.manage"):' in window
    assert 'self.add_page("Camera calibration", lambda: CalibrationPage(self))' in window


def test_calibration_page_builds_only_the_calibration_tab(monkeypatch):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from app.desktop import main as desktop

    page = desktop.CalibrationPage(window=None)
    assert page.tabs.count() == 1 and page.tabs.tabText(0) == "Camera calibration"
    assert hasattr(page, "cal_table") and hasattr(page, "cal_open")
    assert not hasattr(page, "pay_save") and not hasattr(page, "dev_save")   # no site settings
    page.deleteLater()
    app.processEvents()
