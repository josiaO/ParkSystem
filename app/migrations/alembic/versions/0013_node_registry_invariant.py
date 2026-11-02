"""Repair node-registry tables on databases stamped current too early.

Some installations were stamped at the latest revision after ``create_all``
ran with an older model set.  The version number then looked current although
Processing Node tables were absent.  This forward-only repair is deliberately
idempotent and runs on the Site Server before a node can pair.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0013_node_registry_invariant"
down_revision = "0012_exclusive_gate_ownership"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _indexes(table: str) -> set[str]:
    if table not in _tables():
        return set()
    return {row["name"] for row in sa.inspect(op.get_bind()).get_indexes(table) if row.get("name")}


def _index(name: str, table: str, columns: list[str], *, unique: bool = False) -> None:
    if name not in _indexes(table):
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    tables = _tables()
    if "nodes" not in tables:
        op.create_table(
            "nodes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("node_id", sa.String(length=120), nullable=False),
            sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id"), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False, server_default=""),
            sa.Column("node_type", sa.String(length=40), nullable=False, server_default="EDGE_NODE"),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="ACTIVE"),
            sa.Column("credential_hash", sa.String(length=300), nullable=False, server_default=""),
            sa.Column("capabilities", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("version", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("node_id", name="uq_nodes_node_id"),
        )
        tables.add("nodes")
    _index("ix_nodes_node_id", "nodes", ["node_id"], unique=True)
    _index("ix_nodes_site_id", "nodes", ["site_id"])
    _index("ix_nodes_status", "nodes", ["status"])

    if "node_auth_sessions" not in tables:
        op.create_table(
            "node_auth_sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("node_id", sa.Integer(), sa.ForeignKey("nodes.id"), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("token_hash", name="uq_node_auth_sessions_token_hash"),
        )
        tables.add("node_auth_sessions")
    _index("ix_node_auth_sessions_node_id", "node_auth_sessions", ["node_id"])
    _index("ix_node_auth_sessions_token_hash", "node_auth_sessions", ["token_hash"], unique=True)

    if "node_gate_assignments" not in tables:
        op.create_table(
            "node_gate_assignments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("node_id", sa.Integer(), sa.ForeignKey("nodes.id"), nullable=False),
            sa.Column("gate_id", sa.Integer(), sa.ForeignKey("gates.id"), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.UniqueConstraint("node_id", "gate_id", name="uq_node_gate_assignment"),
        )
        tables.add("node_gate_assignments")
    _index("ix_node_gate_assignments_node_id", "node_gate_assignments", ["node_id"])
    _index("ix_node_gate_assignments_gate_id", "node_gate_assignments", ["gate_id"])

    if "uq_node_gate_assignment_active_gate" not in _indexes("node_gate_assignments"):
        duplicates = op.get_bind().execute(sa.text(
            "SELECT gate_id FROM node_gate_assignments "
            "WHERE enabled IS TRUE GROUP BY gate_id HAVING COUNT(*) > 1"
        )).fetchall()
        if duplicates:
            gates = ", ".join(str(row[0]) for row in duplicates)
            raise RuntimeError(
                "Cannot repair exclusive gate ownership; multiple active nodes "
                f"own gate(s): {gates}. Disable conflicting assignments first."
            )
        op.create_index(
            "uq_node_gate_assignment_active_gate",
            "node_gate_assignments",
            ["gate_id"],
            unique=True,
            sqlite_where=sa.text("enabled = 1"),
            postgresql_where=sa.text("enabled = true"),
        )


def downgrade() -> None:
    # Forward repair must not delete live node identities.
    pass
