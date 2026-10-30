"""Add central Edge Node identities and gate assignments.

Revision ID: 0009_node_registry
Revises: 0008_capture_identity
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_node_registry"
down_revision = "0008_capture_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
    op.create_index("ix_nodes_node_id", "nodes", ["node_id"], unique=True)
    op.create_index("ix_nodes_site_id", "nodes", ["site_id"])
    op.create_index("ix_nodes_status", "nodes", ["status"])
    op.create_table(
        "node_auth_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("node_id", sa.Integer(), sa.ForeignKey("nodes.id"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_node_auth_sessions_token_hash"),
    )
    op.create_index("ix_node_auth_sessions_node_id", "node_auth_sessions", ["node_id"])
    op.create_index("ix_node_auth_sessions_token_hash", "node_auth_sessions", ["token_hash"], unique=True)
    op.create_table(
        "node_gate_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("node_id", sa.Integer(), sa.ForeignKey("nodes.id"), nullable=False),
        sa.Column("gate_id", sa.Integer(), sa.ForeignKey("gates.id"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("node_id", "gate_id", name="uq_node_gate_assignment"),
    )
    op.create_index("ix_node_gate_assignments_node_id", "node_gate_assignments", ["node_id"])
    op.create_index("ix_node_gate_assignments_gate_id", "node_gate_assignments", ["gate_id"])


def downgrade() -> None:
    op.drop_index("ix_node_gate_assignments_gate_id", table_name="node_gate_assignments")
    op.drop_index("ix_node_gate_assignments_node_id", table_name="node_gate_assignments")
    op.drop_table("node_gate_assignments")
    op.drop_index("ix_node_auth_sessions_token_hash", table_name="node_auth_sessions")
    op.drop_index("ix_node_auth_sessions_node_id", table_name="node_auth_sessions")
    op.drop_table("node_auth_sessions")
    op.drop_index("ix_nodes_status", table_name="nodes")
    op.drop_index("ix_nodes_site_id", table_name="nodes")
    op.drop_index("ix_nodes_node_id", table_name="nodes")
    op.drop_table("nodes")
