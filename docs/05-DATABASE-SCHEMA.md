# Database schema

## Purpose

Document the live SQLAlchemy schema. SQLite is the production file today; the same models are meant to run on PostgreSQL when `SMARTPARK_DATABASE_URL` is set.

## What owns this

`app/models.py`, created/altered by `app/db.py` `ensure_schema()`.

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

`cameras` also stores `stream_profiles` (MAIN/SUB/LIVE/DETECT/EVIDENCE JSON), `ffmpeg_profile`, `rtsp_transport`, `media_capabilities`, `recognition_mode`, and optional `vendor` / `model_name` / `serial` / `camera_type`. `rtsp_url` remains the fallback URI. `vehicle_captures` may store `plate_country`, `plate_region`, `plate_type`, `source`, and `event_id`. Site locale/timezone/currency and migration flags live in `site_settings` (`site`, `migration`).

## Request / event flow

`ensure_schema()` → `create_all` plus SQLite `ALTER TABLE` for columns added after the first file existed. New tables appear via `create_all`.

## Failure behavior

WAL + `busy_timeout` on SQLite. NullPool so MJPEG does not exhaust a QueuePool.

## Security

`password_secret` on cameras is a local MVP; do not send it to the frontend (`camera_dict` omits it). User passwords are Argon2 hashes.

## Configuration

`SMARTPARK_DATABASE_URL` optional. Default SQLite path from `app/config.py`.

## Tests

In-memory SQLite in pytest/unittest clients. `is_sqlite` / `is_postgres` helpers.

## How to extend safely

Add a column to `ensure_schema()` for existing SQLite files. Add UniqueConstraint for new natural keys.

## Common mistakes

Holding a session open during GPIO or payment HTTP. Using `create_all` alone and expecting old `.db` files to gain columns.
