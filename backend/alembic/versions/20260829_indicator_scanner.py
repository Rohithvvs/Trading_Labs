"""Pine-compatible Indicator Scanner tables

Revision ID: 20260829_indicator_scanner
Revises: 20260826_strategy_tester
Create Date: 2026-08-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260829_indicator_scanner"
down_revision: Union[str, Sequence[str], None] = "20260826_strategy_tester"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "indicator_definitions" in insp.get_table_names():
        return
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "indicator_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("source_code", sa.Text(), nullable=False),
        sa.Column("script_version", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("language_mode", sa.String(length=32), nullable=False, server_default="pine_subset_v1"),
        sa.Column("timeframe", sa.String(length=16), nullable=False, server_default="1D"),
        sa.Column("parsed_definition", json_type, nullable=True),
        sa.Column("validation_status", sa.String(length=16), nullable=False, server_default="valid"),
        sa.Column("validation_errors", json_type, nullable=True),
        sa.Column("required_bars", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_indicator_definitions_user_id", "indicator_definitions", ["user_id"])
    op.create_index("ix_indicator_definitions_user_updated", "indicator_definitions", ["user_id", "updated_at"])
    op.create_table(
        "indicator_scan_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("public_scan_id", sa.String(length=32), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("indicator_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("indicator_name", sa.String(length=120), nullable=False),
        sa.Column("indicator_snapshot", json_type, nullable=False),
        sa.Column("universe", sa.String(length=32), nullable=False, server_default="nse-755"),
        sa.Column("universe_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("timeframe", sa.String(length=16), nullable=False, server_default="1D"),
        sa.Column("filters", json_type, nullable=True),
        sa.Column("sort", json_type, nullable=True),
        sa.Column("input_overrides", json_type, nullable=True),
        sa.Column("scan_date", sa.String(length=16), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("stage", sa.String(length=64), nullable=True),
        sa.Column("progress_pct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("as_of", sa.String(length=32), nullable=True),
        sa.Column("benchmark_symbol", sa.String(length=64), nullable=True),
        sa.Column("summary", json_type, nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["indicator_id"], ["indicator_definitions.id"]),
        sa.UniqueConstraint("public_scan_id", name="uq_indicator_scan_runs_public_scan_id"),
    )
    op.create_index("ix_indicator_scan_runs_user_id", "indicator_scan_runs", ["user_id"])
    op.create_index("ix_indicator_scan_runs_user_started", "indicator_scan_runs", ["user_id", "started_at"])
    op.create_index("ix_indicator_scan_runs_status", "indicator_scan_runs", ["status"])
    op.create_table(
        "indicator_scan_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=True),
        sa.Column("exchange", sa.String(length=8), nullable=False, server_default="NSE"),
        sa.Column("timeframe", sa.String(length=16), nullable=False, server_default="1D"),
        sa.Column("as_of", sa.String(length=16), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ok"),
        sa.Column("matched", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("outputs", json_type, nullable=True),
        sa.Column("ohlcv", json_type, nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("bar_count", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["indicator_scan_runs.id"]),
        sa.UniqueConstraint("run_id", "symbol", name="uq_indicator_scan_results_run_symbol"),
    )
    op.create_index("ix_indicator_scan_results_run_id", "indicator_scan_results", ["run_id"])
    op.create_index("ix_indicator_scan_results_run_matched", "indicator_scan_results", ["run_id", "matched"])


def downgrade() -> None:
    op.drop_table("indicator_scan_results")
    op.drop_table("indicator_scan_runs")
    op.drop_table("indicator_definitions")
