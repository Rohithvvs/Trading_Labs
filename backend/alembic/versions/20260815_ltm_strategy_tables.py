"""LTM book state + namespaced strategy scan tables

Revision ID: 20260815_ltm_strategy_tables
Revises: 20260812_remove_recommendation_engines
Create Date: 2026-08-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260815_ltm_strategy_tables"
down_revision: Union[str, Sequence[str], None] = "20260812_remove_recommendation_engines"
down_revision: Union[str, Sequence[str], None] = "20260812_str005_strategy_execution"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "ltm_book_state",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("strategy_id", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=8), nullable=False, server_default="A"),
        sa.Column("fill_model", sa.String(length=24), nullable=False, server_default="signal_close"),
        sa.Column("cash", sa.Float(), nullable=False),
        sa.Column("equity", sa.Float(), nullable=False),
        sa.Column("initial_capital", sa.Float(), nullable=False),
        sa.Column("session_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_rebalance_index", sa.Integer(), nullable=True),
        sa.Column("last_rebalance_date", sa.Date(), nullable=True),
        sa.Column("clock_status", sa.String(length=16), nullable=False, server_default="WARMUP"),
        sa.Column("holdings", json_type, nullable=True),
        sa.Column("pending_orders", json_type, nullable=True),
        sa.Column("survivorship_biased", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "strategy_scan_latest",
        sa.Column("strategy_id", sa.String(length=64), primary_key=True),
        sa.Column("scan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("payload", json_type, nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "strategy_scan_runs",
        sa.Column("scan_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("progress_pct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage", sa.String(length=64), nullable=True),
        sa.Column("payload", json_type, nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_strategy_scan_runs_strategy_id", "strategy_scan_runs", ["strategy_id"])


def downgrade() -> None:
    op.drop_index("ix_strategy_scan_runs_strategy_id", table_name="strategy_scan_runs")
    op.drop_table("strategy_scan_runs")
    op.drop_table("strategy_scan_latest")
    op.drop_table("ltm_book_state")
