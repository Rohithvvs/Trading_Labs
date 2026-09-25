"""First Run Scanner of an IST day must pull the latest Fyers daily bar and store it."""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from app.schemas import OHLCVPoint
from app.services.fyers_service import FyersService
from app.services.market_data_service import (
    daily_refresh_kind,
    incremental_history_window,
    merge_quote_bar,
    required_scanner_session,
    session_bar_is_final,
    strategy_rows_from_scan_frames,
    symbol_needs_daily_fyers_fetch,
)
from app.utils.symbol import strategy_daily_symbol

IST = ZoneInfo("Asia/Kolkata")


def _utc(y, m, d, hh, mm=0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def test_required_session_follows_the_nse_cash_day():
    assert required_scanner_session(datetime(2026, 9, 25, 10, 0, tzinfo=IST)) == date(2026, 9, 25)
    assert required_scanner_session(datetime(2026, 9, 25, 8, 0, tzinfo=IST)) == date(2026, 9, 24)
    assert required_scanner_session(datetime(2026, 9, 26, 11, 0, tzinfo=IST)) == date(2026, 9, 25)
    assert required_scanner_session(datetime(2026, 9, 28, 8, 0, tzinfo=IST)) == date(2026, 9, 25)
    assert required_scanner_session(datetime(2026, 9, 28, 10, 0, tzinfo=IST)) == date(2026, 9, 28)


def test_first_scan_of_the_day_fetches_when_yesterday_is_all_we_have():
    now = datetime(2026, 9, 28, 10, 0, tzinfo=IST)
    needs = symbol_needs_daily_fyers_fetch(
        260,
        _utc(2026, 9, 25, 10, 0),
        220,
        updated_at=_utc(2026, 9, 25, 11, 0),
        now=now,
        required_session=date(2026, 9, 28),
    )
    assert needs is True


def test_later_scan_the_same_day_reuses_the_database():
    now = datetime(2026, 9, 28, 14, 0, tzinfo=IST)
    needs = symbol_needs_daily_fyers_fetch(
        260,
        _utc(2026, 9, 28, 4, 0),
        220,
        updated_at=_utc(2026, 9, 28, 5, 0),
        now=now,
        required_session=date(2026, 9, 28),
    )
    assert needs is False


def test_stored_session_is_reused_even_if_it_was_written_on_an_earlier_day():
    """Hosted scans must not re-download every name just because updated_at is old."""
    now = datetime(2026, 9, 28, 8, 0, tzinfo=IST)
    needs = symbol_needs_daily_fyers_fetch(
        260,
        _utc(2026, 9, 25, 10, 0),
        220,
        updated_at=_utc(2026, 9, 25, 11, 0),
        now=now,
        required_session=date(2026, 9, 25),
    )
    assert needs is False


def test_one_day_gap_uses_a_batched_quote_not_per_symbol_history():
    assert (
        daily_refresh_kind(
            260,
            _utc(2026, 9, 24, 10, 0),
            220,
            required_session=date(2026, 9, 25),
        )
        == "latest_bar"
    )
    assert (
        daily_refresh_kind(
            40,
            _utc(2026, 9, 24, 10, 0),
            220,
            required_session=date(2026, 9, 25),
        )
        == "history"
    )


def test_quote_bar_lands_on_the_nse_session_date():
    merged, delta = merge_quote_bar(
        None,
        date(2026, 9, 25),
        {"open": 10, "high": 12, "low": 9, "close": 11, "volume": 100},
    )
    assert len(merged) == 1
    assert len(delta) == 1
    from app.services.market_data_service import candle_session_date

    assert candle_session_date(merged.index[0]) == date(2026, 9, 25)


def test_short_gap_rewrites_the_last_stored_session():
    window = incremental_history_window(
        date(2026, 9, 25),
        today=date(2026, 9, 28),
        target=date(2026, 9, 28),
        refresh_latest=False,
    )
    assert window is not None
    start, end, mode = window
    assert start == date(2026, 9, 25)
    assert end == date(2026, 9, 28)
    assert mode == "incremental"


def test_current_bar_skips_fyers_until_the_daily_refresh():
    assert (
        incremental_history_window(
            date(2026, 9, 28),
            today=date(2026, 9, 28),
            target=date(2026, 9, 28),
            refresh_latest=False,
        )
        is None
    )
    refreshed = incremental_history_window(
        date(2026, 9, 28),
        today=date(2026, 9, 28),
        target=date(2026, 9, 28),
        refresh_latest=True,
    )
    assert refreshed == (date(2026, 9, 28), date(2026, 9, 28), "daily_refresh")


def test_strategy_symbol_is_the_equity_store_identity():
    assert strategy_daily_symbol("INFY") == "INFY-EQ"
    assert strategy_daily_symbol("NSE:INFY-EQ") == "INFY-EQ"
    assert strategy_daily_symbol("NIFTY500-INDEX") == "NIFTY500-INDEX"


def test_forming_bar_is_kept_out_of_the_eod_store_until_the_close():
    stamp = _utc(2026, 9, 28, 4, 0)
    frame = pd.DataFrame(
        {"open": [10.0], "high": [12.0], "low": [9.0], "close": [11.0], "volume": [1000]},
        index=pd.DatetimeIndex([stamp]),
    )
    pending = [("INFY", "1D", frame)]
    assert strategy_rows_from_scan_frames(pending, now=datetime(2026, 9, 28, 11, 0, tzinfo=IST)) == []
    assert session_bar_is_final(date(2026, 9, 28), datetime(2026, 9, 28, 11, 0, tzinfo=IST)) is False

    stored = strategy_rows_from_scan_frames(pending, now=datetime(2026, 9, 28, 16, 0, tzinfo=IST))
    assert len(stored) == 1
    assert stored[0]["symbol"] == "INFY-EQ"
    assert stored[0]["trade_date"] == date(2026, 9, 28)
    assert stored[0]["source"] == "FYERS"
    assert stored[0]["close"] == 11.0


def test_fetch_incremental_does_not_call_fyers_when_today_is_already_stored(monkeypatch):
    service = FyersService()
    monkeypatch.setattr(
        "app.services.market_data_service.required_scanner_session",
        lambda now=None: date(2026, 9, 28),
    )
    monkeypatch.setattr(
        "app.utils.datetime_utils.ist_now",
        lambda: datetime(2026, 9, 28, 10, 0, tzinfo=IST),
    )

    def _boom():
        raise AssertionError("Fyers client should not be created")

    monkeypatch.setattr(service, "_client", _boom)
    cached = [
        OHLCVPoint(
            timestamp=_utc(2026, 9, 28, 4, 0),
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        )
    ]
    assert service.fetch_incremental_ohlcv("INFY-EQ", cached, refresh_latest=False) == []


def test_daily_refresh_requests_the_latest_session(monkeypatch):
    service = FyersService()
    monkeypatch.setattr(
        "app.services.market_data_service.required_scanner_session",
        lambda now=None: date(2026, 9, 28),
    )
    monkeypatch.setattr(
        "app.utils.datetime_utils.ist_now",
        lambda: datetime(2026, 9, 28, 10, 0, tzinfo=IST),
    )
    seen: dict = {}

    monkeypatch.setattr(service, "_client", lambda: object())
    monkeypatch.setattr(service, "_is_blacklisted", lambda _symbol: False)

    def _history(_client, payload, _symbol):
        seen["payload"] = payload
        return {"candles": [[1_758_823_500, 10, 12, 9, 11, 1000]]}

    monkeypatch.setattr(service, "_request_history_with_retries", _history)
    cached = [
        OHLCVPoint(
            timestamp=_utc(2026, 9, 25, 10, 0),
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        )
    ]
    bars = service.fetch_incremental_ohlcv("INFY-EQ", cached, refresh_latest=False)
    assert seen["payload"]["range_from"] == "2026-09-25"
    assert seen["payload"]["range_to"] == "2026-09-28"
    assert seen["payload"]["resolution"] == "1D"
    assert len(bars) == 1
    assert bars[0].close == 11


@pytest.mark.asyncio
async def test_persist_writes_completed_bars(monkeypatch):
    stamp = _utc(2026, 9, 25, 10, 0)
    frame = pd.DataFrame(
        {"open": [10.0], "high": [12.0], "low": [9.0], "close": [11.0], "volume": [50]},
        index=pd.DatetimeIndex([stamp]),
    )
    captured: dict = {}

    async def _upsert(rows):
        captured["rows"] = rows
        return (len(rows), 0)

    class _Provider:
        async def fetch_index_range(self, start, end):
            captured["index_range"] = (start, end)
            return [
                {
                    "trade_date": date(2026, 9, 25),
                    "symbol": "NIFTY500",
                    "open": 1,
                    "high": 1,
                    "low": 1,
                    "close": 1,
                    "volume": 0,
                    "source": "FYERS",
                }
            ]

    async def _upsert_index(rows):
        captured["index_rows"] = rows
        return len(rows)

    monkeypatch.setattr(
        "app.services.market_data_ingestion.repository.upsert_daily_bars",
        _upsert,
    )
    monkeypatch.setattr(
        "app.services.market_data_ingestion.repository.upsert_index_bars",
        _upsert_index,
    )
    monkeypatch.setattr(
        "app.services.market_data_ingestion.providers.fyers_eod.FyersEodProvider",
        _Provider,
    )

    from app.services.market_data_service import persist_fyers_scan_bars

    saved = await persist_fyers_scan_bars(
        [("INFY", "1D", frame)],
        refresh_index=True,
        now=datetime(2026, 9, 28, 10, 0, tzinfo=IST),
    )
    assert saved["daily_upserted"] == 1
    assert captured["rows"][0]["symbol"] == "INFY-EQ"
    assert captured["rows"][0]["trade_date"] == date(2026, 9, 25)
    assert captured["rows"][0]["source"] == "FYERS"
    assert captured["index_range"] == (date(2026, 9, 25), date(2026, 9, 25))
    assert saved["index_upserted"] == 1
