"""Pre-recommendation 3-year backtest integration for RE-001 / RE-002.

Reuses existing BacktestService / BacktestAgent mathematics and the production
raw backtest score formula from RecommendationService.

Does NOT implement RE-001/RE-002 indicator strategies inside the simulator —
see strategy_fidelity note on each envelope (known limitation).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from ..config.settings import settings
from ..schemas import AnalysisMode, BacktestResult, OHLCVPoint

logger = logging.getLogger("app.recommendation_backtest")

MIN_TRADES_FOR_SCORE = 5
THREE_YEAR_CALENDAR_DAYS = 3 * 365  # matches BacktestAgent.run_async window
DEFAULT_TIMEOUT_S = 45.0
DEFAULT_CONCURRENCY = 4

BacktestStatus = Literal[
    "SUCCESS",
    "BACKTEST_FAILED",
    "BACKTEST_INSUFFICIENT_DATA",
    "BACKTEST_INSUFFICIENT_TRADES",
    "BACKTEST_TIMEOUT",
    "BACKTEST_DATA_UNAVAILABLE",
    "NO_TECHNICALLY_QUALIFIED_STOCKS",
    "SKIPPED_NOT_QUALIFIED",
    "SKIPPED_DUPLICATE",
    "SKIPPED_BULK_LAB_SCAN",
]

# Process-local dedup of in-flight / completed recommendation backtests
_result_cache: dict[str, "RecommendationBacktestEnvelope"] = {}
_inflight: dict[str, asyncio.Future] = {}
_cache_lock = asyncio.Lock()


@dataclass
class RecommendationBacktestEnvelope:
    """Machine-readable wrapper around a BacktestResult for recommendation generation."""

    symbol: str
    engine_id: str
    status: str
    backtest_start: str | None = None
    backtest_end: str | None = None
    trade_count: int = 0
    total_return: float | None = None
    win_rate: float | None = None
    profit_factor: float | None = None
    max_drawdown: float | None = None
    cagr: float | None = None
    average_trade: float | None = None
    strategy_name: str | None = None
    strategy_configuration: dict[str, Any] = field(default_factory=dict)
    backtest_score: float | None = None  # production raw formula; None if not eligible
    score_eligible: bool = False
    execution_timestamp: str | None = None
    duration_ms: float | None = None
    message: str | None = None
    strategy_fidelity: str = (
        "generic_sma_rsi_macd — existing BacktestService; not engine-native RE entry/exit"
    )
    cache_key: str | None = None
    reused: bool = False
    result: BacktestResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "engine": self.engine_id,
            "engine_id": self.engine_id,
            "backtest_period": {
                "start": self.backtest_start,
                "end": self.backtest_end,
            },
            "backtest_status": self.status,
            "status": self.status,
            "trade_count": self.trade_count,
            "total_return": self.total_return,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "maximum_drawdown": self.max_drawdown,
            "max_drawdown": self.max_drawdown,
            "cagr": self.cagr,
            "average_trade": self.average_trade,
            "strategy_configuration": self.strategy_configuration,
            "strategy_name": self.strategy_name,
            "backtest_score": self.backtest_score,
            "score_eligible": self.score_eligible,
            "execution_timestamp": self.execution_timestamp,
            "duration_ms": self.duration_ms,
            "message": self.message,
            "strategy_fidelity": self.strategy_fidelity,
            "reused": self.reused,
            "cache_key": self.cache_key,
        }

    def as_backtest_list(self) -> list[BacktestResult]:
        if self.result is not None and self.status in {
            "SUCCESS",
            "BACKTEST_INSUFFICIENT_TRADES",
        }:
            return [self.result]
        return []


def three_year_window(as_of: date | None = None) -> tuple[date, date]:
    """3-year calendar window matching BacktestAgent (today - 3*365 → as_of)."""
    end = as_of or date.today()
    start = end - timedelta(days=THREE_YEAR_CALENDAR_DAYS)
    return start, end


def compute_raw_backtest_score(result: BacktestResult | None) -> tuple[float | None, bool]:
    """Production RecommendationService raw_backtest formula.

    raw = clamp(total_return * 4, -20, 100) when trade_count >= 5; else ineligible.
    """
    if result is None:
        return None, False
    try:
        trades = int(getattr(result, "trade_count", 0) or 0)
    except (TypeError, ValueError):
        return None, False
    if trades < MIN_TRADES_FOR_SCORE:
        return None, False
    try:
        tr = float(getattr(result, "total_return", 0.0) or 0.0)
    except (TypeError, ValueError):
        return None, False
    if math.isnan(tr) or math.isinf(tr):
        return None, False
    raw = min(max(tr * 4.0, -20.0), 100.0)
    return round(raw, 2), True


def cache_key(
    *,
    symbol: str,
    engine_id: str,
    mode: str,
    start: date,
    end: date,
    strategy_name: str,
    execution_model: str,
) -> str:
    raw = "|".join(
        [
            symbol.upper(),
            engine_id.upper(),
            mode,
            start.isoformat(),
            end.isoformat(),
            strategy_name,
            execution_model,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _log(event: str, **fields: Any) -> None:
    parts = " | ".join(f"{k}={v}" for k, v in fields.items() if v is not None)
    logger.info("%s | %s", event, parts)


def envelope_skipped_bulk_lab(
    symbol: str,
    engine_id: str,
    reason: str = "bulk_lab_scan_latency",
) -> RecommendationBacktestEnvelope:
    """Skip 3y backtest on the full stage-universe lab path (scanner residual budget).

    Production Top-N still runs full recommendation backtests. Independent lab
    engines evaluate technical gates + decision math without a 20–45s backtest
    per symbol (which otherwise exhausts the 600s scan budget at ~700 symbols).
    """
    env = RecommendationBacktestEnvelope(
        symbol=symbol,
        engine_id=engine_id,
        status="SKIPPED_BULK_LAB_SCAN",
        message=reason,
        execution_timestamp=datetime.now(timezone.utc).isoformat(),
    )
    _log(
        "RECOMMENDATION_BACKTEST_SKIPPED",
        engine=engine_id,
        symbol=symbol,
        status=env.status,
        reason=reason,
    )
    return env


def envelope_not_qualified(symbol: str, engine_id: str, reason: str = "technical_gates_failed") -> RecommendationBacktestEnvelope:
    start, end = three_year_window()
    env = RecommendationBacktestEnvelope(
        symbol=symbol,
        engine_id=engine_id,
        status="SKIPPED_NOT_QUALIFIED",
        backtest_start=start.isoformat(),
        backtest_end=end.isoformat(),
        message=f"Not technically qualified; backtest skipped ({reason}).",
        execution_timestamp=datetime.now(timezone.utc).isoformat(),
    )
    _log(
        "RECOMMENDATION_BACKTEST_SKIPPED",
        engine=engine_id,
        symbol=symbol,
        status=env.status,
        reason=reason,
    )
    return env


def envelope_no_qualified_cohort(engine_id: str = "RE-LAB") -> RecommendationBacktestEnvelope:
    start, end = three_year_window()
    return RecommendationBacktestEnvelope(
        symbol="*",
        engine_id=engine_id,
        status="NO_TECHNICALLY_QUALIFIED_STOCKS",
        backtest_start=start.isoformat(),
        backtest_end=end.isoformat(),
        message="No stocks qualified for backtesting.",
        execution_timestamp=datetime.now(timezone.utc).isoformat(),
    )


def classify_result(
    result: BacktestResult | None,
    *,
    symbol: str,
    engine_id: str,
    start: date,
    end: date,
    duration_ms: float | None = None,
    reused: bool = False,
    cache_key_val: str | None = None,
) -> RecommendationBacktestEnvelope:
    ts = datetime.now(timezone.utc).isoformat()
    if result is None:
        return RecommendationBacktestEnvelope(
            symbol=symbol,
            engine_id=engine_id,
            status="BACKTEST_FAILED",
            backtest_start=start.isoformat(),
            backtest_end=end.isoformat(),
            message="Backtest returned no result.",
            execution_timestamp=ts,
            duration_ms=duration_ms,
            reused=reused,
            cache_key=cache_key_val,
        )

    trades = int(getattr(result, "trade_count", 0) or 0)
    verdict = str(getattr(result, "verdict", "") or "").lower()
    strategy = str(getattr(result, "strategy_name", "") or "")

    score, eligible = compute_raw_backtest_score(result)
    avg_trade = None
    try:
        if trades > 0 and getattr(result, "total_return", None) is not None:
            avg_trade = round(float(result.total_return) / trades, 4)
    except Exception:
        avg_trade = None

    # Insufficient history / empty
    if trades == 0 and verdict in {"insufficient", "failed"} and not getattr(result, "equity_curve", None):
        status: str = "BACKTEST_INSUFFICIENT_DATA"
        msg = "Insufficient historical data for backtest."
    elif trades == 0 and len(getattr(result, "equity_curve", None) or []) <= 1:
        status = "BACKTEST_INSUFFICIENT_DATA"
        msg = "Insufficient historical data for backtest."
    elif trades < MIN_TRADES_FOR_SCORE:
        status = "BACKTEST_INSUFFICIENT_TRADES"
        msg = (
            f"Insufficient historical trades for reliable backtest scoring "
            f"(trade_count={trades}, required>={MIN_TRADES_FOR_SCORE})."
        )
    elif strategy == "error_fallback" or verdict == "failed":
        status = "BACKTEST_FAILED"
        msg = "Backtest execution failed."
    else:
        status = "SUCCESS"
        msg = "Backtest completed successfully."

    cfg = {
        "mode": str(getattr(result, "mode", AnalysisMode.swing)),
        "strategy_name": strategy,
        "execution_model": getattr(result, "feat008_execution_model", None),
        "cost_scenario": getattr(result, "cost_scenario", None),
        "position_sizing_pct": getattr(result, "position_sizing_pct", None),
        "window_days": THREE_YEAR_CALENDAR_DAYS,
        "min_trades_for_score": MIN_TRADES_FOR_SCORE,
    }

    return RecommendationBacktestEnvelope(
        symbol=symbol,
        engine_id=engine_id,
        status=status,
        backtest_start=start.isoformat(),
        backtest_end=end.isoformat(),
        trade_count=trades,
        total_return=float(result.total_return) if result.total_return is not None else None,
        win_rate=float(result.win_rate) if result.win_rate is not None else None,
        profit_factor=float(result.profit_factor) if result.profit_factor is not None else None,
        max_drawdown=float(result.max_drawdown) if result.max_drawdown is not None else None,
        cagr=float(result.cagr) if result.cagr is not None else None,
        average_trade=avg_trade,
        strategy_name=strategy,
        strategy_configuration=cfg,
        backtest_score=score if eligible else None,
        score_eligible=eligible,
        execution_timestamp=ts,
        duration_ms=duration_ms,
        message=msg,
        cache_key=cache_key_val,
        reused=reused,
        result=result,
    )


def try_reuse_existing(
    existing: list[Any] | None,
    *,
    symbol: str,
    engine_id: str,
    start: date,
    end: date,
) -> RecommendationBacktestEnvelope | None:
    """Reuse a swing BacktestResult already produced in this analysis run."""
    if not existing:
        return None
    for bt in existing:
        mode = getattr(bt, "mode", None)
        mode_val = getattr(mode, "value", mode)
        if str(mode_val).lower() not in {"swing", "analysismode.swing"}:
            # Accept objects without mode as swing-like if they have trade_count
            if mode is not None:
                continue
        if getattr(bt, "strategy_name", None) == "error_fallback":
            continue
        if not hasattr(bt, "trade_count") and not isinstance(bt, dict):
            continue
        try:
            # Normalize dict → namespace-like access via SimpleNamespace if needed
            if isinstance(bt, dict):
                from types import SimpleNamespace

                bt_obj = SimpleNamespace(**bt)
                if "mode" not in bt:
                    bt_obj.mode = AnalysisMode.swing
            else:
                bt_obj = bt
            env = classify_result(
                bt_obj,  # type: ignore[arg-type]
                symbol=symbol,
                engine_id=engine_id,
                start=start,
                end=end,
                reused=True,
            )
            env.result = bt if isinstance(bt, BacktestResult) else None
            # Preserve original for as_backtest_list when already BacktestResult
            if isinstance(bt, BacktestResult):
                env.result = bt
            return env
        except Exception:
            continue
    return None


async def run_three_year_backtest(
    *,
    symbol: str,
    engine_id: str,
    candles: list[Any] | None = None,
    existing_backtests: list[Any] | None = None,
    mode: AnalysisMode = AnalysisMode.swing,
    timeout_s: float | None = None,
    allow_reuse: bool = True,
) -> RecommendationBacktestEnvelope:
    """Execute (or reuse) a 3-year backtest for recommendation generation."""
    start, end = three_year_window()
    timeout = float(timeout_s if timeout_s is not None else getattr(settings, "re001_timeout_ms", 3000) or 3000)
    # Backtests need more wall time than lab evaluate; floor at 20s, cap 120s
    timeout = max(20.0, min(120.0, timeout if timeout > 10 else DEFAULT_TIMEOUT_S))

    if not settings.feat008_enabled:
        exec_model = "LEGACY"
        use_realistic = False
        skip_missing = False
    else:
        exec_model = settings.feat008_execution_model
        use_realistic = settings.feat008_composite_uses_realistic
        skip_missing = settings.feat008_skip_on_missing_next_bar

    strategy_name = "sma_rsi_macd" if mode == AnalysisMode.swing else "ema_rsi_volume"
    key = cache_key(
        symbol=symbol,
        engine_id=engine_id,
        mode=mode.value if hasattr(mode, "value") else str(mode),
        start=start,
        end=end,
        strategy_name=strategy_name,
        execution_model=str(exec_model),
    )

    if allow_reuse:
        reused = try_reuse_existing(
            existing_backtests, symbol=symbol, engine_id=engine_id, start=start, end=end
        )
        if reused is not None:
            reused.cache_key = key
            reused.reused = True
            _log(
                "RECOMMENDATION_BACKTEST_COMPLETED",
                engine=engine_id,
                symbol=symbol,
                status=reused.status,
                trade_count=reused.trade_count,
                backtest_score=reused.backtest_score,
                reused=True,
            )
            return reused

    async with _cache_lock:
        if key in _result_cache:
            cached = _result_cache[key]
            cached.reused = True
            _log(
                "RECOMMENDATION_BACKTEST_COMPLETED",
                engine=engine_id,
                symbol=symbol,
                status=cached.status,
                reused=True,
            )
            return cached
        if key in _inflight:
            fut = _inflight[key]
        else:
            fut = asyncio.get_running_loop().create_future()
            _inflight[key] = fut
            fut = None  # signal we are the worker
        worker = fut is None
        wait_fut = _inflight[key]

    if not worker:
        try:
            env = await asyncio.wait_for(wait_fut, timeout=timeout)
            env.reused = True
            return env
        except Exception:
            return RecommendationBacktestEnvelope(
                symbol=symbol,
                engine_id=engine_id,
                status="BACKTEST_TIMEOUT",
                backtest_start=start.isoformat(),
                backtest_end=end.isoformat(),
                message="Timed out waiting for duplicate backtest.",
                execution_timestamp=datetime.now(timezone.utc).isoformat(),
                cache_key=key,
            )

    _log(
        "RECOMMENDATION_BACKTEST_STARTED",
        engine=engine_id,
        symbol=symbol,
        start=start.isoformat(),
        end=end.isoformat(),
    )
    t0 = time.perf_counter()
    try:
        from ..agents.backtest_agent import BacktestAgent

        agent = BacktestAgent()
        # Prefer OHLCVPoint list
        ohlcv: list[OHLCVPoint] = []
        for c in candles or []:
            try:
                if isinstance(c, OHLCVPoint):
                    ohlcv.append(c)
                else:
                    ohlcv.append(
                        OHLCVPoint(
                            timestamp=getattr(c, "timestamp", None) or c.get("timestamp"),  # type: ignore[union-attr]
                            open=float(getattr(c, "open", None) or c["open"]),  # type: ignore[index]
                            high=float(getattr(c, "high", None) or c["high"]),  # type: ignore[index]
                            low=float(getattr(c, "low", None) or c["low"]),  # type: ignore[index]
                            close=float(getattr(c, "close", None) or c["close"]),  # type: ignore[index]
                            volume=int(getattr(c, "volume", None) or c.get("volume") or 0),  # type: ignore[union-attr]
                        )
                    )
            except Exception:
                continue

        if not ohlcv:
            env = RecommendationBacktestEnvelope(
                symbol=symbol,
                engine_id=engine_id,
                status="BACKTEST_DATA_UNAVAILABLE",
                backtest_start=start.isoformat(),
                backtest_end=end.isoformat(),
                message="No OHLCV candles available for backtest.",
                execution_timestamp=datetime.now(timezone.utc).isoformat(),
                cache_key=key,
            )
            _log(
                "RECOMMENDATION_BACKTEST_FAILED",
                engine=engine_id,
                symbol=symbol,
                status=env.status,
            )
        else:
            result = await asyncio.wait_for(
                agent.run_async(
                    symbol,
                    mode,
                    ohlcv,
                    execution_model=exec_model,
                    composite_uses_realistic=use_realistic,
                    skip_on_missing_next_bar=skip_missing,
                    feat008_enabled=settings.feat008_enabled,
                ),
                timeout=timeout,
            )
            duration_ms = (time.perf_counter() - t0) * 1000.0
            env = classify_result(
                result,
                symbol=symbol,
                engine_id=engine_id,
                start=start,
                end=end,
                duration_ms=duration_ms,
                cache_key_val=key,
            )
            if env.status == "SUCCESS":
                _log(
                    "RECOMMENDATION_BACKTEST_COMPLETED",
                    engine=engine_id,
                    symbol=symbol,
                    status=env.status,
                    trade_count=env.trade_count,
                    backtest_score=env.backtest_score,
                    duration_ms=round(duration_ms, 1),
                )
            elif env.status == "BACKTEST_INSUFFICIENT_TRADES":
                _log(
                    "RECOMMENDATION_BACKTEST_INSUFFICIENT_TRADES",
                    engine=engine_id,
                    symbol=symbol,
                    trade_count=env.trade_count,
                )
            elif env.status == "BACKTEST_INSUFFICIENT_DATA":
                _log(
                    "RECOMMENDATION_BACKTEST_INSUFFICIENT_DATA",
                    engine=engine_id,
                    symbol=symbol,
                )
            else:
                _log(
                    "RECOMMENDATION_BACKTEST_FAILED",
                    engine=engine_id,
                    symbol=symbol,
                    status=env.status,
                )
    except asyncio.TimeoutError:
        env = RecommendationBacktestEnvelope(
            symbol=symbol,
            engine_id=engine_id,
            status="BACKTEST_TIMEOUT",
            backtest_start=start.isoformat(),
            backtest_end=end.isoformat(),
            message=f"Backtest timed out after {timeout:.1f}s.",
            execution_timestamp=datetime.now(timezone.utc).isoformat(),
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            cache_key=key,
        )
        _log(
            "RECOMMENDATION_BACKTEST_TIMEOUT",
            engine=engine_id,
            symbol=symbol,
            timeout_s=timeout,
        )
    except Exception as exc:
        env = RecommendationBacktestEnvelope(
            symbol=symbol,
            engine_id=engine_id,
            status="BACKTEST_FAILED",
            backtest_start=start.isoformat(),
            backtest_end=end.isoformat(),
            message=f"Backtest error: {exc}",
            execution_timestamp=datetime.now(timezone.utc).isoformat(),
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            cache_key=key,
        )
        _log(
            "RECOMMENDATION_BACKTEST_FAILED",
            engine=engine_id,
            symbol=symbol,
            err=str(exc),
        )

    async with _cache_lock:
        _result_cache[key] = env
        wait = _inflight.pop(key, None)
        if wait is not None and not wait.done():
            wait.set_result(env)
    return env


async def run_bounded_backtests(
    jobs: list[dict[str, Any]],
    *,
    concurrency: int = DEFAULT_CONCURRENCY,
    timeout_s: float | None = None,
) -> list[RecommendationBacktestEnvelope]:
    """Run multiple recommendation backtests with a semaphore bound."""
    if not jobs:
        return []
    sem = asyncio.Semaphore(max(1, min(int(concurrency), 16)))

    async def _one(job: dict[str, Any]) -> RecommendationBacktestEnvelope:
        async with sem:
            return await run_three_year_backtest(
                symbol=job["symbol"],
                engine_id=job.get("engine_id") or "RE-001",
                candles=job.get("candles"),
                existing_backtests=job.get("existing_backtests"),
                mode=job.get("mode") or AnalysisMode.swing,
                timeout_s=timeout_s,
                allow_reuse=job.get("allow_reuse", True),
            )

    return list(await asyncio.gather(*(_one(j) for j in jobs), return_exceptions=False))


def clear_cache() -> None:
    """Test helper."""
    _result_cache.clear()
    _inflight.clear()
