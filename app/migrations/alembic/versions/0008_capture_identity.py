"""Enforce durable capture event and visit identity.

Revision ID: 0008_capture_identity
Revises: 0007_visit_idempotency
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_capture_identity"
down_revision = "0007_visit_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "vehicle_captures" not in sa.inspect(bind).get_table_names():
        return
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("vehicle_captures")}
    for column, suffix in (("event_id", "event"), ("visit_id", "visit")):
        name = f"uq_vehicle_captures_camera_{suffix}"
        if name in indexes:
            continue
        duplicates = bind.execute(sa.text(
            f"SELECT camera_id FROM vehicle_captures WHERE {column} != '' AND camera_id IS NOT NULL "
            f"GROUP BY camera_id, {column} HAVING COUNT(*) > 1 LIMIT 1"
        )).first()
        if duplicates:
            raise RuntimeError(f"Capture identity migration blocked: duplicate {column} for camera {duplicates[0]}; reconcile historical duplicates from a backup before upgrading")
        condition = sa.text(f"{column} != '' AND camera_id IS NOT NULL")
        op.create_index(name, "vehicle_captures", ["camera_id", column], unique=True,
                        sqlite_where=condition, postgresql_where=condition)


def downgrade() -> None:
    if "vehicle_captures" not in sa.inspect(op.get_bind()).get_table_names():
        return
    for suffix in ("event", "visit"):
        op.drop_index(f"uq_vehicle_captures_camera_{suffix}", table_name="vehicle_captures")
