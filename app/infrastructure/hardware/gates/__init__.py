"""Gate adapters wrap the working GateController (GPIO + Board* + LED)."""

from __future__ import annotations

from app.domain.gates import GateControllerAdapter
from app.infrastructure.hardware.gates.hvx import HVXGateAdapter
from app.infrastructure.hardware.gates.simulated import SimulatedGateAdapter
from app.services.gates import controller

ADAPTERS: dict[str, GateControllerAdapter] = {
    "hvx": HVXGateAdapter(),
    "simulated": SimulatedGateAdapter(),
}


def gate_adapter_for(adapter_id: str | None = None) -> GateControllerAdapter:
    key = (adapter_id or "hvx").strip().lower()
    if key == "simulated":
        return ADAPTERS["simulated"]
    return ADAPTERS["hvx"]


def live_gate_adapter() -> GateControllerAdapter:
    """Same physical-vs-sim switch the working engine already uses."""
    inner = controller()
    from app.services.gates import SimulatedGateController

    if isinstance(inner, SimulatedGateController):
        return SimulatedGateAdapter(inner)
    return HVXGateAdapter(inner)
