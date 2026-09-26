"""Configurable transaction cost & brokerage engine for paper trading

Revision ID: 20260924_charge_engine
Revises: 20260829_indicator_scanner
Create Date: 2026-09-24
"""
from typing import Sequence, Union
from datetime import datetime, timezone
from decimal import Decimal

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260924_charge_engine"
down_revision: Union[str, Sequence[str], None] = "20260829_indicator_scanner"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

    # 1. Create charge profiles table if not exists
    if "paper_trading_charge_profiles" not in tables:
        op.create_table(
            "paper_trading_charge_profiles",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("profile_name", sa.String(length=80), nullable=False),
            sa.Column("broker_id", sa.String(length=32), nullable=False, server_default="DEFAULT"),
            sa.Column("exchange", sa.String(length=16), nullable=False, server_default="NSE"),
            sa.Column("segment", sa.String(length=32), nullable=False, server_default="EQUITY_DELIVERY"),
            sa.Column("currency", sa.String(length=8), nullable=False, server_default="INR"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
            sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
            sa.Column("rounding_mode", sa.String(length=32), nullable=False, server_default="ROUND_HALF_UP"),
            sa.Column("money_decimal_places", sa.Integer(), nullable=False, server_default="2"),
            sa.Column("brokerage_type", sa.String(length=40), nullable=False, server_default="ZERO"),
            sa.Column("brokerage_rate_pct", sa.Numeric(18, 6), nullable=False, server_default="0"),
            sa.Column("brokerage_flat_per_executed_order", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("brokerage_order_cap", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("stt_buy_rate_pct", sa.Numeric(18, 6), nullable=False, server_default="0.10"),
            sa.Column("stt_sell_rate_pct", sa.Numeric(18, 6), nullable=False, server_default="0.10"),
            sa.Column("exchange_transaction_charge_buy_rate_pct", sa.Numeric(18, 6), nullable=False, server_default="0.00307"),
            sa.Column("exchange_transaction_charge_sell_rate_pct", sa.Numeric(18, 6), nullable=False, server_default="0.00307"),
            sa.Column("sebi_turnover_fee_rate_pct", sa.Numeric(18, 6), nullable=False, server_default="0.00010"),
            sa.Column("clearing_charge_buy_rate_pct", sa.Numeric(18, 6), nullable=False, server_default="0"),
            sa.Column("clearing_charge_sell_rate_pct", sa.Numeric(18, 6), nullable=False, server_default="0"),
            sa.Column("gst_rate_pct", sa.Numeric(18, 4), nullable=False, server_default="18.0"),
            sa.Column("stamp_duty_buy_rate_pct", sa.Numeric(18, 6), nullable=False, server_default="0.015"),
            sa.Column("stamp_duty_sell_rate_pct", sa.Numeric(18, 6), nullable=False, server_default="0"),
            sa.Column("dp_charge_on_delivery_sell", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("dp_charge_scope", sa.String(length=32), nullable=False, server_default="PER_SELL_ORDER"),
            sa.Column("include_estimated_exit_charges_in_unrealised_pnl", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("broker_id", "exchange", "segment", "version", name="uq_charge_profile_version"),
        )
        op.create_index("idx_charge_profile_lookup", "paper_trading_charge_profiles", ["broker_id", "exchange", "segment", "is_active"])

        # Seed default INDIA_EQUITY_DELIVERY_DEFAULT profile
        now = datetime.now(timezone.utc)
        op.execute(
            sa.text(
                """
                INSERT INTO paper_trading_charge_profiles (
                    profile_name, broker_id, exchange, segment, currency, is_active, is_default, version,
                    effective_from, rounding_mode, money_decimal_places,
                    brokerage_type, brokerage_rate_pct, brokerage_flat_per_executed_order, brokerage_order_cap,
                    stt_buy_rate_pct, stt_sell_rate_pct,
                    exchange_transaction_charge_buy_rate_pct, exchange_transaction_charge_sell_rate_pct,
                    sebi_turnover_fee_rate_pct, clearing_charge_buy_rate_pct, clearing_charge_sell_rate_pct,
                    gst_rate_pct, stamp_duty_buy_rate_pct, stamp_duty_sell_rate_pct,
                    dp_charge_on_delivery_sell, dp_charge_scope, include_estimated_exit_charges_in_unrealised_pnl,
                    notes, created_at, updated_at
                ) VALUES (
                    'Default NSE Equity Delivery', 'DEFAULT', 'NSE', 'EQUITY_DELIVERY', 'INR', true, true, 1,
                    :now, 'ROUND_HALF_UP', 2,
                    'FLAT_PER_EXECUTED_ORDER', 0, 20.00, 20.00,
                    0.10, 0.10,
                    0.00307, 0.00307,
                    0.00010, 0, 0,
                    18.0, 0.015, 0,
                    0, 'PER_SELL_ORDER', false,
                    'Seeded default statutory charges for Indian cash equity delivery swing trading.', :now, :now
                )
                """
            ).bindparams(now=now)
        )

    # 2. Create charge breakdowns audit table if not exists
    if "paper_trading_charge_breakdowns" not in tables:
        op.create_table(
            "paper_trading_charge_breakdowns",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("account_id", sa.Integer(), sa.ForeignKey("paper_trading_accounts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("paper_trading_orders.id", ondelete="SET NULL"), nullable=True),
            sa.Column("trade_id", sa.Integer(), sa.ForeignKey("paper_trading_trade_history.id", ondelete="SET NULL"), nullable=True),
            sa.Column("position_id", sa.Integer(), nullable=True),
            sa.Column("profile_id", sa.Integer(), sa.ForeignKey("paper_trading_charge_profiles.id", ondelete="SET NULL"), nullable=True),
            sa.Column("profile_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("symbol", sa.String(length=32), nullable=False),
            sa.Column("exchange", sa.String(length=16), nullable=False, server_default="NSE"),
            sa.Column("segment", sa.String(length=32), nullable=False, server_default="EQUITY_DELIVERY"),
            sa.Column("side", sa.String(length=8), nullable=False),
            sa.Column("executed_qty", sa.Numeric(18, 8), nullable=False),
            sa.Column("executed_price", sa.Numeric(18, 8), nullable=False),
            sa.Column("turnover", sa.Numeric(18, 2), nullable=False),
            sa.Column("brokerage", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("stt", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("exchange_charges", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("sebi_charges", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("clearing_charges", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("gst", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("stamp_duty", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("dp_charges", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("total_charges", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("calculation_metadata", json_type, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("idx_charge_breakdown_order", "paper_trading_charge_breakdowns", ["order_id"])
        op.create_index("idx_charge_breakdown_trade", "paper_trading_charge_breakdowns", ["trade_id"])
        op.create_index("idx_charge_breakdown_account", "paper_trading_charge_breakdowns", ["account_id", "created_at"])

    # 3. Add columns to paper_trading_positions if missing
    if "paper_trading_positions" in tables:
        pos_cols = [c["name"] for c in insp.get_columns("paper_trading_positions")]
        if "total_buy_charges" not in pos_cols:
            op.add_column("paper_trading_positions", sa.Column("total_buy_charges", sa.Numeric(18, 2), nullable=False, server_default="0.00"))
        if "break_even_price" not in pos_cols:
            op.add_column("paper_trading_positions", sa.Column("break_even_price", sa.Numeric(18, 8), nullable=True))

    # 4. Add columns to paper_trading_trade_history if missing
    if "paper_trading_trade_history" in tables:
        th_cols = [c["name"] for c in insp.get_columns("paper_trading_trade_history")]
        if "gross_pnl" not in th_cols:
            op.add_column("paper_trading_trade_history", sa.Column("gross_pnl", sa.Numeric(18, 2), nullable=True))
        if "total_charges" not in th_cols:
            op.add_column("paper_trading_trade_history", sa.Column("total_charges", sa.Numeric(18, 2), nullable=True, server_default="0.00"))
        if "net_pnl" not in th_cols:
            op.add_column("paper_trading_trade_history", sa.Column("net_pnl", sa.Numeric(18, 2), nullable=True))
        if "break_even_price" not in th_cols:
            op.add_column("paper_trading_trade_history", sa.Column("break_even_price", sa.Numeric(18, 8), nullable=True))

        # Backfill existing trade history rows so gross_pnl = pnl, net_pnl = pnl, total_charges = 0
        op.execute(
            sa.text(
                """
                UPDATE paper_trading_trade_history
                SET gross_pnl = COALESCE(gross_pnl, pnl),
                    total_charges = COALESCE(total_charges, 0.00),
                    net_pnl = COALESCE(net_pnl, pnl)
                WHERE gross_pnl IS NULL OR net_pnl IS NULL
                """
            )
        )


def downgrade() -> None:
    op.drop_table("paper_trading_charge_breakdowns")
    op.drop_table("paper_trading_charge_profiles")
    op.drop_column("paper_trading_positions", "break_even_price")
    op.drop_column("paper_trading_positions", "total_buy_charges")
    op.drop_column("paper_trading_trade_history", "break_even_price")
    op.drop_column("paper_trading_trade_history", "net_pnl")
    op.drop_column("paper_trading_trade_history", "total_charges")
    op.drop_column("paper_trading_trade_history", "gross_pnl")

