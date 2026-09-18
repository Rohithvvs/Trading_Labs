"""LeanTradingViewValidationService: Compares LEAN vs TradingView vs Existing Engine at the bar/signal level."""

from __future__ import annotations

from datetime import date, datetime
import logging
from typing import Any

from ...services.strategies.breakout52w.tv_ohlc_csv import (
    default_tv_trades_csv_path,
    is_tv_reference_symbol,
    parse_tv_trades_dates,
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

        tv_path = default_tv_trades_csv_path()
        if not is_tv_reference_symbol(symbol) or not tv_path.is_file():
            return LeanValidationReport(
                symbol=symbol,
                strategy=strategy_id,
                startDate=start_d.isoformat(),
                endDate=end_d.isoformat(),
                totalBars=len(lean_result.debug_trace or []),
                signalMatches=0,
                signalMismatches=0,
                tradeMatches=0,
                metricsComparison={
                    "Total Trades": {
                        "LEAN": len(lean_result.trades),
                        "TradingView": None,
                        "Difference": None,
                    }
                },
                mismatchDetails=[
                    {
                        "reason": (
                            "No stored TradingView tape for this symbol. "
                            "Validation only compares against hermes-research Strategy_001 trades.csv (WELCORP)."
                        )
                    }
                ],
                verdict="INCONCLUSIVE",
            )

        tv_entry_dates, first_tv_entry = parse_tv_trades_dates(tv_path)
        lean_entry_dates: set[date] = set()
        for tr in lean_result.trades:
            raw = str(tr.entry_date or "")[:10]
            try:
                lean_entry_dates.add(date.fromisoformat(raw))
            except ValueError:
                continue

        windowed_tv = {d for d in tv_entry_dates if start_d <= d <= end_d}
        matches = lean_entry_dates & windowed_tv
        extra_lean = sorted(lean_entry_dates - windowed_tv)
        missing_tv = sorted(windowed_tv - lean_entry_dates)
        mismatch_details: list[dict[str, Any]] = []
        for d in extra_lean[:25]:
            mismatch_details.append({"date": d.isoformat(), "reason": "LEAN entry not in TradingView tape"})
        for d in missing_tv[:25]:
            mismatch_details.append({"date": d.isoformat(), "reason": "TradingView entry missing from LEAN"})

        metrics_comparison = {
            "Total Trades": {
                "LEAN": len(lean_result.trades),
                "TradingView": len(windowed_tv),
                "Difference": len(lean_result.trades) - len(windowed_tv),
            },
            "Shared entry dates": {
                "LEAN": len(matches),
                "TradingView": len(windowed_tv),
                "Difference": len(windowed_tv) - len(matches),
            },
            "First TV entry": {
                "LEAN": None,
                "TradingView": first_tv_entry.isoformat() if first_tv_entry else None,
                "Difference": None,
            },
        }
        verdict = "PASS" if not extra_lean and not missing_tv else "FAIL"

        report = LeanValidationReport(
            symbol=symbol,
            strategy=strategy_id,
            startDate=start_d.isoformat(),
            endDate=end_d.isoformat(),
            totalBars=len(lean_result.debug_trace or []),
            signalMatches=len(matches),
            signalMismatches=len(extra_lean) + len(missing_tv),
            tradeMatches=len(matches),
            metricsComparison=metrics_comparison,
            mismatchDetails=mismatch_details,
            verdict=verdict,
        )

        logger.info(
            "LEAN_TV_VALIDATION | symbol=%s | total_bars=%d | matches=%d | mismatches=%d | verdict=%s",
            symbol,
            report.total_bars,
            report.signal_matches,
            report.signal_mismatches,
            verdict,
        )
        return report
