"""Baseline: the pre-Alembic schema as produced by create_all + legacy ALTERs.

This revision is intentionally empty. Fresh databases are created with
``Base.metadata.create_all`` and stamped at *head*; databases that predate
Alembic are brought to this shape by ``app.migrations.legacy.apply_legacy_fixups``
and then stamped here so that ``0002`` onwards can run.

Revision ID: 0001_baseline
Revises: None
"""

from __future__ import annotations

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
