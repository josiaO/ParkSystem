"""vehicle_captures.ai_review — optional AI second-opinion payload.

Revision ID: 0003_vehicle_capture_ai_review
Revises: 0002_site_scoped_constraints
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_vehicle_capture_ai_review"
down_revision = "0002_site_scoped_constraints"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if "vehicle_captures" not in sa.inspect(op.get_bind()).get_table_names():
        return
    if "ai_review" not in _columns("vehicle_captures"):
        op.add_column("vehicle_captures", sa.Column("ai_review", sa.JSON(), nullable=True))


def downgrade() -> None:
    if "ai_review" in _columns("vehicle_captures"):
        with op.batch_alter_table("vehicle_captures") as batch:
            batch.drop_column("ai_review")
