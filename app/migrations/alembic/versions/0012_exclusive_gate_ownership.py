"""Allow only one active processing node per physical gate."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0012_exclusive_gate_ownership"
down_revision = "0011_node_registry_repair"
branch_labels = None
depends_on = None


def _indexes() -> set[str]:
    return {
        row["name"]
        for row in sa.inspect(op.get_bind()).get_indexes("node_gate_assignments")
        if row.get("name")
    }


def upgrade() -> None:
    name = "uq_node_gate_assignment_active_gate"
    if name in _indexes():
        return
    # Do not silently pick a winner if an existing installation already has
    # conflicting live owners.  The operator must resolve that unsafe state
    # before the constraint is installed.
    duplicates = op.get_bind().execute(sa.text(
        "SELECT gate_id FROM node_gate_assignments "
        "WHERE enabled IS TRUE GROUP BY gate_id HAVING COUNT(*) > 1"
    )).fetchall()
    if duplicates:
        gates = ", ".join(str(row[0]) for row in duplicates)
        raise RuntimeError(
            "Cannot install exclusive gate ownership; multiple active nodes "
            f"own gate(s): {gates}. Disable the conflicting assignments first."
        )
    op.create_index(
        name,
        "node_gate_assignments",
        ["gate_id"],
        unique=True,
        sqlite_where=sa.text("enabled = 1"),
        postgresql_where=sa.text("enabled = true"),
    )


def downgrade() -> None:
    if "uq_node_gate_assignment_active_gate" in _indexes():
        op.drop_index("uq_node_gate_assignment_active_gate", table_name="node_gate_assignments")
