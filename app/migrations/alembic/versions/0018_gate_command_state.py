"""Gate commands carry an explicit state for the Authorization Commit.

A barrier command is recorded as REQUESTED in the same transaction as the
access decision, *before* the command is sent; the hardware answer moves it
to ACCEPTED or FAILED. A REQUESTED row found after a restart was interrupted
(power cut or crash between commit and answer) and becomes INTERRUPTED for an
operator. See docs/ZIRP_HIGH_THROUGHPUT_ARCHITECTURE.md section 4.

Additive: three nullable/defaulted columns and an index. Existing rows are
back-filled from ``ok`` (ACCEPTED / FAILED). Downgrade drops the columns.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0018_gate_command_state"
down_revision = "0017_manual_open_alerts"
branch_labels = None
depends_on = None


def _columns() -> set[str] | None:
    inspector = sa.inspect(op.get_bind())
    if "gate_commands" not in inspector.get_table_names():
        return None
    return {c["name"] for c in inspector.get_columns("gate_commands")}


def upgrade() -> None:
    columns = _columns()
    if columns is None:
        # Older layouts get gate_commands from the model metadata later.
        return
    if "state" not in columns:
        op.add_column("gate_commands", sa.Column("state", sa.String(20), nullable=False, server_default=""))
        op.execute("UPDATE gate_commands SET state = CASE WHEN ok THEN 'ACCEPTED' ELSE 'FAILED' END")
        op.create_index("ix_gate_commands_state", "gate_commands", ["state"])
    if "side" not in columns:
        op.add_column("gate_commands", sa.Column("side", sa.String(10), nullable=False, server_default=""))
    if "completed_at" not in columns:
        op.add_column("gate_commands", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    columns = _columns()
    if columns is None:
        return
    with op.batch_alter_table("gate_commands") as batch:
        if "state" in columns:
            batch.drop_index("ix_gate_commands_state")
            batch.drop_column("state")
        if "side" in columns:
            batch.drop_column("side")
        if "completed_at" in columns:
            batch.drop_column("completed_at")
