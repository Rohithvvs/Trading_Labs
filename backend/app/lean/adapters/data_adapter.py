"""LeanDataAdapter: Converts Trading Labs historical market data into LEAN TradeBar feeds."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
import logging
from pathlib import Path
from typing import Any, Sequence

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.strategy_market_data import DailyOhlcv, IndexOhlcv
from ...services.market_data_ingestion.repository import (
    fetch_daily_ohlcv_for_symbols,
    fetch_index_history,
)
from ...services.strategy_tester.indicators import BarSeries
from ...services.strategy_tester.scan_service import prepare_scan_market_data
from ...utils.symbol import canonical_symbol
from ..engine.qc_algorithm import Market, Resolution, SecurityType, Symbol, TradeBar

logger = logging.getLogger("app.lean.data_adapter")


class LeanDataAdapter:
    """Transforms Trading Labs NSE historical OHLCV data into QuantConnect LEAN format."""

    @staticmethod
    def bar_series_to_trade_bars(symbol_str: str, series: BarSeries) -> list[TradeBar]:
        """Convert Trading Labs BarSeries into strictly chronological TradeBar list."""
        bars: list[TradeBar] = []
        sym = Symbol(value=canonical_symbol(symbol_str) or symbol_str.upper(), security_type=SecurityType.EQUITY, market=Market.INDIA)
        
        for i in range(len(series)):
            d = series.dates[i]
            dt = datetime.combine(d, time(15, 30))  # Standard NSE market close 15:30 IST
            o = float(series.open[i])
            h = float(series.high[i])
            l = float(series.low[i])
            c = float(series.close[i])
            v = int(series.volume[i]) if series.volume[i] is not None else 0

            # Validate price positivity
            if c > 0 and h >= l and o > 0:
                bars.append(
                    TradeBar(
                        symbol=sym,
                        time=dt,
                        open=o,
                        high=h,
                        low=l,
                        close=c,
                        volume=v,
                        period=timedelta(days=1),
                    )
                )

        # Sort strictly chronologically
        bars.sort(key=lambda b: b.time)
        return bars

    @staticmethod
    def daily_ohlcv_to_trade_bars(symbol_str: str, rows: Sequence[DailyOhlcv | IndexOhlcv]) -> list[TradeBar]:
        """Convert database DailyOhlcv or IndexOhlcv rows into TradeBar list."""
        bars: list[TradeBar] = []
        is_index = isinstance(rows[0], IndexOhlcv) if rows else False
        sec_type = SecurityType.INDEX if is_index else SecurityType.EQUITY
        sym = Symbol(value=canonical_symbol(symbol_str) or symbol_str.upper(), security_type=sec_type, market=Market.INDIA)

        for row in rows:
            d = row.trade_date
            dt = datetime.combine(d, time(15, 30))
            o = float(row.open)
            h = float(row.high)
            l = float(row.low)
            c = float(row.close)
            v = int(row.volume) if row.volume is not None else 0

            if c > 0 and h >= l and o > 0:
                bars.append(
                    TradeBar(
                        symbol=sym,
                        time=dt,
                        open=o,
                        high=h,
                        low=l,
                        close=c,
                        volume=v,
                        period=timedelta(days=1),
                    )
                )

        bars.sort(key=lambda b: b.time)
        return bars

    @classmethod
    async def load_historical_data(
        cls,
        symbols: list[str],
        start_date: date,
        end_date: date,
        warmup_sessions: int = 260,
        benchmark: str | None = "NIFTY500",
    ) -> tuple[dict[str, list[TradeBar]], list[TradeBar] | None]:
        """Fetch and align multi-symbol historical data with required warmup bars."""
        # Calculate from_date ensuring at least warmup_sessions calendar cushion (e.g. 400+ calendar days for 260 trading sessions)
        cushion_days = max(int(warmup_sessions * 1.6), 420)
        from_date = start_date - timedelta(days=cushion_days)

        clean_symbols = [canonical_symbol(s) or s.upper() for s in symbols if s]
        clean_symbols = list(dict.fromkeys(clean_symbols))

        logger.info(
            "LEAN_DATA_LOAD | symbols=%d | from_date=%s | to_date=%s | benchmark=%s",
            len(clean_symbols),
            from_date,
            end_date,
            benchmark,
        )

        series_map, bench_series, source = await prepare_scan_market_data(
            clean_symbols,
            from_date=from_date,
            to_date=end_date,
            need_benchmark=bool(benchmark),
        )

        data_map: dict[str, list[TradeBar]] = {}
        for sym_name, series in series_map.items():
            if series and len(series) > 0:
                bars = cls.bar_series_to_trade_bars(sym_name, series)
                if bars:
                    data_map[sym_name] = bars

        benchmark_bars: list[TradeBar] | None = None
        if bench_series and len(bench_series) > 0 and benchmark:
            benchmark_bars = cls.bar_series_to_trade_bars(benchmark, bench_series)

        logger.info(
            "LEAN_DATA_LOADED | loaded_symbols=%d | benchmark_bars=%s | source=%s",
            len(data_map),
            len(benchmark_bars) if benchmark_bars else 0,
            source,
        )
        return data_map, benchmark_bars

    @staticmethod
    def synchronize_slices(
        data_map: dict[str, list[TradeBar]],
        benchmark_bars: list[TradeBar] | None = None,
    ) -> list[tuple[datetime, dict[Symbol, TradeBar]]]:
        """Synchronize multi-asset bars across exact timestamps into chronological slices."""
        timeline: set[datetime] = set()

        by_symbol_and_time: dict[Symbol, dict[datetime, TradeBar]] = defaultdict(dict)

        for sym_str, bars in data_map.items():
            for b in bars:
                by_symbol_and_time[b.symbol][b.time] = b
                timeline.add(b.time)

        if benchmark_bars:
            for b in benchmark_bars:
                by_symbol_and_time[b.symbol][b.time] = b
                timeline.add(b.time)

        sorted_times = sorted(timeline)
        slices: list[tuple[datetime, dict[Symbol, TradeBar]]] = []

        for t in sorted_times:
            current_bars: dict[Symbol, TradeBar] = {}
            for sym, t_map in by_symbol_and_time.items():
                if t in t_map:
                    current_bars[sym] = t_map[t]
            if current_bars:
                slices.append((t, current_bars))

        return slices
