"""Add adtv_20 to daily_ohlcv (20-session avg of close*volume)

Revision ID: 20260808_daily_ohlcv_adtv20
Revises: 20260808_strategy_market_data
Create Date: 2026-08-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260808_daily_ohlcv_adtv20"
down_revision: Union[str, Sequence[str], None] = "20260808_strategy_market_data"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "daily_ohlcv" in inspector.get_table_names():
        existing = {c["name"] for c in inspector.get_columns("daily_ohlcv")}
        if "adtv_20" not in existing:
            op.add_column(
                "daily_ohlcv",
                sa.Column("adtv_20", sa.Numeric(precision=24, scale=4), nullable=True),
            )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "daily_ohlcv" in inspector.get_table_names():
        existing = {c["name"] for c in inspector.get_columns("daily_ohlcv")}
        if "adtv_20" in existing:
            op.drop_column("daily_ohlcv", "adtv_20")
