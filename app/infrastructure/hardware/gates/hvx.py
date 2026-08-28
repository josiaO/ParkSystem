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
