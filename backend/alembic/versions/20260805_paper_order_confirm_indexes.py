"""Indexes for paper order confirm / cash hot path.

Revision ID: 20260805_paper_confirm_idx
Revises: 20260804_paper_lab_provenance
Create Date: 2026-08-05

Brownfield: additive indexes only — no data changes.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "20260805_paper_confirm_idx"
down_revision: Union[str, None] = "20260804_paper_lab_provenance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent create for brownfield deploys that may already have partial indexes
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_positions_account_status
        ON paper_trading_positions (account_id, status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_orders_account_status_side_type
        ON paper_trading_orders (account_id, status, side, order_type)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_orders_account_status_side_type")
    op.execute("DROP INDEX IF EXISTS idx_positions_account_status")
