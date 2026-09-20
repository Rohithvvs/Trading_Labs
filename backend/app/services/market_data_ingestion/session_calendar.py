"""Classify anomaly trade_dates for repair preview. No network, no DB.

Weekends are always non-trading. NSE holidays are used only when that year
exists in the stored ``backend/data/nse_trading_holidays.json``. Missing years
are WEEKDAY_UNKNOWN — holidays are never invented.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

_WEEKDAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def default_holidays_path() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "nse_trading_holidays.json"


def load_holiday_years(path: Path | None = None) -> dict[str, set[str]]:
    holidays_path = path or default_holidays_path()
    if not holidays_path.exists():
        return {}
    data = json.loads(holidays_path.read_text(encoding="utf-8"))
    raw = data.get("holidays") or {}
    return {str(year): set(dates) for year, dates in raw.items()}


def classify_trade_date(
    day: date,
    *,
    holidays_by_year: dict[str, set[str]] | None = None,
) -> dict[str, Any]:
    """Return calendar_status and whether FYERS should be called."""
    dow = _WEEKDAY_NAMES[day.weekday()]
    base = {
        "trade_date": day.isoformat(),
        "day_of_week": dow,
        "weekday_number": day.weekday(),
    }
    if day.weekday() >= 5:
        return {
            **base,
            "calendar_status": "WEEKEND_NON_TRADING_DAY",
            "should_call_provider": False,
            "phantom_verdict": "NON_TRADING_DAY_PHANTOM",
        }
    years = holidays_by_year if holidays_by_year is not None else load_holiday_years()
    year_key = str(day.year)
    if year_key not in years:
        return {
            **base,
            "calendar_status": "WEEKDAY_UNKNOWN",
            "should_call_provider": True,
            "phantom_verdict": None,
        }
    if day.isoformat() in years[year_key]:
        return {
            **base,
            "calendar_status": "NSE_HOLIDAY_NON_TRADING_DAY",
            "should_call_provider": False,
            "phantom_verdict": "NON_TRADING_DAY_PHANTOM",
        }
    return {
        **base,
        "calendar_status": "EXPECTED_NSE_TRADING_SESSION",
        "should_call_provider": True,
        "phantom_verdict": None,
    }
