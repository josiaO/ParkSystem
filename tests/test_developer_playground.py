import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Camera, Gate
from app.services.simulation import _pulse_gate
from app.services.developer import (
    capture_enabled,
    destructive_tools_enabled,
    gate_opening_enabled,
    save_developer_settings,
)


def test_developer_controls_are_persisted_and_fail_closed(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'developer.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    try:
        with factory() as db:
            # A stale off-switch is inert while Developer mode is off.
            save_developer_settings(db, {"gate_opening_enabled": False})
            assert gate_opening_enabled(db) is True
            assert destructive_tools_enabled(db) is False

            save_developer_settings(db, {
                "developer_mode": True,
                "gate_opening_enabled": False,
                "capture_enabled": False,
                "destructive_tools_enabled": True,
            })
            assert gate_opening_enabled(db) is False
            assert capture_enabled(db) is False
            assert destructive_tools_enabled(db) is True
    finally:
        engine.dispose()


def test_gate_pulse_is_blocked_before_controller_when_disabled(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gate.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    try:
        with factory() as db:
            save_developer_settings(db, {
                "developer_mode": True,
                "gate_opening_enabled": False,
            })
            result = asyncio.run(_pulse_gate(
                db,
                Gate(id=1, name="Entry"),
                [Camera(id=1, name="Entry camera", lane_direction="ENTRY")],
                reason="developer test",
                side="ENTRY",
                led_text="WELCOME",
            ))
            assert result is not None
            assert result.ok is False
            assert "disabled" in result.message
    finally:
        engine.dispose()
