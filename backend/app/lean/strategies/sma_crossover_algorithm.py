"""QuantConnect LEAN SMA Crossover QCAlgorithm."""

from __future__ import annotations

from datetime import datetime

from ..engine.indicators import SimpleMovingAverage
from ..engine.qc_algorithm import QCAlgorithm, Resolution, Slice, Symbol


class SmaCrossoverLeanAlgorithm(QCAlgorithm):
    """Standard SMA Crossover (e.g. 20/50 SMA) LEAN Algorithm."""

    def __init__(
        self,
        symbols: list[str],
        start_date: datetime,
        end_date: datetime,
        initial_cash: float = 100000.0,
        fast_period: int = 20,
        slow_period: int = 50,
        allocation_pct: float = 1.0,
    ) -> None:
        super().__init__()
        self.target_symbols = symbols
        self.set_start_date(start_date.year, start_date.month, start_date.day)
        self.set_end_date(end_date.year, end_date.month, end_date.day)
        self.set_cash(initial_cash)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.allocation_pct = allocation_pct

        self.fast_smas: dict[Symbol, SimpleMovingAverage] = {}
        self.slow_smas: dict[Symbol, SimpleMovingAverage] = {}

    def initialize(self) -> None:
        for sym_str in self.target_symbols:
            sec = self.add_equity(sym_str, Resolution.DAILY)
            sym = sec.symbol
            self.fast_smas[sym] = SimpleMovingAverage(self.fast_period, name=f"{sym.value}_FastSMA")
            self.slow_smas[sym] = SimpleMovingAverage(self.slow_period, name=f"{sym.value}_SlowSMA")

    def on_data(self, slice: Slice) -> None:
        self.time = slice.time
        for sym, sec in self.securities.items():
            if not slice.contains_key(sym):
                continue
            bar = slice[sym]
            c = float(bar.close)
            fast_ind = self.fast_smas[sym]
            slow_ind = self.slow_smas[sym]

            fast_ind.update(bar.time, c)
            slow_ind.update(bar.time, c)

            if not fast_ind.is_ready or not slow_ind.is_ready:
                continue

            fast_val = fast_ind.value
            slow_val = slow_ind.value
            holding = self.portfolio[sym]

            if fast_val > slow_val:
                if not holding.invested:
                    self.set_holdings(sym, self.allocation_pct, tag="SMA Golden Cross Entry")
            elif fast_val < slow_val:
                if holding.invested:
                    self.liquidate(sym, tag="SMA Death Cross Exit")
