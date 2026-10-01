# Secrets and redaction

## Purpose

The database stores `credentials_ref`, not raw camera passwords, and no secret
(RTSP password, provider key, webhook hash, mobile-money credential, Gemini
key) leaves the process through API responses, logs, exception bodies or the
diagnostics bundle.

## SecretStore (`app/infrastructure/secrets`)

| Backend | Where | When |
| --- | --- | --- |
| `dpapi` | `data_dir/secrets/<ref>.bin`, DPAPI machine scope via ctypes `CryptProtectData` | **default on Windows** (`SMARTPARK_SECRETS_BACKEND=auto`) |
| `file` | `data_dir/secrets/<ref>.secret`, directory 0700 / file 0600 | opt-in on Linux/macOS; also what `dpapi` degrades to off Windows |
| `memory` | process dict | tests |
| `db` | legacy: raw value stays in `cameras.password_secret` | **default on non-Windows** so evaluation databases keep working |

Set `SMARTPARK_SECRETS_BACKEND` to `dpapi`, `file`, `memory` or `db`. `auto`
picks `dpapi` on Windows and `db` elsewhere. Invalid values fall back to `db`.

Refs look like `camera:<32 hex>`; anything else is rejected before touching the
filesystem (no path traversal). `Camera.password_secret` is now a property:

- setter → `store_secret()` writes to the backend, keeps the same ref on
  rotation, empties the legacy column; with the `db` backend it writes the
  column as before.
- getter → `resolve_secret(ref, fallback=column)`; adapters (`hvx.py`,
  `rtsp.py`, `onvif.py`, `mediamtx_sources.py`) are unchanged.
- deleting a camera deletes its stored secret.

At every Site Service start `services/secrets_migration.migrate_plaintext_secrets`
moves any remaining plaintext rows into the active external backend and logs the
count. Failures are per camera and never block start-up.

DPAPI was implemented against the documented `CryptProtectData` /
`CryptUnprotectData` signatures (UI forbidden, local-machine scope, fixed
entropy) but **has not been executed on Windows in this environment**; the
technician checklist in `PHASE-2-ACCEPTANCE.md` covers it. Windows Credential
Manager was not used: the 32-bit HVX host and the 64-bit Site Service would
need separate vaults, while machine-scope DPAPI blobs under `PROGRAMDATA` are
readable by both.

## Redaction (`app/services/redaction.py`)

One implementation, four surfaces:

| Surface | Hook |
| --- | --- |
| API error bodies | FastAPI handlers for `HTTPException` and `Exception` in `api_main` |
| Logs | `RedactingFilter` installed by `logging_setup.configure_logging` on the `smartpark`, root and uvicorn loggers |
| Health / diagnostics | `health.details()` and `GET /health/diagnostics` pass through `redact_obj` |
| Payments | `infrastructure/payments/common.redact` / `scrub_text` delegate here |

`redact_text` masks URL credentials (`rtsp://admin:***@…`), `password=` /
`token:` style pairs, known key formats (`FLWSECK…`, `AIza…`, `sk-…`, bearer
tokens) and every *registered* secret verbatim — configured provider keys and
webhook hashes from settings plus any camera password resolved at runtime.
`redact_obj` additionally masks secret-like keys (`password`, `api_key`,
`secret_hash`, `checksum`, `pin`, `authorization`…) and phone-number keys, while
leaving identifiers such as `credentials_ref`, `idempotency_key`,
`public_token`, `token_cached` and `*_configured` flags readable.

`camera_dict` returns `rtsp_url` redacted; `PATCH /cameras/{id}` recognises the
masked value coming back from the edit form and keeps the stored URL, so
operators can save other fields without re-typing the RTSP password.

## Diagnostics bundle

`GET /health/diagnostics` (permission `hardware.view`) returns app/runtime
info, `schema` (Alembic revision vs head), `secret_store` backend, which secret
settings are configured (booleans only), camera and gate summaries and the full
health payload — all redacted. Attach it to support tickets instead of raw logs.

## Rollback

`SMARTPARK_SECRETS_BACKEND=db` restores the legacy behaviour for new writes.
Cameras whose credential was already moved keep working: with `db` active and
an empty column, `resolve_secret` falls back to reading the platform's external
store (DPAPI on Windows, file store elsewhere) for that ref. Setting a camera's
password again while `db` is active writes the column. Redaction has no switch:
it only removes text.
