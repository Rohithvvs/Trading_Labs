"""Calendar classification for repair preview. No network."""
from __future__ import annotations

from datetime import date

import pytest

from app.services.market_data_ingestion.session_calendar import classify_trade_date, load_holiday_years

pytestmark = pytest.mark.unit


def test_saturday_and_sunday_are_weekend():
    sat = classify_trade_date(date(2026, 8, 1))
    sun = classify_trade_date(date(2026, 8, 2))
    assert sat["calendar_status"] == "WEEKEND_NON_TRADING_DAY"
    assert sat["day_of_week"] == "Saturday"
    assert sat["should_call_provider"] is False
    assert sun["day_of_week"] == "Sunday"
    assert sun["should_call_provider"] is False


def test_stored_2026_holiday_without_inventing_dates():
    holidays = load_holiday_years()
    assert "2026" in holidays
    assert "2026-01-26" in holidays["2026"]
    day = classify_trade_date(date(2026, 1, 26), holidays_by_year=holidays)
    assert day["calendar_status"] == "NSE_HOLIDAY_NON_TRADING_DAY"
    assert day["should_call_provider"] is False


def test_weekday_with_year_in_file_is_expected_session():
    day = classify_trade_date(date(2026, 8, 3), holidays_by_year=load_holiday_years())
    assert day["day_of_week"] == "Monday"
    assert day["calendar_status"] == "EXPECTED_NSE_TRADING_SESSION"
    assert day["should_call_provider"] is True


def test_year_absent_from_file_is_unknown_not_invented_holiday():
    day = classify_trade_date(date(2009, 5, 18), holidays_by_year={"2026": set()})
    assert day["calendar_status"] == "WEEKDAY_UNKNOWN"
    assert day["should_call_provider"] is True
