"""Turso candle history must not silently read or write Postgres."""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.db.turso import InMemoryTursoClient, open_probed_turso_client
from app.services.indicator_scanner.ta_functions import sma
from app.services.market_data_ingestion import ensure as ens
from app.services.market_data_ingestion import repository as repo
from app.services.market_data_ingestion.candle_diagnostics import count_scan_repairs
from app.services.market_data_ingestion.symbol_parity import classify_symbol_sets
from app.services.market_data_ingestion.turso_repository import select_daily_ohlcv_for_symbols
from app.services.strategy_tester.scan_service import _series_from_rows, fill_missing_from_historical_candles

pytestmark = pytest.mark.unit


def _forbid_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    def _opened():
        raise AssertionError("postgres session opened")

    monkeypatch.setattr(repo, "_use_turso_history", lambda: True)
    monkeypatch.setattr(repo, "AsyncSessionLocal", _opened)


@pytest.mark.asyncio
async def test_turso_read_failure_does_not_open_postgres(monkeypatch: pytest.MonkeyPatch):
    _forbid_postgres(monkeypatch)
    with patch(
        "app.services.market_data_ingestion.turso_repository.fetch_max_equity_trade_date",
        new=AsyncMock(side_effect=TimeoutError("slow")),
    ):
        with pytest.raises(repo.CandleHistoryBackendError, match="Postgres was not used"):
            await repo.max_equity_trade_date()


@pytest.mark.asyncio
async def test_empty_turso_history_does_not_open_postgres(monkeypatch: pytest.MonkeyPatch):
    _forbid_postgres(monkeypatch)
    with patch(
        "app.services.market_data_ingestion.turso_repository.fetch_daily_ohlcv_for_symbols",
        new=AsyncMock(return_value=[]),
    ):
        rows = await repo.fetch_daily_ohlcv_for_symbols(
            ["INFY-EQ"],
            from_date=date(2026, 8, 1),
            to_date=date(2026, 10, 1),
        )
    assert rows == []


@pytest.mark.asyncio
async def test_turso_upsert_zero_does_not_open_postgres(monkeypatch: pytest.MonkeyPatch):
    _forbid_postgres(monkeypatch)
    with patch(
        "app.services.market_data_ingestion.turso_repository.upsert_daily_rows",
        return_value=0,
    ), patch(
        "app.services.market_data_ingestion.turso_repository._client",
        return_value=object(),
    ):
        accepted, rejected = await repo.upsert_daily_bars(
            [
                {
                    "trade_date": date(2026, 10, 1),
                    "symbol": "INFY-EQ",
                    "open": 10,
                    "high": 11,
                    "low": 9,
                    "close": 10.5,
                    "volume": 100,
                    "source": "FYERS",
                }
            ]
        )
    assert accepted == 0
    assert rejected == 0


@pytest.mark.asyncio
async def test_session_coverage_reads_turso_only(monkeypatch: pytest.MonkeyPatch):
    _forbid_postgres(monkeypatch)
    payload = {
        "present": set(),
        "with_delivery": set(),
        "with_adtv": set(),
        "present_count": 747,
        "delivery_count": 17,
        "adtv_count": 388,
        "universe_count": 1,
        "index_present": True,
        "max_equity_date": date(2026, 10, 1),
    }
    with patch(
        "app.services.market_data_ingestion.turso_repository.fetch_session_coverage_snapshot",
        new=AsyncMock(return_value=payload),
    ):
        snap = await repo.session_coverage_snapshot(date(2026, 10, 1), ["INFY-EQ"])
    assert snap["present_count"] == 747
    assert snap["max_equity_date"] == date(2026, 10, 1)


@pytest.mark.asyncio
async def test_postgres_candle_write_is_blocked_in_turso_mode(monkeypatch: pytest.MonkeyPatch):
    _forbid_postgres(monkeypatch)
    with pytest.raises(repo.CandleHistoryBackendError, match="Refusing Postgres candle write"):
        await repo.backfill_adtv_20_for_session(date(2026, 10, 1), symbols=["INFY-EQ"])


def test_fail_closed_error_does_not_include_secret():
    secret = "super-secret-token-value"
    with pytest.raises(repo.CandleHistoryBackendError, match="Postgres was not used") as caught:
        repo._refuse_postgres_fallback("fetch_daily_ohlcv_for_symbols", RuntimeError(secret))
    assert secret not in str(caught.value)


def test_startup_probe_failure_does_not_select_postgres(monkeypatch: pytest.MonkeyPatch):
    class _Boom:
        def execute(self, *_args, **_kwargs):
            raise TimeoutError("slow")

        def close(self) -> None:
            return None

    monkeypatch.setattr("app.db.turso.connect_turso", lambda _settings: _Boom())
    with pytest.raises(RuntimeError, match="Postgres candle history was not selected"):
        open_probed_turso_client(object())


@pytest.mark.asyncio
async def test_historical_candle_fill_is_skipped_when_turso(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.services.market_data_ingestion.history_backend.uses_turso",
        lambda: True,
    )
    filled = await fill_missing_from_historical_candles(
        ["CUPID"],
        {},
        from_date=date(2026, 1, 1),
        to_date=date(2026, 10, 1),
    )
    assert filled == 0


def test_symbol_sets_are_classified_dynamically():
    groups = classify_symbol_sets(
        ["CUPID-EQ", "SCHNEIDER", "WELSPUNLIV"],
        ["SCHNEIDER-EQ", "WOCKPHARMA"],
    )
    assert groups["local_only"] == ["CUPID", "WELSPUNLIV"]
    assert groups["production_only"] == ["WOCKPHARMA"]
    assert groups["both"] == ["SCHNEIDER"]


def test_date_range_does_not_return_bars_outside_the_window():
    client = InMemoryTursoClient()
    client.execute(
        """
        CREATE TABLE daily_ohlcv (
            trade_date TEXT, symbol TEXT, open REAL, high REAL, low REAL,
            close REAL, volume INTEGER, delivery_qty INTEGER, delivery_pct REAL,
            turnover REAL, adtv_20 REAL
        )
        """
    )
    client.execute(
        "INSERT INTO daily_ohlcv VALUES (?, ?, 1, 1, 1, 100, 10, NULL, NULL, NULL, NULL)",
        ["2026-08-14", "INFY-EQ"],
    )
    client.execute(
        "INSERT INTO daily_ohlcv VALUES (?, ?, 1, 1, 1, 110, 12, NULL, NULL, NULL, NULL)",
        ["2026-10-01", "INFY-EQ"],
    )
    rows = select_daily_ohlcv_for_symbols(
        client,
        ["INFY-EQ"],
        from_date=date(2026, 9, 1),
        to_date=date(2026, 10, 1),
        columns=["trade_date", "symbol", "close"],
    )
    assert [row["trade_date"] for row in rows] == [date(2026, 10, 1)]
    assert rows[0]["close"] == 110


def test_indicators_are_not_computed_across_a_fabricated_gap():
    items = [
        (date(2026, 8, 14), 10.0, 12.0, 9.0, 100.0, 1000.0),
        (date(2026, 10, 1), 11.0, 13.0, 10.0, 110.0, 1100.0),
    ]
    series = _series_from_rows(items, apply_holiday_calendar=False)
    assert series.dates == [date(2026, 8, 14), date(2026, 10, 1)]
    assert len(series) == 2
    assert sma(series.close, 50) == [None, None]
    assert sma(series.close, 14) == [None, None]


def test_scanner_fast_path_does_not_require_delivery_when_ohlcv_is_complete():
    snap = {
        "index_present": True,
        "present_count": 747,
        "equity_coverage": 0.99,
        "delivery_coverage": 17 / 747,
        "adtv_coverage": 388 / 747,
        "missing_ohlcv": [],
    }
    assert ens._is_fast_fresh(
        snap,
        threshold=0.95,
        force=False,
        universe_size=755,
        has_date_gap=False,
        ignore_soft_fields=True,
    )
    assert not ens._is_fast_fresh(
        snap,
        threshold=0.95,
        force=False,
        universe_size=755,
        has_date_gap=False,
        ignore_soft_fields=False,
    )


@pytest.mark.asyncio
async def test_turso_health_counts_only_the_latest_session():
    """A full-table count of ~2.2M rows must not be the health probe."""
    import app.services.market_data_provider as provider_mod

    class _Client:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        def execute(self, sql: str, params=None):
            self.calls.append((sql, params))
            if "MAX(trade_date)" in sql:
                return [{"max_date": "2026-10-01"}]
            return [{"n": 744}]

    client = _Client()
    payload = await provider_mod.TursoMarketHistoryProvider(client=client).check_health()
    assert payload["reachable"] is True
    assert payload["max_trade_date"] == "2026-10-01"
    assert payload["symbols_on_latest_date"] == 744
    assert payload["silent_postgres_fallback"] is False
    assert "row_count" not in payload
    joined = " ".join(sql for sql, _params in client.calls).upper()
    assert "COUNT(DISTINCT" not in joined
    assert any(params == ["2026-10-01"] for _sql, params in client.calls)


def test_repair_counter_ignores_an_already_fresh_ensure():
    attempts, failures = count_scan_repairs(
        {
            "daily_sync": {"status": "ok", "history_from": None},
            "ensure": {"status": "ALREADY_FRESH"},
            "repair": {"cloned_rows_deleted": 0, "thin_history": []},
        }
    )
    assert attempts == 0
    assert failures == 0
