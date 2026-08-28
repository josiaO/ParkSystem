"""Gate B edge agents are V2. Direct server-to-device is the working path."""

from __future__ import annotations

from app.domain.devices import ConnectionMode


def is_direct(mode: str | None) -> bool:
    value = (mode or ConnectionMode.DIRECT.value).upper()
    return value != ConnectionMode.EDGE_AGENT.value


def edge_agent_status() -> dict:
    return {
        "available": False,
        "default_mode": ConnectionMode.DIRECT.value,
        "note": "Keep DIRECT. Edge agents can queue later without changing the HVX host.",
    }
