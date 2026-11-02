# Adding a camera vendor

Implement `CameraAdapter` (`connect`, `health`, `capabilities`, `snapshot`, `live_sources`, plus `disconnect` if the SDK needs it).

1. Register in `app/infrastructure/hardware/cameras/__init__.py`.
2. Declare capabilities; do not pretend native plates if the camera has none.
3. Make the adapter ID flow into `CameraLiveSpec`; native adapters must be selected from identity even before a handle exists.
4. Keep vendor DLLs in a separate worker/host process and expose a bounded latest-frame contract.
5. Contract tests in `tests/test_adapters.py` / `tests/test_migration_architecture.py`.
6. Onboarding should recommend the adapter from probe results.
7. Shadow on one camera. Production only after soak.

Do **not** edit `handle_plate_event` or fee/session code. Unknown `adapter_id`
still falls back to HVX only for legacy compatibility; production deployments
should select a registered adapter explicitly.

Dashboard vs code: [10-ADDING-A-NEW-CAMERA-VENDOR.md](10-ADDING-A-NEW-CAMERA-VENDOR.md).

