"""Exchange-calendar helpers for expected last completed NSE cash session."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from ..trading_hours_service import CLOSE_TIME, TradingHoursService, trading_hours


def expected_last_completed_session(now: datetime | None = None) -> date:
    """Return the last completed NSE cash trading session date.

    Before market close on a trading day, the previous trading day is expected.
    After close (or on non-trading days), today's session if it was a trading day,
    else walk backward.
    """
    th = trading_hours if trading_hours is not None else TradingHoursService()
    ist = th._to_ist(now)
    d = ist.date()

    def prev_trading_day(start: date) -> date:
        cur = start
        for _ in range(20):
            if th.is_trading_day(datetime(cur.year, cur.month, cur.day)):
                return cur
            cur = cur - timedelta(days=1)
        return start

    if th.is_trading_day(ist):
        if ist.time() >= CLOSE_TIME:
            return d
        # Session still open or pre-open → previous completed session
        return prev_trading_day(d - timedelta(days=1))
    return prev_trading_day(d)
