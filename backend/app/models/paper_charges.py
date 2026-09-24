from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from ..db.base import Base

JsonVariant = JSON().with_variant(JSONB, "postgresql")


class ChargeProfile(Base):
    """Configurable and versioned transaction cost / brokerage profile.

    Supports equity delivery, intraday, futures, options across brokers and exchanges.
    """

    __tablename__ = "paper_trading_charge_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    profile_name: Mapped[str] = mapped_column(String(80), nullable=False)
    broker_id: Mapped[str] = mapped_column(String(32), default="DEFAULT", index=True)
    exchange: Mapped[str] = mapped_column(String(16), default="NSE", index=True)
    segment: Mapped[str] = mapped_column(String(32), default="EQUITY_DELIVERY", index=True)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, index=True)

    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    rounding_mode: Mapped[str] = mapped_column(String(32), default="ROUND_HALF_UP")
    money_decimal_places: Mapped[int] = mapped_column(Integer, default=2)

    # Brokerage configuration
    # ZERO | PERCENTAGE | FLAT_PER_EXECUTED_ORDER | MIN_OF_PERCENTAGE_OR_FLAT_CAP
    brokerage_type: Mapped[str] = mapped_column(String(40), default="ZERO")
    brokerage_rate_pct: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    brokerage_flat_per_executed_order: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    brokerage_order_cap: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))

    # Statutory taxes & exchange fees (in percentage, e.g. 0.10 means 0.10%)
    stt_buy_rate_pct: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0.10"))
    stt_sell_rate_pct: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0.10"))

    exchange_transaction_charge_buy_rate_pct: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0.00307"))
    exchange_transaction_charge_sell_rate_pct: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0.00307"))

    sebi_turnover_fee_rate_pct: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0.00010"))

    clearing_charge_buy_rate_pct: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    clearing_charge_sell_rate_pct: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))

    gst_rate_pct: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("18.0"))
    stamp_duty_buy_rate_pct: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0.015"))
    stamp_duty_sell_rate_pct: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))

    # Depository Participant (DP) charge on delivery sales
    dp_charge_on_delivery_sell: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    # PER_SELL_ORDER | PER_ISIN_PER_DAY
    dp_charge_scope: Mapped[str] = mapped_column(String(32), default="PER_SELL_ORDER")

    # Portfolio P&L behavior
    include_estimated_exit_charges_in_unrealised_pnl: Mapped[bool] = mapped_column(Boolean, default=False)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("broker_id", "exchange", "segment", "version", name="uq_charge_profile_version"),
        Index("idx_charge_profile_lookup", "broker_id", "exchange", "segment", "is_active"),
    )


class TradeChargeBreakdown(Base):
    """Immutable audit breakdown of all statutory and broker charges for an executed fill or trade."""

    __tablename__ = "paper_trading_charge_breakdowns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_trading_accounts.id", ondelete="CASCADE"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("paper_trading_orders.id", ondelete="SET NULL"), nullable=True, index=True)
    trade_id: Mapped[int | None] = mapped_column(ForeignKey("paper_trading_trade_history.id", ondelete="SET NULL"), nullable=True, index=True)
    position_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    profile_id: Mapped[int | None] = mapped_column(ForeignKey("paper_trading_charge_profiles.id", ondelete="SET NULL"), nullable=True)
    profile_version: Mapped[int] = mapped_column(Integer, default=1)

    symbol: Mapped[str] = mapped_column(String(32), index=True)
    exchange: Mapped[str] = mapped_column(String(16), default="NSE")
    segment: Mapped[str] = mapped_column(String(32), default="EQUITY_DELIVERY")
    side: Mapped[str] = mapped_column(String(8), index=True)  # BUY | SELL

    executed_qty: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    executed_price: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    turnover: Mapped[Decimal] = mapped_column(Numeric(18, 2))

    # Itemized charges
    brokerage: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    stt: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    exchange_charges: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    sebi_charges: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    clearing_charges: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    gst: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    stamp_duty: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    dp_charges: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    total_charges: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))

    calculation_metadata: Mapped[dict[str, Any] | None] = mapped_column(JsonVariant, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        Index("idx_charge_breakdown_order", "order_id"),
        Index("idx_charge_breakdown_trade", "trade_id"),
        Index("idx_charge_breakdown_account", "account_id", "created_at"),
    )

