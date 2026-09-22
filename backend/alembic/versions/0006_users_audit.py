"""Local-account lockout fields and admin audit log.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    columns = {c["name"] for c in insp.get_columns("local_account")}
    if "disabled_at" not in columns:
        op.add_column("local_account", sa.Column("disabled_at", sa.DateTime(), nullable=True))
    if "failed_logins" not in columns:
        op.add_column(
            "local_account",
            sa.Column("failed_logins", sa.Integer(), nullable=False, server_default="0"),
        )
    if "locked_until" not in columns:
        op.add_column("local_account", sa.Column("locked_until", sa.DateTime(), nullable=True))

    if "audit_log" not in set(insp.get_table_names()):
        op.create_table(
            "audit_log",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("at", sa.DateTime(), nullable=False),
            sa.Column("actor_id", sa.String(64), nullable=False),
            sa.Column("action", sa.String(64), nullable=False),
            sa.Column("target", sa.String(200), nullable=False, server_default=""),
            sa.Column("detail_json", sa.Text(), nullable=True),
        )
        op.create_index("ix_audit_log_at", "audit_log", ["at"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_at", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_column("local_account", "locked_until")
    op.drop_column("local_account", "failed_logins")
    op.drop_column("local_account", "disabled_at")
