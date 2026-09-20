"""Bounded INFY-EQ Turso copy guards. Fakes only — no live Postgres/Turso."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.cli import turso_migrate_daily_ohlcv as cli
from app.db.turso import DAILY_UPSERT_SQL, InMemoryTursoClient, apply_v1_schema
from app.services.market_data_ingestion.turso_bounded_copy import (
    APPROVED_TEST_SYMBOL,
    run_bounded_infy_copy,
    validate_bounded_test_request,
)

pytestmark = pytest.mark.unit

LOCAL = "postgresql://postgres:x@localhost:5432/trading_data"
NEON = "postgresql://u:p@ep-example.neon.tech/db"


def _ok_kwargs(**overrides):
    kw = dict(
        symbols=["INFY-EQ"],
        tables=["daily_ohlcv"],
        limit=100,
        batch_size=100,
        local_postgres_url=LOCAL,
        exclude_json="phantom_rows_delete_review.json",
        exclusion_report="turso_exclusion_report_test.json",
        result_report="turso_test_migration_result.json",
        confirm_local_backup=True,
    )
    kw.update(overrides)
    return kw


def test_rejects_missing_symbols():
    errs = validate_bounded_test_request(**_ok_kwargs(symbols=None))
    assert any("missing --symbols" in e for e in errs)


def test_rejects_other_symbol():
    errs = validate_bounded_test_request(**_ok_kwargs(symbols=["TCS-EQ"]))
    assert any("INFY-EQ" in e for e in errs)


def test_rejects_limit_above_100():
    errs = validate_bounded_test_request(**_ok_kwargs(limit=101))
    assert any("exceeds approved maximum 100" in e for e in errs)


def test_rejects_other_table():
    errs = validate_bounded_test_request(**_ok_kwargs(tables=["index_ohlcv"]))
    assert any("daily_ohlcv" in e for e in errs)


def test_rejects_missing_exclusion_report():
    errs = validate_bounded_test_request(**_ok_kwargs(exclusion_report=""))
    assert any("missing --exclusion-report" in e for e in errs)


def test_rejects_non_local_host():
    errs = validate_bounded_test_request(**_ok_kwargs(local_postgres_url=NEON))
    assert any("non-local" in e for e in errs)


def test_cli_execute_without_guards_refuses(capsys):
    code = cli.main(["--execute", "--confirm-local-backup"])
    assert code == 2
    payload = __import__("json").loads(capsys.readouterr().out)
    assert payload["status"] == "REFUSED"
    assert payload["wrote"] is False
    assert payload["wrote_postgres"] is False


def test_bounded_copy_upserts_and_reports_exclusions(tmp_path: Path):
    phantom = tmp_path / "phantom_rows_delete_review.json"
    phantom.write_text(
        __import__("json").dumps(
            {
                "items": [
                    {
                        "table": "daily_ohlcv",
                        "symbol": "INFY-EQ",
                        "trade_date": "2026-08-01",
                        "reason": "weekend phantom",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    rows = [
        {
            "trade_date": date(2026, 8, 1),
            "symbol": "INFY-EQ",
            "open": 1,
            "high": 1,
            "low": 1,
            "close": 1,
            "volume": 1,
            "source": "FYERS",
            "loaded_at": "2026-08-01T00:00:00+00:00",
        },
        {
            "trade_date": date(2026, 8, 3),
            "symbol": "INFY-EQ",
            "open": 100,
            "high": 110,
            "low": 90,
            "close": 105,
            "volume": 1000,
            "delivery_qty": 10,
            "delivery_pct": 1.0,
            "turnover": 1.0,
            "adtv_20": 1.0,
            "source": "FYERS",
            "loaded_at": "2026-08-03T00:00:00+00:00",
        },
        {
            "trade_date": date(2026, 8, 4),
            "symbol": "INFY-EQ",
            "open": 50,
            "high": 40,
            "low": 45,
            "close": 48,
            "volume": 1,
            "source": "FYERS",
            "loaded_at": "2026-08-04T00:00:00+00:00",
        },
    ]
    client = InMemoryTursoClient()
    apply_v1_schema(client, execute=True)
    excl = tmp_path / "turso_exclusion_report_test.json"
    result_path = tmp_path / "turso_test_migration_result.json"
    payload = run_bounded_infy_copy(
        local_postgres_url=LOCAL,
        turso_client=client,
        exclude_json_paths=[str(phantom)],
        exclusion_report_path=str(excl),
        result_report_path=str(result_path),
        limit=100,
        batch_size=100,
        fetch_rows=lambda url, symbol, limit: rows,
    )
    assert payload["wrote_postgres"] is False
    assert payload["copied"] == 1
    assert payload["excluded_reported"] == 2
    stored = client.execute("SELECT trade_date, symbol FROM daily_ohlcv")
    assert len(stored) == 1
    assert stored[0]["symbol"] == APPROVED_TEST_SYMBOL
    # rerun is idempotent
    payload2 = run_bounded_infy_copy(
        local_postgres_url=LOCAL,
        turso_client=client,
        exclude_json_paths=[str(phantom)],
        exclusion_report_path=str(excl),
        result_report_path=str(result_path),
        fetch_rows=lambda url, symbol, limit: rows,
    )
    stored2 = client.execute("SELECT COUNT(*) AS n FROM daily_ohlcv")
    assert int(stored2[0]["n"]) == 1
    assert payload2["copied"] == 1
    assert excl.exists() and result_path.exists()
    client.close()
    assert "INSERT" in DAILY_UPSERT_SQL and "ON CONFLICT" in DAILY_UPSERT_SQL
