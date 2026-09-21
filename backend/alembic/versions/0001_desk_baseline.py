"""Desk baseline: universe, runs, settings.

Idempotent on purpose: SQLite desks created before Alembic already have these tables
(from ``SQLModel.metadata.create_all``), so each step checks the live schema first and only
adds what is missing. This also folds in the old ad-hoc ``market_id`` migrations.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _columns(table: str) -> set[str]:
    return {c["name"] for c in _inspector().get_columns(table)}


def upgrade() -> None:
    insp = _inspector()
    tables = set(insp.get_table_names())

    if "universerow" not in tables:
        op.create_table(
            "universerow",
            sa.Column("market_id", sa.String(), primary_key=True),
            sa.Column("ticker", sa.String(), primary_key=True),
            sa.Column("name", sa.String(), nullable=True),
            sa.Column("sector", sa.String(), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("added_at", sa.DateTime(), nullable=False),
        )
    elif "market_id" not in _columns("universerow"):
        # Legacy single-venue desk: rebuild with the composite key, defaulting rows to "us".
        bind = op.get_bind()
        rows = bind.execute(
            sa.text("SELECT ticker, name, sector, active, added_at FROM universerow")
        ).fetchall()
        op.drop_table("universerow")
        op.create_table(
            "universerow",
            sa.Column("market_id", sa.String(), primary_key=True),
            sa.Column("ticker", sa.String(), primary_key=True),
            sa.Column("name", sa.String(), nullable=True),
            sa.Column("sector", sa.String(), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("added_at", sa.DateTime(), nullable=False),
        )
        for ticker, name, sector, active, added_at in rows:
            bind.execute(
                sa.text(
                    "INSERT INTO universerow (market_id, ticker, name, sector, active, added_at) "
                    "VALUES ('us', :t, :n, :s, :a, :d)"
                ),
                {"t": ticker, "n": name, "s": sector, "a": bool(active), "d": added_at},
            )

    if "analysisrunrow" not in tables:
        op.create_table(
            "analysisrunrow",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("stage", sa.String(), nullable=False),
            sa.Column("risk_appetite", sa.String(), nullable=False),
            sa.Column("market_id", sa.String(), nullable=False, server_default="us"),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("error", sa.String(), nullable=True),
            sa.Column("payload_json", sa.Text(), nullable=True),
        )
    elif "market_id" not in _columns("analysisrunrow"):
        op.add_column(
            "analysisrunrow",
            sa.Column("market_id", sa.String(), nullable=False, server_default="us"),
        )

    existing_indexes = {
        ix["name"] for ix in _inspector().get_indexes("analysisrunrow") if ix.get("name")
    }
    for name, column in (
        ("ix_analysisrunrow_status", "status"),
        ("ix_analysisrunrow_market_id", "market_id"),
        ("ix_analysisrunrow_started_at", "started_at"),
    ):
        if name not in existing_indexes:
            op.create_index(name, "analysisrunrow", [column])

    if "settingrow" not in tables:
        op.create_table(
            "settingrow",
            sa.Column("key", sa.String(), primary_key=True),
            sa.Column("value", sa.String(), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("settingrow")
    op.drop_table("analysisrunrow")
    op.drop_table("universerow")
