"""Linked-vehicle authorization groups, visitor passes and exit confirmations.

Additive. New tables:

* ``vehicle_groups`` – private-owner groups and company fleets.
* ``vehicle_group_occupancies`` – the slot a member holds while inside. The
  partial unique index ``uq_vehicle_group_occupancy_live_slot`` (group, slot)
  WHERE released_at IS NULL is the concurrency authority: two linked cars
  arriving at the same moment cannot both hold a PRIVATE group's only slot.
* ``visitor_passes`` – temporary authorization without vehicle registration.
* ``exit_confirmations`` – audit of manual exit confirmations and reconciliations.

New nullable columns: ``registered_vehicles.group_id``,
``parking_sessions.authorization_group_id`` and ``parking_sessions.visitor_pass_id``.
Existing rows keep NULL, so every existing vehicle stays independent and every
existing flow behaves exactly as before.

Downgrade drops the new tables and columns (group membership, visitor passes and
the exit-confirmation audit are lost; sessions and vehicles are kept).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0021_linked_vehicle_groups"
down_revision = "0020_clear_legacy_capture_zones"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _tables() -> set[str]:
    return set(_inspector().get_table_names())


def _columns(table: str) -> set[str]:
    return {c["name"] for c in _inspector().get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {i["name"] for i in _inspector().get_indexes(table) if i.get("name")}


def _postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    tables = _tables()
    if "vehicle_groups" not in tables:
        op.create_table(
            "vehicle_groups",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id"), nullable=False, server_default="1"),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("kind", sa.String(20), nullable=False, server_default="PRIVATE"),
            sa.Column("company_name", sa.String(160), nullable=False, server_default=""),
            sa.Column("owner_name", sa.String(160), nullable=False, server_default=""),
            sa.Column("contact_phone", sa.String(40), nullable=False, server_default=""),
            sa.Column("max_active_sessions", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("exit_release", sa.String(24), nullable=False, server_default="EXIT_LANE"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("site_id", "name", name="uq_vehicle_groups_site_name"),
            # PRIVATE groups are one-at-a-time by definition; the database refuses
            # anything else even if an API bug or a manual SQL edit tries it.
            sa.CheckConstraint("kind <> 'PRIVATE' OR max_active_sessions = 1", name="ck_vehicle_groups_private_single"),
            sa.CheckConstraint("max_active_sessions >= 0", name="ck_vehicle_groups_limit_nonnegative"),
        )
        op.create_index("ix_vehicle_groups_site_id", "vehicle_groups", ["site_id"])
        op.create_index("ix_vehicle_groups_kind", "vehicle_groups", ["kind"])

    if "visitor_passes" not in tables:
        op.create_table(
            "visitor_passes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id"), nullable=False, server_default="1"),
            sa.Column("plate", sa.String(32), nullable=False),
            sa.Column("visitor_name", sa.String(160), nullable=False, server_default=""),
            sa.Column("host_group_id", sa.Integer(), sa.ForeignKey("vehicle_groups.id", ondelete="SET NULL"), nullable=True),
            sa.Column("host_name", sa.String(160), nullable=False, server_default=""),
            sa.Column("purpose", sa.String(240), nullable=False, server_default=""),
            sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
            sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
            sa.Column("max_entries", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("entries_used", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint("max_entries = 0 OR entries_used <= max_entries", name="ck_visitor_passes_entries"),
        )
        op.create_index("ix_visitor_passes_site_id", "visitor_passes", ["site_id"])
        op.create_index("ix_visitor_passes_site_plate", "visitor_passes", ["site_id", "plate"])
        op.create_index("ix_visitor_passes_host_group_id", "visitor_passes", ["host_group_id"])

    if "registered_vehicles" in tables and "group_id" not in _columns("registered_vehicles"):
        # SQLite cannot ALTER TABLE ADD CONSTRAINT; the model declares the FK and
        # PostgreSQL gets a real one below.
        op.add_column("registered_vehicles", sa.Column("group_id", sa.Integer(), nullable=True))
        op.create_index("ix_registered_vehicles_group_id", "registered_vehicles", ["group_id"])
        if _postgres():
            op.create_foreign_key(
                "fk_registered_vehicles_group_id", "registered_vehicles", "vehicle_groups",
                ["group_id"], ["id"], ondelete="SET NULL",
            )

    if "parking_sessions" in tables:
        cols = _columns("parking_sessions")
        if "authorization_group_id" not in cols:
            op.add_column("parking_sessions", sa.Column("authorization_group_id", sa.Integer(), nullable=True))
            op.create_index("ix_parking_sessions_authorization_group_id", "parking_sessions", ["authorization_group_id"])
            if _postgres():
                op.create_foreign_key(
                    "fk_parking_sessions_authorization_group_id", "parking_sessions", "vehicle_groups",
                    ["authorization_group_id"], ["id"],
                )
        if "visitor_pass_id" not in cols:
            op.add_column("parking_sessions", sa.Column("visitor_pass_id", sa.Integer(), nullable=True))
            op.create_index("ix_parking_sessions_visitor_pass_id", "parking_sessions", ["visitor_pass_id"])
            if _postgres():
                op.create_foreign_key(
                    "fk_parking_sessions_visitor_pass_id", "parking_sessions", "visitor_passes",
                    ["visitor_pass_id"], ["id"],
                )

    if "vehicle_group_occupancies" not in _tables():
        op.create_table(
            "vehicle_group_occupancies",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("site_id", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("group_id", sa.Integer(), sa.ForeignKey("vehicle_groups.id"), nullable=False),
            sa.Column("slot", sa.Integer(), nullable=False),
            sa.Column("state", sa.String(20), nullable=False, server_default="ACTIVE"),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("parking_sessions.id"), nullable=True),
            sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("registered_vehicles.id", ondelete="SET NULL"), nullable=True),
            sa.Column("plate", sa.String(32), nullable=False, server_default=""),
            sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("exit_reported_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("release_evidence", sa.String(40), nullable=False, server_default=""),
            sa.Column("release_reason", sa.String(240), nullable=False, server_default=""),
            sa.Column("released_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint("slot >= 1", name="ck_vehicle_group_occupancy_slot"),
            sa.CheckConstraint(
                "(state = 'RELEASED') = (released_at IS NOT NULL)",
                name="ck_vehicle_group_occupancy_released_state",
            ),
        )
        op.create_index(
            "uq_vehicle_group_occupancy_live_slot", "vehicle_group_occupancies", ["group_id", "slot"], unique=True,
            sqlite_where=sa.text("released_at IS NULL"), postgresql_where=sa.text("released_at IS NULL"),
        )
        op.create_index(
            "uq_vehicle_group_occupancy_session", "vehicle_group_occupancies", ["session_id"], unique=True,
            sqlite_where=sa.text("session_id IS NOT NULL"), postgresql_where=sa.text("session_id IS NOT NULL"),
        )
        op.create_index("ix_vehicle_group_occupancies_group_state", "vehicle_group_occupancies", ["group_id", "state"])
        for column in ("site_id", "group_id", "state", "vehicle_id", "plate"):
            op.create_index(f"ix_vehicle_group_occupancies_{column}", "vehicle_group_occupancies", [column])

    if "exit_confirmations" not in _tables():
        op.create_table(
            "exit_confirmations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("site_id", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("parking_sessions.id"), nullable=True),
            sa.Column("occupancy_id", sa.Integer(), sa.ForeignKey("vehicle_group_occupancies.id"), nullable=True),
            sa.Column("group_id", sa.Integer(), sa.ForeignKey("vehicle_groups.id", ondelete="SET NULL"), nullable=True),
            sa.Column("plate", sa.String(32), nullable=False, server_default=""),
            sa.Column("action", sa.String(40), nullable=False),
            sa.Column("evidence", sa.String(40), nullable=False, server_default=""),
            sa.Column("identified_by", sa.String(20), nullable=False, server_default=""),
            sa.Column("previous_state", sa.String(20), nullable=False, server_default=""),
            sa.Column("new_state", sa.String(20), nullable=False, server_default=""),
            sa.Column("session_closed", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("operator_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("operator_name", sa.String(120), nullable=False, server_default=""),
            sa.Column("reason", sa.String(240), nullable=False, server_default=""),
            sa.Column("entry_image_ref", sa.String(300), nullable=False, server_default=""),
            sa.Column("amount_owed", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("currency", sa.String(8), nullable=False, server_default=""),
            sa.Column("extra", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        for column in ("site_id", "session_id", "occupancy_id", "group_id", "plate", "action", "operator_id", "created_at"):
            op.create_index(f"ix_exit_confirmations_{column}", "exit_confirmations", [column])


def downgrade() -> None:
    tables = _tables()
    for table in ("exit_confirmations", "vehicle_group_occupancies"):
        if table in tables:
            op.drop_table(table)
    if "parking_sessions" in tables:
        cols = _columns("parking_sessions")
        indexes = _indexes("parking_sessions")
        for name in ("visitor_pass_id", "authorization_group_id"):
            if name in cols:
                if f"ix_parking_sessions_{name}" in indexes:
                    op.drop_index(f"ix_parking_sessions_{name}", table_name="parking_sessions")
                with op.batch_alter_table("parking_sessions") as batch:
                    batch.drop_column(name)
    if "registered_vehicles" in tables and "group_id" in _columns("registered_vehicles"):
        if "ix_registered_vehicles_group_id" in _indexes("registered_vehicles"):
            op.drop_index("ix_registered_vehicles_group_id", table_name="registered_vehicles")
        with op.batch_alter_table("registered_vehicles") as batch:
            batch.drop_column("group_id")
    for table in ("visitor_passes", "vehicle_groups"):
        if table in _tables():
            op.drop_table(table)
