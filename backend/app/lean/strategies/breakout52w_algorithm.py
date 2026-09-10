"""QuantConnect LEAN 52-Week High Breakout QCAlgorithm (09_52w_breakout)."""

from __future__ import annotations

from datetime import datetime
import math
from typing import Any

from ..engine.indicators import AverageTrueRange, PriorSessionMaximum, SimpleMovingAverage
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
from ..models import LeanDebugTraceBar


class Breakout52wLeanAlgorithm(QCAlgorithm):
    """52-Week High Breakout Strategy Algorithm in QuantConnect LEAN.
    
    Rules:
    1. Close >= Prior 252 Trading Sessions High (today's high excluded).
    2. Volume > 20-Session Volume SMA.
    3. Benchmark (NIFTY 500) Close > Benchmark 50-Session SMA.
    4. Sizing: Portfolio-level slot allocation (e.g. 10% per slot, max 10 slots).
    5. Ranking: 60-session momentum descending.
    6. Exit: Trailing stop or Close < 20-Session Low / Signal invalidation.
    """

    def __init__(
        self,
        symbols: list[str],
        start_date: datetime,
        end_date: datetime,
        initial_cash: float = 100000.0,
        max_positions: int = 10,
        allocation_pct: float = 0.10,
        atr_multiplier: float = 3.0,
        benchmark_ticker: str = "NIFTY500",
        debug_mode: bool = False,
        debug_symbol: str | None = None,
    ) -> None:
        super().__init__()
        self.target_symbols = symbols
        self.set_start_date(start_date.year, start_date.month, start_date.day)
        self.set_end_date(end_date.year, end_date.month, end_date.day)
        self.set_cash(initial_cash)
        self.max_positions = max_positions
        self.allocation_pct = allocation_pct
        self.atr_multiplier = atr_multiplier
        self.benchmark_ticker = benchmark_ticker
        self.debug_mode = debug_mode
        self.debug_symbol = debug_symbol.upper() if debug_symbol else (symbols[0].upper() if len(symbols) == 1 else None)

        # Indicators per symbol
        self.prior_highs: dict[Symbol, PriorSessionMaximum] = {}
        self.vol_smas: dict[Symbol, SimpleMovingAverage] = {}
        self.atrs: dict[Symbol, AverageTrueRange] = {}
        self.close_windows: dict[Symbol, RollingWindow[float]] = {}
        self.trailing_stops: dict[Symbol, float] = {}

        # Benchmark indicator
        self.bench_sma50 = SimpleMovingAverage(50, name="BenchmarkSMA50")

        # Debug trace log
        self.debug_trace_records: list[LeanDebugTraceBar] = []
        self._bar_index_map: dict[str, int] = {}

    def initialize(self) -> None:
        """Initialize securities, indicators and subscription feeds."""
        for sym_str in self.target_symbols:
            sec = self.add_equity(sym_str, Resolution.DAILY)
            sym = sec.symbol
            self.prior_highs[sym] = PriorSessionMaximum(252, name=f"{sym.value}_High252")
            self.vol_smas[sym] = SimpleMovingAverage(20, name=f"{sym.value}_VolSMA20")
            self.atrs[sym] = AverageTrueRange(14, name=f"{sym.value}_ATR14")
            self.close_windows[sym] = RollingWindow[float](260)
            self._bar_index_map[sym.value] = 0

        if self.benchmark_ticker:
            self.set_benchmark(self.benchmark_ticker)

    def on_data(self, slice: Slice) -> None:
        """Event-driven bar-by-bar execution."""
        self.time = slice.time

        # Update Benchmark
        bench_ok = True
        if self.benchmark_symbol and slice.contains_key(self.benchmark_symbol):
            b_bar = slice[self.benchmark_symbol]
            self.bench_sma50.update(b_bar.time, b_bar.close)
            if self.bench_sma50.is_ready:
                bench_ok = float(b_bar.close) > float(self.bench_sma50.value)

        # Update symbol indicators
        candidates: list[tuple[Symbol, float, float]] = []  # (symbol, momentum60, entry_price)

        for sym, sec in self.securities.items():
            if sym == self.benchmark_symbol or not slice.contains_key(sym):
                continue

            bar = slice[sym]
            c = float(bar.close)
            h = float(bar.high)
            v = float(bar.volume)

            # Update rolling windows & indicators
            prior_h_ind = self.prior_highs[sym]
            vol_sma_ind = self.vol_smas[sym]
            atr_ind = self.atrs[sym]
            win = self.close_windows[sym]

            # Read current values BEFORE updating with today's bar
            prior_h = prior_h_ind.value if prior_h_ind.is_ready else None
            
            # Now update indicators with today's bar
            prior_h_ind.update(bar.time, h)
            vol_sma_ind.update(bar.time, v)
            atr_ind.update(bar)
            win.add(c)

            self._bar_index_map[sym.value] += 1
            b_idx = self._bar_index_map[sym.value]

            # 252 Lookback values
            close_252 = win[252] if len(win) > 252 else None
            mom_252 = ((c / close_252) - 1.0) if (close_252 and close_252 > 0) else None
            mom_60 = ((c / win[60]) - 1.0) if (len(win) > 60 and win[60] > 0) else -999.0
            vol_sma = vol_sma_ind.value if vol_sma_ind.is_ready else None

            # Check 52W Breakout Conditions
            entry_cond = False
            if prior_h is not None and vol_sma is not None and bench_ok:
                if c >= prior_h and v > vol_sma:
                    entry_cond = True

            # Position check & exit logic
            holding = self.portfolio[sym]
            exit_cond = False
            order_action: str | None = None
            fill_px: float | None = None

            if holding.invested:
                # Update trailing stop
                atr_val = atr_ind.value if atr_ind.is_ready else (c * 0.03)
                curr_stop = c - (atr_val * self.atr_multiplier)
                if sym not in self.trailing_stops:
                    self.trailing_stops[sym] = curr_stop
                else:
                    self.trailing_stops[sym] = max(self.trailing_stops[sym], curr_stop)

                # Check trailing stop exit
                if c < self.trailing_stops[sym]:
                    exit_cond = True
                    self.liquidate(sym, tag=f"Trailing Stop Exit ({self.trailing_stops[sym]:.2f})")
                    self.trailing_stops.pop(sym, None)
                    order_action = "SELL_STOP"
            else:
                if entry_cond:
                    candidates.append((sym, mom_60, c))

            # Record debug trace if requested
            if self.debug_mode and (self.debug_symbol is None or sym.value.upper() == self.debug_symbol):
                self.debug_trace_records.append(
                    LeanDebugTraceBar(
                        symbol=sym.value,
                        date=bar.time.strftime("%Y-%m-%d"),
                        barIndex=b_idx,
                        open=float(bar.open),
                        high=h,
                        low=float(bar.low),
                        close=c,
                        volume=int(v),
                        close252=round(close_252, 2) if close_252 else None,
                        momentum252=round(mom_252, 4) if mom_252 else None,
                        high252=round(prior_h, 2) if prior_h else None,
                        volSma20=round(vol_sma, 0) if vol_sma else None,
                        entryCondition=entry_cond,
                        exitCondition=exit_cond,
                        positionQty=holding.quantity,
                        orderAction=order_action,
                        fillPrice=fill_px,
                    )
                )

        # Allocate slots for ranked candidates
        if candidates:
            # Rank candidates by 60-session momentum descending
            candidates.sort(key=lambda x: x[1], reverse=True)
            current_invested_count = sum(1 for s, sec in self.securities.items() if s != self.benchmark_symbol and sec.holdings.invested)
            available_slots = max(0, self.max_positions - current_invested_count)

            for sym, mom, px in candidates[:available_slots]:
                if not self.portfolio[sym].invested:
                    # Allocate slot
                    self.set_holdings(sym, self.allocation_pct, tag=f"52W Breakout Entry (Mom60={mom:.2f})")
