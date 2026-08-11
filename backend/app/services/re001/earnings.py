"""RE-001 earnings blackout — reuses event_calendar table (no parallel stack).

Reject BUY when scheduled EARNINGS are within 3 trading days of the trigger.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("app.re001")

EARNINGS_BLACKOUT_TRADING_DAYS = 3


def _as_date(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00")).date()
    except Exception:
        return None


def trading_days_between(start: date, end: date) -> int | None:
    """Count trading days from start (exclusive) to end (inclusive).

    Returns 0 if end == start (earnings today). Uses TradingHoursService.
    """
    if end < start:
        return None
    if end == start:
        return 0
    try:
        from ..trading_hours_service import TradingHoursService

        th = TradingHoursService()
        count = 0
        cur = start
        # walk calendar days; count trading days after start up to and including end
        while cur < end:
            cur = cur + timedelta(days=1)
            if th.is_trading_day(datetime(cur.year, cur.month, cur.day)):
                count += 1
            # safety bound
            if (cur - start).days > 60:
                break
        return count
    except Exception as exc:
        logger.debug("RE-001 trading_days_between fallback | %s", exc)
        # Weekend-aware fallback
        count = 0
        cur = start
        while cur < end:
            cur = cur + timedelta(days=1)
            if cur.weekday() < 5:
                count += 1
            if (cur - start).days > 60:
                break
        return count


def lookup_next_earnings(
    symbol: str,
    *,
    as_of: datetime | None = None,
    days_ahead: int = 30,
) -> dict[str, Any]:
    """Query event_calendar for next company EARNINGS.

    Fail-open: if DB unavailable or no row, earnings_clear=True (unknown ≠ block).
    """
    as_of = as_of or datetime.now(timezone.utc)
    as_of_d = _as_date(as_of) or date.today()
    sym = (symbol or "").strip().upper().replace("NSE:", "").replace("-EQ", "")
    if not sym:
        return {
            "next_earnings_date": None,
            "trading_days_until_earnings": None,
            "earnings_clear": True,
            "source": "none",
        }

    try:
        from sqlalchemy import and_, select

        from ...db.session import SessionLocal
        from ...models.event_calendar import EventCalendar

        db = SessionLocal()
        try:
            # Load near-term company EARNINGS rows and filter in Python for robust
            # aware/naive datetime comparison (event_date storage varies).
            horizon = as_of_d + timedelta(days=days_ahead)
            stmt = (
                select(EventCalendar)
                .where(
                    and_(
                        EventCalendar.symbol == sym,
                        EventCalendar.event_type == "EARNINGS",
                    )
                )
                .order_by(EventCalendar.event_date.asc())
            )
            rows = list(db.execute(stmt).scalars().all())
            next_row = None
            for row in rows:
                ed = _as_date(row.event_date)
                if ed is None:
                    continue
                if as_of_d <= ed <= horizon:
                    next_row = row
                    break

            if next_row is None:
                return {
                    "next_earnings_date": None,
                    "trading_days_until_earnings": None,
                    "earnings_clear": True,
                    "source": "event_calendar_empty",
                }

            ed = _as_date(next_row.event_date)
            td = trading_days_between(as_of_d, ed) if ed else None
            clear = True
            if td is not None and td <= EARNINGS_BLACKOUT_TRADING_DAYS:
                clear = False
            return {
                "next_earnings_date": ed.isoformat() if ed else None,
                "trading_days_until_earnings": td,
                "earnings_clear": clear,
                "source": "event_calendar",
            }
        finally:
            db.close()
    except Exception as exc:
        logger.debug(
            "RE-001 earnings lookup failed (fail-open clear) | symbol=%s | err=%s",
            sym,
            exc,
        )
        return {
            "next_earnings_date": None,
            "trading_days_until_earnings": None,
            "earnings_clear": True,
            "source": "error_fail_open",
            "error": str(exc),
        }


def earnings_info_from_override(
    override: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Normalize optional context override for tests / injected calendar data."""
    if not override:
        return None
    clear = override.get("earnings_clear")
    if clear is None and override.get("trading_days_until_earnings") is not None:
        try:
            td = int(override["trading_days_until_earnings"])
            clear = td > EARNINGS_BLACKOUT_TRADING_DAYS
        except (TypeError, ValueError):
            clear = True
    if clear is None:
        clear = True
    return {
        "next_earnings_date": override.get("next_earnings_date"),
        "trading_days_until_earnings": override.get("trading_days_until_earnings"),
        "earnings_clear": bool(clear),
        "source": override.get("source") or "override",
    }
