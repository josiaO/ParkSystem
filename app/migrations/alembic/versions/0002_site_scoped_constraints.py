"""Site-scoped uniqueness + camera credentials_ref.

* ``cameras``, ``tariffs``, ``access_plans``, ``registered_vehicles`` gain
  ``site_id`` (NOT NULL, default 1, FK sites.id) backfilled to the default site.
* ``gates.site_id`` becomes NOT NULL with the same default.
* Global ``UNIQUE(name)`` / ``UNIQUE(plate)`` become ``UNIQUE(site_id, name)``
  / ``UNIQUE(site_id, plate)`` so two sites may reuse a gate/camera/plan name.
* ``cameras.credentials_ref`` (SecretStore reference) is added.

Idempotent: each step checks the live schema first, so a database created by
``create_all`` at head and stamped is left untouched.

Revision ID: 0002_site_scoped_constraints
Revises: 0001_baseline
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
import warnings

revision = "0002_site_scoped_constraints"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

DEFAULT_SITE_ID = 1

# table -> (scoped column, composite constraint name, legacy unique index name or None)
SCOPED = {
    "gates": ("name", "uq_gates_site_name", None),
    "cameras": ("name", "uq_cameras_site_name", None),
    "tariffs": ("name", "uq_tariffs_site_name", None),
    "access_plans": ("name", "uq_access_plans_site_name", None),
    "registered_vehicles": ("plate", "uq_registered_vehicles_site_plate", "ix_registered_vehicles_plate"),
}


def _insp():
    return sa.inspect(op.get_bind())


def _tables() -> set[str]:
    return set(_insp().get_table_names())


def _columns(table: str) -> set[str]:
    return {c["name"] for c in _insp().get_columns(table)}


def _unique_names(table: str) -> set[str]:
    return {c.get("name") or "" for c in _insp().get_unique_constraints(table)}


def _index_names(table: str) -> set[str]:
    return {i["name"] for i in _insp().get_indexes(table) if i.get("name")}


def _ensure_default_site() -> None:
    bind = op.get_bind()
    if "sites" not in _tables():
        return
    exists = bind.execute(sa.text("SELECT id FROM sites WHERE id = :sid"), {"sid": DEFAULT_SITE_ID}).first()
    if not exists:
        bind.execute(
            sa.text(
                "INSERT INTO sites (id, name, timezone, locale, currency, enabled) "
                "VALUES (:sid, 'Default Site', 'UTC', 'en', 'USD', 1)"
            ),
            {"sid": DEFAULT_SITE_ID},
        )


def _add_site_id(table: str) -> None:
    if "site_id" not in _columns(table):
        op.add_column(table, sa.Column("site_id", sa.Integer(), nullable=True, server_default=str(DEFAULT_SITE_ID)))
    op.get_bind().execute(sa.text(f"UPDATE {table} SET site_id = :sid WHERE site_id IS NULL"), {"sid": DEFAULT_SITE_ID})


def _reflected_without_uniques(table: str) -> sa.Table:
    """copy_from table for SQLite batch mode with the global uniques stripped."""
    meta = sa.MetaData()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="SQL-parsed foreign key constraint")
        reflected = sa.Table(table, meta, autoload_with=op.get_bind())
    for constraint in list(reflected.constraints):
        if isinstance(constraint, sa.UniqueConstraint):
            reflected.constraints.remove(constraint)
    for index in list(reflected.indexes):
        if index.unique:
            index.unique = False
    for column in reflected.columns:
        column.unique = None
    return reflected


def _scope_unique_sqlite(table: str, column: str, uq_name: str) -> None:
    reflected = _reflected_without_uniques(table)
    existing_indexes = _index_names(table)
    with op.batch_alter_table(table, copy_from=reflected, recreate="always") as batch:
        batch.alter_column("site_id", existing_type=sa.Integer(), nullable=False, server_default=str(DEFAULT_SITE_ID))
        batch.create_unique_constraint(uq_name, ["site_id", column])
        batch.create_foreign_key(f"fk_{table}_site_id_sites", "sites", ["site_id"], ["id"])
        if f"ix_{table}_site_id" not in existing_indexes:
            batch.create_index(f"ix_{table}_site_id", ["site_id"])
        if f"ix_{table}_{column}" not in existing_indexes:
            batch.create_index(f"ix_{table}_{column}", [column])


def _scope_unique_generic(table: str, column: str, uq_name: str, legacy_index: str | None) -> None:
    insp = _insp()
    for constraint in insp.get_unique_constraints(table):
        cols = list(constraint.get("column_names") or [])
        if cols == [column] and constraint.get("name"):
            op.drop_constraint(constraint["name"], table, type_="unique")
    for index in insp.get_indexes(table):
        if index.get("unique") and list(index.get("column_names") or []) == [column] and index.get("name"):
            op.drop_index(index["name"], table_name=table)
    op.alter_column(table, "site_id", existing_type=sa.Integer(), nullable=False, server_default=str(DEFAULT_SITE_ID))
    op.create_unique_constraint(uq_name, table, ["site_id", column])
    op.create_foreign_key(f"fk_{table}_site_id_sites", table, "sites", ["site_id"], ["id"])
    existing = _index_names(table)
    if f"ix_{table}_site_id" not in existing:
        op.create_index(f"ix_{table}_site_id", table, ["site_id"])
    if f"ix_{table}_{column}" not in existing:
        op.create_index(f"ix_{table}_{column}", table, [column])


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables()
    _ensure_default_site()

    if "cameras" in tables and "credentials_ref" not in _columns("cameras"):
        op.add_column("cameras", sa.Column("credentials_ref", sa.String(120), nullable=False, server_default=""))

    for table, (column, uq_name, legacy_index) in SCOPED.items():
        if table not in tables:
            continue
        _add_site_id(table)
        if uq_name in _unique_names(table):
            continue  # already site-scoped (fresh create_all schema)
        if bind.dialect.name == "sqlite":
            _scope_unique_sqlite(table, column, uq_name)
        else:
            _scope_unique_generic(table, column, uq_name, legacy_index)


def downgrade() -> None:
    """Best effort: restore global uniqueness (fails if two sites share a name)."""
    bind = op.get_bind()
    tables = _tables()
    for table, (column, uq_name, _legacy_index) in SCOPED.items():
        if table not in tables or uq_name not in _unique_names(table):
            continue
        if bind.dialect.name == "sqlite":
            meta = sa.MetaData()
            reflected = sa.Table(table, meta, autoload_with=bind)
            for constraint in list(reflected.constraints):
                if isinstance(constraint, sa.UniqueConstraint) and constraint.name == uq_name:
                    reflected.constraints.remove(constraint)
            with op.batch_alter_table(table, copy_from=reflected, recreate="always") as batch:
                batch.create_unique_constraint(f"uq_{table}_{column}", [column])
        else:
            op.drop_constraint(uq_name, table, type_="unique")
            op.create_unique_constraint(f"uq_{table}_{column}", table, [column])
    if "cameras" in tables and "credentials_ref" in _columns("cameras"):
        with op.batch_alter_table("cameras") as batch:
            batch.drop_column("credentials_ref")
