"""Open a numbered lane: camera GPIO + Board* TCP + LED UDP.

Each side has three actuators. Open tries all three that have an IP/handle:

- ``Net_GateSetup`` / ``Net_WriteGPIOState`` on the QY camera (live barrier relay)
- Board* TCP I/O controller (not a camera)
- IpAddr* LEDSender2010 UDP text
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.config import settings
from app.models import Camera, Gate
from app.services.board_tcp import send_board_command
from app.services.hvx_client import HVXHostClient, HVXHostUnavailable
from app.services.led_udp import send_led_text
from app.services.camera_lpr import CAMCMD_PULSE_DEFAULT_MS
from app.services.site_cameras import side_label

ENTRY_LED = "WELCOME"
EXIT_LED = "THANKYOU"


@dataclass
class GateCommandResult:
    ok: bool
    simulated: bool
    message: str
    timestamp: str
    actuators: list[dict] = field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GateController:
    async def open(self, gate: Gate, cameras: list[Camera], reason: str, **kwargs) -> GateCommandResult:
        raise NotImplementedError


class SimulatedGateController(GateController):
    async def open(self, gate: Gate, cameras: list[Camera], reason: str, **kwargs) -> GateCommandResult:
        return GateCommandResult(
            ok=True,
            simulated=True,
            message=f"Simulated OPEN for lane {gate.name}: {reason}",
            timestamp=_now(),
        )


class PhysicalGateController(GateController):
    async def open(
        self,
        gate: Gate,
        cameras: list[Camera],
        reason: str,
        *,
        side: str | None = None,
        dry_run: bool = False,
        led_text: str | None = None,
        action: str = "open",
    ) -> GateCommandResult:
        wanted = (side or "").upper() or None
        rows = [c for c in cameras if c.enabled]
        if wanted in {"ENTRY", "EXIT"}:
            rows = [c for c in rows if (c.lane_direction or "").upper() == wanted]
        elif len(rows) > 1:
            return GateCommandResult(
                False, False,
                f"Pick ENTRY or EXIT for lane {gate.name}. Opening without a side would pulse both barriers.",
                _now(),
            )
        if not rows:
            return GateCommandResult(False, False, f"No cameras on lane {gate.name} for that side", _now())

        hvx = HVXHostClient()
        actuators: list[dict] = []
        any_ok = False
        for camera in rows:
            label = f"{gate.name} {side_label(camera.lane_direction)}"
            gpio = await _gpio_pulse(hvx, camera, dry_run=dry_run)
            board = await send_board_command(camera.controller_ip or "", action=action, dry_run=dry_run)
            text = led_text or (EXIT_LED if (camera.lane_direction or "").upper() == "EXIT" else ENTRY_LED)
            led = await send_led_text(camera.display_ip or "", text, dry_run=dry_run)
            row = {
                "camera_id": camera.id,
                "name": camera.name or label,
                "gpio": gpio,
                "board": board.__dict__,
                "led": led.__dict__,
            }
            actuators.append(row)
            if gpio.get("ok") or board.ok or led.ok:
                any_ok = True

        message = (
            f"{'dry-run ' if dry_run else ''}{action} lane {gate.name}"
            + (f" {wanted}" if wanted else "")
            + f": {reason}"
        )
        if not any_ok:
            return GateCommandResult(False, False, message + " — no actuator succeeded", _now(), actuators)
        return GateCommandResult(True, dry_run, message, _now(), actuators)


async def _gpio_pulse(hvx: HVXHostClient, camera: Camera, *, dry_run: bool) -> dict:
    handle = camera.sdk_handle
    index = settings.gpio_index
    pulse_ms = settings.gpio_pulse_ms or CAMCMD_PULSE_DEFAULT_MS
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "api": "Net_WriteGPIOState + Net_GateSetup",
            "handle": handle,
            "index": index,
            "pulse_ms": pulse_ms,
            "message": f"dry-run GPIO pulse index={index} handle={handle}",
        }
    if handle is None:
        return {"ok": False, "message": f"{camera.name} is not SDK-connected; GPIO skipped"}
    try:
        return await hvx.gpio_pulse(handle=int(handle), index=index, pulse_ms=pulse_ms)
    except HVXHostUnavailable as exc:
        return {"ok": False, "message": f"GPIO host unavailable: {exc}"}
    except Exception as exc:
        return {"ok": False, "message": f"GPIO failed: {exc}"}


def controller() -> GateController:
    if settings.gate_physical_control_enabled:
        return PhysicalGateController()
    return SimulatedGateController()
