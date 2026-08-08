"""Add experiment_id to recommendation_engine_decisions for RE-002 attribution.

Revision ID: 20260804_re002_experiment_id
Revises: 20260803_re001_engine_decisions
Create Date: 2026-08-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260804_re002_experiment_id"
down_revision: Union[str, None] = "20260803_re001_engine_decisions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if "recommendation_engine_decisions" not in tables:
        return
    cols = {c["name"] for c in inspector.get_columns("recommendation_engine_decisions")}
    if "experiment_id" not in cols:
        op.add_column(
            "recommendation_engine_decisions",
            sa.Column("experiment_id", sa.String(length=64), nullable=True),
        )
        op.create_index(
            "ix_recommendation_engine_decisions_experiment_id",
            "recommendation_engine_decisions",
            ["experiment_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if "recommendation_engine_decisions" not in tables:
        return
    cols = {c["name"] for c in inspector.get_columns("recommendation_engine_decisions")}
    if "experiment_id" in cols:
        try:
            op.drop_index(
                "ix_recommendation_engine_decisions_experiment_id",
                table_name="recommendation_engine_decisions",
            )
        except Exception:
            pass
        op.drop_column("recommendation_engine_decisions", "experiment_id")
