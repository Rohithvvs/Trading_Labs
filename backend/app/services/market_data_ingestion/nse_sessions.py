"""NSE cash-market session calendar for daily bar counts (close[n], SMA, etc.).

TradingView 1D Pine counts *exchange sessions*, not calendar days and not
holiday/weekend/cloned rows that may sit in daily_ohlcv. This module is the
shared filter so scanners never treat those rows as bars.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

from ..trading_hours_service import TradingHoursService, trading_hours

IST = ZoneInfo("Asia/Kolkata")

# Close-to-close ratios that usually mean a split/bonus, not a traded move.
_SPLIT_FACTORS = (
    10.0,
    5.0,
    4.0,
    3.0,
    2.0,
    1.5,
    1.25,
    2.0 / 3.0,
    0.5,
    1.0 / 3.0,
    0.25,
    0.2,
    0.1,
)


def _hours() -> TradingHoursService:
    return trading_hours if trading_hours is not None else TradingHoursService()


def is_nse_cash_session(day: date) -> bool:
    """True on an NSE cash trading day (not weekend, not holiday)."""
    if day.weekday() >= 5:
        return False
    noon = datetime(day.year, day.month, day.day, 12, 0, tzinfo=IST)
    return _hours().is_trading_day(noon)


def session_on_or_before(day: date) -> date:
    cur = day
    for _ in range(40):
        if is_nse_cash_session(cur):
            return cur
        cur -= timedelta(days=1)
    return day


def nth_session_ending(end: date, n: int) -> date:
    """Date of the n-th NSE cash session ending at `end` (n=1 is the last session).

    Used as a fetch-window start so close[252] can be the 252nd *session* back,
    not `end - 252 calendar days`.
    """
    if n <= 1:
        return session_on_or_before(end)
    cur = session_on_or_before(end)
    remaining = n - 1
    while remaining > 0:
        cur -= timedelta(days=1)
        if is_nse_cash_session(cur):
            remaining -= 1
    return cur


def iter_nse_sessions(start: date, end: date) -> list[date]:
    if start > end:
        return []
    out: list[date] = []
    cur = start
    while cur <= end:
        if is_nse_cash_session(cur):
            out.append(cur)
        cur += timedelta(days=1)
    return out


def nse_session_dates(
    start: date,
    end: date,
    index_dates: Iterable[date] | None = None,
) -> set[date]:
    """Cash-session set for a window, aligned with TradingView's 1D calendar.

    Index weekday prints can *add* sessions the holiday JSON missed (special
    tapes). They must not *delete* cash sessions when the index store has a
    hole — dropping those bars desyncs EMA/RSI from Pine Screener.
    """
    calendar = set(iter_nse_sessions(start, end))
    if index_dates is None:
        return calendar
    idx = {d for d in index_dates if start <= d <= end and d.weekday() < 5}
    if not idx:
        return calendar
    return calendar | idx


def same_ohlcv(left: Sequence, right: Sequence, *, start: int = 1) -> bool:
    if left is None or right is None:
        return False
    n = min(len(left), len(right))
    if n <= start:
        return False
    for i in range(start, n):
        a, b = left[i], right[i]
        if a is None or b is None:
            return False
        try:
            if abs(float(a) - float(b)) >= 1e-6:
                return False
        except (TypeError, ValueError):
            return False
    return True


def split_like_factor(prev_close: float, close: float, *, tol: float = 0.04) -> float | None:
    """Return a split/bonus factor when the overnight ratio matches a corporate action."""
    if prev_close is None or close is None:
        return None
    try:
        prev = float(prev_close)
        curr = float(close)
    except (TypeError, ValueError):
        return None
    if prev <= 0 or curr <= 0:
        return None
    ratio = prev / curr
    for factor in _SPLIT_FACTORS:
        if abs(ratio - factor) <= tol * factor:
            return factor
    return None


@dataclass
class SessionFilterStats:
    input_bars: int = 0
    kept_bars: int = 0
    dropped_weekend: int = 0
    dropped_holiday: int = 0
    dropped_non_session: int = 0
    dropped_cloned: int = 0
    split_like_jumps: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "input_bars": self.input_bars,
            "kept_bars": self.kept_bars,
            "dropped_weekend": self.dropped_weekend,
            "dropped_holiday": self.dropped_holiday,
            "dropped_non_session": self.dropped_non_session,
            "dropped_cloned": self.dropped_cloned,
            "split_like_jumps": list(self.split_like_jumps),
        }


def filter_session_ohlcv_rows(
    items: Sequence[tuple],
    *,
    session_dates: set[date] | None = None,
    apply_holiday_calendar: bool = True,
) -> tuple[list[tuple], SessionFilterStats]:
    """Keep one bar per valid NSE cash session; drop holidays, weekends, clones."""
    stats = SessionFilterStats()
    by_date: dict[date, tuple] = {}
    for row in items:
        if not row or row[0] is None:
            continue
        by_date[row[0]] = row
    ordered = [by_date[day] for day in sorted(by_date)]
    stats.input_bars = len(ordered)
    kept: list[tuple] = []
    hours = _hours()
    for row in ordered:
        day = row[0]
        if day.weekday() >= 5:
            stats.dropped_weekend += 1
            continue
        if session_dates is not None:
            if day not in session_dates:
                stats.dropped_non_session += 1
                continue
        elif apply_holiday_calendar:
            noon = datetime(day.year, day.month, day.day, 12, 0, tzinfo=IST)
            if hours.is_nse_holiday(noon):
                stats.dropped_holiday += 1
                continue
            if not is_nse_cash_session(day):
                stats.dropped_non_session += 1
                continue
        if kept and same_ohlcv(row, kept[-1]):
            stats.dropped_cloned += 1
            continue
        if kept:
            factor = split_like_factor(kept[-1][4], row[4])
            if factor is not None:
                stats.split_like_jumps.append(
                    {
                        "trade_date": day.isoformat(),
                        "prev_close": float(kept[-1][4]) if kept[-1][4] is not None else None,
                        "close": float(row[4]) if row[4] is not None else None,
                        "factor": factor,
                    }
                )
        kept.append(row)
    stats.kept_bars = len(kept)
    return kept, stats
