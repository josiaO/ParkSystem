"""Preserve entry/exit gate identity and exit command idempotency.

Revision ID: 0006_exit_lane_engine
Revises: 0005_receipt_qr_jobs
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_exit_lane_engine"
down_revision = "0005_receipt_qr_jobs"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "parking_sessions" not in tables:
        return
    cols = _columns("parking_sessions")
    additions = (
        ("entry_gate_id", sa.Column("entry_gate_id", sa.Integer(), nullable=True)),
        ("exit_gate_id", sa.Column("exit_gate_id", sa.Integer(), nullable=True)),
        ("exit_open_command_uuid", sa.Column("exit_open_command_uuid", sa.String(64), nullable=False, server_default="")),
    )
    for name, col in additions:
        if name not in cols:
            op.add_column("parking_sessions", col)

    op.execute(sa.text(
        "UPDATE parking_sessions SET entry_gate_id = gate_id "
        "WHERE entry_gate_id IS NULL AND gate_id IS NOT NULL"
    ))

    indexes = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("parking_sessions") if i.get("name")}
    if "ix_parking_sessions_entry_gate_id" not in indexes:
        op.create_index("ix_parking_sessions_entry_gate_id", "parking_sessions", ["entry_gate_id"])
    if "ix_parking_sessions_exit_gate_id" not in indexes:
        op.create_index("ix_parking_sessions_exit_gate_id", "parking_sessions", ["exit_gate_id"])


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "parking_sessions" not in tables:
        return
    indexes = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("parking_sessions") if i.get("name")}
    for idx in ("ix_parking_sessions_exit_gate_id", "ix_parking_sessions_entry_gate_id"):
        if idx in indexes:
            op.drop_index(idx, table_name="parking_sessions")
    cols = _columns("parking_sessions")
    for name in ("exit_open_command_uuid", "exit_gate_id", "entry_gate_id"):
        if name in cols:
            with op.batch_alter_table("parking_sessions") as batch:
                batch.drop_column(name)
