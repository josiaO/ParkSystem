"""Visit-scoped entry idempotency.

Revision ID: 0007_visit_idempotency
Revises: 0006_exit_lane_engine
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_visit_idempotency"
down_revision = "0006_exit_lane_engine"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    if table not in set(sa.inspect(bind).get_table_names()):
        return set()
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def _indexes(table: str) -> set[str]:
    bind = op.get_bind()
    if table not in set(sa.inspect(bind).get_table_names()):
        return set()
    return {i["name"] for i in sa.inspect(bind).get_indexes(table) if i.get("name")}


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "parking_sessions" in tables:
        cols = _columns("parking_sessions")
        if "visit_id" not in cols:
            op.add_column(
                "parking_sessions",
                sa.Column("visit_id", sa.String(64), nullable=False, server_default=""),
            )
            cols = _columns("parking_sessions")
        names = _indexes("parking_sessions")
        if (
            "uq_parking_sessions_site_camera_visit" not in names
            and "visit_id" in cols
            and "camera_id" in cols
        ):
            op.create_index(
                "uq_parking_sessions_site_camera_visit",
                "parking_sessions",
                ["site_id", "camera_id", "visit_id"],
                unique=True,
                sqlite_where=sa.text("visit_id != '' AND camera_id IS NOT NULL"),
                postgresql_where=sa.text("visit_id != '' AND camera_id IS NOT NULL"),
            )
    if "vehicle_captures" in tables:
        cols = _columns("vehicle_captures")
        if "visit_id" not in cols:
            op.add_column(
                "vehicle_captures",
                sa.Column("visit_id", sa.String(64), nullable=False, server_default=""),
            )
        names = _indexes("vehicle_captures")
        if "ix_vehicle_captures_visit_id" not in names:
            op.create_index("ix_vehicle_captures_visit_id", "vehicle_captures", ["visit_id"])

    if "parking_entry_claims" not in tables:
        op.create_table(
            "parking_entry_claims",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("site_id", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("camera_id", sa.Integer(), nullable=False),
            sa.Column("visit_id", sa.String(64), nullable=False),
            sa.Column("plate", sa.String(32), nullable=False, server_default=""),
            sa.Column("event_id", sa.String(64), nullable=False, server_default=""),
            sa.Column("session_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "uq_parking_entry_claims_visit",
            "parking_entry_claims",
            ["site_id", "camera_id", "visit_id"],
            unique=True,
        )
        op.create_index("ix_parking_entry_claims_session_id", "parking_entry_claims", ["session_id"])


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "parking_entry_claims" in tables:
        op.drop_table("parking_entry_claims")
    if "vehicle_captures" in tables:
        names = _indexes("vehicle_captures")
        if "ix_vehicle_captures_visit_id" in names:
            op.drop_index("ix_vehicle_captures_visit_id", table_name="vehicle_captures")
        if "visit_id" in _columns("vehicle_captures"):
            with op.batch_alter_table("vehicle_captures") as batch:
                batch.drop_column("visit_id")
    if "parking_sessions" in tables:
        names = _indexes("parking_sessions")
        if "uq_parking_sessions_site_camera_visit" in names:
            op.drop_index("uq_parking_sessions_site_camera_visit", table_name="parking_sessions")
        if "visit_id" in _columns("parking_sessions"):
            with op.batch_alter_table("parking_sessions") as batch:
                batch.drop_column("visit_id")
