"""Add indexes used by the capture, exit, receipt, and payment hot paths.

Revision ID: 0010_hot_path_indexes
Revises: 0009_node_registry
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0010_hot_path_indexes"
down_revision = "0009_node_registry"
branch_labels = None
depends_on = None


def _indexes(table: str) -> set[str]:
    bind = op.get_bind()
    if table not in set(sa.inspect(bind).get_table_names()):
        return set()
    return {item["name"] for item in sa.inspect(bind).get_indexes(table) if item.get("name")}


def _add_index(name: str, table: str, columns: list[str], *, unique: bool = False, where: str | None = None) -> None:
    if name in _indexes(table):
        return
    kwargs = {"unique": unique}
    if where:
        condition = sa.text(where)
        kwargs["sqlite_where"] = condition
        kwargs["postgresql_where"] = condition
    op.create_index(name, table, columns, **kwargs)


def upgrade() -> None:
    _add_index(
        "uq_parking_sessions_site_exit_event",
        "parking_sessions",
        ["site_id", "exit_event_id"],
        unique=True,
        where="exit_event_id != ''",
    )
    _add_index(
        "ix_parking_sessions_site_status_plate",
        "parking_sessions",
        ["site_id", "status", "plate"],
    )
    _add_index("ix_vehicle_captures_camera_image", "vehicle_captures", ["camera_id", "image_id"])
    _add_index("ix_vehicle_captures_camera_latest", "vehicle_captures", ["camera_id", "id"])
    _add_index(
        "uq_receipts_print_job_id",
        "receipts",
        ["print_job_id"],
        unique=True,
        where="print_job_id != ''",
    )
    _add_index("ix_payment_intents_provider_status_id", "payment_intents", ["provider_id", "status", "id"])
    _add_index("ix_payment_transactions_session_status", "payment_transactions", ["session_id", "status"])


def downgrade() -> None:
    for table, names in {
        "payment_transactions": ["ix_payment_transactions_session_status"],
        "payment_intents": ["ix_payment_intents_provider_status_id"],
        "receipts": ["uq_receipts_print_job_id"],
        "vehicle_captures": ["ix_vehicle_captures_camera_latest", "ix_vehicle_captures_camera_image"],
        "parking_sessions": ["ix_parking_sessions_site_status_plate", "uq_parking_sessions_site_exit_event"],
    }.items():
        existing = _indexes(table)
        for name in names:
            if name in existing:
                op.drop_index(name, table_name=table)
