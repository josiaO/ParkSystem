"""HVX gate adapter — wraps PhysicalGateController. Does not reimplement GPIO."""

from __future__ import annotations

from typing import Any

from app.services.gates import GateCommandResult, GateController, controller


class HVXGateAdapter:
    id = "hvx"

    def __init__(self, inner: GateController | None = None):
        self._inner = inner

    def _controller(self) -> GateController:
        return self._inner or controller()

    async def open(self, gate: Any, cameras: list, reason: str, **kwargs) -> GateCommandResult:
        return await self._controller().open(gate, cameras, reason, **kwargs)

    async def health(self, gate: Any | None = None) -> dict[str, Any]:
        return {
            "ok": True,
            "adapter_id": self.id,
            "actuators": ["camera_gpio", "board_tcp", "led_udp"],
            "wraps": "app.services.gates.controller",
        }

    async def close(self, gate: Any, cameras: list, reason: str, **kwargs) -> GateCommandResult:
        inner = getattr(self._controller(), "close", None)
        if callable(inner):
            return await inner(gate, cameras, reason, **kwargs)
        from datetime import datetime, timezone
        return GateCommandResult(
            ok=False,
            simulated=False,
            message="HVX boom is pulse-open on this site; close is not wired on the adapter.",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    async def get_state(self, gate: Any | None = None) -> dict[str, Any]:
        return {
            "adapter_id": self.id,
            "state": "UNKNOWN",
            "note": "Physical boom state is not polled; last command is in gate_commands.",
        }
