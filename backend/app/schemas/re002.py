"""RE-002 Decision Object and Lab DTOs (contracts: re002-decision-object, re002-lab-api)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from .re001 import TradeGuidance  # shared trade guidance shape


Re002Stage = Literal["OFF", "LAB_SHADOW", "PAPER_LINKED"]
RecommendationState = Literal["BUY", "WATCH", "REJECT"]
MarketRegimeBucket = Literal["Bull", "Sideways", "Bear", "UNKNOWN"]
EvaluationStatus = Literal["success", "rejected_by_rules", "error", "timeout"]


class Re002Registration(BaseModel):
    engine_id: str = "RE-002"
    name: str = "Relative Strength Momentum Engine"
    engine_version: str = "1.0"
    stage: Re002Stage = "OFF"
    enabled: bool = False
    experiment_id: str | None = None
    # True only when evaluation side effects will run (enabled + lab stage + experiment gate)
    active: bool = False


class Re002DecisionObject(BaseModel):
    recommendation_id: str
    engine_id: str = "RE-002"
    engine_version: str = "1.0"
    experiment_id: str | None = None
    market_regime: MarketRegimeBucket = "UNKNOWN"
    trading_objective: str = "relative_strength_leadership"
    trading_style: str = "long_only_swing"
    strategy_family: str | None = None
    strategy_name: str | None = None
    recommendation_state: RecommendationState
    confidence_score: float
    risk_profile: dict[str, Any] | str = Field(default_factory=dict)
    portfolio_decision: dict[str, Any] | str = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    technical_analysis: dict[str, Any] | None = None
    explanation: str | dict[str, Any] = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reason_codes: list[str] = Field(default_factory=list)
    trade_guidance: TradeGuidance | None = None
    production_action: str | None = None
    production_score: float | None = None
    is_mismatch: bool | None = None
    symbol: str | None = None
    scan_run_id: str | None = None
    analysis_history_id: int | None = None
    evaluation_status: EvaluationStatus = "success"


class Re002ComparisonRow(BaseModel):
    symbol: str
    recommendation_id: str
    production_action: str | None = None
    production_score: float | None = None
    re002_state: RecommendationState
    confidence_score: float
    strategy_name: str | None = None
    strategy_family: str | None = None
    is_mismatch: bool | None = None
    experiment_id: str | None = None


class Re002ScanComparisonResponse(BaseModel):
    scan_run_id: str
    items: list[Re002ComparisonRow] = Field(default_factory=list)


class Re002HealthSegment(BaseModel):
    engine_id: str = "RE-002"
    buy_count: int = 0
    watch_count: int = 0
    reject_count: int = 0
    error_count: int = 0
    timeout_count: int = 0
    mismatch_count: int = 0
    total: int = 0
    avg_rs_of_buys: float | None = None
    experiment_id: str | None = None
    runtime_counters: dict[str, int] | None = None
    runtime_counters_authoritative: bool = False


class Re002ScanRunSummary(BaseModel):
    scan_run_id: str
    decision_count: int = 0
    latest_created_at: str | None = None


class Re002RecentScansResponse(BaseModel):
    items: list[Re002ScanRunSummary] = Field(default_factory=list)


class Re002HistoryResponse(BaseModel):
    engine_id: str = "RE-002"
    total: int = 0
    limit: int = 50
    offset: int = 0
    items: list[dict[str, Any]] = Field(default_factory=list)
    as_of: str | None = None
