"""Revocable kiosk device credentials.

Additive and reversible: a new table only. Downgrade drops it, which revokes
every enrolled kiosk (they fall back to operator sign-in).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0016_kiosk_devices"
down_revision = "0015_camera_tls_opt_in"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "kiosk_devices" in _tables():
        return
    op.create_table(
        "kiosk_devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.String(80), nullable=False),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False, server_default=""),
        sa.Column("status", sa.String(30), nullable=False, server_default="ACTIVE"),
        sa.Column("credential_hash", sa.String(300), nullable=False, server_default=""),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_kiosk_devices_device_id", "kiosk_devices", ["device_id"], unique=True)
    op.create_index("ix_kiosk_devices_site_id", "kiosk_devices", ["site_id"])
    op.create_index("ix_kiosk_devices_status", "kiosk_devices", ["status"])
    op.create_index("ix_kiosk_devices_user_id", "kiosk_devices", ["user_id"])


def downgrade() -> None:
    if "kiosk_devices" in _tables():
        op.drop_table("kiosk_devices")
