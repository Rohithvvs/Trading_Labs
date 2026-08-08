"""Composite indexes for Day-by-Day Analytics & Recommendation Lab performance.

Revision ID: 20260805_perf_indexes
Revises: 20260805_paper_confirm_idx
Create Date: 2026-08-05

Brownfield: additive composite indexes for query optimization.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "20260805_perf_indexes"
down_revision: Union[str, None] = "20260805_paper_confirm_idx"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_re_decisions_engine_scan_created
        ON recommendation_engine_decisions (engine_id, scan_run_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_re_decisions_engine_created
        ON recommendation_engine_decisions (engine_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_re_decisions_scan_engine
        ON recommendation_engine_decisions (scan_run_id, engine_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_re_decisions_engine_symbol_created
        ON recommendation_engine_decisions (engine_id, symbol, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_trade_history_account_closed
        ON paper_trading_trade_history (account_id, closed_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_trade_history_account_closed")
    op.execute("DROP INDEX IF EXISTS idx_re_decisions_engine_symbol_created")
    op.execute("DROP INDEX IF EXISTS idx_re_decisions_scan_engine")
    op.execute("DROP INDEX IF EXISTS idx_re_decisions_engine_created")
    op.execute("DROP INDEX IF EXISTS idx_re_decisions_engine_scan_created")
