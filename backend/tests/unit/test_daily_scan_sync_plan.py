"""Indicator-scan Fyers refresh must not download per-symbol history for today."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.services.daily_scan_sync_service import plan_daily_scan_sync

IST = ZoneInfo("Asia/Kolkata")


def test_after_close_one_day_gap_uses_quotes_only():
    """IND-20260925-009 started at 16:01 IST. Today's bar is a quote, not 755 history calls."""
    now = datetime(2026, 9, 25, 16, 1, tzinfo=IST)
    plan = plan_daily_scan_sync(now, date(2026, 9, 24))
    assert plan["quote_session"] == date(2026, 9, 25)
    assert plan["quote_source"] == "FYERS"
    assert plan["history_from"] is None
    assert plan["history_to"] is None


def test_during_market_keeps_older_gap_on_history_and_today_on_quotes():
    now = datetime(2026, 9, 25, 11, 0, tzinfo=IST)
    plan = plan_daily_scan_sync(now, date(2026, 9, 23))
    assert plan["quote_session"] == date(2026, 9, 25)
    assert plan["quote_source"] == "FYERS_LIVE_1D"
    assert plan["history_from"] == date(2026, 9, 24)
    assert plan["history_to"] == date(2026, 9, 24)


def test_before_open_with_latest_session_stored_fetches_nothing():
    now = datetime(2026, 9, 25, 8, 0, tzinfo=IST)
    plan = plan_daily_scan_sync(now, date(2026, 9, 24))
    assert plan["quote_session"] is None
    assert plan["history_from"] is None
