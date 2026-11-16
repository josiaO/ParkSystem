from __future__ import annotations

class _HVXGPIOMixin:
    def read_gpio(self, handle: int, index: int = 1) -> dict:
        if not hasattr(self.dll, "Net_ReadGPIOState"):
            raise HVXSDKError("Net_ReadGPIOState not exported")
        value = ctypes.c_ubyte(0)
        rc = int(self.dll.Net_ReadGPIOState(int(handle), index & 0xFF, ctypes.byref(value)))
        row = {
            "ok": rc == DC_NO_ERROR,
            "rc": rc,
            "rc_name": describe_rc(rc),
            "handle": int(handle),
            "index": int(index),
            "value": int(value.value),
        }
        with self._lock:
            self._gpio_state[(int(handle), int(index))] = row
        return row

    def gpio_states(self, handle: int, indexes: list[int] | None = None) -> list[dict]:
        rows = []
        for index in indexes or [1, 2]:
            try:
                rows.append(self.read_gpio(handle, index))
            except Exception as exc:
                rows.append({"ok": False, "handle": int(handle), "index": int(index), "error": str(exc)})
        return rows

    def gate_setup(self, handle: int, state: int = GATE_STATE_OPEN, index: int = 0) -> int:
        if not hasattr(self.dll, "Net_GateSetup"):
            raise HVXSDKError("Net_GateSetup not exported")
        cmd = T_ControlGate()
        cmd.ucState = state & 0xFF
        cmd.ucIndex = index & 0xFF
        cmd.ucGateDefSta = 0
        cmd.ucReserved = 0
        return int(self.dll.Net_GateSetup(int(handle), ctypes.byref(cmd)))

    def write_gpio(self, handle: int, index: int, value: int) -> int:
        if not hasattr(self.dll, "Net_WriteGPIOState"):
            raise HVXSDKError("Net_WriteGPIOState not exported")
        return int(self.dll.Net_WriteGPIOState(int(handle), index & 0xFF, value & 0xFF))

    def gpio_pulse(self, handle: int, index: int = 0, pulse_ms: int = 500, *, trace_id: str = "") -> dict:
        """Close the relay, hold it for ``pulse_ms``, open it again.

        ``timing`` reports each SDK step against perf_counter_ns so the caller
        can see when the relay was commanded (``relay_on_perf_ns``) separately
        from when this call returns (after the hold).
        """
        def ms_since(start_ns: int) -> float:
            return round((time.perf_counter_ns() - start_ns) / 1_000_000.0, 3)

        steps = []
        gate_rc = None
        started_ns = time.perf_counter_ns()
        timing: dict = {"sdk_start_perf_ns": started_ns}
        _trace("host.gpio.sdk_start", trace=trace_id or None, camera=int(handle), index=int(index), pulse_ms=int(pulse_ms))
        if hasattr(self.dll, "Net_GateSetup"):
            step_ns = time.perf_counter_ns()
            gate_rc = self.gate_setup(handle, GATE_STATE_OPEN, index)
            timing["gate_setup_ms"] = ms_since(step_ns)
            timing["gate_setup_returned_perf_ns"] = time.perf_counter_ns()
            steps.append({"api": "Net_GateSetup", "rc": gate_rc, "name": describe_rc(gate_rc), "state": GATE_STATE_OPEN, "index": index})
        step_ns = time.perf_counter_ns()
        on_rc = self.write_gpio(handle, index, GPIO_SHORT)
        timing["write_on_ms"] = ms_since(step_ns)
        timing["relay_on_perf_ns"] = time.perf_counter_ns()
        steps.append({"api": "Net_WriteGPIOState", "rc": on_rc, "name": describe_rc(on_rc), "index": index, "value": GPIO_SHORT})
        _trace(
            "host.gpio.relay_on", trace=trace_id or None, camera=int(handle), index=int(index),
            gate_setup_rc=gate_rc, write_on_rc=on_rc, gate_setup_ms=timing.get("gate_setup_ms"),
            write_on_ms=timing["write_on_ms"], sdk_start_to_relay_on_ms=ms_since(started_ns),
        )
        hold_ns = time.perf_counter_ns()
        time.sleep(max(0.05, min(int(pulse_ms), 5000) / 1000.0))
        timing["hold_ms"] = ms_since(hold_ns)
        step_ns = time.perf_counter_ns()
        off_rc = self.write_gpio(handle, index, GPIO_OPEN_CIRCUIT)
        timing["write_off_ms"] = ms_since(step_ns)
        timing["total_ms"] = ms_since(started_ns)
        steps.append({"api": "Net_WriteGPIOState", "rc": off_rc, "name": describe_rc(off_rc), "index": index, "value": GPIO_OPEN_CIRCUIT})
        ok = on_rc == DC_NO_ERROR or gate_rc == DC_NO_ERROR
        HOST_METRICS.observe("gpio.sdk_start_to_relay_on", (timing["relay_on_perf_ns"] - started_ns) / 1_000_000.0)
        HOST_METRICS.observe("gpio.write_on", timing["write_on_ms"])
        if timing.get("gate_setup_ms") is not None:
            HOST_METRICS.observe("gpio.gate_setup", timing["gate_setup_ms"])
        HOST_METRICS.observe("gpio.pulse_total", timing["total_ms"])
        HOST_METRICS.incr("gpio.pulses_ok" if ok else "gpio.pulses_failed")
        _trace(
            "host.gpio.sdk_done", trace=trace_id or None, camera=int(handle), index=int(index), ok=ok,
            write_off_rc=off_rc, hold_ms=timing["hold_ms"], write_off_ms=timing["write_off_ms"],
            total_ms=timing["total_ms"],
        )
        return {
            "ok": ok,
            "handle": int(handle),
            "index": int(index),
            "pulse_ms": int(pulse_ms),
            "gate_setup_rc": gate_rc,
            "write_on_rc": on_rc,
            "write_off_rc": off_rc,
            "steps": steps,
            "timing": timing,
            "message": "GPIO pulse on live camera relay" if ok else "GPIO pulse failed",
        }
