"""Manual barrier openings and their alert outbox.

Additive and reversible: two new tables. Downgrade drops them (the record of
past manual openings and their alert delivery state is lost).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0017_manual_open_alerts"
down_revision = "0016_kiosk_devices"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()
    if "manual_open_events" not in tables:
        op.create_table(
            "manual_open_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id"), nullable=False, server_default="1"),
            sa.Column("source", sa.String(40), nullable=False),
            sa.Column("gate_id", sa.Integer(), sa.ForeignKey("gates.id"), nullable=True),
            sa.Column("camera_id", sa.Integer(), sa.ForeignKey("cameras.id"), nullable=True),
            sa.Column("lane_label", sa.String(120), nullable=False, server_default=""),
            sa.Column("side", sa.String(10), nullable=False, server_default=""),
            sa.Column("operator_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("operator_name", sa.String(120), nullable=False, server_default=""),
            sa.Column("reason", sa.String(240), nullable=False, server_default=""),
            sa.Column("plate", sa.String(32), nullable=False, server_default=""),
            sa.Column("plate_confidence", sa.Numeric(6, 3), nullable=False, server_default="0"),
            sa.Column("plate_seconds_before", sa.Numeric(10, 1), nullable=True),
            sa.Column("capture_id", sa.Integer(), sa.ForeignKey("vehicle_captures.id"), nullable=True),
            sa.Column("photo_ref", sa.String(300), nullable=False, server_default=""),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("parking_sessions.id"), nullable=True),
            sa.Column("parker_kind", sa.String(40), nullable=False, server_default=""),
            sa.Column("entry_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("duration_seconds", sa.Integer(), nullable=True),
            sa.Column("amount_due", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("amount_paid", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("amount_owed", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("currency", sa.String(8), nullable=False, server_default=""),
            sa.Column("command_ok", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("command_message", sa.Text(), nullable=False, server_default=""),
            sa.Column("extra", sa.JSON(), nullable=True),
            sa.Column("alert_status", sa.String(20), nullable=False, server_default="NONE"),
            sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("acknowledged_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("acknowledge_note", sa.String(240), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        for column in ("site_id", "source", "gate_id", "camera_id", "operator_id", "plate", "session_id", "alert_status", "created_at"):
            op.create_index(f"ix_manual_open_events_{column}", "manual_open_events", [column])
        op.create_index("ix_manual_open_events_ack_created", "manual_open_events", ["acknowledged_at", "created_at"])
    if "alert_deliveries" not in tables:
        op.create_table(
            "alert_deliveries",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("manual_open_events.id"), nullable=False),
            sa.Column("channel", sa.String(20), nullable=False),
            sa.Column("recipient", sa.String(300), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("event_id", "channel", "recipient", name="uq_alert_delivery_target"),
        )
        op.create_index("ix_alert_deliveries_event_id", "alert_deliveries", ["event_id"])
        op.create_index("ix_alert_deliveries_status", "alert_deliveries", ["status"])
        op.create_index("ix_alert_deliveries_due", "alert_deliveries", ["status", "next_attempt_at"])


def downgrade() -> None:
    tables = _tables()
    if "alert_deliveries" in tables:
        op.drop_table("alert_deliveries")
    if "manual_open_events" in tables:
        op.drop_table("manual_open_events")
