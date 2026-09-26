"""Update default paper trading brokerage to Rs 20 flat per executed trade

Revision ID: 20260926_brokerage_20_flat
Revises: 20260924_charge_engine
Create Date: 2026-09-26
"""
from typing import Sequence, Union
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision: str = "20260926_brokerage_20_flat"
down_revision: Union[str, Sequence[str], None] = "20260924_charge_engine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    now = datetime.now(timezone.utc)
    op.execute(
        sa.text(
            """
            UPDATE paper_trading_charge_profiles
            SET brokerage_type = 'FLAT_PER_EXECUTED_ORDER',
                brokerage_rate_pct = 0,
                brokerage_flat_per_executed_order = 20.00,
                brokerage_order_cap = 20.00,
                updated_at = :now
            WHERE broker_id = 'DEFAULT'
              AND exchange = 'NSE'
              AND segment = 'EQUITY_DELIVERY'
            """
        ).bindparams(now=now)
    )


def downgrade() -> None:
    now = datetime.now(timezone.utc)
    op.execute(
        sa.text(
            """
            UPDATE paper_trading_charge_profiles
            SET brokerage_type = 'ZERO',
                brokerage_rate_pct = 0,
                brokerage_flat_per_executed_order = 0,
                brokerage_order_cap = 0,
                updated_at = :now
            WHERE broker_id = 'DEFAULT'
              AND exchange = 'NSE'
              AND segment = 'EQUITY_DELIVERY'
            """
        ).bindparams(now=now)
    )
