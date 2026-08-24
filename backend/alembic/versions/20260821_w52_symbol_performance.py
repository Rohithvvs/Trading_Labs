"""Per-symbol 52W Strategy Tester metrics

Revision ID: 20260821_w52_symbol_performance
Revises: 20260816_strategy_scan_completed_at
Create Date: 2026-08-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260821_w52_symbol_performance"
down_revision: Union[str, Sequence[str], None] = "20260816_strategy_scan_completed_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "w52_symbol_performance",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("strategy_id", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("window", sa.String(length=16), nullable=False),
        sa.Column("execution_profile", sa.String(length=24), nullable=False, server_default="KERNEL"),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("evaluation_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ok"),
        sa.Column("unavailable_reason", sa.String(length=64), nullable=True),
        sa.Column("data_hash", sa.String(length=32), nullable=True),
        sa.Column("candle_count", sa.Integer(), nullable=True),
        sa.Column("coverage_ratio", sa.Float(), nullable=True),
        sa.Column("total_pnl", sa.Float(), nullable=True),
        sa.Column("max_drawdown", sa.Float(), nullable=True),
        sa.Column("max_drawdown_inr", sa.Float(), nullable=True),
        sa.Column("total_trades", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("profitable_trades", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("losing_trades", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("breakeven", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("profit_factor", sa.Float(), nullable=True),
        sa.Column("profit_factor_infinite", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("gross_profit", sa.Float(), nullable=True),
        sa.Column("gross_loss", sa.Float(), nullable=True),
        sa.Column("commission", sa.Float(), nullable=True),
        sa.Column("expected_payoff", sa.Float(), nullable=True),
        sa.Column("expected_payoff_inr", sa.Float(), nullable=True),
        sa.Column("largest_profit", sa.Float(), nullable=True),
        sa.Column("largest_loss", sa.Float(), nullable=True),
        sa.Column("largest_profit_inr", sa.Float(), nullable=True),
        sa.Column("largest_loss_inr", sa.Float(), nullable=True),
        sa.Column("average_winning_trade", sa.Float(), nullable=True),
        sa.Column("average_losing_trade", sa.Float(), nullable=True),
        sa.Column("average_winning_trade_inr", sa.Float(), nullable=True),
        sa.Column("average_losing_trade_inr", sa.Float(), nullable=True),
        sa.Column("outlier_pnl", sa.Float(), nullable=True),
        sa.Column("outlier_trades", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("win_rate", sa.Float(), nullable=True),
        sa.Column("total_return", sa.Float(), nullable=True),
        sa.Column("cagr", sa.Float(), nullable=True),
        sa.Column("initial_capital", sa.Float(), nullable=True),
        sa.Column("ending_capital", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="closed_trade_ledger"),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("trades", json_type, nullable=True),
        sa.Column("ledger", json_type, nullable=True),
        sa.Column("coverage", json_type, nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "strategy_id",
            "symbol",
            "window",
            "execution_profile",
            name="uq_w52_symbol_performance",
        ),
    )
    op.create_index("ix_w52_symbol_performance_symbol", "w52_symbol_performance", ["symbol"])
    op.create_index("ix_w52_symbol_performance_window", "w52_symbol_performance", ["window"])


def downgrade() -> None:
    op.drop_index("ix_w52_symbol_performance_window", table_name="w52_symbol_performance")
    op.drop_index("ix_w52_symbol_performance_symbol", table_name="w52_symbol_performance")
    op.drop_table("w52_symbol_performance")
