"""strategy-grade daily market data tables + stocks_master lifecycle columns

Revision ID: 20260808_strategy_market_data
Revises: 20260807_lab_decision_indexes
Create Date: 2026-08-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260808_strategy_market_data"
# Linear parent matching the Neon DB head used in development/production.
down_revision: Union[str, Sequence[str], None] = "20260807_lab_decision_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    is_pg = conn.dialect.name == "postgresql"
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # --- stocks_master lifecycle columns (idempotent) ---
    cols = {
        "industry": sa.Column("industry", sa.String(length=128), nullable=True),
        "is_nifty500": sa.Column("is_nifty500", sa.Boolean(), nullable=True),
        "first_seen": sa.Column("first_seen", sa.DateTime(timezone=True), nullable=True),
        "last_seen": sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
    }
    inspector = sa.inspect(conn)
    existing = {c["name"] for c in inspector.get_columns("stocks_master")} if "stocks_master" in inspector.get_table_names() else set()
    for name, col in cols.items():
        if name not in existing:
            op.add_column("stocks_master", col)
    if "is_nifty500" not in existing or True:
        try:
    if "stocks_master" in existing_tables:
        cols = {
            "industry": sa.Column("industry", sa.String(length=128), nullable=True),
            "is_nifty500": sa.Column("is_nifty500", sa.Boolean(), nullable=True),
            "first_seen": sa.Column("first_seen", sa.DateTime(timezone=True), nullable=True),
            "last_seen": sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        }
        existing_cols = {c["name"] for c in inspector.get_columns("stocks_master")}
        for name, col in cols.items():
            if name not in existing_cols:
                op.add_column("stocks_master", col)

        if "is_nifty500" in existing_cols:
            op.execute(
                sa.text(
                    "UPDATE stocks_master SET is_nifty500 = TRUE "
                    "WHERE universe = 'NIFTY500' AND (is_nifty500 IS NULL OR is_nifty500 = FALSE)"
                )
            )
        except Exception:
            pass
    try:
        op.create_index("ix_stocks_master_is_nifty500", "stocks_master", ["is_nifty500"], unique=False)
    except Exception:
        pass

        existing_indexes = {ix["name"] for ix in inspector.get_indexes("stocks_master")}
        if "ix_stocks_master_is_nifty500" not in existing_indexes:
            op.create_index("ix_stocks_master_is_nifty500", "stocks_master", ["is_nifty500"], unique=False)

    # --- daily_ohlcv ---
    op.create_table(
        "daily_ohlcv",
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("open", sa.Numeric(18, 8), nullable=False),
        sa.Column("high", sa.Numeric(18, 8), nullable=False),
        sa.Column("low", sa.Numeric(18, 8), nullable=False),
        sa.Column("close", sa.Numeric(18, 8), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("delivery_qty", sa.BigInteger(), nullable=True),
        sa.Column("delivery_pct", sa.Numeric(9, 4), nullable=True),
        sa.Column("turnover", sa.Numeric(24, 4), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=True),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("trade_date", "symbol", name="pk_daily_ohlcv"),
    )
    op.create_index("ix_daily_ohlcv_symbol_trade_date", "daily_ohlcv", ["symbol", "trade_date"], unique=False)
    op.create_index("ix_daily_ohlcv_trade_date", "daily_ohlcv", ["trade_date"], unique=False)
    if "daily_ohlcv" not in existing_tables:
        op.create_table(
            "daily_ohlcv",
            sa.Column("trade_date", sa.Date(), nullable=False),
            sa.Column("symbol", sa.String(length=32), nullable=False),
            sa.Column("open", sa.Numeric(18, 8), nullable=False),
            sa.Column("high", sa.Numeric(18, 8), nullable=False),
            sa.Column("low", sa.Numeric(18, 8), nullable=False),
            sa.Column("close", sa.Numeric(18, 8), nullable=False),
            sa.Column("volume", sa.BigInteger(), nullable=False),
            sa.Column("delivery_qty", sa.BigInteger(), nullable=True),
            sa.Column("delivery_pct", sa.Numeric(9, 4), nullable=True),
            sa.Column("turnover", sa.Numeric(24, 4), nullable=True),
            sa.Column("source", sa.String(length=40), nullable=True),
            sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("trade_date", "symbol", name="pk_daily_ohlcv"),
        )
        op.create_index("ix_daily_ohlcv_symbol_trade_date", "daily_ohlcv", ["symbol", "trade_date"], unique=False)
        op.create_index("ix_daily_ohlcv_trade_date", "daily_ohlcv", ["trade_date"], unique=False)

    # --- index_ohlcv ---
    op.create_table(
        "index_ohlcv",
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("open", sa.Numeric(18, 8), nullable=False),
        sa.Column("high", sa.Numeric(18, 8), nullable=False),
        sa.Column("low", sa.Numeric(18, 8), nullable=False),
        sa.Column("close", sa.Numeric(18, 8), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=True),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("trade_date", "symbol", name="pk_index_ohlcv"),
    )
    op.create_index("ix_index_ohlcv_symbol_trade_date", "index_ohlcv", ["symbol", "trade_date"], unique=False)
    if "index_ohlcv" not in existing_tables:
        op.create_table(
            "index_ohlcv",
            sa.Column("trade_date", sa.Date(), nullable=False),
            sa.Column("symbol", sa.String(length=32), nullable=False),
            sa.Column("open", sa.Numeric(18, 8), nullable=False),
            sa.Column("high", sa.Numeric(18, 8), nullable=False),
            sa.Column("low", sa.Numeric(18, 8), nullable=False),
            sa.Column("close", sa.Numeric(18, 8), nullable=False),
            sa.Column("volume", sa.BigInteger(), nullable=True),
            sa.Column("source", sa.String(length=40), nullable=True),
            sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("trade_date", "symbol", name="pk_index_ohlcv"),
        )
        op.create_index("ix_index_ohlcv_symbol_trade_date", "index_ohlcv", ["symbol", "trade_date"], unique=False)

    # --- data_load_log ---
    details_type = postgresql.JSONB() if is_pg else sa.JSON()
    id_col = sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False) if is_pg else sa.Column("id", sa.String(36), nullable=False)
    op.create_table(
        "data_load_log",
        id_col,
        sa.Column("load_type", sa.String(length=16), nullable=False),
        sa.Column("trigger_source", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("data_date", sa.Date(), nullable=True),
        sa.Column("range_from", sa.Date(), nullable=True),
        sa.Column("range_to", sa.Date(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("rows_fetched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("details_json", details_type, nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_data_load_log"),
    )
    op.create_index("ix_data_load_log_started_at", "data_load_log", ["started_at"], unique=False)
    op.create_index("ix_data_load_log_type_date", "data_load_log", ["load_type", "data_date"], unique=False)
    op.create_index("ix_data_load_log_status", "data_load_log", ["status"], unique=False)
    if "data_load_log" not in existing_tables:
        details_type = postgresql.JSONB() if is_pg else sa.JSON()
        id_col = sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False) if is_pg else sa.Column("id", sa.String(36), nullable=False)
        op.create_table(
            "data_load_log",
            id_col,
            sa.Column("load_type", sa.String(length=16), nullable=False),
            sa.Column("trigger_source", sa.String(length=16), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("data_date", sa.Date(), nullable=True),
            sa.Column("range_from", sa.Date(), nullable=True),
            sa.Column("range_to", sa.Date(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("rows_fetched", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("rows_inserted", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("rows_updated", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("rows_failed", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("rows_skipped", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("provider", sa.String(length=64), nullable=True),
            sa.Column("error_summary", sa.Text(), nullable=True),
            sa.Column("details_json", details_type, nullable=True),
            sa.PrimaryKeyConstraint("id", name="pk_data_load_log"),
        )
        op.create_index("ix_data_load_log_started_at", "data_load_log", ["started_at"], unique=False)
        op.create_index("ix_data_load_log_type_date", "data_load_log", ["load_type", "data_date"], unique=False)
        op.create_index("ix_data_load_log_status", "data_load_log", ["status"], unique=False)


def downgrade() -> None:
    op.drop_table("data_load_log")
    op.drop_table("index_ohlcv")
    op.drop_table("daily_ohlcv")
    for col in ("last_seen", "first_seen", "is_nifty500", "industry"):
        try:
            op.drop_column("stocks_master", col)
        except Exception:
            pass
