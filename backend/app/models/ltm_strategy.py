"""LTM book state and namespaced strategy-scan persistence."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ..db.base import Base


class LtmBookState(Base):
    __tablename__ = "ltm_book_state"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default="default")
    strategy_id: Mapped[str] = mapped_column(String(32), nullable=False, default="17_long_term_mom")
    mode: Mapped[str] = mapped_column(String(8), nullable=False, default="A")
    fill_model: Mapped[str] = mapped_column(String(24), nullable=False, default="signal_close")
    cash: Mapped[float] = mapped_column(Float, nullable=False, default=100000.0)
    equity: Mapped[float] = mapped_column(Float, nullable=False, default=100000.0)
    initial_capital: Mapped[float] = mapped_column(Float, nullable=False, default=100000.0)
    session_index: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)
    last_rebalance_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_rebalance_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    clock_status: Mapped[str] = mapped_column(String(16), nullable=False, default="WARMUP")
    holdings: Mapped[list | dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    pending_orders: Mapped[list | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    survivorship_biased: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class StrategyScanLatest(Base):
    __tablename__ = "strategy_scan_latest"

    strategy_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    payload: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StrategyScanRun(Base):
    __tablename__ = "strategy_scan_runs"

    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    progress_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
