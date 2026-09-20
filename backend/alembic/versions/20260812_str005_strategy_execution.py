"""Compatibility stub for STR-005 strategy execution.

Revision ID: 20260812_str005_strategy_execution
Revises: 20260812_remove_recommendation_engines
Create Date: 2026-08-12
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260812_str005_strategy_execution"
down_revision: Union[str, Sequence[str], None] = "20260812_remove_recommendation_engines"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

