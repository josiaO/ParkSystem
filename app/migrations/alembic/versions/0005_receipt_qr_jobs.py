"""Receipt tokens, print-job columns, unique session QR identity.

Revision ID: 0005_receipt_qr_jobs
Revises: 0004_parking_session_engine
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_receipt_qr_jobs"
down_revision = "0004_parking_session_engine"
branch_labels = None
depends_on = None

SESSION_COLUMNS = (
    ("human_reference", sa.Column("human_reference", sa.String(16), nullable=False, server_default="")),
    ("print_job_id", sa.Column("print_job_id", sa.String(64), nullable=False, server_default="")),
    ("print_job_status", sa.Column("print_job_status", sa.String(20), nullable=False, server_default="")),
    ("print_retry_count", sa.Column("print_retry_count", sa.Integer(), nullable=False, server_default="0")),
    ("printer_error", sa.Column("printer_error", sa.String(240), nullable=False, server_default="")),
)

RECEIPT_COLUMNS = (
    ("print_job_id", sa.Column("print_job_id", sa.String(64), nullable=False, server_default="")),
    ("retry_count", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0")),
    ("printer_error", sa.Column("printer_error", sa.String(240), nullable=False, server_default="")),
)


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table) if i.get("name")}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    tables = set(insp.get_table_names())
    if "parking_sessions" in tables:
        existing = _columns("parking_sessions")
        for name, col in SESSION_COLUMNS:
            if name not in existing:
                op.add_column("parking_sessions", col)
        names = _indexes("parking_sessions")
        if "uq_parking_sessions_public_token" not in names:
            op.create_index(
                "uq_parking_sessions_public_token",
                "parking_sessions",
                ["public_token"],
                unique=True,
                sqlite_where=sa.text("public_token != ''"),
                postgresql_where=sa.text("public_token != ''"),
            )
        if "uq_parking_sessions_human_reference" not in names:
            op.create_index(
                "uq_parking_sessions_human_reference",
                "parking_sessions",
                ["human_reference"],
                unique=True,
                sqlite_where=sa.text("human_reference != ''"),
                postgresql_where=sa.text("human_reference != ''"),
            )
    if "receipts" in tables:
        existing = _columns("receipts")
        for name, col in RECEIPT_COLUMNS:
            if name not in existing:
                op.add_column("receipts", col)
        names = _indexes("receipts")
        if "ix_receipts_print_job_id" not in names:
            op.create_index("ix_receipts_print_job_id", "receipts", ["print_job_id"])


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    tables = set(insp.get_table_names())
    if "parking_sessions" in tables:
        names = _indexes("parking_sessions")
        for idx in ("uq_parking_sessions_human_reference", "uq_parking_sessions_public_token"):
            if idx in names:
                op.drop_index(idx, table_name="parking_sessions")
        existing = _columns("parking_sessions")
        for name, _col in reversed(SESSION_COLUMNS):
            if name in existing:
                with op.batch_alter_table("parking_sessions") as batch:
                    batch.drop_column(name)
    if "receipts" in tables:
        names = _indexes("receipts")
        if "ix_receipts_print_job_id" in names:
            op.drop_index("ix_receipts_print_job_id", table_name="receipts")
        existing = _columns("receipts")
        for name, _col in reversed(RECEIPT_COLUMNS):
            if name in existing:
                with op.batch_alter_table("receipts") as batch:
                    batch.drop_column(name)
