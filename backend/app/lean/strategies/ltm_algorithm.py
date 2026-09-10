"""QuantConnect LEAN Long-Term Buy & Hold Momentum QCAlgorithm (17_long_term_mom)."""

from __future__ import annotations

from datetime import datetime
import math
from typing import Any

from ..engine.qc_algorithm import (
    OrderDirection,
    OrderTicket,
    QCAlgorithm,
    Resolution,
    RollingWindow,
    Slice,
    Symbol,
    TradeBar,
)


class LongTermMomentumLeanAlgorithm(QCAlgorithm):
    """Long-Term Buy & Hold Momentum Strategy Algorithm in QuantConnect LEAN.
    
    Rules (from 17_long_term_mom specification):
    1. Lookback: Momentum_252 = Close[t] / Close[t-252] - 1.0.
    2. Eligibility: Momentum_252 > 0.50 (strict).
    3. Rebalance Calendar:
       - WARMUP = 252 sessions.
       - Rebalance every 252 trading sessions.
       - Non-rebalance sessions: Do not trade, mark to market.
    4. Sizing:
       - Mode A: Cash / N across top min(10, |Eligible|) names.
       - Mode B: 10% of current equity per name, max 10 names.
    5. Ranking: Momentum_252 desc, symbol asc tie-break.
    6. Full turnover: Sell entire book, then buy new basket.
    """

    def __init__(
        self,
        symbols: list[str],
        start_date: datetime,
        end_date: datetime,
        initial_cash: float = 100000.0,
        max_positions: int = 10,
        allocation_pct: float = 0.10,
        momentum_gate: float = 0.50,
        rebalance_period: int = 252,
        benchmark_ticker: str = "NIFTY500",
        sizing_mode: str = "A",
        debug_mode: bool = False,
    ) -> None:
        super().__init__()
        self.target_symbols = symbols
        self.set_start_date(start_date.year, start_date.month, start_date.day)
        self.set_end_date(end_date.year, end_date.month, end_date.day)
        self.set_cash(initial_cash)
        self.max_positions = max_positions
        self.allocation_pct = allocation_pct
        self.momentum_gate = momentum_gate
        self.rebalance_period = rebalance_period
        self.benchmark_ticker = benchmark_ticker
        self.sizing_mode = sizing_mode.upper()
        self.debug_mode = debug_mode

        # Indicator state
        self.close_windows: dict[Symbol, RollingWindow[float]] = {}
        self.sessions_since_rebalance: int = 0
        self.session_index: int = 0
        self.has_first_rebalance: bool = False

    def initialize(self) -> None:
        """Initialize securities, rolling windows, and benchmark."""
        for sym_str in self.target_symbols:
            sec = self.add_equity(sym_str, Resolution.DAILY)
            sym = sec.symbol
            self.close_windows[sym] = RollingWindow[float](265)

        if self.benchmark_ticker:
            self.set_benchmark(self.benchmark_ticker)

    def on_data(self, slice: Slice) -> None:
        """Event-driven annual rebalance momentum cycle."""
        self.time = slice.time

        # 1. Update closing price windows for available symbols
        valid_count = 0
        for sym, sec in self.securities.items():
            if sym == self.benchmark_symbol or not slice.contains_key(sym):
                continue
            bar = slice[sym]
            c = float(bar.close)
            if c > 0 and math.isfinite(c):
                self.close_windows[sym].add(c)
                valid_count += 1

        if valid_count == 0:
            return

        # 2. Update session index
        self.session_index += 1

        # Warmup gate: at least 252 sessions of history
        if self.session_index < self.rebalance_period:
            return

        # Increment rebalance clock
        self.sessions_since_rebalance += 1

        # Check if rebalance session reached
        is_rebalance_session = False
        if not self.has_first_rebalance:
            is_rebalance_session = True
            self.has_first_rebalance = True
        elif self.sessions_since_rebalance >= self.rebalance_period:
            is_rebalance_session = True

        if not is_rebalance_session:
            return

        # 3. REBALANCE TRIGGERED: Liquidate entire current book first
        for sym, sec in self.securities.items():
            if sym != self.benchmark_symbol and sec.holdings.invested:
                self.liquidate(sym, tag="Annual LTM Rebalance Liquidation")

        # 4. Calculate 252-session momentum for all eligible names
        candidates: list[tuple[Symbol, float]] = []

        for sym, sec in self.securities.items():
            if sym == self.benchmark_symbol or not slice.contains_key(sym):
                continue
            win = self.close_windows.get(sym)
            if not win or len(win) <= self.rebalance_period:
                continue

            bar = slice[sym]
            c_now = float(bar.close)
            c_past = win[self.rebalance_period]

            if c_past is not None and c_past > 0 and math.isfinite(c_past) and c_now > 0 and math.isfinite(c_now):
                mom252 = (c_now / c_past) - 1.0
                if mom252 > self.momentum_gate:  # Strict > 0.50
                    candidates.append((sym, mom252))

        # 5. Deterministic Sort: Rank key 1: Momentum_252 desc, Rank key 2: symbol asc
        candidates.sort(key=lambda x: (-x[1], x[0].value))

        selected = candidates[: self.max_positions]
        n_selected = len(selected)

        # 6. Sizing and Allocation
        if n_selected > 0:
            current_equity = self.portfolio.total_portfolio_value
            current_cash = max(0.0, self.portfolio.cash)

            if self.sizing_mode == "A":
                notional_per_slot = current_cash / float(n_selected)
            else:
                notional_per_slot = current_equity * self.allocation_pct

            for sym, mom in selected:
                bar = slice[sym]
                px = float(bar.close)
                if px > 0:
                    qty = int(notional_per_slot / px)
                    if qty > 0:
                        self.market_order(sym, qty, tag=f"LTM Buy (Mom: {mom*100:.1f}%)")

        self.sessions_since_rebalance = 0

    def on_end_of_algorithm(self) -> None:
        for sym, sec in self.securities.items():
            if sym != self.benchmark_symbol and sec.holdings.invested:
                self.liquidate(sym, tag="End of Sample Liquidation")
