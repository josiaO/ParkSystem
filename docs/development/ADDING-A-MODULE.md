# Adding a Module

1. Add `ModuleDefinition` in `app/domain/modules.py` with dependencies, permissions, nav ids.
2. Register nav item in `NAVIGATION` if UI exposure is needed.
3. Add to relevant deployment profiles.
4. Guard routes with `require_module_permission()` from `app/services/modules.py`.
5. Declare `background_jobs` and skip workers when disabled via `job_allowed()`.
6. Add tests in `tests/test_modules.py`.
7. Document under `docs/modules/`.

Keep hardware paths in adapters under `app/infrastructure/`.
