"""Users, per-user preferences, and watchlists; Auth.js adapter tables.

The ``users`` / ``accounts`` / ``sessions`` / ``verification_token`` tables match the schema
expected by ``@auth/pg-adapter`` (camelCase column names are deliberate). They are created
with portable types so the same migration runs on SQLite in development.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- application tables ---------------------------------------------------------------
    op.create_table(
        "app_user",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column("image", sa.String(2000), nullable=True),
        sa.Column("role", sa.String(16), nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_app_user_email", "app_user", ["email"])

    op.create_table(
        "user_preference",
        sa.Column(
            "user_id",
            sa.String(64),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("market_id", sa.String(32), nullable=False, server_default="us"),
        sa.Column("risk_appetite", sa.String(16), nullable=False, server_default="balanced"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "watchlist",
        sa.Column(
            "user_id",
            sa.String(64),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("market_id", sa.String(32), primary_key=True),
        sa.Column("ticker", sa.String(32), primary_key=True),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("added_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_watchlist_market_ticker", "watchlist", ["market_id", "ticker"])

    # --- Auth.js (@auth/pg-adapter) tables ------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("emailVerified", sa.DateTime(timezone=True), nullable=True),
        sa.Column("image", sa.Text(), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "userId",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(255), nullable=False),
        sa.Column("providerAccountId", sa.String(255), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.BigInteger(), nullable=True),
        sa.Column("id_token", sa.Text(), nullable=True),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("session_state", sa.Text(), nullable=True),
        sa.Column("token_type", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_accounts_provider_account",
        "accounts",
        ["provider", "providerAccountId"],
        unique=True,
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "userId",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sessionToken", sa.String(255), nullable=False),
    )
    op.create_index("ix_sessions_token", "sessions", ["sessionToken"], unique=True)

    op.create_table(
        "verification_token",
        sa.Column("identifier", sa.Text(), primary_key=True),
        sa.Column("token", sa.Text(), primary_key=True),
        sa.Column("expires", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("verification_token")
    op.drop_table("sessions")
    op.drop_table("accounts")
    op.drop_table("users")
    op.drop_table("watchlist")
    op.drop_table("user_preference")
    op.drop_table("app_user")
