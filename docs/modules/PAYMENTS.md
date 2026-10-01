# PAYMENTS Module

See [MODULE-REGISTRY.md](MODULE-REGISTRY.md) and [OVERVIEW.md](OVERVIEW.md).

Implementation lives under `app/domain/`, `app/services/`, and `app/infrastructure/` — working HVX/Media paths are preserved.

## Sub-modules and routes

| Module | Routes | Notes |
| --- | --- | --- |
| `payments.core` | `/payments`, `/payments/health`, `/payments/reconcile`, `/api/webhooks/{provider}`, `/sessions/{id}/pay` | Ledger, provider webhooks, reconciliation job |
| `payments.kiosk` | `/p/{token}/kiosk-pay` | Operator-confirmed cash |
| `payments.public_web` | `/p/{token}`, `/p/{token}/status`, `/p/{token}/pay`, `/api/public/payment-intents`, `/api/public/payment-status/{token}` | Phone receipt + pay page |

When `payments.core` is disabled (e.g. `LPR_ONLY`), every route above returns 404 and the reconciliation loop does nothing — no provider code runs.

## Providers

`simulated` (default), `kiosk_manual`, `mobile_money` (generic HMAC placeholder), `flutterwave` (TEST by default) and `clickpesa` (live-disabled). External providers are documented in [`../MOBILE-MONEY-PROVIDERS.md`](../MOBILE-MONEY-PROVIDERS.md); the ledger rules are in [`../14-PAYMENT-ARCHITECTURE.md`](../14-PAYMENT-ARCHITECTURE.md).
