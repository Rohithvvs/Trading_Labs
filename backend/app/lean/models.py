"""QuantConnect LEAN Backtesting Engine Normalized Input / Output Models."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LeanJobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PositionSizingMethod(str, Enum):
    PERCENT_EQUITY = "PERCENT_EQUITY"
    EQUAL_WEIGHT = "EQUAL_WEIGHT"
    FIXED_CASH = "FIXED_CASH"
    FIXED_QUANTITY = "FIXED_QUANTITY"
    RISK_BASED = "RISK_BASED"


class ExecutionModelType(str, Enum):
    NEXT_BAR_OPEN = "NEXT_BAR_OPEN"
    IMMEDIATE_CLOSE = "IMMEDIATE_CLOSE"
    REALISTIC_NSE = "REALISTIC_NSE"


class EngineType(str, Enum):
    LEAN = "LEAN"
    EXISTING = "EXISTING"


class LeanBacktestRequest(BaseModel):
    """Normalized backtest request model."""
    model_config = ConfigDict(populate_by_name=True)

    strategy_id: str = Field(default="09_52w_breakout", alias="strategyId")
    strategy_name: str = Field(default="52-Week High Breakout", alias="strategyName")
    symbols: list[str] = Field(default_factory=lambda: ["RELIANCE"], alias="symbols")
    start_date: date = Field(default_factory=lambda: date(2020, 1, 1), alias="startDate")
    end_date: date = Field(default_factory=lambda: date.today(), alias="endDate")
    initial_capital: float = Field(default=100000.0, ge=1000.0, alias="initialCapital")
    commission_rate: float = Field(default=0.0005, ge=0.0, alias="commission")
    slippage_rate: float = Field(default=0.0005, ge=0.0, alias="slippage")
    position_sizing: PositionSizingMethod = Field(
        default=PositionSizingMethod.PERCENT_EQUITY, alias="positionSizing"
    )
    position_sizing_value: float = Field(default=10.0, ge=0.1, le=100.0, alias="positionSizingValue")
    max_positions: int = Field(default=10, ge=1, le=100, alias="maxPositions")
    benchmark: str | None = Field(default="NIFTY500", alias="benchmark")
    timeframe: str = Field(default="Daily", alias="timeframe")
    data_source: str = Field(default="NSE", alias="dataSource")
    execution_mode: EngineType = Field(default=EngineType.LEAN, alias="executionMode")
    parameters: dict[str, Any] = Field(default_factory=dict, alias="parameters")
    debug_mode: bool = Field(default=False, alias="debugMode")
    debug_symbol: str | None = Field(default=None, alias="debugSymbol")

    @field_validator("symbols", mode="before")
    @classmethod
    def clean_symbols(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            if v.strip().upper() in {"ALL", "ALL_755", "NIFTY500", "ALL_STOCKS"}:
                return ["ALL_755"]
            return [s.strip().upper() for s in v.split(",") if s.strip()]
        if isinstance(v, list):
            cleaned = [str(s).strip().upper() for s in v if str(s).strip()]
            return cleaned or ["RELIANCE"]
        return ["RELIANCE"]


class LeanTrade(BaseModel):
    """Normalized trade record."""
    model_config = ConfigDict(populate_by_name=True)

    trade_id: int = Field(alias="tradeId")
    symbol: str
    entry_date: str = Field(alias="entryDate")
    entry_price: float = Field(alias="entryPrice")
    exit_date: str | None = Field(default=None, alias="exitDate")
    exit_price: float | None = Field(default=None, alias="exitPrice")
    quantity: int
    direction: Literal["LONG", "SHORT"] = "LONG"
    gross_pnl: float = Field(default=0.0, alias="grossPnL")
    commission: float = Field(default=0.0)
    slippage: float = Field(default=0.0)
    net_pnl: float = Field(default=0.0, alias="netPnL")
    return_pct: float = Field(default=0.0, alias="returnPct")
    holding_period: int = Field(default=0, alias="holdingPeriod")
    entry_reason: str = Field(default="Signal", alias="entryReason")
    exit_reason: str = Field(default="Exit Signal", alias="exitReason")
    is_open: bool = Field(default=False, alias="isOpen")


class LeanEquityPoint(BaseModel):
    """Normalized equity curve data point."""
    model_config = ConfigDict(populate_by_name=True)

    date: str
    equity: float
    cash: float
    invested_capital: float = Field(default=0.0, alias="investedCapital")
    drawdown: float = 0.0
    drawdown_pct: float = Field(default=0.0, alias="drawdownPct")


class LeanPositionHistory(BaseModel):
    """Snapshot of portfolio positions at a date."""
    model_config = ConfigDict(populate_by_name=True)

    date: str
    symbol: str
    quantity: int
    average_price: float = Field(alias="averagePrice")
    market_value: float = Field(alias="marketValue")
    unrealized_pnl: float = Field(default=0.0, alias="unrealizedPnL")
    realized_pnl: float = Field(default=0.0, alias="realizedPnL")


class LeanBacktestSummary(BaseModel):
    """Normalized performance summary metrics."""
    model_config = ConfigDict(populate_by_name=True)

    initial_capital: float = Field(alias="initialCapital")
    final_equity: float = Field(alias="finalEquity")
    net_profit: float = Field(alias="netProfit")
    net_profit_pct: float = Field(alias="netProfitPct")
    cagr: float | None = None
    sharpe_ratio: float = Field(default=0.0, alias="sharpeRatio")
    sortino_ratio: float = Field(default=0.0, alias="sortinoRatio")
    maximum_drawdown: float = Field(default=0.0, alias="maximumDrawdown")
    maximum_drawdown_pct: float = Field(default=0.0, alias="maximumDrawdownPct")
    calmar_ratio: float | None = Field(default=None, alias="calmarRatio")
    total_trades: int = Field(default=0, alias="totalTrades")
    winning_trades: int = Field(default=0, alias="winningTrades")
    losing_trades: int = Field(default=0, alias="losingTrades")
    win_rate: float = Field(default=0.0, alias="winRate")
    profit_factor: float = Field(default=0.0, alias="profitFactor")
    average_trade: float = Field(default=0.0, alias="averageTrade")
    average_winning_trade: float = Field(default=0.0, alias="averageWinningTrade")
    average_losing_trade: float = Field(default=0.0, alias="averageLosingTrade")
    expectancy: float = 0.0
    total_commission: float = Field(default=0.0, alias="totalCommission")
    total_slippage: float = Field(default=0.0, alias="totalSlippage")
    execution_model: str = Field(default="LEAN NextBarOpen", alias="executionModel")
    data_source: str = Field(default="Trading Labs NSE Data", alias="dataSource")
    data_coverage_ratio: float = Field(default=1.0, alias="dataCoverageRatio")
    trading_days_count: int = Field(default=0, alias="tradingDaysCount")


class LeanDebugTraceBar(BaseModel):
    """Bar-by-bar debug step for symbol audit."""
    model_config = ConfigDict(populate_by_name=True)

    symbol: str
    date: str
    bar_index: int = Field(alias="barIndex")
    open: float
    high: float
    low: float
    close: float
    volume: int
    close_252: float | None = Field(default=None, alias="close252")
    momentum_252: float | None = Field(default=None, alias="momentum252")
    high_252: float | None = Field(default=None, alias="high252")
    vol_sma_20: float | None = Field(default=None, alias="volSma20")
    entry_condition: bool = Field(default=False, alias="entryCondition")
    exit_condition: bool = Field(default=False, alias="exitCondition")
    position_qty: int = Field(default=0, alias="positionQty")
    order_action: str | None = Field(default=None, alias="orderAction")
    fill_price: float | None = Field(default=None, alias="fillPrice")


class LeanValidationReport(BaseModel):
    """TradingView vs LEAN vs Existing Engine comparison report."""
    model_config = ConfigDict(populate_by_name=True)

    symbol: str
    strategy: str
    start_date: str = Field(alias="startDate")
    end_date: str = Field(alias="endDate")
    total_bars: int = Field(alias="totalBars")
    signal_matches: int = Field(alias="signalMatches")
    signal_mismatches: int = Field(alias="signalMismatches")
    trade_matches: int = Field(alias="tradeMatches")
    metrics_comparison: dict[str, dict[str, Any]] = Field(
        default_factory=dict, alias="metricsComparison"
    )
    mismatch_details: list[dict[str, Any]] = Field(
        default_factory=list, alias="mismatchDetails"
    )
    verdict: str = "PASS"


class LeanBacktestResult(BaseModel):
    """Full backtest execution result payload."""
    model_config = ConfigDict(populate_by_name=True)

    job_id: str = Field(alias="jobId")
    strategy_id: str = Field(alias="strategyId")
    strategy_name: str = Field(alias="strategyName")
    engine: str = "LEAN"
    status: LeanJobStatus = LeanJobStatus.COMPLETED
    start_date: str = Field(alias="startDate")
    end_date: str = Field(alias="endDate")
    symbols: list[str] = Field(default_factory=list)
    summary: LeanBacktestSummary
    trades: list[LeanTrade] = Field(default_factory=list)
    equity_curve: list[LeanEquityPoint] = Field(default_factory=list, alias="equityCurve")
    positions: list[LeanPositionHistory] = Field(default_factory=list)
    debug_trace: list[LeanDebugTraceBar] | None = Field(default=None, alias="debugTrace")
    runtime_metrics: dict[str, Any] = Field(default_factory=dict, alias="runtimeMetrics")
    validation_parity: LeanValidationReport | None = Field(default=None, alias="validationParity")


class LeanJobRecord(BaseModel):
    """Internal job state tracking model."""
    model_config = ConfigDict(populate_by_name=True)

    job_id: str = Field(default_factory=lambda: f"LEAN-{uuid.uuid4().hex[:12].upper()}", alias="jobId")
    strategy_id: str = Field(alias="strategyId")
    strategy_name: str = Field(alias="strategyName")
    user_id: str | None = Field(default=None, alias="userId")
    created_at: datetime = Field(default_factory=datetime.utcnow, alias="createdAt")
    started_at: datetime | None = Field(default=None, alias="startedAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    status: LeanJobStatus = LeanJobStatus.QUEUED
    progress_pct: int = Field(default=0, alias="progressPct")
    stage: str = "Queued"
    error: str | None = None
    request: LeanBacktestRequest
    result: LeanBacktestResult | None = None
