"""Gate adapter contract and lane-mode policy.

COMMISSIONING and PRODUCTION keep today's physical path.
SHADOW only suppresses *automatic* barrier pulses.
MAINTENANCE blocks automatic pulses; manual Hardware Lab still works.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

SHADOW = "SHADOW"
MAINTENANCE = "MAINTENANCE"
COMMISSIONING = "COMMISSIONING"
PRODUCTION = "PRODUCTION"

NO_AUTOMATIC_PULSE_MODES = {SHADOW, MAINTENANCE}


@runtime_checkable
class GateLike(Protocol):
    name: str
    mode: str


@runtime_checkable
class GateControllerAdapter(Protocol):
    id: str

    async def open(self, gate: Any, cameras: list, reason: str, **kwargs) -> Any: ...

    async def health(self, gate: Any | None = None) -> dict[str, Any]: ...


def should_pulse_physical(*, gate: GateLike | None, automatic: bool) -> bool:
    """Whether an open may hit GPIO/Board/LED for real.

    Manual opens (Hardware Lab / operator) stay available in every mode so
    commissioning the working HVX boom is not blocked.
    """
    if gate is None or not automatic:
        return True
    mode = (getattr(gate, "mode", None) or "").upper()
    return mode not in NO_AUTOMATIC_PULSE_MODES
