"""QuantConnect LEAN RSI Mean Reversion QCAlgorithm."""

from __future__ import annotations

from datetime import datetime

from ..engine.indicators import RelativeStrengthIndex
from ..engine.qc_algorithm import QCAlgorithm, Resolution, Slice, Symbol


class RsiOversoldLeanAlgorithm(QCAlgorithm):
    """Standard RSI Oversold (e.g. RSI < 30 buy, RSI > 70 sell) LEAN Algorithm."""

    def __init__(
        self,
        symbols: list[str],
        start_date: datetime,
        end_date: datetime,
        initial_cash: float = 100000.0,
        rsi_period: int = 14,
        oversold_level: float = 30.0,
        overbought_level: float = 70.0,
        allocation_pct: float = 1.0,
    ) -> None:
        super().__init__()
        self.target_symbols = symbols
        self.set_start_date(start_date.year, start_date.month, start_date.day)
        self.set_end_date(end_date.year, end_date.month, end_date.day)
        self.set_cash(initial_cash)
        self.rsi_period = rsi_period
        self.oversold_level = oversold_level
        self.overbought_level = overbought_level
        self.allocation_pct = allocation_pct

        self.rsis: dict[Symbol, RelativeStrengthIndex] = {}

    def initialize(self) -> None:
        for sym_str in self.target_symbols:
            sec = self.add_equity(sym_str, Resolution.DAILY)
            sym = sec.symbol
            self.rsis[sym] = RelativeStrengthIndex(self.rsi_period, name=f"{sym.value}_RSI14")

    def on_data(self, slice: Slice) -> None:
        self.time = slice.time
        for sym, sec in self.securities.items():
            if not slice.contains_key(sym):
                continue
            bar = slice[sym]
            c = float(bar.close)
            rsi_ind = self.rsis[sym]
            rsi_ind.update(bar.time, c)

            if not rsi_ind.is_ready:
                continue

            rsi_val = rsi_ind.value
            holding = self.portfolio[sym]

            if rsi_val <= self.oversold_level:
                if not holding.invested:
                    self.set_holdings(sym, self.allocation_pct, tag=f"RSI Oversold Entry ({rsi_val:.1f})")
            elif rsi_val >= self.overbought_level:
                if holding.invested:
                    self.liquidate(sym, tag=f"RSI Overbought Exit ({rsi_val:.1f})")
