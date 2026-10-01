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


def test_later_quote_day_does_not_hide_missing_sessions():
    """1 Oct can be stored while 21-30 Sep are empty. History must still cover that hole."""
    now = datetime(2026, 10, 1, 10, 0, tzinfo=IST)
    counts = {
        date(2026, 9, 17): 147,
        date(2026, 9, 18): 741,
        date(2026, 10, 1): 747,
    }
    plan = plan_daily_scan_sync(now, date(2026, 10, 1), counts)
    assert plan["quote_session"] == date(2026, 10, 1)
    assert plan["quote_source"] == "FYERS_LIVE_1D"
    assert plan["history_from"] == date(2026, 9, 21)
    assert plan["history_to"] == date(2026, 9, 30)


def test_covered_sessions_skip_history_on_the_morning_scan():
    now = datetime(2026, 10, 1, 10, 0, tzinfo=IST)
    counts = {
        date(2026, 9, 18): 741,
        date(2026, 9, 21): 750,
        date(2026, 9, 22): 750,
        date(2026, 9, 23): 750,
        date(2026, 9, 24): 750,
        date(2026, 9, 25): 750,
        date(2026, 9, 28): 750,
        date(2026, 9, 29): 750,
        date(2026, 9, 30): 750,
        date(2026, 10, 1): 747,
    }
    plan = plan_daily_scan_sync(now, date(2026, 10, 1), counts)
    assert plan["history_from"] is None
    assert plan["history_to"] is None
    assert plan["quote_session"] == date(2026, 10, 1)


def test_before_open_still_fetches_a_hole_behind_today():
    now = datetime(2026, 10, 1, 8, 0, tzinfo=IST)
    counts = {date(2026, 9, 18): 741, date(2026, 10, 1): 747}
    plan = plan_daily_scan_sync(now, date(2026, 10, 1), counts)
    assert plan["quote_session"] is None
    assert plan["history_from"] == date(2026, 9, 21)
    assert plan["history_to"] == date(2026, 9, 30)
