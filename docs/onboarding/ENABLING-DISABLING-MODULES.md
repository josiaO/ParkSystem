# Enabling and Disabling Modules

1. Open **Setup Wizard** or call `PUT /modules/profile`.
2. Dependencies are validated automatically (e.g. `parking.sessions` requires `recognition.alpr` and `access.gates`).
3. Disabled modules:
   - Hide from navigation
   - Return 404 on module-guarded routes
   - Show **Disabled** (neutral) in health — not an error
4. Feature flags (`migration` settings) remain independent for HVX/Media/FastALPR rollout.

To grow from LPR-only to parking: apply `PARKING_LITE` — no reinstall required.
