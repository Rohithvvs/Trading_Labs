"""Strategy Tester scan universe + live market-data wiring."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.strategy_tester.indicators import BarSeries
from app.services.strategy_tester.scan_service import (
    apply_live_bar,
    ensure_universe_market_data,
    fill_missing_completed_bar_series,
    load_universe,
    overlay_live_session,
    parse_run_dates,
    prepare_scan_market_data,
    _series_from_rows,
)


def _instrument(i: int) -> SimpleNamespace:
    return SimpleNamespace(
        symbol=f"S{i}",
        company_name=f"Company {i}",
        universe_symbol=f"S{i}-EQ",
    )


def _series(n: int = 5, start: date = date(2026, 8, 20)) -> BarSeries:
    dates = [start + timedelta(days=i) for i in range(n)]
    close = [100.0 + i for i in range(n)]
    return BarSeries(
        dates=list(dates),
        open=list(close),
        high=[c + 1 for c in close],
        low=[c - 1 for c in close],
        close=list(close),
        volume=[1000.0] * n,
    )


@pytest.mark.asyncio
async def test_load_universe_uses_full_nifty500_live_set():
    instruments = [_instrument(i) for i in range(755)]
    with patch(
        "app.services.strategy_tester.scan_service.UniverseService.list_active_instruments",
        new=AsyncMock(return_value=instruments),
    ) as listed, patch(
        "app.services.strategy_tester.scan_service.load_unique_nifty500_csv_rows",
        return_value=[],
    ) as csv_load:
        rows = await load_universe("ALL_755")
    listed.assert_awaited_with("NIFTY500")
    csv_load.assert_not_called()
    assert len(rows) == 755
    assert rows[0]["symbol"] == "S0"
    assert rows[0]["store_symbol"] == "S0-EQ"


@pytest.mark.asyncio
async def test_load_universe_backfills_csv_when_stocks_master_is_truncated():
    instruments = [_instrument(i) for i in range(65)]
    csv_rows = [{"canonical_symbol": f"S{i}", "company_name": f"Csv {i}", "symbol": f"S{i}"} for i in range(755)]
    with patch(
        "app.services.strategy_tester.scan_service.UniverseService.list_active_instruments",
        new=AsyncMock(return_value=instruments),
    ), patch(
        "app.services.strategy_tester.scan_service.load_unique_nifty500_csv_rows",
        return_value=csv_rows,
    ):
        rows = await load_universe("ALL_755")
    assert len(rows) == 755
    assert {r["symbol"] for r in rows} == {f"S{i}" for i in range(755)}


@pytest.mark.asyncio
async def test_load_universe_drops_dummy_placeholders():
    instruments = [
        _instrument(0),
        SimpleNamespace(symbol="DUMMYALCAR", company_name="Dummy", universe_symbol="DUMMYALCAR-EQ"),
        SimpleNamespace(symbol="DUMMYVEDL1", company_name="Dummy 1", universe_symbol="DUMMYVEDL1-EQ"),
    ]
    with patch(
        "app.services.strategy_tester.scan_service.UniverseService.list_active_instruments",
        new=AsyncMock(return_value=instruments),
    ), patch(
        "app.services.strategy_tester.scan_service.load_unique_nifty500_csv_rows",
        return_value=[{"canonical_symbol": "S0", "company_name": "Company 0", "symbol": "S0"}],
    ):
        rows = await load_universe("ALL_755")
    assert [r["symbol"] for r in rows] == ["S0"]
    assert all(not str(r["symbol"]).startswith("DUMMY") for r in rows)


def test_apply_live_bar_replaces_same_session_and_appends_next():
    series = _series(n=2, start=date(2026, 8, 27))
    apply_live_bar(
        series,
        date(2026, 8, 28),
        {"open": 110, "high": 112, "low": 109, "close": 111, "volume": 5000},
    )
    assert series.dates[-1] == date(2026, 8, 28)
    assert series.close[-1] == 111.0
    apply_live_bar(
        series,
        date(2026, 8, 28),
        {"open": 111, "high": 115, "low": 110, "close": 114, "volume": 9000},
    )
    assert series.dates.count(date(2026, 8, 28)) == 1
    assert series.close[-1] == 114.0
    assert series.volume[-1] == 9000.0


def test_apply_live_bar_does_not_invent_a_cloned_next_session():
    """Weekend FYERS quotes still print Thursday. Do not stamp them as Friday."""
    series = _series(n=1, start=date(2026, 8, 27))
    last = {
        "open": series.open[-1],
        "high": series.high[-1],
        "low": series.low[-1],
        "close": series.close[-1],
        "volume": series.volume[-1],
    }
    apply_live_bar(series, date(2026, 8, 28), last)
    assert series.dates == [date(2026, 8, 27)]
    assert series.close[-1] == last["close"]


def test_series_from_rows_drops_duplicate_dates_and_trailing_clones():
    rows = [
        (date(2026, 8, 26), 100.0, 101.0, 99.0, 100.5, 1000.0),
        (date(2026, 8, 27), 1685.5, 1717.0, 1664.0, 1696.8, 443550.0),
        (date(2026, 8, 27), 1685.5, 1717.0, 1664.0, 1696.8, 443550.0),
        (date(2026, 8, 28), 1685.5, 1717.0, 1664.0, 1696.8, 443550.0),
    ]
    series = _series_from_rows(rows)
    assert series.dates == [date(2026, 8, 26), date(2026, 8, 27)]
    assert series.close[-1] == 1696.8


def test_series_from_rows_drops_holidays_weekends_and_mid_series_clones():
    rows = [
        (date(2025, 12, 24), 100.0, 101.0, 99.0, 100.0, 1000.0),  # Wednesday
        (date(2025, 12, 25), 100.0, 101.0, 99.0, 100.0, 1000.0),  # Christmas holiday clone
        (date(2025, 12, 26), 102.0, 103.0, 101.0, 102.5, 1100.0),  # Friday
        (date(2025, 12, 27), 102.0, 103.0, 101.0, 102.5, 1100.0),  # Saturday
        (date(2025, 12, 29), 104.0, 105.0, 103.0, 104.0, 1200.0),  # Monday
    ]
    series = _series_from_rows(rows)
    assert series.dates == [date(2025, 12, 24), date(2025, 12, 26), date(2025, 12, 29)]
    assert series.close == [100.0, 102.5, 104.0]


@pytest.mark.asyncio
async def test_ensure_universe_market_data_forwards_live_symbols():
    with patch(
        "app.services.market_data_ingestion.ensure.ensure_latest_market_data",
        new=AsyncMock(return_value={"status": "ALREADY_FRESH"}),
    ) as ensure:
        result = await ensure_universe_market_data(["RELIANCE-EQ", "TCS-EQ"])
    assert result["status"] == "ALREADY_FRESH"
    ensure.assert_awaited()
    kwargs = ensure.await_args.kwargs
    assert kwargs["symbols"] == ["RELIANCE-EQ", "TCS-EQ"]
    assert kwargs["trigger_source"] == "SCANNER"


@pytest.mark.asyncio
async def test_overlay_live_session_applies_fyers_quotes_when_window_includes_today():
    series_map = {"AAA": _series(n=3, start=date(2026, 8, 26))}
    live_bar = {"open": 200.0, "high": 205.0, "low": 199.0, "close": 204.0, "volume": 12_000.0}
    with (
        patch(
            "app.services.strategy_tester.scan_service.fill_missing_completed_bar_series",
            new=AsyncMock(side_effect=lambda series, symbols, **kw: (series, kw.get("benchmark"), "stored_eod")),
        ),
        patch(
            "app.services.strategies.breakout52w.session_overlay.should_overlay_session",
            return_value=date(2026, 8, 28),
        ),
        patch(
            "app.services.strategies.breakout52w.session_overlay.fetch_live_session_bars",
            new=AsyncMock(return_value=({"AAA": live_bar}, 24000.0)),
        ),
        patch(
            "app.services.market_data_ingestion.repository.upsert_daily_bars",
            new=AsyncMock(return_value=(1, 0)),
        ),
        patch(
            "app.services.market_data_ingestion.repository.upsert_index_bars",
            new=AsyncMock(return_value=(1, 0)),
        ),
    ):
        out, bench, source = await overlay_live_session(
            series_map,
            ["AAA"],
            end_date=date(2026, 8, 28),
            benchmark=_series(n=3, start=date(2026, 8, 26)),
        )
    assert source == "live_session"
    assert out["AAA"].dates[-1] == date(2026, 8, 28)
    assert out["AAA"].close[-1] == 204.0
    assert bench is not None
    assert bench.close[-1] == 24000.0


@pytest.mark.asyncio
async def test_overlay_fetches_quotes_when_helper_is_none_but_end_date_is_live_session(monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    series_map = {"AAA": _series(n=3, start=date(2026, 9, 2))}
    live_bar = {"open": 200.0, "high": 205.0, "low": 199.0, "close": 204.0, "volume": 12_000.0}
    friday_noon = datetime(2026, 9, 4, 12, 18, tzinfo=ZoneInfo("Asia/Kolkata"))

    class _Hours:
        def now_ist(self):
            return friday_noon

    monkeypatch.setattr(
        "app.services.trading_hours_service.trading_hours",
        _Hours(),
        raising=False,
    )
    with (
        patch(
            "app.services.strategy_tester.scan_service.fill_missing_completed_bar_series",
            new=AsyncMock(side_effect=lambda series, symbols, **kw: (series, kw.get("benchmark"), "stored_eod")),
        ),
        patch(
            "app.services.strategies.breakout52w.session_overlay.should_overlay_session",
            return_value=None,
        ),
        patch(
            "app.services.strategies.breakout52w.session_overlay.fetch_live_session_bars",
            new=AsyncMock(return_value=({"AAA": live_bar}, 24000.0)),
        ) as quotes,
        patch(
            "app.services.market_data_ingestion.repository.upsert_daily_bars",
            new=AsyncMock(return_value=(1, 0)),
        ),
        patch(
            "app.services.market_data_ingestion.repository.upsert_index_bars",
            new=AsyncMock(return_value=(1, 0)),
        ),
    ):
        out, _bench, source = await overlay_live_session(
            series_map,
            ["AAA"],
            end_date=date(2026, 9, 4),
            benchmark=_series(n=3, start=date(2026, 9, 2)),
        )
    quotes.assert_awaited()
    assert source == "live_session"
    assert out["AAA"].dates[-1] == date(2026, 9, 4)
    assert out["AAA"].close[-1] == 204.0


@pytest.mark.asyncio
async def test_overlay_skips_weekend_quote_stamp():
    series_map = {"AAA": _series(n=2, start=date(2026, 8, 26))}
    live_bar = {"open": 1690.0, "high": 1698.0, "low": 1685.0, "close": 1696.8, "volume": 279609.25}
    with (
        patch(
            "app.services.strategy_tester.scan_service.fill_missing_completed_bar_series",
            new=AsyncMock(side_effect=lambda series, symbols, **kw: (series, kw.get("benchmark"), "stored_eod")),
        ),
        patch(
            "app.services.strategies.breakout52w.session_overlay.should_overlay_session",
            return_value=None,
        ),
        patch(
            "app.services.strategies.breakout52w.session_overlay.fetch_live_session_bars",
            new=AsyncMock(return_value=({"AAA": live_bar}, 23528.55)),
        ) as quotes,
    ):
        out, _bench, source = await overlay_live_session(
            series_map,
            ["AAA"],
            end_date=date(2026, 8, 29),
            benchmark=_series(n=2, start=date(2026, 8, 26)),
        )
    quotes.assert_not_awaited()
    assert source == "stored_eod"
    assert out["AAA"].dates[-1] == date(2026, 8, 27)


@pytest.mark.asyncio
async def test_overlay_does_not_stamp_thursday_quotes_as_friday():
    series = _series(n=2, start=date(2026, 8, 26))
    clone = {
        "open": series.open[-1],
        "high": series.high[-1],
        "low": series.low[-1],
        "close": series.close[-1],
        "volume": series.volume[-1],
    }
    series_map = {"AAA": series}
    with (
        patch(
            "app.services.strategy_tester.scan_service.fill_missing_completed_bar_series",
            new=AsyncMock(side_effect=lambda series, symbols, **kw: (series, kw.get("benchmark"), "stored_eod")),
        ),
        patch(
            "app.services.strategies.breakout52w.session_overlay.should_overlay_session",
            return_value=None,
        ),
        patch(
            "app.services.market_data_ingestion.calendar_utils.expected_last_completed_session",
            return_value=date(2026, 8, 28),
        ),
        patch(
            "app.services.strategies.breakout52w.session_overlay.fetch_live_session_bars",
            new=AsyncMock(return_value=({"AAA": clone}, series.close[-1])),
        ),
        patch(
            "app.services.market_data_ingestion.repository.upsert_daily_bars",
            new=AsyncMock(return_value=(1, 0)),
        ) as upserted,
        patch(
            "app.services.market_data_ingestion.repository.upsert_index_bars",
            new=AsyncMock(return_value=(1, 0)),
        ),
    ):
        out, _bench, source = await overlay_live_session(
            series_map,
            ["AAA"],
            end_date=date(2026, 8, 29),
            benchmark=_series(n=2, start=date(2026, 8, 26)),
        )
    assert out["AAA"].dates[-1] == date(2026, 8, 27)
    assert source == "stored_eod"
    upserted.assert_not_awaited()


@pytest.mark.asyncio
async def test_fill_missing_completed_bar_series_appends_fyers_history_up_to_target():
    series_map = {"AAA": _series(n=2, start=date(2026, 8, 26))}
    bench = _series(n=2, start=date(2026, 8, 26))
    completed = {
        date(2026, 8, 27): {"AAA": {"high": 120.0, "low": 110.0, "close": 118.0, "volume": 8000.0}},
        date(2026, 8, 28): {"AAA": {"high": 125.0, "low": 117.0, "close": 124.0, "volume": 9000.0}},
    }
    with (
        patch(
            "app.services.market_data_ingestion.calendar_utils.expected_last_completed_session",
            return_value=date(2026, 8, 28),
        ),
        patch(
            "app.services.strategies.breakout52w.session_overlay.fetch_missing_completed_bars",
            new=AsyncMock(return_value=(completed, {date(2026, 8, 28): 23500.0}, [], [])),
        ),
        patch(
            "app.services.market_data_ingestion.repository.upsert_daily_bars",
            new=AsyncMock(return_value=(2, 0)),
        ),
        patch(
            "app.services.market_data_ingestion.repository.upsert_index_bars",
            new=AsyncMock(return_value=(1, 0)),
        ),
    ):
        out, bench_out, source = await fill_missing_completed_bar_series(
            series_map,
            ["AAA"],
            end_date=date(2026, 8, 28),
            benchmark=bench,
        )
    assert source == "completed_history"
    assert out["AAA"].dates[-1] == date(2026, 8, 28)
    assert out["AAA"].close[-1] == 124.0
    assert bench_out is not None
    assert bench_out.close[-1] == 23500.0


@pytest.mark.asyncio
async def test_fill_does_not_skip_stale_symbols_when_one_name_is_already_current():
    """A liquid name on Friday must not skip Thursday names — that mixed tape ≠ Pine Screener."""
    series_map = {
        "AAA": _series(n=3, start=date(2026, 8, 26)),
        "BBB": _series(n=1, start=date(2026, 8, 26)),
    }
    bench = _series(n=3, start=date(2026, 8, 26))
    completed = {
        date(2026, 8, 27): {"BBB": {"high": 120.0, "low": 110.0, "close": 118.0, "volume": 8000.0}},
        date(2026, 8, 28): {"BBB": {"high": 125.0, "low": 117.0, "close": 124.0, "volume": 9000.0}},
    }
    with (
        patch(
            "app.services.market_data_ingestion.calendar_utils.expected_last_completed_session",
            return_value=date(2026, 8, 28),
        ),
        patch(
            "app.services.strategies.breakout52w.session_overlay.fetch_missing_completed_bars",
            new=AsyncMock(return_value=(completed, {date(2026, 8, 28): 23500.0}, [], [])),
        ) as fetched,
        patch(
            "app.services.market_data_ingestion.repository.upsert_daily_bars",
            new=AsyncMock(return_value=(2, 0)),
        ),
        patch(
            "app.services.market_data_ingestion.repository.upsert_index_bars",
            new=AsyncMock(return_value=(1, 0)),
        ),
    ):
        out, _bench, source = await fill_missing_completed_bar_series(
            series_map,
            ["AAA", "BBB"],
            end_date=date(2026, 8, 28),
            benchmark=bench,
        )
    fetched.assert_awaited()
    assert fetched.await_args.args[0] == ["BBB"]


@pytest.mark.asyncio
async def test_fill_skips_universe_fetch_when_history_is_a_clone():
    series = _series(n=2, start=date(2026, 8, 26))
    clone_bar = {
        "open": series.open[-1],
        "high": series.high[-1],
        "low": series.low[-1],
        "close": series.close[-1],
        "volume": series.volume[-1],
    }
    with (
        patch(
            "app.services.market_data_ingestion.calendar_utils.expected_last_completed_session",
            return_value=date(2026, 8, 28),
        ),
        patch(
            "app.services.strategies.breakout52w.session_overlay.fetch_missing_completed_bars",
            new=AsyncMock(return_value=({date(2026, 8, 28): {"AAA": clone_bar}}, {}, [], [])),
        ) as fetched,
    ):
        out, _bench, source = await fill_missing_completed_bar_series(
            {"AAA": series},
            ["AAA"],
            end_date=date(2026, 8, 28),
            benchmark=_series(n=2, start=date(2026, 8, 26)),
        )
    assert source == "stored_eod"
    assert out["AAA"].dates[-1] == date(2026, 8, 27)
    assert fetched.await_count == 1


def test_parse_run_dates_advances_stale_end_date_to_ist_today():
    from app.services.strategy_tester.scan_service import _ist_today

    today = _ist_today()
    stale = (today - timedelta(days=5)).isoformat()
    start, end = parse_run_dates("2024-01-01", stale)
    assert start == date(2024, 1, 1)
    assert end == today


@pytest.mark.asyncio
async def test_prepare_scan_market_data_uses_daily_ohlcv_then_live_overlay():
    stored = {"RELIANCE": _series(n=4, start=date(2026, 8, 24))}
    with (
        patch(
            "app.services.strategy_tester.scan_service.load_bar_series",
            new=AsyncMock(return_value=stored),
        ),
        patch(
            "app.services.strategy_tester.scan_service.fill_missing_from_historical_candles",
            new=AsyncMock(return_value=0),
        ),
        patch(
            "app.services.strategy_tester.scan_service.load_benchmark_series",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.strategy_tester.scan_service.overlay_live_session",
            new=AsyncMock(return_value=(stored, None, "live_session")),
        ) as overlay,
    ):
        series, bench, source = await prepare_scan_market_data(
            ["RELIANCE"],
            from_date=date(2025, 1, 1),
            to_date=date(2026, 8, 28),
            need_benchmark=False,
        )
    overlay.assert_awaited()
    assert series is stored
    assert bench is None
    assert source == "daily_ohlcv+live_session"
