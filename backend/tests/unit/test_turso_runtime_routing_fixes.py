"""Unit tests for Turso runtime routing fixes and bypass prevention.

Mocks and fakes only: strictly NO network, NO database, NO Neon, NO Turso, NO localhost.
"""
from __future__ import annotations

import asyncio
from collections import namedtuple
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config.settings import settings
from app.models.strategy_market_data import DailyOhlcv
from app.services.market_data_ingestion import history_backend as hb
from app.services.market_data_ingestion import repository as repo
from app.services.market_data_ingestion import turso_repository as turso_repo
from app.services.strategies.breakout52w import scan_service as b52_scan
from app.services.strategies.ltm import candle_backfill as ltm_backfill
from app.services.strategies.ltm import scan_service as ltm_scan

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 1. Repository: fetch_daily_ohlcv_for_symbols namedtuple adaptation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_daily_ohlcv_for_symbols_turso_tuple_unpacking(monkeypatch: pytest.MonkeyPatch):
    """Turso dict rows must be converted into namedtuples for callers unpacking tuples."""
    monkeypatch.setattr(repo, "_use_turso_history", lambda: True)

    fake_dict_rows = [
        {
            "trade_date": date(2024, 1, 2),
            "symbol": "INFY-EQ",
            "open": 1500.0,
            "high": 1520.0,
            "low": 1490.0,
            "close": 1510.0,
            "volume": 100000,
            "delivery_qty": 50000,
            "delivery_pct": 50.0,
            "turnover": 151000000.0,
            "adtv_20": 150000000.0,
        },
        {
            "trade_date": date(2024, 1, 3),
            "symbol": "INFY-EQ",
            "open": 1510.0,
            "high": 1530.0,
            "low": 1505.0,
            "close": 1525.0,
            "volume": 120000,
            "delivery_qty": 60000,
            "delivery_pct": 50.0,
            "turnover": 183000000.0,
            "adtv_20": 152000000.0,
        },
    ]

    with patch(
        "app.services.market_data_ingestion.turso_repository.fetch_daily_ohlcv_for_symbols",
        new=AsyncMock(return_value=fake_dict_rows),
    ):
        # 3-column query (used by LTM: trade_date, symbol, close)
        rows_3 = await repo.fetch_daily_ohlcv_for_symbols(
            ["INFY-EQ"],
            columns=(DailyOhlcv.trade_date, DailyOhlcv.symbol, DailyOhlcv.close),
        )
        assert len(rows_3) == 2
        # Tuple unpacking test:
        trade_date, sym, close = rows_3[0]
        assert trade_date == date(2024, 1, 2)
        assert sym == "INFY-EQ"
        assert close == 1510.0
        # Attribute access test:
        assert rows_3[0].trade_date == date(2024, 1, 2)
        assert rows_3[0].symbol == "INFY-EQ"
        assert rows_3[0].close == 1510.0

        # 6-column query (used by Breakout52W: trade_date, symbol, high, low, close, volume)
        rows_6 = await repo.fetch_daily_ohlcv_for_symbols(
            ["INFY-EQ"],
            columns=(
                DailyOhlcv.trade_date,
                DailyOhlcv.symbol,
                DailyOhlcv.high,
                DailyOhlcv.low,
                DailyOhlcv.close,
                DailyOhlcv.volume,
            ),
        )
        assert len(rows_6) == 2
        trade_date, sym, high, low, close, volume = rows_6[1]
        assert trade_date == date(2024, 1, 3)
        assert sym == "INFY-EQ"
        assert high == 1530.0
        assert low == 1505.0
        assert close == 1525.0
        assert volume == 120000


# ---------------------------------------------------------------------------
# 2. Repository: Metadata functions route to Turso
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_repository_metadata_functions_route_to_turso(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(repo, "_use_turso_history", lambda: True)

    with (
        patch(
            "app.services.market_data_ingestion.turso_repository.fetch_max_equity_trade_date",
            new=AsyncMock(return_value=date(2026, 9, 18)),
        ) as mock_max_eq,
        patch(
            "app.services.market_data_ingestion.turso_repository.fetch_equity_date_span",
            new=AsyncMock(return_value=(date(2003, 12, 10), date(2026, 9, 18), 5000)),
        ) as mock_span,
        patch(
            "app.services.market_data_ingestion.turso_repository.fetch_max_index_trade_date",
            new=AsyncMock(return_value=date(2026, 9, 18)),
        ) as mock_max_ix,
        patch(
            "app.services.market_data_ingestion.turso_repository.fetch_min_index_trade_date",
            new=AsyncMock(return_value=date(2008, 7, 22)),
        ) as mock_min_ix,
        patch(
            "app.services.market_data_ingestion.turso_repository.fetch_index_row_count",
            new=AsyncMock(return_value=4493),
        ) as mock_cnt_ix,
        patch(
            "app.services.market_data_ingestion.turso_repository.fetch_symbols_present_on",
            new=AsyncMock(return_value={"INFY-EQ", "TCS-EQ"}),
        ) as mock_syms,
        patch(
            "app.services.market_data_ingestion.turso_repository.fetch_index_present",
            new=AsyncMock(return_value=True),
        ) as mock_ix_pres,
        patch(
            "app.services.market_data_ingestion.turso_repository.fetch_symbol_has_sufficient_history",
            new=AsyncMock(return_value=True),
        ) as mock_suff,
        patch(
            "app.services.market_data_ingestion.turso_repository.fetch_recent_equity_before",
            new=AsyncMock(return_value=[{"symbol": "INFY-EQ"}]),
        ) as mock_rec,
    ):
        assert await repo.max_equity_trade_date() == date(2026, 9, 18)
        mock_max_eq.assert_awaited_once()

        assert await repo.equity_date_span("INFY-EQ") == (date(2003, 12, 10), date(2026, 9, 18), 5000)
        mock_span.assert_awaited_once()

        assert await repo.max_index_trade_date("NIFTY500") == date(2026, 9, 18)
        mock_max_ix.assert_awaited_once()

        assert await repo.min_index_trade_date("NIFTY500") == date(2008, 7, 22)
        mock_min_ix.assert_awaited_once()

        assert await repo.index_row_count("NIFTY500") == 4493
        mock_cnt_ix.assert_awaited_once()

        assert await repo.symbols_present_on(date(2026, 9, 18)) == {"INFY-EQ", "TCS-EQ"}
        mock_syms.assert_awaited_once()

        assert await repo.index_present(date(2026, 9, 18)) is True
        mock_ix_pres.assert_awaited_once()

        assert await repo.symbol_has_sufficient_history("INFY-EQ") is True
        mock_suff.assert_awaited_once()

        rec = await repo.fetch_recent_equity_before("INFY-EQ", date(2026, 9, 18))
        assert len(rec) == 1
        mock_rec.assert_awaited_once()


# ---------------------------------------------------------------------------
# 3. Breakout 52W: Routes index fetch to Turso and prevents Postgres fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_breakout52w_load_from_strategy_routes_to_turso(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(b52_scan, "uses_turso", lambda: True)

    Row = namedtuple("DailyOhlcvRow", ["trade_date", "symbol", "high", "low", "close", "volume"])
    fake_equity = [
        Row(date(2024, 1, 2), "INFY-EQ", 1520.0, 1490.0, 1510.0, 100000),
        Row(date(2024, 1, 3), "INFY-EQ", 1530.0, 1505.0, 1525.0, 120000),
    ]
    fake_index = [
        {"trade_date": date(2024, 1, 2), "close": 21000.0},
        {"trade_date": date(2024, 1, 3), "close": 21100.0},
    ]

    mock_db_session = MagicMock()

    with (
        patch("app.services.strategies.breakout52w.scan_service.fetch_daily_ohlcv_for_symbols", new=AsyncMock(return_value=fake_equity)),
        patch("app.services.strategies.breakout52w.scan_service.fetch_index_history", new=AsyncMock(return_value=fake_index)) as mock_idx,
        patch("app.services.strategies.breakout52w.scan_service.AsyncSessionLocal", new=mock_db_session),
    ):
        dates, high_m, low_m, close_m, vol_m, index = await b52_scan._load_from_strategy(["INFY-EQ"], from_date=date(2024, 1, 1))

        # Must NOT open an AsyncSessionLocal
        mock_db_session.assert_not_called()
        mock_idx.assert_awaited_once_with(settings.strategy_index_store_symbol, from_date=date(2024, 1, 2))
        assert dates == [date(2024, 1, 2), date(2024, 1, 3)]
        assert index == {date(2024, 1, 2): 21000.0, date(2024, 1, 3): 21100.0}
        assert high_m["INFY-EQ"][date(2024, 1, 2)] == 1520.0


@pytest.mark.asyncio
async def test_breakout52w_turso_empty_index_raises_controlled_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(b52_scan, "uses_turso", lambda: True)

    Row = namedtuple("DailyOhlcvRow", ["trade_date", "symbol", "high", "low", "close", "volume"])
    fake_equity = [Row(date(2024, 1, 2), "INFY-EQ", 1520.0, 1490.0, 1510.0, 100000)]

    with (
        patch("app.services.strategies.breakout52w.scan_service.fetch_daily_ohlcv_for_symbols", new=AsyncMock(return_value=fake_equity)),
        patch("app.services.strategies.breakout52w.scan_service.fetch_index_history", new=AsyncMock(return_value=[])),
    ):
        with pytest.raises(RuntimeError, match="Turso index history for .* returned no data"):
            await b52_scan._load_from_strategy(["INFY-EQ"], from_date=date(2024, 1, 1))


@pytest.mark.asyncio
async def test_breakout52w_turso_insufficient_sessions_raises_controlled_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(b52_scan, "uses_turso", lambda: True)

    with (
        patch(
            "app.services.strategies.breakout52w.scan_service._load_from_strategy",
            new=AsyncMock(return_value=([date(2024, 1, 2)], {}, {}, {}, {}, {})),
        ),
        patch("app.services.strategies.breakout52w.scan_service._load_from_candles") as mock_candles,
    ):
        with pytest.raises(RuntimeError, match="Turso daily candle history has insufficient sessions"):
            await b52_scan._load_matrices(["INFY-EQ"], from_date=date(2024, 1, 1))
        # Refuses fallback to historical_candles:
        mock_candles.assert_not_called()


# ---------------------------------------------------------------------------
# 4. LTM: Routes index fetch to Turso and prevents Postgres fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ltm_load_matrix_from_strategy_routes_to_turso(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ltm_scan, "uses_turso", lambda: True)

    Row = namedtuple("DailyOhlcvRow", ["trade_date", "symbol", "close"])
    fake_equity = [
        Row(date(2024, 1, 2), "INFY-EQ", 1510.0),
        Row(date(2024, 1, 3), "INFY-EQ", 1525.0),
    ]
    fake_index = [
        {"trade_date": date(2024, 1, 2), "close": 21000.0},
        {"trade_date": date(2024, 1, 3), "close": 21100.0},
    ]

    mock_db_session = MagicMock()

    with (
        patch("app.services.strategies.ltm.scan_service.fetch_daily_ohlcv_for_symbols", new=AsyncMock(return_value=fake_equity)),
        patch("app.services.strategies.ltm.scan_service.fetch_index_history", new=AsyncMock(return_value=fake_index)) as mock_idx,
        patch("app.services.strategies.ltm.scan_service.AsyncSessionLocal", new=mock_db_session),
    ):
        dates, matrix, index = await ltm_scan._load_matrix_from_strategy(["INFY-EQ"])

        mock_db_session.assert_not_called()
        mock_idx.assert_awaited_once_with(settings.strategy_index_store_symbol)
        assert dates == [date(2024, 1, 2), date(2024, 1, 3)]
        assert index == {date(2024, 1, 2): 21000.0, date(2024, 1, 3): 21100.0}
        assert matrix["INFY-EQ"][date(2024, 1, 2)] == 1510.0


@pytest.mark.asyncio
async def test_ltm_turso_empty_index_raises_controlled_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ltm_scan, "uses_turso", lambda: True)

    Row = namedtuple("DailyOhlcvRow", ["trade_date", "symbol", "close"])
    fake_equity = [Row(date(2024, 1, 2), "INFY-EQ", 1510.0)]

    with (
        patch("app.services.strategies.ltm.scan_service.fetch_daily_ohlcv_for_symbols", new=AsyncMock(return_value=fake_equity)),
        patch("app.services.strategies.ltm.scan_service.fetch_index_history", new=AsyncMock(return_value=[])),
    ):
        with pytest.raises(RuntimeError, match="Turso index history for .* returned no data"):
            await ltm_scan._load_matrix_from_strategy(["INFY-EQ"])


@pytest.mark.asyncio
async def test_ltm_turso_insufficient_sessions_raises_controlled_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ltm_scan, "uses_turso", lambda: True)

    with (
        patch(
            "app.services.strategies.ltm.scan_service._load_matrix_from_strategy",
            new=AsyncMock(return_value=([date(2024, 1, 2)], {}, {})),
        ),
        patch("app.services.strategies.ltm.scan_service._load_matrix_from_historical_candles") as mock_candles,
    ):
        with pytest.raises(RuntimeError, match="Turso daily candle history has insufficient sessions"):
            await ltm_scan._load_matrix(["INFY-EQ"])
        mock_candles.assert_not_called()


# ---------------------------------------------------------------------------
# 5. LTM Candle Backfill: strategy_session_count & ensure_strategy_daily_ready
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ltm_candle_backfill_turso_session_count_and_guard(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(hb, "uses_turso", lambda: True)

    with (
        patch(
            "app.services.market_data_ingestion.turso_repository.fetch_distinct_session_count",
            new=AsyncMock(return_value=4000),
        ) as mock_turso_cnt,
        patch(
            "app.services.strategies.ltm.candle_backfill.backfill_daily_ohlcv_from_candles",
        ) as mock_backfill,
    ):
        count = await ltm_backfill.strategy_session_count()
        assert count == 4000
        mock_turso_cnt.assert_awaited_once()

        # 4000 >= 253 -> returns 0, no backfill attempted
        result = await ltm_backfill.ensure_strategy_daily_ready(["INFY-EQ"], min_sessions=253)
        assert result == 0
        mock_backfill.assert_not_called()


@pytest.mark.asyncio
async def test_ltm_candle_backfill_turso_insufficient_sessions_fails_closed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(hb, "uses_turso", lambda: True)

    with (
        patch(
            "app.services.market_data_ingestion.turso_repository.fetch_distinct_session_count",
            new=AsyncMock(return_value=100),
        ),
        patch(
            "app.services.strategies.ltm.candle_backfill.backfill_daily_ohlcv_from_candles",
        ) as mock_backfill,
    ):
        with pytest.raises(RuntimeError, match="Turso daily candle history has insufficient sessions"):
            await ltm_backfill.ensure_strategy_daily_ready(["INFY-EQ"], min_sessions=253)
        mock_backfill.assert_not_called()

