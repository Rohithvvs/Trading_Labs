"""ExistingBacktestEngine: Wraps Trading Labs legacy/existing backtest engine."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable
import uuid

from ...schemas import AnalysisMode, OHLCVPoint
from ...services.backtest_service import BacktestService
from ..adapters.result_parser import LeanResultParser
from ..models import (
    LeanBacktestRequest,
    LeanBacktestResult,
    LeanJobStatus,
)
from .base import BacktestEngine
from .qc_algorithm import TradeBar


class ExistingBacktestEngine(BacktestEngine):
    """Wraps existing BacktestService for dual-engine comparison."""

    @property
    def engine_name(self) -> str:
        return "EXISTING"

    async def run_backtest(
        self,
        request: LeanBacktestRequest,
        data_map: dict[str, list[TradeBar]],
        benchmark_bars: list[TradeBar] | None = None,
        progress_callback: Callable[[int, str], Any] | None = None,
    ) -> LeanBacktestResult:
        t_start = time.perf_counter()
        job_id = f"EXISTING-{uuid.uuid4().hex[:12].upper()}"

        if progress_callback:
            progress_callback(10, "Running Existing Engine Backtest...")

        svc = BacktestService()
        all_trades: list[dict[str, Any]] = []
        equity_records: list[dict[str, Any]] = []
        position_snapshots: list[dict[str, Any]] = []
        trading_days = 0

        # Execute for each symbol
        for sym_str, bars in data_map.items():
            ohlcv_points = [
                OHLCVPoint(
                    timestamp=b.time,
                    open=b.open,
                    high=b.high,
                    low=b.low,
                    close=b.close,
                    volume=b.volume,
                )
                for b in bars
            ]

            res = svc.run(
                symbol=sym_str,
                mode=AnalysisMode.swing,
                candles=ohlcv_points,
                cost_scenario="BASE_COST",
                position_sizing_pct=request.position_sizing_value,
                execution_model="REALISTIC",
            )

            # Convert trades
            for tr in res.trades:
                all_trades.append({
                    "trade_id": tr.get("trade_id", len(all_trades) + 1),
                    "symbol": sym_str,
                    "entry_date": tr.get("entry_date"),
                    "entry_price": tr.get("entry_price", 0.0),
                    "exit_date": tr.get("exit_date"),
                    "exit_price": tr.get("exit_price"),
                    "quantity": 100,
                    "direction": "LONG",
                    "gross_pnl": 0.0,
                    "commission": 0.0,
                    "slippage": 0.0,
                    "net_pnl": tr.get("pnl_percent", 0.0) * request.initial_capital / 100.0,
                    "return_pct": tr.get("pnl_percent", 0.0),
                    "holding_period": 1,
                    "entry_reason": "Existing Engine Signal",
                    "exit_reason": tr.get("exit_reason", "Exit Signal"),
                    "is_open": False,
                })

            if res.equity_curve and not equity_records:
                for pt in res.equity_curve:
                    equity_records.append({
                        "date": pt.get("label"),
                        "equity": pt.get("equity", request.initial_capital),
                        "cash": pt.get("equity", request.initial_capital),
                        "invested": 0.0,
                    })
                trading_days = len(bars)

        t_elapsed = time.perf_counter() - t_start

        if progress_callback:
            progress_callback(100, "Completed")

        result = LeanResultParser.parse(
            job_id=job_id,
            strategy_id=request.strategy_id,
            strategy_name=request.strategy_name,
            start_date_str=request.start_date.isoformat(),
            end_date_str=request.end_date.isoformat(),
            initial_capital=request.initial_capital,
            equity_records=equity_records,
            closed_trades=all_trades,
            position_snapshots=position_snapshots,
            symbols=list(data_map.keys()),
            trading_days_count=trading_days,
            execution_model_name="Existing Backtest Engine",
            data_source=request.data_source,
        )

        result.engine = "EXISTING"
        result.runtime_metrics = {
            "execution_time_seconds": round(t_elapsed, 3),
            "engine": "EXISTING",
        }
        return result
