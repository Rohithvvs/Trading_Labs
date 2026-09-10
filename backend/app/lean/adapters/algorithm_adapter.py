"""LeanAlgorithmAdapter: Instantiates the appropriate QCAlgorithm for a strategy request."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ...services.strategy_tester.presets import preset_by_id
from ...services.strategy_tester.schema import parse_strategy_config
from ..engine.qc_algorithm import QCAlgorithm
from ..models import LeanBacktestRequest
from ..strategies.breakout52w_algorithm import Breakout52wLeanAlgorithm
from ..strategies.dynamic_rule_algorithm import DynamicRuleLeanAlgorithm
from ..strategies.ltm_algorithm import LongTermMomentumLeanAlgorithm
from ..strategies.momentum_pulse_algorithm import MomentumPulseLeanAlgorithm
from ..strategies.rsi_oversold_algorithm import RsiOversoldLeanAlgorithm
from ..strategies.sma_crossover_algorithm import SmaCrossoverLeanAlgorithm


class LeanAlgorithmAdapter:
    """Factory and adapter for LEAN QCAlgorithm strategy instances."""

    @classmethod
    def create_algorithm(cls, request: LeanBacktestRequest) -> QCAlgorithm:
        strat_id = str(request.strategy_id).strip().lower()
        start_dt = datetime.combine(request.start_date, datetime.min.time())
        end_dt = datetime.combine(request.end_date, datetime.max.time())
        alloc_pct = (request.position_sizing_value / 100.0) if request.position_sizing_value > 0 else (1.0 / max(1, request.max_positions))

        if strat_id in {"09_52w_breakout", "52w_breakout", "breakout52w", "09"}:
            atr_mult = float(request.parameters.get("atr_multiplier", 3.0))
            return Breakout52wLeanAlgorithm(
                symbols=request.symbols,
                start_date=start_dt,
                end_date=end_dt,
                initial_cash=request.initial_capital,
                max_positions=request.max_positions,
                allocation_pct=alloc_pct,
                atr_multiplier=atr_mult,
                benchmark_ticker=request.benchmark or "NIFTY500",
                debug_mode=request.debug_mode,
                debug_symbol=request.debug_symbol,
            )

        if strat_id in {"momentum_pulse", "momentum_pulse_finder", "pulse"}:
            return MomentumPulseLeanAlgorithm(
                symbols=request.symbols,
                start_date=start_dt,
                end_date=end_dt,
                initial_cash=request.initial_capital,
                max_positions=request.max_positions,
                allocation_pct=alloc_pct,
                ema_length=int(request.parameters.get("ema_length", 20)),
                rsi_length=int(request.parameters.get("rsi_length", 14)),
                rsi_level=float(request.parameters.get("rsi_level", 50.0)),
            )

        if strat_id in {"17_long_term_mom", "long_term_mom", "ltm", "17", "ltm_momentum_252"}:
            mom_gate = float(request.parameters.get("momentum_gate", 0.50))
            reb_period = int(request.parameters.get("rebalance_period", 252))
            sizing = str(request.parameters.get("sizing_mode", "A"))
            return LongTermMomentumLeanAlgorithm(
                symbols=request.symbols,
                start_date=start_dt,
                end_date=end_dt,
                initial_cash=request.initial_capital,
                max_positions=request.max_positions,
                allocation_pct=alloc_pct,
                momentum_gate=mom_gate,
                rebalance_period=reb_period,
                benchmark_ticker=request.benchmark or "NIFTY500",
                sizing_mode=sizing,
                debug_mode=request.debug_mode,
            )

        if strat_id in {"01_sma_cross", "sma_crossover", "sma_cross", "01"}:
            fast = int(request.parameters.get("fast_period", 20))
            slow = int(request.parameters.get("slow_period", 50))
            return SmaCrossoverLeanAlgorithm(
                symbols=request.symbols,
                start_date=start_dt,
                end_date=end_dt,
                initial_cash=request.initial_capital,
                fast_period=fast,
                slow_period=slow,
                allocation_pct=alloc_pct,
            )

        if strat_id in {"02_rsi_oversold", "rsi_oversold", "rsi", "02"}:
            period = int(request.parameters.get("rsi_period", 14))
            oversold = float(request.parameters.get("oversold_level", 30.0))
            overbought = float(request.parameters.get("overbought_level", 70.0))
            return RsiOversoldLeanAlgorithm(
                symbols=request.symbols,
                start_date=start_dt,
                end_date=end_dt,
                initial_cash=request.initial_capital,
                rsi_period=period,
                oversold_level=oversold,
                overbought_level=overbought,
                allocation_pct=alloc_pct,
            )

        # Check preset catalog or fallback to DynamicRuleLeanAlgorithm
        preset = preset_by_id(strat_id)
        config_dict = dict(preset) if preset else {"name": request.strategy_name, "filters": []}
        config_dict.update(request.parameters)
        parsed_config = parse_strategy_config(config_dict)

        return DynamicRuleLeanAlgorithm(
            symbols=request.symbols,
            config=parsed_config,
            start_date=start_dt,
            end_date=end_dt,
            initial_cash=request.initial_capital,
            max_positions=request.max_positions,
            allocation_pct=alloc_pct,
            benchmark_ticker=request.benchmark,
        )
