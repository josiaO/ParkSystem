"""Simulated gate adapter wrapping SimulatedGateController."""

from __future__ import annotations

from typing import Any

from app.services.gates import GateCommandResult, SimulatedGateController


class SimulatedGateAdapter:
    id = "simulated"

    def __init__(self, inner: SimulatedGateController | None = None):
        self._inner = inner or SimulatedGateController()

    async def open(self, gate: Any, cameras: list, reason: str, **kwargs) -> GateCommandResult:
        return await self._inner.open(gate, cameras, reason, **kwargs)

    async def health(self, gate: Any | None = None) -> dict[str, Any]:
        return {"ok": True, "adapter_id": self.id, "simulated": True}

    async def close(self, gate: Any, cameras: list, reason: str, **kwargs) -> GateCommandResult:
        from datetime import datetime, timezone
        return GateCommandResult(
            ok=True,
            simulated=True,
            message="simulated close",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    async def get_state(self, gate: Any | None = None) -> dict[str, Any]:
        return {"adapter_id": self.id, "state": "SIMULATED"}
