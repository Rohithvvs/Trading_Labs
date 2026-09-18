"""Add completed_at to strategy_scan_latest (last successful scan only)

Revision ID: 20260816_strategy_scan_completed_at
Revises: 20260816_w52_book_state
Create Date: 2026-08-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260816_strategy_scan_completed_at"
down_revision: Union[str, Sequence[str], None] = "20260816_w52_book_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "strategy_scan_latest",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("strategy_scan_latest", "completed_at")
