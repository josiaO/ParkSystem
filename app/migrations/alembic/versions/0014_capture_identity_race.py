"""Enforce positive camera image identity for concurrent capture callbacks.

The application already deduplicates image IDs in Python, but two processes
can pass that check at the same time. Duplicate historical image IDs are kept
as captures and weakened to ``0`` rather than deleted; new positive IDs become
database-enforced idempotency keys.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0014_capture_identity_race"
down_revision = "0013_node_registry_invariant"
branch_labels = None
depends_on = None


def _indexes(table: str) -> set[str]:
    bind = op.get_bind()
    if table not in set(sa.inspect(bind).get_table_names()):
        return set()
    return {row["name"] for row in sa.inspect(bind).get_indexes(table) if row.get("name")}


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "vehicle_captures" not in tables:
        return
    if "uq_vehicle_captures_camera_image_identity" in _indexes("vehicle_captures"):
        return

    duplicates = bind.execute(sa.text(
        "SELECT camera_id, image_id, MIN(id) AS keep_id "
        "FROM vehicle_captures "
        "WHERE camera_id IS NOT NULL AND image_id > 0 "
        "GROUP BY camera_id, image_id HAVING COUNT(*) > 1"
    )).mappings().all()
    for row in duplicates:
        bind.execute(sa.text(
            "UPDATE vehicle_captures SET image_id = 0 "
            "WHERE camera_id = :camera_id AND image_id = :image_id AND id <> :keep_id"
        ), dict(row))

    op.create_index(
        "uq_vehicle_captures_camera_image_identity",
        "vehicle_captures",
        ["camera_id", "image_id"],
        unique=True,
        sqlite_where=sa.text("image_id > 0 AND camera_id IS NOT NULL"),
        postgresql_where=sa.text("image_id > 0 AND camera_id IS NOT NULL"),
    )


def downgrade() -> None:
    if "uq_vehicle_captures_camera_image_identity" in _indexes("vehicle_captures"):
        op.drop_index("uq_vehicle_captures_camera_image_identity", table_name="vehicle_captures")
