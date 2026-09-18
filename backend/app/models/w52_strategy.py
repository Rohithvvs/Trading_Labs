"""52-Week High Breakout book state. Scan latest/runs reuse 037 tables."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ..db.base import Base


class W52BookState(Base):
    __tablename__ = "w52_book_state"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default="default")
    strategy_id: Mapped[str] = mapped_column(String(32), nullable=False, default="09_52w_breakout")
    mode: Mapped[str] = mapped_column(String(8), nullable=False, default="B")
    fill_model: Mapped[str] = mapped_column(String(24), nullable=False, default="signal_close")
    cash: Mapped[float] = mapped_column(Float, nullable=False, default=100000.0)
    equity: Mapped[float] = mapped_column(Float, nullable=False, default=100000.0)
    initial_capital: Mapped[float] = mapped_column(Float, nullable=False, default=100000.0)
    session_index: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)
    last_session_processed: Mapped[date | None] = mapped_column(Date, nullable=True)
    book_status: Mapped[str] = mapped_column(String(16), nullable=False, default="WARMUP")
    market_ok: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    nifty_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    nifty_sma50: Mapped[float | None] = mapped_column(Float, nullable=True)
    holdings: Mapped[list | dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    pending_orders: Mapped[list | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    sold_today: Mapped[list | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    survivorship_biased: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class W52SymbolPerformance(Base):
    """Per-symbol Strategy Tester metrics from closed-trade replay.

    One row per (strategy, symbol, window, execution profile). Counts and
    P&L come only from simulated fills, never from signals or assumptions.
    """

    __tablename__ = "w52_symbol_performance"
    __table_args__ = (
        UniqueConstraint(
            "strategy_id",
            "symbol",
            "window",
            "execution_profile",
            name="uq_w52_symbol_performance",
        ),
        Index("ix_w52_symbol_performance_symbol", "symbol"),
        Index("ix_w52_symbol_performance_window", "window"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[str] = mapped_column(String(32), nullable=False, default="09_52w_breakout")
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    window: Mapped[str] = mapped_column(String(16), nullable=False)
    execution_profile: Mapped[str] = mapped_column(String(24), nullable=False, default="KERNEL")
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    evaluation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ok")
    unavailable_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    candle_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    coverage_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)

    total_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown_inr: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    profitable_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    losing_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    breakeven: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    profit_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    profit_factor_infinite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    gross_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    commission: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_payoff: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_payoff_inr: Mapped[float | None] = mapped_column(Float, nullable=True)
    largest_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    largest_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    largest_profit_inr: Mapped[float | None] = mapped_column(Float, nullable=True)
    largest_loss_inr: Mapped[float | None] = mapped_column(Float, nullable=True)
    average_winning_trade: Mapped[float | None] = mapped_column(Float, nullable=True)
    average_losing_trade: Mapped[float | None] = mapped_column(Float, nullable=True)
    average_winning_trade_inr: Mapped[float | None] = mapped_column(Float, nullable=True)
    average_losing_trade_inr: Mapped[float | None] = mapped_column(Float, nullable=True)
    outlier_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    outlier_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    cagr: Mapped[float | None] = mapped_column(Float, nullable=True)
    initial_capital: Mapped[float | None] = mapped_column(Float, nullable=True)
    ending_capital: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="closed_trade_ledger")
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    trades: Mapped[list | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    ledger: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    coverage: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
