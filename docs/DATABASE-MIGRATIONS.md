# Database migrations (Alembic)

## Purpose

Alembic is the schema authority for the live store. SQLite remains the
production file for small sites and every test; PostgreSQL is the same models
behind `SMARTPARK_DATABASE_URL`. Ad-hoc `ALTER TABLE` at start-up is over: the
old list is frozen in `app/migrations/legacy.py` and only runs once, when a
pre-Alembic file is first adopted.

## Layout

```text
alembic.ini                              CLI entry (URL always comes from settings)
app/migrations/runner.py                 upgrade_to_head / current_revision / status
app/migrations/legacy.py                 frozen pre-Alembic column fixups (do not extend)
app/migrations/alembic/env.py            target_metadata = Base.metadata, batch mode on SQLite
app/migrations/alembic/versions/
  0001_baseline.py                       empty marker = "schema as create_all produced it"
  0002_site_scoped_constraints.py        site_id + per-site uniqueness + cameras.credentials_ref
  0003_vehicle_capture_ai_review.py      vehicle_captures.ai_review JSON
  0004_parking_session_engine.py         session site_id, lanes, lifecycle, event ids, open-plate uniqueness
```

## What happens at start-up

`app.db.ensure_schema()` → `app.migrations.runner.upgrade_to_head(engine)`:

| Database state | Action |
| --- | --- |
| No application tables | `Base.metadata.create_all` then `alembic stamp head` |
| Tables, no `alembic_version` (pre-Alembic file) | legacy column fixups → `create_all` for tables that never existed → `stamp 0001_baseline` → `upgrade head` |
| `alembic_version` present | `upgrade head` |

The runner holds a process lock, logs `schema adopt/fresh/upgrade`, and raises
on failure: a half-migrated schema stops the Site Service instead of running
against unknown columns. `GET /health/details` → `database.schema` reports
`revision`, `head`, `up_to_date`, `mode`, `legacy_fixups` and `duration_ms`.

Revision `0002` is idempotent: it inspects the live schema and skips tables that
already carry the composite constraint, so a fresh `create_all` schema that is
forced through `upgrade` is left untouched. It was exercised against a real
pre-Alembic evaluation file (unnamed `UNIQUE (name)` constraints, gates with
`site_id NULL`) and against fresh files.

## Site-scoped constraints (0002)

| Table | Old | New |
| --- | --- | --- |
| `gates` | `UNIQUE(name)`, `site_id NULL` | `site_id NOT NULL DEFAULT 1`, `uq_gates_site_name (site_id, name)` |
| `cameras` | `UNIQUE(name)` | `site_id`, `uq_cameras_site_name`, `credentials_ref VARCHAR(120) DEFAULT ''` |
| `tariffs` | `UNIQUE(name)` | `site_id`, `uq_tariffs_site_name` |
| `access_plans` | `UNIQUE(name)` | `site_id`, `uq_access_plans_site_name` |
| `registered_vehicles` | unique index on `plate` | `site_id`, non-unique `ix_registered_vehicles_plate`, `uq_registered_vehicles_site_plate` |

Existing rows are backfilled to site `1` (created if the `sites` row is
missing). Models default `site_id` to `DEFAULT_SITE_ID`, so single-site code
paths and the 409 "already exists" behaviour are unchanged.

SQLite cannot drop an unnamed constraint, so the revision reflects each table,
strips its `UniqueConstraint`s / unique index flags and rebuilds the table with
`op.batch_alter_table(copy_from=..., recreate="always")`. On PostgreSQL the
same revision drops constraints by their reflected names.

## Operator commands

```bash
.venv/bin/alembic current            # revision on the configured database
.venv/bin/alembic history
.venv/bin/alembic upgrade head       # normally unnecessary; the Site Service does this
.venv/bin/alembic downgrade 0001_baseline   # best effort; fails if two sites share a name
```

Back up `smartpark.db` before a manual downgrade. The Site Service never
downgrades on its own.

## Adding a schema change

1. Change `app/models.py`.
2. `.venv/bin/alembic revision -m "short_name"` and rename the file to
   `000N_short_name.py` with `revision = "000N_short_name"`.
3. Write `upgrade()`/`downgrade()` by hand. Use `op.batch_alter_table` for any
   SQLite constraint change; check `sa.inspect(op.get_bind())` first so the
   revision is idempotent.
4. Add a test in `tests/test_platform_migrations_secrets.py` that builds the
   old shape with raw SQL and runs `upgrade_to_head`.
5. Do **not** touch `app/migrations/legacy.py`.

## PostgreSQL status

The revision uses dialect-neutral operations and inspector-driven constraint
names; it has not yet been executed against a live PostgreSQL instance in this
environment. That acceptance run remains outstanding (see
`docs/engineering/PHASE-2-ACCEPTANCE.md`).
