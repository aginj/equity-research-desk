"""Rating snapshots and run trigger attribution.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    columns = {c["name"] for c in insp.get_columns("analysisrunrow")}
    if "triggered_by" not in columns:
        op.add_column("analysisrunrow", sa.Column("triggered_by", sa.String(80), nullable=True))

    tables = set(insp.get_table_names())
    if "rating_snapshot" not in tables:
        op.create_table(
            "rating_snapshot",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "run_id",
                sa.String(32),
                sa.ForeignKey("analysisrunrow.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("market_id", sa.String(32), nullable=False),
            sa.Column("ticker", sa.String(32), nullable=False),
            sa.Column("action", sa.String(16), nullable=False),
            sa.Column("conviction", sa.Float(), nullable=False, server_default="0"),
            sa.Column("price", sa.Float(), nullable=False, server_default="0"),
            sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
            sa.Column("sector", sa.String(80), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_rating_snapshot_run_id", "rating_snapshot", ["run_id"])
        op.create_index("ix_rating_snapshot_market_id", "rating_snapshot", ["market_id"])
        op.create_index("ix_rating_snapshot_ticker", "rating_snapshot", ["ticker"])
        op.create_index("ix_rating_snapshot_finished_at", "rating_snapshot", ["finished_at"])
        op.create_index(
            "uq_rating_snapshot_run_ticker",
            "rating_snapshot",
            ["run_id", "ticker"],
            unique=True,
        )


def downgrade() -> None:
    op.drop_index("uq_rating_snapshot_run_ticker", table_name="rating_snapshot")
    op.drop_index("ix_rating_snapshot_finished_at", table_name="rating_snapshot")
    op.drop_index("ix_rating_snapshot_ticker", table_name="rating_snapshot")
    op.drop_index("ix_rating_snapshot_market_id", table_name="rating_snapshot")
    op.drop_index("ix_rating_snapshot_run_id", table_name="rating_snapshot")
    op.drop_table("rating_snapshot")
    op.drop_column("analysisrunrow", "triggered_by")
