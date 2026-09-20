"""In-memory Turso schema + upsert tests. No cloud or local Postgres I/O."""
from __future__ import annotations

from datetime import date

import pytest

from backend.app.db.turso import (
    DAILY_UPSERT_SQL,
    InMemoryTursoClient,
    apply_v1_schema,
    inspect_v1_schema,
)
from backend.app.db.turso_schema import V1_TABLES, load_v1_schema_sql, split_sql_statements
from backend.app.services.market_data_ingestion.turso_migrate import (
    EXPECTED_DAILY_COLUMNS,
    validate_models_against_v1_schema,
)
from backend.app.services.market_data_ingestion.turso_repository import (
    select_equity_history,
    upsert_daily_rows,
    upsert_index_rows,
)

pytestmark = pytest.mark.unit


def test_upsert_sql_uses_parameter_placeholders():
    assert "?" in DAILY_UPSERT_SQL
    assert "%s" not in DAILY_UPSERT_SQL
    assert "f\"INSERT" not in DAILY_UPSERT_SQL
    assert DAILY_UPSERT_SQL.count("?") == 13


def test_v1_sql_is_idempotent_and_excludes_historical_candles():
    sql = load_v1_schema_sql()
    assert "CREATE TABLE IF NOT EXISTS daily_ohlcv" in sql
    assert "CREATE TABLE IF NOT EXISTS index_ohlcv" in sql
    created = [line for line in sql.lower().splitlines() if "create table" in line]
    assert not any("historical_candles" in line for line in created)
    stmts = split_sql_statements(sql)
    assert len(stmts) >= 4
    for col in EXPECTED_DAILY_COLUMNS:
        assert col in sql


def test_validate_models_against_schema():
    result = validate_models_against_v1_schema()
    assert result["ok"] is True
    assert result["live_compare"] is False
    assert list(result["tables"]) == list(V1_TABLES)


def test_inspect_v1_schema_after_apply():
    client = InMemoryTursoClient()
    apply_v1_schema(client, execute=True)
    meta = inspect_v1_schema(client)
    assert meta["ok"] is True
    assert meta["wrote"] is False
    assert "daily_ohlcv" in meta["tables"]
    assert "index_ohlcv" in meta["tables"]
    assert "historical_candles" not in meta["tables"]
    assert "idx_daily_ohlcv_symbol_trade_date" in meta["indexes"]
    client.close()


def test_schema_apply_dry_run_does_not_write():
    client = InMemoryTursoClient()
    result = apply_v1_schema(client, execute=False)
    assert result["wrote"] is False
    assert result["status"] == "DRY_RUN"
    rows = client.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='daily_ohlcv'"
    )
    assert rows == []
    client.close()


def test_upsert_idempotent_and_coalesce_delivery():
    client = InMemoryTursoClient()
    apply_v1_schema(client, execute=True)
    row = {
        "trade_date": date(2024, 1, 2),
        "symbol": "RELIANCE-EQ",
        "open": 100.0,
        "high": 110.0,
        "low": 90.0,
        "close": 105.0,
        "volume": 1000,
        "delivery_qty": 400,
        "delivery_pct": 40.0,
        "turnover": 105000.0,
        "adtv_20": 1.0,
        "source": "FYERS",
    }
    upsert_daily_rows(client, [row])
    row2 = dict(row)
    row2["close"] = 106.0
    row2["delivery_qty"] = None
    row2["delivery_pct"] = None
    upsert_daily_rows(client, [row2])
    got = select_equity_history(client, "RELIANCE-EQ")
    assert len(got) == 1
    assert got[0]["close"] == 106.0
    assert got[0]["delivery_qty"] == 400
    assert got[0]["delivery_pct"] == 40.0
    count = client.execute("SELECT COUNT(*) AS n FROM daily_ohlcv")
    assert int(count[0]["n"]) == 1
    client.close()


def test_index_upsert_and_order():
    client = InMemoryTursoClient()
    apply_v1_schema(client, execute=True)
    upsert_index_rows(
        client,
        [
            {
                "trade_date": date(2024, 1, 3),
                "symbol": "NIFTY500",
                "open": 1,
                "high": 1,
                "low": 1,
                "close": 1,
                "volume": 0,
                "source": "FYERS",
            },
            {
                "trade_date": date(2024, 1, 2),
                "symbol": "NIFTY500",
                "open": 1,
                "high": 2,
                "low": 1,
                "close": 2,
                "volume": 0,
                "source": "FYERS",
            },
        ],
    )
    from backend.app.services.market_data_ingestion.turso_repository import select_index_history

    rows = select_index_history(client, "NIFTY500")
    assert [r["trade_date"] for r in rows] == [date(2024, 1, 2), date(2024, 1, 3)]
    client.close()
