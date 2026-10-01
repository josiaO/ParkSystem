# Database schema

## Purpose

Document the live SQLAlchemy schema. SQLite is the production file today; the same models are meant to run on PostgreSQL when `SMARTPARK_DATABASE_URL` is set.

## What owns this

`app/models.py` defines the tables. Schema changes are **Alembic revisions** under `app/migrations/alembic/versions/`; `app/db.py` `ensure_schema()` delegates to `app/migrations/runner.upgrade_to_head()` at start-up. See `docs/DATABASE-MIGRATIONS.md`.

## What it must NOT do

- Require a Postgres migration before the site can run
- Use SQLite-only column types that block a later URL switch
- Drop historical operator/payment rows

## Diagram

See `docs/04-DOMAIN-MODEL.md`.

## Main data structures

Core tables: `users`, `roles`, `user_roles`, `auth_sessions`, `gates`, `cameras`, `parking_sessions`, `vehicle_captures`, `access_plans`, `registered_vehicles`, `tariffs`, `receipts`, `site_settings`, `audit_logs`.

Ledger / decision tables: `payment_intents`, `payment_transactions`, `access_decisions`, `gate_commands`.

Indexes of note: plate + session status, `public_token`, payment `idempotency_key`, `provider_transaction_id`, `gate_commands.command_uuid`.

Site scoping (revision `0002`): `gates`, `cameras`, `tariffs`, `access_plans` and `registered_vehicles` carry `site_id` (NOT NULL, default `1`, FK `sites.id`). Names are unique **per site** — `uq_gates_site_name`, `uq_cameras_site_name`, `uq_tariffs_site_name`, `uq_access_plans_site_name` — and plates per site via `uq_registered_vehicles_site_plate`. Two sites may reuse `Entry` or `1#`; the same site still gets a 409 on a duplicate.

`cameras` also stores `stream_profiles` (MAIN/SUB/LIVE/DETECT/EVIDENCE JSON), `ffmpeg_profile`, `rtsp_transport`, `media_capabilities`, `recognition_mode`, and optional `vendor` / `model_name` / `serial` / `camera_type`. `rtsp_url` remains the fallback URI. `vehicle_captures` may store `plate_country`, `plate_region`, `plate_type`, `source`, and `event_id`. Site locale/timezone/currency and migration flags live in `site_settings` (`site`, `migration`).

## Request / event flow

`ensure_schema()` → `upgrade_to_head(engine)`: fresh file → `create_all` + `alembic stamp head`; pre-Alembic file → frozen legacy column fixups (`app/migrations/legacy.py`) once, `stamp 0001_baseline`, `upgrade head`; managed file → `upgrade head`. Health reports `database.schema.revision` vs `head`.

## Failure behavior

WAL + `busy_timeout` on SQLite. NullPool so MJPEG does not exhaust a QueuePool.

## Security

Camera credentials go through the SecretStore (`app/infrastructure/secrets`): the row stores `credentials_ref` and the legacy `password_secret` column is emptied once an external backend (DPAPI on Windows, opt-in file store elsewhere) is active. Use the `Camera.password_secret` *property*; never query the column. `camera_dict` returns `credentials_ref`/`password_configured` and a redacted `rtsp_url`. User passwords are Argon2 hashes. See `docs/SECRETS-AND-REDACTION.md`.

## Configuration

`SMARTPARK_DATABASE_URL` optional. Default SQLite path from `app/config.py`.

## Tests

In-memory SQLite in pytest/unittest clients. `is_sqlite` / `is_postgres` helpers.

## How to extend safely

Add the column/constraint to `app/models.py` **and** write an Alembic revision (`alembic revision -m "..."` then hand-edit; use `op.batch_alter_table` for SQLite). Never add ALTERs to `app/migrations/legacy.py`. Natural keys are site-scoped: `UniqueConstraint("site_id", ...)`.

## Common mistakes

Holding a session open during GPIO or payment HTTP. Editing models without a revision (the runner will not invent one). Reading `Camera._password_secret` directly instead of the property.
