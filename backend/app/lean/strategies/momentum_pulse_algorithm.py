"""LEAN algorithm for Momentum Pulse Finder: Close > EMA 20 and RSI 14 crosses above 50."""

from __future__ import annotations

from datetime import datetime

from ..engine.qc_algorithm import QCAlgorithm, Resolution, Slice, Symbol
from ...services.indicator_scanner.ta_functions import crossover, crossunder, ema, rsi


class MomentumPulseLeanAlgorithm(QCAlgorithm):
    """Same entry as the Indicator Scanner Momentum Pulse Finder Pine."""

    def __init__(
        self,
        symbols: list[str],
        start_date: datetime,
        end_date: datetime,
        initial_cash: float = 100000.0,
        max_positions: int = 10,
        allocation_pct: float = 0.10,
        ema_length: int = 20,
        rsi_length: int = 14,
        rsi_level: float = 50.0,
    ) -> None:
        super().__init__()
        self.target_symbols = symbols
        self.set_start_date(start_date.year, start_date.month, start_date.day)
        self.set_end_date(end_date.year, end_date.month, end_date.day)
        self.set_cash(initial_cash)
        self.max_positions = max_positions
        self.allocation_pct = allocation_pct
        self.ema_length = ema_length
        self.rsi_length = rsi_length
        self.rsi_level = rsi_level
        self.closes: dict[Symbol, list[float]] = {}

    def initialize(self) -> None:
        for sym_str in self.target_symbols:
            sec = self.add_equity(sym_str, Resolution.DAILY)
            self.closes[sec.symbol] = []

    def on_data(self, slice: Slice) -> None:
        self.time = slice.time
        invested = sum(1 for sec in self.securities.values() if self.portfolio[sec.symbol].invested)
        for sym, sec in self.securities.items():
            if not slice.contains_key(sym):
                continue
            close = float(slice[sym].close)
            series = self.closes.setdefault(sym, [])
            series.append(close)
            if len(series) < max(self.ema_length, self.rsi_length) + 2:
                continue
            ema_s = ema(series, self.ema_length)
            rsi_s = rsi(series, self.rsi_length)
            level = [self.rsi_level] * len(series)
            up = crossover(rsi_s, level)
            down = crossunder(rsi_s, level)
            ema_now = ema_s[-1]
            holding = self.portfolio[sym]
            pulse = (
                ema_now is not None
                and close > float(ema_now)
                and bool(up[-1])
            )
            if pulse and not holding.invested and invested < self.max_positions:
                self.set_holdings(sym, self.allocation_pct, tag="Momentum Pulse")
                invested += 1
            elif holding.invested and (
                (ema_now is not None and close < float(ema_now)) or bool(down[-1])
            ):
                self.liquidate(sym, tag="Momentum Pulse exit")
                invested = max(0, invested - 1)
