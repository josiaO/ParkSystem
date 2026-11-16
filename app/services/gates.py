"""Open a numbered lane through barrier actuators, with display as side effect.

Barrier authority is deliberately narrower than "any I/O succeeded":

- camera GPIO / vendor gate relay is a barrier actuator;
- Board* TCP relay is a barrier actuator;
- LED UDP is display-only and can never make a gate command successful.

This prevents a healthy sign/display from being mistaken for a physically
opened boom gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import time

from app.config import settings
from app.core import latency_trace
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
        barrier_ok = False
        tracer = latency_trace.get_tracer()
        open_started = time.perf_counter_ns()
        tracer.emit("gate.open_start", gate=gate.name, side=wanted, action=action, dry_run=dry_run,
                    cameras=[c.id for c in rows])

        def elapsed_ms(start_ns: int) -> float:
            return round((time.perf_counter_ns() - start_ns) / 1e6, 3)

        for camera in rows:
            label = f"{gate.name} {side_label(camera.lane_direction)}"
            # These run one after another. The board relay (when it is the
            # barrier actuator) is only commanded after the GPIO pulse call
            # has returned, which includes the pulse hold time.
            step = time.perf_counter_ns()
            gpio = await _gpio_pulse(hvx, camera, dry_run=dry_run)
            gpio_ms = elapsed_ms(step)
            step = time.perf_counter_ns()
            board = await send_board_command(camera.controller_ip or "", action=action, dry_run=dry_run)
            board_ms = elapsed_ms(step)
            text = led_text or (EXIT_LED if (camera.lane_direction or "").upper() == "EXIT" else ENTRY_LED)
            step = time.perf_counter_ns()
            led = await send_led_text(camera.display_ip or "", text, dry_run=dry_run)
            led_ms = elapsed_ms(step)
            tracer.emit(
                "gate.actuators", camera=camera.id, gpio_ok=bool(gpio.get("ok")), gpio_ms=gpio_ms,
                board_configured=bool(camera.controller_ip), board_ok=bool(board.ok), board_ms=board_ms,
                board_started_after_open_ms=round(gpio_ms, 3), led_ms=led_ms,
                since_open_start_ms=elapsed_ms(open_started),
            )
            row = {
                "camera_id": camera.id,
                "name": camera.name or label,
                "gpio": gpio,
                "board": board.__dict__,
                "led": led.__dict__,
            }
            actuators.append(row)
            # Only devices capable of moving the boom count as gate success.
            # LED/display delivery is useful telemetry, never authorization that
            # the physical barrier opened.
            if gpio.get("ok") or board.ok:
                barrier_ok = True

        tracer.emit("gate.open_result", ok=barrier_ok, dry_run=dry_run, total_ms=elapsed_ms(open_started))
        message = (
            f"{'dry-run ' if dry_run else ''}{action} lane {gate.name}"
            + (f" {wanted}" if wanted else "")
            + f": {reason}"
        )
        if not barrier_ok:
            display_note = " (display updated)" if any(
                bool((item.get("led") or {}).get("ok")) for item in actuators
            ) else ""
            return GateCommandResult(
                False,
                dry_run,
                message + " — no barrier actuator succeeded" + display_note,
                _now(),
                actuators,
            )
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
