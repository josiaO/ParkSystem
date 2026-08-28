# HVX gate integration

## Purpose

Each numbered lane side has three actuators. The opener tries all three that have an IP or SDK handle:

1. Camera GPIO — `Net_GateSetup` / `Net_WriteGPIOState` through the HVX host
2. Board* TCP I/O controller (`app.services.board_tcp`)
3. IpAddr* LED UDP (`app.services.led_udp`)

`HVXGateAdapter` wraps `app.services.gates.controller()`. It does not reimplement pulses.

Physical vs simulated is `SMARTPARK_GATE_PHYSICAL_CONTROL_ENABLED`. This site runs with physical enabled. Confirm the lane in the UI before a manual open.

## SHADOW

Automatic parking opens (`take_receipt`, paid exit) become `dry_run`. Manual `/gates/{id}/open` and camera barrier buttons still pulse so commissioning stays possible.
