"""Period bounds, cache identity, and trade-in-window rules for 52W boards.

Does not change entry, exit, ATR, volume, market-filter, or ranking rules.
Separates data warmup from the requested performance window.
"""

from __future__ import annotations

import calendar
import hashlib
import json
from datetime import date, timedelta
from typing import Any, Iterable

from .book_engine import Trade
from .identity import (
    ATTRIBUTION_PERIODS,
    HISTORICAL_PERIOD,
    STRATEGY_ID,
    STRATEGY_VERSION,
    TIMEFRAME,
    UNIVERSE_ID,
    WARMUP_CALENDAR_DAYS,
    WARMUP_SESSIONS,
)

PeriodKey = str


class PeriodRequestError(ValueError):
    """Rejected or unusable backtest period request."""


def _shift_years(end: date, years: int) -> date:
    try:
        return end.replace(year=end.year - years)
    except ValueError:
        last = calendar.monthrange(end.year - years, end.month)[1]
        return date(end.year - years, end.month, min(end.day, last))


def period_window_start(end: date, period: str) -> date:
    """Inclusive calendar start matching the Scanner period tabs."""
    key = (period or "").upper()
    if key == "1D":
        return end
    if key == "1W":
        return end - timedelta(days=6)
    if key == "1M":
        month = end.month - 1
        year = end.year
        if month <= 0:
            month += 12
            year -= 1
        last = calendar.monthrange(year, month)[1]
        return date(year, month, min(end.day, last))
    years = {"1Y": 1, "3Y": 3, "5Y": 5, "7Y": 7, "8Y": 8, "18Y": 18}.get(key)
    if years is None:
        return end
    return _shift_years(end, years)


def resolve_period_bounds(
    asof: date,
    period: str,
    *,
    start: date | None = None,
    end: date | None = None,
) -> tuple[str, date, date]:
    """Resolve a board period. Future ends clamp to asof. Start after asof is empty."""
    key = (period or "").upper()
    if key not in ATTRIBUTION_PERIODS and start is None:
        key = "3Y"
    resolved_end = end or asof
    if resolved_end > asof:
        resolved_end = asof
    resolved_start = start or period_window_start(resolved_end, key if key in ATTRIBUTION_PERIODS else "3Y")
    if start is not None and end is not None and start > end:
        resolved_start, resolved_end = resolved_end, resolved_start
    if resolved_start > resolved_end:
        raise PeriodRequestError(
            f"period start {resolved_start.isoformat()} is after end {resolved_end.isoformat()}"
        )
    return (key if key in ATTRIBUTION_PERIODS else "CUSTOM"), resolved_start, resolved_end


def scan_fetch_from_date(asof: date) -> date:
    """SQL lower bound: longest board window plus warmup calendar pad."""
    start = period_window_start(asof, HISTORICAL_PERIOD)
    return start - timedelta(days=WARMUP_CALENDAR_DAYS)


def slice_replay_dates(
    dates: list[date],
    *,
    period_start: date,
    period_end: date,
    warmup_sessions: int = WARMUP_SESSIONS,
) -> dict[str, Any]:
    """Warmup sessions before period_start, then dates through period_end.

    Signals/trades before period_start are not part of the performance window.
    """
    capped = [d for d in dates if d <= period_end]
    period_idx = next((i for i, d in enumerate(capped) if d >= period_start), None)
    if period_idx is None:
        return {
            "dates": [],
            "warmup_dates": [],
            "performance_dates": [],
            "warmup_start": None,
            "actual_start": None,
            "actual_end": None,
            "warmup_sessions_used": 0,
            "insufficient_warmup": True,
            "empty": True,
        }
    warmup_idx = max(0, period_idx - warmup_sessions)
    sliced = capped[warmup_idx:]
    warmup_dates = capped[warmup_idx:period_idx]
    performance_dates = capped[period_idx:]
    return {
        "dates": sliced,
        "warmup_dates": warmup_dates,
        "performance_dates": performance_dates,
        "warmup_start": warmup_dates[0] if warmup_dates else (sliced[0] if sliced else None),
        "actual_start": performance_dates[0] if performance_dates else None,
        "actual_end": performance_dates[-1] if performance_dates else None,
        "warmup_sessions_used": len(warmup_dates),
        "insufficient_warmup": len(warmup_dates) < warmup_sessions,
        "empty": not performance_dates,
    }


def trade_in_requested_period(tr: Trade, start: date, end: date) -> bool:
    """Count a trade iff it was opened inside the requested performance window.

    Overlap-on-exit is wrong for end-of-sample liquidation: those exits are
    stamped with the evaluation date, so every still-open name would appear
    in 1D through 18Y.
    """
    return start <= tr.entry_date <= end


def filter_period_trades(trades: Iterable[Trade], start: date, end: date) -> list[Trade]:
    return [tr for tr in trades if trade_in_requested_period(tr, start, end)]


def backtest_cache_key(
    *,
    strategy_id: str = STRATEGY_ID,
    strategy_version: str = STRATEGY_VERSION,
    universe_id: str = UNIVERSE_ID,
    timeframe: str = TIMEFRAME,
    start_date: date,
    end_date: date,
    parameter_hash: str = "default",
    execution_config_hash: str = "default",
) -> str:
    payload = {
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "universe_id": universe_id,
        "timeframe": timeframe,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "parameter_hash": parameter_hash,
        "execution_config_hash": execution_config_hash,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


PERIOD_EXPECTED_SESSIONS: dict[str, int] = {
    "1D": 1,
    "1W": 5,
    "1M": 21,
    "1Y": 252,
    "3Y": 756,
    "5Y": 1260,
    "7Y": 1764,
    "8Y": 2016,
    "18Y": 4536,
}


def expected_sessions_for_period(
    period: str,
    *,
    start: date | None = None,
    end: date | None = None,
) -> int | None:
    key = (period or "").upper()
    if key == "ALL":
        return None
    if key in PERIOD_EXPECTED_SESSIONS:
        return PERIOD_EXPECTED_SESSIONS[key]
    if start and end:
        days = max((end - start).days, 1)
        return max(1, int(round(days * 252 / 365.25)))
    return None


def result_identity(
    *,
    start: date,
    end: date,
    trades: list[Trade],
) -> str:
    rows = sorted(
        (
            tr.symbol,
            tr.entry_date.isoformat(),
            tr.exit_date.isoformat() if tr.exit_date else "",
            tr.reason,
        )
        for tr in trades
    )
    raw = json.dumps(
        {"start": start.isoformat(), "end": end.isoformat(), "trades": rows},
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def trade_identities(trades: list[Trade]) -> list[tuple[str, str, str, str]]:
    return sorted(
        (
            tr.symbol,
            tr.entry_date.isoformat(),
            tr.exit_date.isoformat() if tr.exit_date else "",
            tr.reason,
        )
        for tr in trades
    )


SIGNAL_SEMANTICS = {
    "field": "signal",
    "meaning": (
        "Today's 52-Week High Breakout scan recommendation "
        "(BUY / HOLD / WATCH / REJECT). Independent of historical book-trade returns."
    ),
}
