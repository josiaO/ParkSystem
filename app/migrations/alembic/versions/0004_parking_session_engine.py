"""Parking session lifecycle columns and site-wide uniqueness.

Revision ID: 0004_parking_session_engine
Revises: 0003_vehicle_capture_ai_review
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_parking_session_engine"
down_revision = "0003_vehicle_capture_ai_review"
branch_labels = None
depends_on = None

COLUMNS = (
    ("site_id", "INTEGER DEFAULT 1"),
    ("plate_raw", "VARCHAR(32) DEFAULT ''"),
    ("plate_status", "VARCHAR(20) DEFAULT ''"),
    ("entry_lane_id", "INTEGER"),
    ("exit_lane_id", "INTEGER"),
    ("exit_camera_id", "INTEGER"),
    ("lifecycle", "VARCHAR(40) DEFAULT ''"),
    ("receipt_printed_at", "DATETIME"),
    ("receipt_taken_at", "DATETIME"),
    ("payment_status", "VARCHAR(20) DEFAULT ''"),
    ("paid_at", "DATETIME"),
    ("payment_exit_grace_until", "DATETIME"),
    ("entry_event_id", "VARCHAR(64) DEFAULT ''"),
    ("exit_event_id", "VARCHAR(64) DEFAULT ''"),
    ("entry_image_ref", "VARCHAR(260) DEFAULT ''"),
    ("open_command_uuid", "VARCHAR(64) DEFAULT ''"),
    ("closed_at", "DATETIME"),
    ("updated_at", "DATETIME"),
)


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table) if i.get("name")}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "parking_sessions" not in insp.get_table_names():
        return
    existing = _columns("parking_sessions")
    for name, ddl in COLUMNS:
        if name in existing:
            continue
        col = {
            "site_id": sa.Column("site_id", sa.Integer(), nullable=False, server_default="1"),
            "plate_raw": sa.Column("plate_raw", sa.String(32), nullable=False, server_default=""),
            "plate_status": sa.Column("plate_status", sa.String(20), nullable=False, server_default=""),
            "entry_lane_id": sa.Column("entry_lane_id", sa.Integer(), nullable=True),
            "exit_lane_id": sa.Column("exit_lane_id", sa.Integer(), nullable=True),
            "exit_camera_id": sa.Column("exit_camera_id", sa.Integer(), nullable=True),
            "lifecycle": sa.Column("lifecycle", sa.String(40), nullable=False, server_default=""),
            "receipt_printed_at": sa.Column("receipt_printed_at", sa.DateTime(timezone=True), nullable=True),
            "receipt_taken_at": sa.Column("receipt_taken_at", sa.DateTime(timezone=True), nullable=True),
            "payment_status": sa.Column("payment_status", sa.String(20), nullable=False, server_default=""),
            "paid_at": sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
            "payment_exit_grace_until": sa.Column("payment_exit_grace_until", sa.DateTime(timezone=True), nullable=True),
            "entry_event_id": sa.Column("entry_event_id", sa.String(64), nullable=False, server_default=""),
            "exit_event_id": sa.Column("exit_event_id", sa.String(64), nullable=False, server_default=""),
            "entry_image_ref": sa.Column("entry_image_ref", sa.String(260), nullable=False, server_default=""),
            "open_command_uuid": sa.Column("open_command_uuid", sa.String(64), nullable=False, server_default=""),
            "closed_at": sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            "updated_at": sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        }[name]
        op.add_column("parking_sessions", col)
    if "site_id" not in existing:
        op.get_bind().execute(sa.text("UPDATE parking_sessions SET site_id = 1 WHERE site_id IS NULL"))
    names = _indexes("parking_sessions")
    if "ix_parking_sessions_site_id" not in names:
        op.create_index("ix_parking_sessions_site_id", "parking_sessions", ["site_id"])
    if "uq_parking_sessions_site_entry_event" not in names:
        op.create_index(
            "uq_parking_sessions_site_entry_event",
            "parking_sessions",
            ["site_id", "entry_event_id"],
            unique=True,
            sqlite_where=sa.text("entry_event_id != ''"),
            postgresql_where=sa.text("entry_event_id != ''"),
        )
    if "uq_parking_sessions_one_open_plate" not in names:
        op.create_index(
            "uq_parking_sessions_one_open_plate",
            "parking_sessions",
            ["site_id", "plate"],
            unique=True,
            sqlite_where=sa.text("status IN ('WAITING_RECEIPT','ACTIVE','PAID','OPEN')"),
            postgresql_where=sa.text("status IN ('WAITING_RECEIPT','ACTIVE','PAID','OPEN')"),
        )


def downgrade() -> None:
    names = _indexes("parking_sessions")
    for idx in ("uq_parking_sessions_one_open_plate", "uq_parking_sessions_site_entry_event", "ix_parking_sessions_site_id"):
        if idx in names:
            op.drop_index(idx, table_name="parking_sessions")
    existing = _columns("parking_sessions")
    for name, _ddl in reversed(COLUMNS):
        if name in existing and name != "site_id":
            with op.batch_alter_table("parking_sessions") as batch:
                batch.drop_column(name)
            existing.discard(name)
