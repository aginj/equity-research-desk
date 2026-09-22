"""Local username/password accounts (hashed) for sign-in without OAuth.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "local_account",
        sa.Column(
            "user_id",
            sa.String(64),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("username", sa.String(32), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_local_account_username", "local_account", ["username"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_local_account_username", table_name="local_account")
    op.drop_table("local_account")
