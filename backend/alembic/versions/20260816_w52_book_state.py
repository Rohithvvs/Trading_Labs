"""52-Week High Breakout book state

Revision ID: 20260816_w52_book_state
Revises: 20260815_ltm_strategy_tables
Create Date: 2026-08-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260816_w52_book_state"
down_revision: Union[str, Sequence[str], None] = "20260815_ltm_strategy_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "w52_book_state" not in inspector.get_table_names():
        json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
        op.create_table(
            "w52_book_state",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("strategy_id", sa.String(length=32), nullable=False),
            sa.Column("mode", sa.String(length=8), nullable=False, server_default="B"),
            sa.Column("fill_model", sa.String(length=24), nullable=False, server_default="signal_close"),
            sa.Column("cash", sa.Float(), nullable=False),
            sa.Column("equity", sa.Float(), nullable=False),
            sa.Column("initial_capital", sa.Float(), nullable=False),
            sa.Column("session_index", sa.Integer(), nullable=False, server_default="-1"),
            sa.Column("last_session_processed", sa.Date(), nullable=True),
            sa.Column("book_status", sa.String(length=16), nullable=False, server_default="WARMUP"),
            sa.Column("market_ok", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("nifty_close", sa.Float(), nullable=True),
            sa.Column("nifty_sma50", sa.Float(), nullable=True),
            sa.Column("holdings", json_type, nullable=True),
            sa.Column("pending_orders", json_type, nullable=True),
            sa.Column("sold_today", json_type, nullable=True),
            sa.Column("survivorship_biased", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "w52_book_state" in inspector.get_table_names():
        op.drop_table("w52_book_state")
