"""Per-camera opt-out of HTTPS certificate verification for snapshots.

Additive and reversible: a boolean column that defaults to false, so every
existing camera verifies certificates until an operator opts it out.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0015_camera_tls_opt_in"
down_revision = "0014_capture_identity_race"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    if table not in set(sa.inspect(bind).get_table_names()):
        return set()
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    columns = _columns("cameras")
    if not columns or "allow_insecure_tls" in columns:
        return
    op.add_column(
        "cameras",
        sa.Column("allow_insecure_tls", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    if "allow_insecure_tls" in _columns("cameras"):
        with op.batch_alter_table("cameras") as batch:
            batch.drop_column("allow_insecure_tls")
