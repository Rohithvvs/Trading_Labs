"""Add technical_analysis to recommendation_engine_decisions

Revision ID: 4077a451eb8f
Revises: 20260808_daily_ohlcv_adtv20
Create Date: 2026-08-09 20:35:15.910439

Intentional scope only: add nullable JSONB technical_analysis column.
The original autogenerate also proposed dropping unrelated tables/indexes
(event_calendar, user_profiles, walk_forward, etc.) due to model metadata
drift — those changes are deliberately excluded.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "4077a451eb8f"
down_revision: Union[str, Sequence[str], None] = "20260808_daily_ohlcv_adtv20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = {c["name"] for c in inspector.get_columns("recommendation_engine_decisions")}
    if "technical_analysis" not in cols:
        op.add_column(
            "recommendation_engine_decisions",
            sa.Column(
                "technical_analysis",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = {c["name"] for c in inspector.get_columns("recommendation_engine_decisions")}
    if "technical_analysis" in cols:
        op.drop_column("recommendation_engine_decisions", "technical_analysis")
