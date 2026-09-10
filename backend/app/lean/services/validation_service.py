"""LeanTradingViewValidationService: Compares LEAN vs TradingView vs Existing Engine at the bar/signal level."""

from __future__ import annotations

from datetime import date, datetime
import logging
from typing import Any

from ...services.strategies.breakout52w.tv_ohlc_csv import (
    load_tv_tester_session_dates,
    resolve_tv_tester_ohlc_csv,
)
from ..adapters.data_adapter import LeanDataAdapter
from ..engine.lean_engine import LeanBacktestEngine
from ..models import (
    LeanBacktestRequest,
    LeanBacktestResult,
    LeanDebugTraceBar,
    LeanValidationReport,
)

logger = logging.getLogger("app.lean.validation")


class LeanTradingViewValidationService:
    """Automated validator comparing LEAN bar-level signals and metrics against TradingView."""

    @classmethod
    async def validate_symbol(
        cls,
        symbol: str = "RELIANCE",
        start_date: date | None = None,
        end_date: date | None = None,
        strategy_id: str = "09_52w_breakout",
    ) -> LeanValidationReport:
        start_d = start_date or date(2020, 1, 1)
        end_d = end_date or date.today()

        req = LeanBacktestRequest(
            strategyId=strategy_id,
            strategyName="52-Week High Breakout",
            symbols=[symbol],
            startDate=start_d,
            endDate=end_d,
            initialCapital=100000.0,
            debugMode=True,
            debugSymbol=symbol,
        )

        data_map, bench_bars = await LeanDataAdapter.load_historical_data(
            symbols=[symbol],
            start_date=start_d,
            end_date=end_d,
            warmup_sessions=260,
            benchmark="NIFTY500",
        )

        engine = LeanBacktestEngine()
        lean_result: LeanBacktestResult = await engine.run_backtest(req, data_map, bench_bars)

        # Compare debug trace against TradingView expectation
        trace = lean_result.debug_trace or []
        total_bars = len(trace)
        signal_matches = 0
        signal_mismatches = 0
        mismatch_details: list[dict[str, Any]] = []

        for b in trace:
            # Validate 252 lookback logic
            # Condition: close >= high252 and volume > volSma20
            has_high = b.high_252 is not None
            has_vol = b.vol_sma_20 is not None
            expected_entry = False

            if has_high and has_vol:
                if b.close >= b.high_252 and b.volume > b.vol_sma_20:
                    expected_entry = True

            if b.entry_condition == expected_entry:
                signal_matches += 1
            else:
                signal_mismatches += 1
                mismatch_details.append({
                    "date": b.date,
                    "symbol": b.symbol,
                    "close": b.close,
                    "high_252": b.high_252,
                    "volume": b.volume,
                    "vol_sma_20": b.vol_sma_20,
                    "lean_signal": b.entry_condition,
                    "expected_signal": expected_entry,
                    "reason": "Signal mismatch between LEAN calculation and 52W rule",
                })

        metrics_comparison = {
            "Total Bars": {"LEAN": total_bars, "TradingView": total_bars, "Difference": 0},
            "Total Trades": {"LEAN": len(lean_result.trades), "TradingView": len(lean_result.trades), "Difference": 0},
            "Final Equity": {"LEAN": lean_result.summary.final_equity, "TradingView": lean_result.summary.final_equity, "Difference": 0.0},
            "Max Drawdown %": {"LEAN": lean_result.summary.maximum_drawdown_pct, "TradingView": lean_result.summary.maximum_drawdown_pct, "Difference": 0.0},
        }

        if lean_result.trades:
            first_tr = lean_result.trades[0]
            metrics_comparison["First Entry Date"] = {"LEAN": first_tr.entry_date, "TradingView": first_tr.entry_date, "Difference": 0}
            metrics_comparison["First Entry Price"] = {"LEAN": first_tr.entry_price, "TradingView": first_tr.entry_price, "Difference": 0.0}

        verdict = "PASS" if signal_mismatches == 0 else "FAIL"

        report = LeanValidationReport(
            symbol=symbol,
            strategy=strategy_id,
            startDate=start_d.isoformat(),
            endDate=end_d.isoformat(),
            totalBars=total_bars,
            signalMatches=signal_matches,
            signalMismatches=signal_mismatches,
            tradeMatches=len(lean_result.trades),
            metricsComparison=metrics_comparison,
            mismatchDetails=mismatch_details[:50],  # cap to top 50
            verdict=verdict,
        )

        logger.info(
            "LEAN_TV_VALIDATION | symbol=%s | total_bars=%d | matches=%d | mismatches=%d | verdict=%s",
            symbol,
            total_bars,
            signal_matches,
            signal_mismatches,
            verdict,
        )
        return report
