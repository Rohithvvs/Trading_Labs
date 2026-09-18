"""Pre-scan OHLCV validation. Invalid rows are stripped before evaluation."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ..strategy_tester.indicators import BarSeries
from ..market_data_ingestion.nse_sessions import (
    SessionFilterStats,
    filter_session_ohlcv_rows,
    split_like_factor,
)


@dataclass
class ScanDataQuality:
    end_session: date | None = None
    session_count: int = 0
    symbols_checked: int = 0
    dropped_weekend: int = 0
    dropped_holiday: int = 0
    dropped_non_session: int = 0
    dropped_cloned: int = 0
    insufficient_history: list[str] = field(default_factory=list)
    missing_end_session: list[str] = field(default_factory=list)
    split_like: list[dict[str, Any]] = field(default_factory=list)
    last_bar_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "end_session": self.end_session.isoformat() if self.end_session else None,
            "session_calendar_bars": self.session_count,
            "symbols_checked": self.symbols_checked,
            "dropped_weekend_bars": self.dropped_weekend,
            "dropped_holiday_bars": self.dropped_holiday,
            "dropped_non_session_bars": self.dropped_non_session,
            "dropped_cloned_bars": self.dropped_cloned,
            "insufficient_history_count": len(self.insufficient_history),
            "insufficient_history_sample": self.insufficient_history[:40],
            "missing_end_session_count": len(self.missing_end_session),
            "missing_end_session_sample": self.missing_end_session[:40],
            "split_like_jumps": self.split_like[:40],
            "last_bar_counts": dict(self.last_bar_counts),
        }


def _series_to_rows(series: BarSeries) -> list[tuple]:
    rows = []
    for i, day in enumerate(series.dates):
        rows.append(
            (
                day,
                series.open[i] if i < len(series.open) else None,
                series.high[i] if i < len(series.high) else None,
                series.low[i] if i < len(series.low) else None,
                series.close[i] if i < len(series.close) else None,
                series.volume[i] if i < len(series.volume) else None,
            )
        )
    return rows


def sanitize_bar_series(
    series: BarSeries | None,
    *,
    session_dates: set[date] | None = None,
) -> tuple[BarSeries | None, SessionFilterStats]:
    if series is None or not series.dates:
        return None, SessionFilterStats()
    kept, stats = filter_session_ohlcv_rows(_series_to_rows(series), session_dates=session_dates)
    if not kept:
        return None, stats
    return (
        BarSeries(
            dates=[row[0] for row in kept],
            open=[_as_float(row[1]) for row in kept],
            high=[_as_float(row[2]) for row in kept],
            low=[_as_float(row[3]) for row in kept],
            close=[_as_float(row[4]) for row in kept],
            volume=[_as_float(row[5]) for row in kept],
        ),
        stats,
    )


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate_and_sanitize_universe(
    series_by_symbol: dict[str, BarSeries],
    *,
    end_session: date,
    session_dates: set[date] | None,
    min_bars: int,
    benchmark: BarSeries | None = None,
) -> tuple[dict[str, BarSeries], BarSeries | None, ScanDataQuality]:
    """Strip holiday/weekend/cloned bars and record why names will skip."""
    report = ScanDataQuality(end_session=end_session)
    if session_dates:
        report.session_count = len(session_dates)
    cleaned: dict[str, BarSeries] = {}
    last_dates: Counter[str] = Counter()
    for symbol, series in series_by_symbol.items():
        report.symbols_checked += 1
        out, stats = sanitize_bar_series(series, session_dates=session_dates)
        report.dropped_weekend += stats.dropped_weekend
        report.dropped_holiday += stats.dropped_holiday
        report.dropped_non_session += stats.dropped_non_session
        report.dropped_cloned += stats.dropped_cloned
        for jump in stats.split_like_jumps:
            report.split_like.append({"symbol": symbol, **jump})
        if out is None or not out.dates:
            report.insufficient_history.append(symbol)
            continue
        if len(out) < min_bars:
            report.insufficient_history.append(symbol)
        if out.dates[-1] != end_session:
            report.missing_end_session.append(symbol)
        last_dates[out.dates[-1].isoformat()] += 1
        cleaned[symbol] = out
    report.last_bar_counts = dict(last_dates)
    bench_out = benchmark
    if benchmark is not None:
        bench_out, _stats = sanitize_bar_series(benchmark, session_dates=session_dates)
    return cleaned, bench_out, report


def leftover_split_like(series: BarSeries) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for i in range(1, len(series.close)):
        factor = split_like_factor(series.close[i - 1], series.close[i])
        if factor is None:
            continue
        found.append(
            {
                "trade_date": series.dates[i].isoformat(),
                "prev_close": series.close[i - 1],
                "close": series.close[i],
                "factor": factor,
            }
        )
    return found
