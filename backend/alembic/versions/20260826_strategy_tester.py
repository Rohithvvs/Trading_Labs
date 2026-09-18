"""Strategy Tester tables

Revision ID: 20260826_strategy_tester
Revises: 20260821_w52_symbol_performance
Create Date: 2026-08-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260826_strategy_tester"
down_revision: Union[str, Sequence[str], None] = "20260821_w52_symbol_performance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "strategy_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_preset", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("preset_id", sa.String(length=64), nullable=True),
        sa.Column("config", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_strategy_definitions_user_id", "strategy_definitions", ["user_id"])
    op.create_table(
        "strategy_test_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("public_run_id", sa.String(length=32), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("strategy_definition_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("strategy_name", sa.String(length=160), nullable=False),
        sa.Column("strategy_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("strategy_snapshot", json_type, nullable=False),
        sa.Column("universe", sa.String(length=32), nullable=False, server_default="ALL_755"),
        sa.Column("universe_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("timeframe", sa.String(length=16), nullable=False, server_default="1D"),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("initial_capital", sa.Float(), nullable=False, server_default="100000"),
        sa.Column("calculation_version", sa.String(length=32), nullable=False),
        sa.Column("data_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("progress_pct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("buy_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("watch_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reject_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_symbol", sa.String(length=32), nullable=True),
        sa.Column("stage", sa.String(length=64), nullable=True),
        sa.Column("summary", json_type, nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["strategy_definition_id"], ["strategy_definitions.id"]),
        sa.UniqueConstraint("public_run_id", name="uq_strategy_test_runs_public_run_id"),
    )
    op.create_index("ix_strategy_test_runs_user_id", "strategy_test_runs", ["user_id"])
    op.create_index("ix_strategy_test_runs_user_started", "strategy_test_runs", ["user_id", "started_at"])
    op.create_index("ix_strategy_test_runs_status", "strategy_test_runs", ["status"])
    op.create_table(
        "strategy_test_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("company", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ok"),
        sa.Column("signal", sa.String(length=16), nullable=True),
        sa.Column("entry_price", sa.Float(), nullable=True),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("return_pct", sa.Float(), nullable=True),
        sa.Column("return_bucket", sa.String(length=16), nullable=True),
        sa.Column("return_formula", sa.Text(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("indicators", json_type, nullable=True),
        sa.Column("passed_filters", json_type, nullable=True),
        sa.Column("failed_filters", json_type, nullable=True),
        sa.Column("filter_details", json_type, nullable=True),
        sa.Column("primary_failure_reason", sa.Text(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("candle_count", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["strategy_test_runs.id"]),
        sa.UniqueConstraint("run_id", "symbol", name="uq_strategy_test_results_run_symbol"),
    )
    op.create_index("ix_strategy_test_results_run_id", "strategy_test_results", ["run_id"])
    op.create_index("ix_strategy_test_results_run_signal", "strategy_test_results", ["run_id", "signal"])
    op.create_index("ix_strategy_test_results_run_return", "strategy_test_results", ["run_id", "return_pct"])
    op.create_table(
        "strategy_filter_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filter_id", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("passed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pass_pct", sa.Float(), nullable=True),
        sa.Column("fail_pct", sa.Float(), nullable=True),
        sa.Column("funnel_remaining", sa.Integer(), nullable=True),
        sa.Column("funnel_step", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["strategy_test_runs.id"]),
    )
    op.create_index("ix_strategy_filter_results_run", "strategy_filter_results", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_strategy_filter_results_run", table_name="strategy_filter_results")
    op.drop_table("strategy_filter_results")
    op.drop_index("ix_strategy_test_results_run_return", table_name="strategy_test_results")
    op.drop_index("ix_strategy_test_results_run_signal", table_name="strategy_test_results")
    op.drop_index("ix_strategy_test_results_run_id", table_name="strategy_test_results")
    op.drop_table("strategy_test_results")
    op.drop_index("ix_strategy_test_runs_status", table_name="strategy_test_runs")
    op.drop_index("ix_strategy_test_runs_user_started", table_name="strategy_test_runs")
    op.drop_index("ix_strategy_test_runs_user_id", table_name="strategy_test_runs")
    op.drop_table("strategy_test_runs")
    op.drop_index("ix_strategy_definitions_user_id", table_name="strategy_definitions")
    op.drop_table("strategy_definitions")
