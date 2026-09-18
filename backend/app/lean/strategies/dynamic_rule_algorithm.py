"""QuantConnect LEAN Dynamic Rule QCAlgorithm (Visual Builder & Filter Trees)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ...services.strategy_tester.filter_engine import evaluate_tree
from ...services.strategy_tester.indicators import BarSeries
from ...services.strategy_tester.schema import StrategyDefinitionConfig
from ...services.strategy_tester.signals import BUY, REJECT, classify_signal
from ..engine.qc_algorithm import QCAlgorithm, Resolution, Slice, Symbol


class DynamicRuleLeanAlgorithm(QCAlgorithm):
    """Executes Trading Labs Visual Builder / Filter Tree Strategy in LEAN."""

    def __init__(
        self,
        symbols: list[str],
        config: StrategyDefinitionConfig,
        start_date: datetime,
        end_date: datetime,
        initial_cash: float = 100000.0,
        max_positions: int = 10,
        allocation_pct: float = 0.10,
        benchmark_ticker: str | None = "NIFTY500",
    ) -> None:
        super().__init__()
        self.target_symbols = symbols
        self.config = config
        self.set_start_date(start_date.year, start_date.month, start_date.day)
        self.set_end_date(end_date.year, end_date.month, end_date.day)
        self.set_cash(initial_cash)
        self.max_positions = max_positions
        self.allocation_pct = allocation_pct
        self.benchmark_ticker = benchmark_ticker

        # Keep per-symbol historical series for AST evaluator
        self.hist_open: dict[Symbol, list[float]] = {}
        self.hist_high: dict[Symbol, list[float]] = {}
        self.hist_low: dict[Symbol, list[float]] = {}
        self.hist_close: dict[Symbol, list[float]] = {}
        self.hist_volume: dict[Symbol, list[float]] = {}
        self.hist_dates: dict[Symbol, list[Any]] = {}

        # Benchmark history
        self.bench_open: list[float] = []
        self.bench_high: list[float] = []
        self.bench_low: list[float] = []
        self.bench_close: list[float] = []
        self.bench_volume: list[float] = []
        self.bench_dates: list[Any] = []

    def initialize(self) -> None:
        for sym_str in self.target_symbols:
            sec = self.add_equity(sym_str, Resolution.DAILY)
            sym = sec.symbol
            self.hist_open[sym] = []
            self.hist_high[sym] = []
            self.hist_low[sym] = []
            self.hist_close[sym] = []
            self.hist_volume[sym] = []
            self.hist_dates[sym] = []

        if self.benchmark_ticker:
            self.set_benchmark(self.benchmark_ticker)

    def on_data(self, slice: Slice) -> None:
        self.time = slice.time
        d = slice.time.date()

        # Update Benchmark
        bench_series = None
        if self.benchmark_symbol and slice.contains_key(self.benchmark_symbol):
            b_bar = slice[self.benchmark_symbol]
            self.bench_open.append(float(b_bar.open))
            self.bench_high.append(float(b_bar.high))
            self.bench_low.append(float(b_bar.low))
            self.bench_close.append(float(b_bar.close))
            self.bench_volume.append(float(b_bar.volume))
            self.bench_dates.append(d)

            bench_series = BarSeries(
                open=self.bench_open,
                high=self.bench_high,
                low=self.bench_low,
                close=self.bench_close,
                volume=self.bench_volume,
                dates=self.bench_dates,
            )

        candidates: list[tuple[Symbol, float]] = []

        for sym, sec in self.securities.items():
            if sym == self.benchmark_symbol or not slice.contains_key(sym):
                continue

            bar = slice[sym]
            c = float(bar.close)

            # Append bar to history
            self.hist_open[sym].append(float(bar.open))
            self.hist_high[sym].append(float(bar.high))
            self.hist_low[sym].append(float(bar.low))
            self.hist_close[sym].append(c)
            self.hist_volume[sym].append(float(bar.volume))
            self.hist_dates[sym].append(d)

            series = BarSeries(
                open=self.hist_open[sym],
                high=self.hist_high[sym],
                low=self.hist_low[sym],
                close=self.hist_close[sym],
                volume=self.hist_volume[sym],
                dates=self.hist_dates[sym],
            )

            eval_i = len(series) - 1
            if eval_i < 20:
                continue

            try:
                filt = evaluate_tree(self.config.root, series, eval_i, benchmark=bench_series)
                signal, _ = classify_signal(filt, self.config.signal)
            except Exception:
                signal = REJECT

            holding = self.portfolio[sym]
            if signal == BUY and not holding.invested:
                candidates.append((sym, c))
            elif signal == REJECT and holding.invested:
                self.liquidate(sym, tag="Rule Invalidation Exit")

        if candidates:
            current_invested = sum(1 for s, sec in self.securities.items() if s != self.benchmark_symbol and sec.holdings.invested)
            available = max(0, self.max_positions - current_invested)
            for sym, px in candidates[:available]:
                if not self.portfolio[sym].invested:
                    self.set_holdings(sym, self.allocation_pct, tag="Dynamic Rule Entry")
