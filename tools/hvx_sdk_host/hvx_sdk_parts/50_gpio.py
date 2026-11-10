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

    def gpio_pulse(self, handle: int, index: int = 0, pulse_ms: int = 500) -> dict:
        steps = []
        gate_rc = None
        if hasattr(self.dll, "Net_GateSetup"):
            gate_rc = self.gate_setup(handle, GATE_STATE_OPEN, index)
            steps.append({"api": "Net_GateSetup", "rc": gate_rc, "name": describe_rc(gate_rc), "state": GATE_STATE_OPEN, "index": index})
        on_rc = self.write_gpio(handle, index, GPIO_SHORT)
        steps.append({"api": "Net_WriteGPIOState", "rc": on_rc, "name": describe_rc(on_rc), "index": index, "value": GPIO_SHORT})
        time.sleep(max(0.05, min(int(pulse_ms), 5000) / 1000.0))
        off_rc = self.write_gpio(handle, index, GPIO_OPEN_CIRCUIT)
        steps.append({"api": "Net_WriteGPIOState", "rc": off_rc, "name": describe_rc(off_rc), "index": index, "value": GPIO_OPEN_CIRCUIT})
        ok = on_rc == DC_NO_ERROR or gate_rc == DC_NO_ERROR
        return {
            "ok": ok,
            "handle": int(handle),
            "index": int(index),
            "pulse_ms": int(pulse_ms),
            "gate_setup_rc": gate_rc,
            "write_on_rc": on_rc,
            "write_off_rc": off_rc,
            "steps": steps,
            "message": "GPIO pulse on live camera relay" if ok else "GPIO pulse failed",
        }
