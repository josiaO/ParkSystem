# Adding a camera vendor

Implement `CameraAdapter` (`connect`, `health`, `capabilities`, `snapshot`, `live_sources`, plus `disconnect` if the SDK needs it).

1. Register in `app/infrastructure/hardware/cameras/ADAPTERS`.
2. Declare capabilities; do not pretend native plates if the camera has none.
3. Contract tests in `tests/test_adapters.py` / `tests/test_migration_architecture.py`.
4. Onboarding should recommend the adapter from probe results.
5. Shadow on one camera. Production only after soak.

Do **not** edit `handle_plate_event` or fee/session code. Unknown `adapter_id` still falls back to HVX.

Dashboard vs code: [10-ADDING-A-NEW-CAMERA-VENDOR.md](10-ADDING-A-NEW-CAMERA-VENDOR.md).
