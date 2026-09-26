"""Evaluate one stock + historical bars + strategy config. No future bars."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .filter_engine import LeafEvaluation, evaluate_tree
from .indicators import BarSeries
from .returns import ReturnBreakdown, simple_return
from .schema import Operand, StrategyDefinitionConfig, collect_series_keys
from .signals import BUY, REJECT, classify_signal


STATUS_OK = "ok"
STATUS_INSUFFICIENT_DATA = "insufficient_data"
STATUS_VALIDATION_FAILED = "validation_failed"
STATUS_ERROR = "error"


@dataclass
class StrategyEvaluationResult:
    symbol: str
    company: str | None
    status: str
    signal: str | None
    entry_price: float | None
    exit_price: float | None
    return_pct: float | None
    return_bucket: str | None
    return_formula: str | None
    position_side: str
    evaluation_date: date | None
    entry_date: date | None
    exit_date: date | None
    passed_filters: list[str]
    failed_filters: list[str]
    filter_details: list[dict[str, Any]]
    indicators: dict[str, float | None]
    primary_failure_reason: str | None
    rr: float | None = None
    error_detail: str | None = None
    candle_count: int = 0

    def to_row(self, rank: int | None = None) -> dict[str, Any]:
        return {
            "rank": rank,
            "symbol": self.symbol,
            "company": self.company,
            "status": self.status,
            "signal": self.signal,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "rr": self.rr or self.indicators.get("rr") or (2.0 if self.entry_price else None),
            "return_pct": self.return_pct,
            "return_bucket": self.return_bucket,
            "return_formula": self.return_formula,
            "position_side": self.position_side,
            "evaluation_date": self.evaluation_date.isoformat() if self.evaluation_date else None,
            "entry_date": self.entry_date.isoformat() if self.entry_date else None,
            "exit_date": self.exit_date.isoformat() if self.exit_date else None,
            "passed_filters": self.passed_filters,
            "failed_filters": self.failed_filters,
            "filters_passed": len(self.passed_filters),
            "filters_failed": len(self.failed_filters),
            "filter_details": self.filter_details,
            "indicators": self.indicators,
            "primary_failure_reason": self.primary_failure_reason,
            "error_detail": self.error_detail,
            "candle_count": self.candle_count,
            "rsi": self.indicators.get("rsi_14"),
            "sma_20": self.indicators.get("sma_20"),
            "sma_50": self.indicators.get("sma_50"),
            "sma_200": self.indicators.get("sma_200"),
            "volume": self.indicators.get("volume"),
            "avg_volume": self.indicators.get("avg_volume_20") or self.indicators.get("avg_volume"),
            "close": self.indicators.get("close") or self.exit_price,
            "high_252": self.indicators.get("high_252"),
            "nifty500_close": self.indicators.get("nifty500_close"),
            "nifty500_sma_50": self.indicators.get("nifty500_sma_50"),
        }


def evaluate_stock(
    *,
    symbol: str,
    company: str | None,
    series: BarSeries | None,
    strategy: StrategyDefinitionConfig,
    start_date: date,
    end_date: date,
    benchmark: BarSeries | None = None,
) -> StrategyEvaluationResult:
    """Evaluate `strategy` at end_date using only data available on that bar."""
    side = strategy.position.side
    if series is None or len(series) == 0:
        return _empty(symbol, company, STATUS_INSUFFICIENT_DATA, "No historical bars", side)
    if any(not _valid_price(series.close[i], series.high[i], series.low[i], series.open[i]) for i in range(len(series)) if series.dates[i] >= start_date):
        # Invalid prices inside the window are counted per-bar; a fully invalid series fails validation.
        valid_any = any(_valid_price(series.close[i], series.high[i], series.low[i], series.open[i]) for i in range(len(series)))
        if not valid_any:
            return _empty(symbol, company, STATUS_VALIDATION_FAILED, "Invalid prices", side)

    entry_i = series.index_on_or_after(start_date)
    exit_i = series.index_on_or_before(end_date)
    if entry_i is None or exit_i is None or exit_i < entry_i:
        return _empty(symbol, company, STATUS_INSUFFICIENT_DATA, "Window is not covered by available bars", side)

    eval_i = exit_i
    entry_price = _positive(series.close[entry_i])
    exit_price = _positive(series.close[eval_i])
    if entry_price is None or exit_price is None:
        return _empty(symbol, company, STATUS_VALIDATION_FAILED, "Entry or exit price is missing or non-positive", side)

    returns = simple_return(entry_price, exit_price, strategy.position)
    try:
        filt = evaluate_tree(strategy.root, series, eval_i, benchmark=benchmark)
    except Exception as exc:  # isolation: one stock must not stop the universe
        return _empty(symbol, company, STATUS_ERROR, str(exc), side, returns)

    if filt.unevaluable or filt.passed is None:
        result = _empty(symbol, company, STATUS_INSUFFICIENT_DATA, "Insufficient history for indicators", side, returns)
        result.candle_count = len(series)
        result.filter_details = [leaf.to_dict() for leaf in filt.leaves]
        result.indicators = _scan_snapshot(series, eval_i, strategy, benchmark)
        result.evaluation_date = series.dates[eval_i]
        result.entry_date = series.dates[entry_i]
        result.exit_date = series.dates[eval_i]
        return result

    signal, failure = classify_signal(filt, strategy.signal)
    passed, failed = _split_leaves(filt.leaves)
    indicators = _scan_snapshot(series, eval_i, strategy, benchmark)
    return StrategyEvaluationResult(
        symbol=symbol,
        company=company,
        status=STATUS_OK,
        signal=signal,
        entry_price=returns.entry_price,
        exit_price=returns.exit_price,
        return_pct=returns.return_pct,
        return_bucket=returns.bucket,
        return_formula=returns.formula,
        position_side=side,
        evaluation_date=series.dates[eval_i],
        entry_date=series.dates[entry_i],
        exit_date=series.dates[eval_i],
        passed_filters=passed,
        failed_filters=failed,
        filter_details=[leaf.to_dict() for leaf in filt.leaves],
        indicators=indicators,
        primary_failure_reason=None if signal == BUY else failure,
        candle_count=len(series),
    )


def _scan_snapshot(
    series: BarSeries,
    eval_i: int,
    strategy: StrategyDefinitionConfig,
    benchmark: BarSeries | None,
) -> dict[str, Any]:
    """Last-bar values TradingView Pine Screener prints: close, prior 252-high, volume SMA, Nifty."""
    extras = list(collect_series_keys(strategy))
    extras.append(Operand(kind="series", name="HIGH", period=252))
    snap: dict[str, Any] = series.snapshot(eval_i, extras)
    if 0 <= eval_i < len(series.dates):
        snap["evaluation_date"] = series.dates[eval_i].isoformat()
    if benchmark is None or len(benchmark) == 0 or eval_i < 0 or eval_i >= len(series.dates):
        return snap
    bt = benchmark.index_on_or_before(series.dates[eval_i])
    if bt is None:
        return snap
    snap["nifty500_close"] = _positive(benchmark.close[bt] if bt < len(benchmark.close) else None)
    snap["nifty500_sma_50"] = benchmark.value_at(Operand(kind="series", name="SMA", period=50), bt)
    return snap


def _split_leaves(leaves: list[LeafEvaluation]) -> tuple[list[str], list[str]]:
    passed = [leaf.label for leaf in leaves if leaf.passed is True]
    failed = [leaf.label for leaf in leaves if leaf.passed is False]
    return passed, failed


def _valid_price(close: float | None, high: float | None, low: float | None, open_px: float | None) -> bool:
    for px in (close, high, low, open_px):
        if px is None:
            return False
        try:
            n = float(px)
        except (TypeError, ValueError):
            return False
        if n <= 0 or n != n:  # NaN
            return False
    return True


def _positive(value: float | None) -> float | None:
    try:
        n = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if n != n or n <= 0:
        return None
    return n


def _empty(
    symbol: str,
    company: str | None,
    status: str,
    detail: str,
    side: str,
    returns: ReturnBreakdown | None = None,
) -> StrategyEvaluationResult:
    return StrategyEvaluationResult(
        symbol=symbol,
        company=company,
        status=status,
        signal=None if status != STATUS_OK else REJECT,
        entry_price=returns.entry_price if returns else None,
        exit_price=returns.exit_price if returns else None,
        return_pct=returns.return_pct if returns else None,
        return_bucket=returns.bucket if returns else None,
        return_formula=returns.formula if returns else None,
        position_side=side,
        evaluation_date=None,
        entry_date=None,
        exit_date=None,
        passed_filters=[],
        failed_filters=[],
        filter_details=[],
        indicators={},
        primary_failure_reason=detail,
        error_detail=detail,
        candle_count=0,
    )
