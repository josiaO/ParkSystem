# Gate adapters

## Purpose

Boom control is a separate boundary from cameras and video.

## What owns this

- Contract: `app/domain/gates.py` (`open`, `close`, `get_state`, `health`)
- HVX wrap: `app/infrastructure/hardware/gates/hvx.py` → `app/services/gates.py`
- Registry: `app/infrastructure/hardware/gates/ADAPTERS`

This site pulses open via camera GPIO + Board* TCP + LED UDP. `close()` is declared for future Modbus/PLC/ONVIF-relay adapters; HVX reports that pulse-open is the wired behaviour.

SHADOW only dry-runs **automatic** opens. COMMISSIONING remains the default. Manual Hardware Lab opens stay available.

Parking must not know which adapter is used: `live_gate_adapter()`.
