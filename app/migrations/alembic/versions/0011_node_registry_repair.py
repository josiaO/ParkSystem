"""Repair node-registry tables on databases stamped before the registry existed.

Some early production databases were stamped at the latest revision after
``create_all`` ran with an older model set.  They therefore report a current
Alembic revision while still lacking the node tables required by Processing
Node pairing.  This revision is deliberately idempotent so it repairs those
databases without touching existing node data.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0011_node_registry_repair"
down_revision = "0010_hot_path_indexes"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _indexes(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {item["name"] for item in inspector.get_indexes(table) if item.get("name")}


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


def downgrade() -> None:
    # The original 0009 migration owns these tables. This repair is forward
    # compatible only; downgrading it must not delete live node identities.
    pass
