"""Daily/index source allowlist. Does not govern ACS/historical_candles persistence."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.turso import InMemoryTursoClient, apply_v1_schema
from app.services.market_data_ingestion.source_policy import (
    ALLOWED_DAILY_INDEX_SOURCES,
    classify_daily_index_source,
    filter_strategy_store_sources,
)
from app.services.market_data_ingestion.turso_repository import upsert_daily_rows

pytestmark = pytest.mark.unit

_APP = Path(__file__).resolve().parents[2] / "app"


def _bar(**overrides):
    row = {
        "trade_date": date(2026, 8, 1),
        "symbol": "INFY-EQ",
        "open": 100.0,
        "high": 110.0,
        "low": 90.0,
        "close": 105.0,
        "volume": 1_000_000,
        "source": "FYERS",
    }
    row.update(overrides)
    return row


def test_allowlist_is_fyers_eod_only():
    assert ALLOWED_DAILY_INDEX_SOURCES == frozenset({"FYERS"})
    assert classify_daily_index_source("FYERS")["decision"] == "accept"


def test_historical_candles_source_rejected_even_if_ohlc_valid():
    classified = classify_daily_index_source("historical_candles")
    assert classified["decision"] == "reject"
    assert "forbidden_source:historical_candles" == classified["reason"]
    allowed, rejected = filter_strategy_store_sources(
        [_bar(source="historical_candles")], table_name="daily_ohlcv"
    )
    assert allowed == []
    assert rejected[0]["open"] == 100.0  # payload not rewritten
    assert rejected[0]["source"] == "historical_candles"


def test_unknown_source_rejected():
    assert classify_daily_index_source("YAHOO_FALLBACK")["decision"] == "reject"
    assert classify_daily_index_source("")["reason"] == "missing_source"
    assert classify_daily_index_source(None)["reason"] == "missing_source"


def test_live_quote_tag_rejected_as_cache_derived():
    assert classify_daily_index_source("FYERS_LIVE_1D")["decision"] == "reject"


@pytest.mark.asyncio
async def test_valid_fyers_source_reaches_daily_upsert():
    from app.services.market_data_ingestion import repository as repo

    execute = AsyncMock()
    commit = AsyncMock()
    session = MagicMock()
    session.execute = execute
    session.commit = commit

    class Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            return False

    with (
        patch.object(repo, "_use_turso_history", return_value=False),
        patch.object(repo, "AsyncSessionLocal", return_value=Ctx()),
        patch.object(repo, "pg_insert") as insert,
    ):
        insert.return_value.values.return_value.on_conflict_do_update.return_value = "stmt"
        n, rejected = await repo.upsert_daily_bars([_bar(source="FYERS")])
    assert n == 1
    assert rejected == 0
    execute.assert_awaited()
    values = insert.return_value.values.call_args[0][0]
    assert values[0]["source"] == "FYERS"


@pytest.mark.asyncio
async def test_historical_candles_rejected_before_daily_upsert():
    from app.services.market_data_ingestion import repository as repo

    class BoomSession:
        async def __aenter__(self):
            raise AssertionError("daily_ohlcv session must not open for ACS source")

        async def __aexit__(self, *args):
            return False

    with (
        patch.object(repo, "_use_turso_history", return_value=False),
        patch.object(repo, "AsyncSessionLocal", return_value=BoomSession()),
    ):
        n, rejected = await repo.upsert_daily_bars(
            [_bar(source="historical_candles")]
        )
    assert n == 0
    assert rejected == 1


@pytest.mark.asyncio
async def test_unknown_source_rejected_before_daily_upsert():
    from app.services.market_data_ingestion import repository as repo

    class BoomSession:
        async def __aenter__(self):
            raise AssertionError("must not open session for unknown source")

        async def __aexit__(self, *args):
            return False

    with (
        patch.object(repo, "_use_turso_history", return_value=False),
        patch.object(repo, "AsyncSessionLocal", return_value=BoomSession()),
    ):
        n, rejected = await repo.upsert_daily_bars([_bar(source="chart-cache")])
    assert n == 0
    assert rejected == 1


@pytest.mark.asyncio
async def test_index_ohlcv_follows_same_source_policy():
    from app.services.market_data_ingestion import repository as repo

    class BoomSession:
        async def __aenter__(self):
            raise AssertionError("index_ohlcv session must not open for ACS source")

        async def __aexit__(self, *args):
            return False

    with (
        patch.object(repo, "_use_turso_history", return_value=False),
        patch.object(repo, "AsyncSessionLocal", return_value=BoomSession()),
    ):
        n = await repo.upsert_index_bars(
            [_bar(symbol="NIFTY500", source="historical_candles")]
        )
    assert n == 0


def test_acs_historical_candles_module_does_not_import_daily_source_policy():
    acs = (_APP / "services" / "authoritative_candle_store.py").read_text(encoding="utf-8")
    mds = (_APP / "services" / "market_data_service.py").read_text(encoding="utf-8")
    persist = (_APP / "services" / "persistence_service.py").read_text(encoding="utf-8")
    for text in (acs, mds, persist):
        assert "source_policy" not in text
        assert "ALLOWED_DAILY_INDEX_SOURCES" not in text
        assert "filter_strategy_store_sources" not in text


def test_turso_daily_write_applies_same_source_policy():
    client = InMemoryTursoClient()
    apply_v1_schema(client, execute=True)
    n_bad = upsert_daily_rows(client, [_bar(source="historical_candles")])
    n_ok = upsert_daily_rows(client, [_bar(source="FYERS")])
    assert n_bad == 0
    assert n_ok == 1
    stored = client.execute("SELECT source FROM daily_ohlcv")
    assert stored == [{"source": "FYERS"}]
    client.close()
