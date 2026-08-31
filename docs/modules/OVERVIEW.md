# SmartPark Module Overview

SmartPark Edge is a **modular monolith**: one codebase, many deployment shapes. Enabled modules determine UI, API surface, background jobs, and health — not separate products.

## Layers

| Layer | Location | Role |
|-------|----------|------|
| Domain contracts | `app/domain/` | Modules, events, site policy, adapter protocols |
| Application | `app/application/` | Thin use-case wrappers (growing) |
| Infrastructure | `app/infrastructure/` | Adapters (HVX, MediaMTX, FastALPR, gates, printers, payments) |
| Services | `app/services/` | Runtime orchestration (preserves working paths) |

## Three-way gating

1. **Module entitlement** — site owns the capability (`site_settings.modules`)
2. **Feature flag** — rollout/shadow (`site_settings.migration`, env)
3. **Permission** — user may act (RBAC)

Navigation appears when: `module enabled AND user has permission`.

## Deployment profiles

Presets live in `app/domain/modules.py`: `LPR_ONLY`, `SECURITY`, `ACCESS_CONTROL`, `PARKING_LITE`, `PARKING_PRO`, `ENTERPRISE`, `CUSTOM`.

See [DEPLOYMENT-PROFILES.md](../onboarding/DEPLOYMENT-PROFILES.md).

## Working engine rule

HVX NetSDK host, MediaMTX sidecar, and gate GPIO paths are **wrapped**, not replaced. Unknown camera adapters fall back to HVX.
