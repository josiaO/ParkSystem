"""Capture photos can be written after the access decision.

``vehicle_captures.evidence_state``: '' for rows written the old way (photos
saved with the row), PENDING while the evidence writer runs, then STORED or
MISSING. See app/services/evidence.py.

Additive: one defaulted column and an index. Downgrade drops them.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0019_capture_evidence_state"
down_revision = "0018_gate_command_state"
branch_labels = None
depends_on = None


def _columns() -> set[str] | None:
    inspector = sa.inspect(op.get_bind())
    if "vehicle_captures" not in inspector.get_table_names():
        return None
    return {c["name"] for c in inspector.get_columns("vehicle_captures")}


def upgrade() -> None:
    columns = _columns()
    if columns is None or "evidence_state" in columns:
        return
    op.add_column("vehicle_captures", sa.Column("evidence_state", sa.String(12), nullable=False, server_default=""))
    op.create_index("ix_vehicle_captures_evidence_state", "vehicle_captures", ["evidence_state"])


def downgrade() -> None:
    columns = _columns()
    if columns is None or "evidence_state" not in columns:
        return
    with op.batch_alter_table("vehicle_captures") as batch:
        batch.drop_index("ix_vehicle_captures_evidence_state")
        batch.drop_column("evidence_state")
