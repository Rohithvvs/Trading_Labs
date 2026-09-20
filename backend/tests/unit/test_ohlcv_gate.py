"""OHLC upsert gate. No live database."""
from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.market_data_ingestion.validators.ohlcv_gate import (
    classify_ohlcv_bar,
    filter_valid_ohlcv_rows,
    rejection_audit_record,
    validate_ohlcv_bar,
)
from app.services.strategies.ltm.candle_backfill import _session_date

pytestmark = pytest.mark.unit


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


def test_valid_daily_bar_accepted():
    classified = classify_ohlcv_bar(_bar())
    assert classified["decision"] == "accept"
    assert classified["severity"] == "ok"
    assert validate_ohlcv_bar(_bar()) == []


def test_optional_delivery_fields_may_be_missing():
    row = _bar()
    row.pop("delivery_qty", None)
    row.pop("adtv_20", None)
    assert validate_ohlcv_bar(row) == []


def test_material_open_below_low_rejected():
    reasons = validate_ohlcv_bar(_bar(open=80.0, high=110.0, low=90.0, close=105.0))
    assert "open_below_low" in reasons


def test_material_close_above_high_rejected():
    reasons = validate_ohlcv_bar(_bar(close=120.0, high=110.0, low=90.0, open=100.0))
    assert "close_above_high" in reasons


def test_high_below_low_rejected():
    assert "high_lt_low" in validate_ohlcv_bar(_bar(high=90.0, low=100.0))


def test_negative_volume_rejected():
    assert "negative_volume" in validate_ohlcv_bar(_bar(volume=-1))


def test_tick_rounding_classified_but_accepted():
    # BEL-style: close 410.70 vs high 410.65 is exactly one NSE tick (0.05).
    row = _bar(open=410.0, high=410.65, low=400.0, close=410.70)
    classified = classify_ohlcv_bar(row)
    assert classified["decision"] == "accept"
    assert classified["severity"] == "rounding"
    assert "rounding_close_above_high" in classified["rounding_reasons"]
    assert classified["material_reasons"] == []
    assert validate_ohlcv_bar(row) == []
    # 0.35 is material (7 ticks).
    assert "close_above_high" in validate_ohlcv_bar(
        _bar(open=410.0, high=410.65, low=400.0, close=411.0)
    )


def test_historical_candles_source_materially_invalid_rejected():
    row = _bar(source="historical_candles", open=12.0, high=10.0, low=9.0, close=8.5)
    accepted, rejected = filter_valid_ohlcv_rows([row])
    assert accepted == []
    assert rejected[0]["source"] == "historical_candles"
    assert "open_above_high" in rejected[0]["_reject_reasons"]
    assert "close_below_low" in rejected[0]["_reject_reasons"]


def test_fyers_live_1d_source_materially_invalid_rejected():
    row = _bar(source="FYERS_LIVE_1D", open=50.0, high=110.0, low=90.0, close=105.0)
    accepted, rejected = filter_valid_ohlcv_rows([row])
    assert accepted == []
    assert rejected[0]["source"] == "FYERS_LIVE_1D"
    assert "open_below_low" in rejected[0]["_reject_reasons"]


def test_irfc_2026_08_01_prior_close_as_open_while_low_higher():
    """IRFC-style: open/close equal prior close, low is above that print."""
    row = _bar(
        symbol="IRFC-EQ",
        trade_date=date(2026, 8, 1),
        open=100.0,
        close=100.0,
        low=102.0,
        high=108.0,
        volume=800,
        source="historical_candles",
    )
    classified = classify_ohlcv_bar(row)
    assert classified["decision"] == "reject"
    assert "open_below_low" in classified["material_reasons"]
    assert "close_below_low" in classified["material_reasons"]
    accepted, rejected = filter_valid_ohlcv_rows([row, _bar()])
    assert [a["symbol"] for a in accepted] == ["INFY-EQ"]
    assert rejected[0]["symbol"] == "IRFC-EQ"


def test_rejection_audit_strips_secrets():
    row = _bar(source="historical_candles", open=50.0, high=110.0, low=90.0)
    row["password"] = "nope"
    row["TURSO_AUTH_TOKEN"] = "nope"
    classified = classify_ohlcv_bar(row)
    record = rejection_audit_record(row, classified, context="upsert_daily_bars")
    dumped = str(record)
    assert "nope" not in dumped
    assert "password" not in record["payload_json"]
    assert record["material_reasons"]


@pytest.mark.asyncio
async def test_bad_row_cannot_reach_repository_upsert():
    from app.services.market_data_ingestion import repository as repo

    bad = _bar(
        symbol="IRFC-EQ",
        open=100.0,
        close=100.0,
        low=102.0,
        high=108.0,
        source="historical_candles",
    )

    class BoomSession:
        async def __aenter__(self):
            raise AssertionError("session must not open when every row is rejected")

        async def __aexit__(self, *args):
            return False

    with (
        patch.object(repo, "_use_turso_history", return_value=False),
        patch.object(repo, "AsyncSessionLocal", return_value=BoomSession()),
    ):
        accepted, rejected = await repo.upsert_daily_bars([bad])
    assert accepted == 0
    assert rejected == 1


@pytest.mark.asyncio
async def test_valid_row_still_reaches_postgres_upsert():
    from app.services.market_data_ingestion import repository as repo

    good = _bar(source="FYERS")
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
        n, rejected = await repo.upsert_daily_bars([good])
    assert n == 1
    assert rejected == 0
    execute.assert_awaited()
    commit.assert_awaited()
    values = insert.return_value.values.call_args[0][0]
    assert values[0]["symbol"] == "INFY-EQ"
    assert values[0]["source"] == "FYERS"


def test_session_date_uses_ist_not_utc_calendar():
    ts = datetime(2026, 7, 31, 18, 30, tzinfo=timezone.utc)
    assert _session_date(ts) == date(2026, 8, 1)
    assert ts.date() == date(2026, 7, 31)
