"""NSE cash-market holiday calendar used by scanners and session overlay."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.services.market_data_ingestion.calendar_utils import expected_last_completed_session
from app.services.trading_hours_service import TradingHoursService


def _hours() -> TradingHoursService:
    TradingHoursService._holidays_loaded = False
    TradingHoursService._holiday_cache = {}
    return TradingHoursService()


def test_raksha_bandhan_2026_is_not_a_trading_holiday():
    th = _hours()
    friday = datetime(2026, 8, 28, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert th.is_nse_holiday(friday) is False
    assert th.is_trading_day(friday) is True


def test_ganesh_chaturthi_2026_is_a_trading_holiday():
    th = _hours()
    day = datetime(2026, 9, 14, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert th.is_nse_holiday(day) is True
    assert th.is_trading_day(day) is False


def test_sunday_after_raksha_bandhan_uses_friday_session():
    sunday = datetime(2026, 8, 30, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert expected_last_completed_session(sunday) == date(2026, 8, 28)
