"""LeanBacktestEngine: The official QuantConnect LEAN event-driven backtesting execution engine."""

from __future__ import annotations

import asyncio
from datetime import datetime
import logging
import time
from typing import Any, Callable
import uuid

from ..adapters.algorithm_adapter import LeanAlgorithmAdapter
from ..adapters.data_adapter import LeanDataAdapter
from ..adapters.result_parser import LeanResultParser
from ..models import (
    LeanBacktestRequest,
    LeanBacktestResult,
    LeanJobStatus,
)
from .base import BacktestEngine
from .execution_models import NextBarOpenExecutionModel
from .fee_models import ConstantFeeModel, NseFeeModel
from .qc_algorithm import QCAlgorithm, Slice, Symbol, TradeBar
from .slippage_models import ConstantSlippageModel

logger = logging.getLogger("app.lean.engine")


class LeanBacktestEngine(BacktestEngine):
    """Event-driven QuantConnect LEAN Core Backtesting Engine."""

    @property
    def engine_name(self) -> str:
        return "LEAN"

    async def run_backtest(
        self,
        request: LeanBacktestRequest,
        data_map: dict[str, list[TradeBar]],
        benchmark_bars: list[TradeBar] | None = None,
        progress_callback: Callable[[int, str], Any] | None = None,
    ) -> LeanBacktestResult:
        """Execute event-driven LEAN backtest cycle."""
        t_start = time.perf_counter()
        job_id = f"LEAN-{uuid.uuid4().hex[:12].upper()}"

        logger.info(
            "LEAN_ENGINE_START | job_id=%s | strategy=%s | symbols=%d | start=%s | end=%s",
            job_id,
            request.strategy_id,
            len(data_map),
            request.start_date,
            request.end_date,
        )

        if progress_callback:
            progress_callback(5, "Initializing LEAN Algorithm...")

        # 1. Instantiate Algorithm & Models
        algo: QCAlgorithm = LeanAlgorithmAdapter.create_algorithm(request)
        algo.commission_rate = request.commission_rate
        algo.slippage_rate = request.slippage_rate
        algo.debug_mode = request.debug_mode
        algo.initialize()

        execution_model = NextBarOpenExecutionModel()
        fee_model = NseFeeModel(brokerage_rate=request.commission_rate) if request.data_source == "NSE" else ConstantFeeModel(request.commission_rate)
        slippage_model = ConstantSlippageModel(percent=request.slippage_rate)

        # 2. Synchronize multi-symbol timeline into Slices
        if progress_callback:
            progress_callback(15, "Synchronizing Time Slices...")

        timeline_slices = LeanDataAdapter.synchronize_slices(data_map, benchmark_bars)
        total_slices = len(timeline_slices)

        if total_slices == 0:
            logger.warning("LEAN_ENGINE_NO_DATA | job_id=%s", job_id)
            return LeanResultParser.parse(
                job_id=job_id,
                strategy_id=request.strategy_id,
                strategy_name=request.strategy_name,
                start_date_str=request.start_date.isoformat(),
                end_date_str=request.end_date.isoformat(),
                initial_capital=request.initial_capital,
                equity_records=[],
                closed_trades=[],
                position_snapshots=[],
                symbols=list(data_map.keys()),
                trading_days_count=0,
                execution_model_name="LEAN NextBarOpen",
                data_source=request.data_source,
            )

        # Filter timeline to active backtest window (warmup bars feed indicators, but equity tracking starts on start_date)
        equity_records: list[dict[str, Any]] = []
        position_snapshots: list[dict[str, Any]] = []
        trading_days_count = 0
        backtest_start_dt = datetime.combine(request.start_date, datetime.min.time())

        # 3. Main Event Loop
        last_progress_pct = 15
        for idx, (t, bars) in enumerate(timeline_slices):
            current_slice = Slice(time=t, bars=bars)

            # Step A: Execute pending orders generated at previous bar close
            execution_model.execute_pending_orders(
                algorithm=algo,
                current_slice=current_slice,
                fee_model=fee_model,
                slippage_model=slippage_model,
            )

            # Step B: Update current security prices
            for sym, bar in bars.items():
                if sym in algo.securities:
                    sec = algo.securities[sym]
                    sec.open = bar.open
                    sec.high = bar.high
                    sec.low = bar.low
                    sec.close = bar.close
                    sec.volume = bar.volume
                    sec.time = bar.time

            # Step C: Trigger algorithm OnData
            algo.on_data(current_slice)

            # Step D: Equity and Position Accounting (only within user date range)
            if t >= backtest_start_dt:
                trading_days_count += 1
                curr_portfolio_val = algo.portfolio.total_portfolio_value()
                curr_cash = algo.portfolio.cash
                curr_invested = algo.portfolio.invested_capital()

                d_str = t.strftime("%Y-%m-%d")
                equity_records.append({
                    "date": d_str,
                    "equity": curr_portfolio_val,
                    "cash": curr_cash,
                    "invested": curr_invested,
                })

                for sym, sec in algo.securities.items():
                    if sym != algo.benchmark_symbol and sec.holdings.invested:
                        position_snapshots.append({
                            "date": d_str,
                            "symbol": sym.value,
                            "quantity": sec.holdings.quantity,
                            "average_price": sec.holdings.average_price,
                            "market_value": sec.holdings.quantity * sec.price,
                            "unrealized_pnl": sec.holdings.unrealized_pnl(sec.price),
                            "realized_pnl": algo.portfolio.realized_pnl,
                        })

            # Progress update
            progress_pct = int(15 + (idx / total_slices * 80))
            if progress_callback and progress_pct > last_progress_pct + 10:
                last_progress_pct = progress_pct
                progress_callback(progress_pct, f"Evaluating Bar {idx+1}/{total_slices}...")
                await asyncio.sleep(0)  # Yield to event loop

        # 4. Finalize Algorithm
        if progress_callback:
            progress_callback(95, "Compiling Performance Metrics...")

        algo.on_end_of_algorithm()
        if algo._pending_orders and timeline_slices:
            last_t, last_bars = timeline_slices[-1]
            last_slice = Slice(time=last_t, bars=last_bars)
            execution_model.execute_pending_orders(
                algorithm=algo,
                current_slice=last_slice,
                fee_model=fee_model,
                slippage_model=slippage_model,
            )

        # Extract debug trace
        debug_trace = getattr(algo, "debug_trace_records", None)

        t_elapsed = time.perf_counter() - t_start

        # 5. Parse and Normalize Output
        result = LeanResultParser.parse(
            job_id=job_id,
            strategy_id=request.strategy_id,
            strategy_name=request.strategy_name,
            start_date_str=request.start_date.isoformat(),
            end_date_str=request.end_date.isoformat(),
            initial_capital=request.initial_capital,
            equity_records=equity_records,
            closed_trades=algo._closed_trades,
            position_snapshots=position_snapshots,
            symbols=list(data_map.keys()),
            trading_days_count=trading_days_count,
            execution_model_name="LEAN NextBarOpen",
            data_source=request.data_source,
            debug_trace=debug_trace,
        )

        result.runtime_metrics = {
            "execution_time_seconds": round(t_elapsed, 3),
            "bars_processed": total_slices,
            "symbols_evaluated": len(data_map),
            "trades_generated": len(algo._closed_trades),
            "engine": "LEAN",
        }

        if progress_callback:
            progress_callback(100, "Completed")

        logger.info(
            "LEAN_ENGINE_COMPLETE | job_id=%s | trades=%d | final_equity=%.2f | elapsed=%.3fs",
            job_id,
            len(result.trades),
            result.summary.final_equity,
            t_elapsed,
        )
        return result
