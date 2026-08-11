"""Strategy-grade daily market data models (SoT for scanners/strategies)."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ..db.base import Base


class DailyOhlcv(Base):
    __tablename__ = "daily_ohlcv"

    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    delivery_qty: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    delivery_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 4), nullable=True)
    turnover: Mapped[Decimal | None] = mapped_column(Numeric(24, 4), nullable=True)
    adtv_20: Mapped[Decimal | None] = mapped_column(Numeric(24, 4), nullable=True)
    source: Mapped[str | None] = mapped_column(String(40), nullable=True)
    loaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_daily_ohlcv_symbol_trade_date", "symbol", "trade_date"),
        Index("ix_daily_ohlcv_trade_date", "trade_date"),
    )


class IndexOhlcv(Base):
    __tablename__ = "index_ohlcv"

    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source: Mapped[str | None] = mapped_column(String(40), nullable=True)
    loaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_index_ohlcv_symbol_trade_date", "symbol", "trade_date"),
    )


class DataLoadLog(Base):
    __tablename__ = "data_load_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    load_type: Mapped[str] = mapped_column(String(16), nullable=False)  # FULL | DAILY
    trigger_source: Mapped[str] = mapped_column(String(16), nullable=False)  # CLI | SCHEDULE
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    data_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    range_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    range_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_fetched: Mapped[int] = mapped_column(Integer, default=0)
    rows_inserted: Mapped[int] = mapped_column(Integer, default=0)
    rows_updated: Mapped[int] = mapped_column(Integer, default=0)
    rows_failed: Mapped[int] = mapped_column(Integer, default=0)
    rows_skipped: Mapped[int] = mapped_column(Integer, default=0)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)

    __table_args__ = (
        Index("ix_data_load_log_started_at", "started_at"),
        Index("ix_data_load_log_type_date", "load_type", "data_date"),
        Index("ix_data_load_log_status", "status"),
    )
