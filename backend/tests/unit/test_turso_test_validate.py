"""INFY-EQ bounded compare tests. No live Postgres/Turso."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.cli import turso_validate_daily_ohlcv as cli
from app.services.market_data_ingestion.turso_test_validate import (
    FAILED,
    PASSED,
    canonical_loaded_at,
    compare_bounded_daily_rows,
    validate_infy_test_compare_request,
)

pytestmark = pytest.mark.unit

LOCAL = "postgresql://postgres:x@localhost:5432/trading_data"


def _bar(**overrides):
    row = {
        "trade_date": date(2020, 1, 2),
        "symbol": "INFY-EQ",
        "open": "100.1",
        "high": "110.0",
        "low": "90.0",
        "close": "105.5",
        "volume": 1000,
        "delivery_qty": 10,
        "delivery_pct": "1.5",
        "turnover": "1000.0",
        "adtv_20": "900.0",
        "source": "FYERS",
        "loaded_at": datetime(2020, 1, 2, 10, 0, tzinfo=timezone.utc),
    }
    row.update(overrides)
    return row


def test_canonical_loaded_at_normalizes_offset():
    a = canonical_loaded_at("2020-01-02T10:00:00+00:00")
    b = canonical_loaded_at("2020-01-02T10:00:00.000000+00:00")
    assert a == b


def test_compare_pass_equal_scaled_prices():
    local = [_bar(open="100.1")]
    turso = [_bar(open="100.10000000", loaded_at="2020-01-02T10:00:00+00:00")]
    result = compare_bounded_daily_rows(local, turso)
    assert result["ok"] is True
    assert result["final_line"] == PASSED
    assert result["wrote"] is False


def test_compare_detects_missing_extra_and_ohlc():
    local = [_bar(), _bar(trade_date=date(2020, 1, 3))]
    turso = [_bar(close="999.0"), _bar(trade_date=date(2020, 1, 4))]
    result = compare_bounded_daily_rows(local, turso)
    assert result["ok"] is False
    assert result["final_line"] == FAILED
    assert result["missing_in_turso"]
    assert result["extra_in_turso"]
    assert result["field_mismatch_count"] >= 1


def test_request_guards():
    assert validate_infy_test_compare_request(
        symbols=["TCS-EQ"],
        tables=["daily_ohlcv"],
        limit=100,
        local_postgres_url=LOCAL,
        output="turso_test_validation_infy.json",
    )
    assert validate_infy_test_compare_request(
        symbols=["INFY-EQ"],
        tables=["index_ohlcv"],
        limit=100,
        local_postgres_url=LOCAL,
        output="x.json",
    )
    assert validate_infy_test_compare_request(
        symbols=["INFY-EQ"],
        tables=["daily_ohlcv"],
        limit=50,
        local_postgres_url=LOCAL,
        output="x.json",
    )
    assert validate_infy_test_compare_request(
        symbols=["INFY-EQ"],
        tables=["daily_ohlcv"],
        limit=100,
        local_postgres_url=LOCAL,
        output="",
    )
    assert not validate_infy_test_compare_request(
        symbols=["INFY-EQ"],
        tables=["daily_ohlcv"],
        limit=100,
        local_postgres_url=LOCAL,
        output="turso_test_validation_infy.json",
    )


def test_cli_live_without_bounds_refuses(capsys):
    code = cli.main(["--live", "--json"])
    assert code == 2
    out = capsys.readouterr().out
    payload = __import__("json").loads(out[out.index("{") : out.rindex("}") + 1])
    assert payload["wrote"] is False
    assert payload["skipped"] is True
