# Adding an Adapter

Adapter registries (do not bypass working HVX path):

| Registry | Path |
|----------|------|
| Cameras | `app/infrastructure/hardware/cameras/` |
| Gates | `app/infrastructure/hardware/gates/` |
| Recognition | `app/infrastructure/recognition/` |
| Media | `app/infrastructure/media/registry.py` |
| Printers | `app/infrastructure/hardware/printers.py` |
| Payments | `app/infrastructure/payments/` |

1. Implement the domain protocol (`app/domain/*.py`).
2. Register in the adapter `ADAPTERS` or `PROVIDERS` dict.
3. Default unknown camera ids to `hvx`.
4. Output normalized recognition via `normalize_event()` / `PlateRecognized`.
5. Add contract tests — see `tests/test_adapters.py`, `tests/test_migration_architecture.py`.

Parking and session code must not change when adding a vendor.
