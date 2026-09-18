"""Pine-compatible Indicator Scanner persistence."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ..db.base import Base


class IndicatorDefinition(Base):
    __tablename__ = "indicator_definitions"
    __table_args__ = (Index("ix_indicator_definitions_user_updated", "user_id", "updated_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_code: Mapped[str] = mapped_column(Text, nullable=False)
    script_version: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    language_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="pine_subset_v1")
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False, default="1D")
    parsed_definition: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    validation_status: Mapped[str] = mapped_column(String(16), nullable=False, default="valid")
    validation_errors: Mapped[list | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    required_bars: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class IndicatorScanRun(Base):
    __tablename__ = "indicator_scan_runs"
    __table_args__ = (
        UniqueConstraint("public_scan_id", name="uq_indicator_scan_runs_public_scan_id"),
        Index("ix_indicator_scan_runs_user_started", "user_id", "started_at"),
        Index("ix_indicator_scan_runs_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    public_scan_id: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    indicator_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("indicator_definitions.id"), nullable=True
    )
    indicator_name: Mapped[str] = mapped_column(String(120), nullable=False)
    indicator_snapshot: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    universe: Mapped[str] = mapped_column(String(32), nullable=False, default="nse-755")
    universe_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False, default="1D")
    filters: Mapped[list | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    sort: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    input_overrides: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    scan_date: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    progress_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    as_of: Mapped[str | None] = mapped_column(String(32), nullable=True)
    benchmark_symbol: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IndicatorScanResult(Base):
    __tablename__ = "indicator_scan_results"
    __table_args__ = (
        UniqueConstraint("run_id", "symbol", name="uq_indicator_scan_results_run_symbol"),
        Index("ix_indicator_scan_results_run_matched", "run_id", "matched"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("indicator_scan_runs.id"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    exchange: Mapped[str] = mapped_column(String(8), nullable=False, default="NSE")
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False, default="1D")
    as_of: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ok")
    matched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    outputs: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    ohlcv: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    bar_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
