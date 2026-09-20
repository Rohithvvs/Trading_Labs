"""Full Turso V1 copy guards and in-memory upsert. No live databases."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.cli import turso_migrate_daily_ohlcv as cli
from app.db.turso import InMemoryTursoClient, apply_v1_schema
from app.services.market_data_ingestion.turso_full_copy import (
    run_full_v1_copy,
    validate_full_copy_request,
)

pytestmark = pytest.mark.unit

LOCAL = "postgresql://postgres:x@localhost:5432/trading_data"
NEON = "postgresql://u:p@ep-example.neon.tech/db"


def _ok_kwargs(**overrides):
    kw = dict(
        full=True,
        confirm_local_backup=True,
        symbols=None,
        tables=["daily_ohlcv", "index_ohlcv"],
        limit=None,
        batch_size=500,
        local_postgres_url=LOCAL,
        exclude_json="phantom_rows_delete_review.json",
        exclusion_report="turso_exclusion_report_full.json",
        result_report="turso_full_migration_result.json",
        migration_policy="validated_legacy_backfill_v1",
    )
    kw.update(overrides)
    return kw


def test_full_copy_rejects_symbols_and_limit():
    errs = validate_full_copy_request(**_ok_kwargs(symbols=["INFY-EQ"], limit=100))
    assert any("--symbols" in e for e in errs)
    assert any("--limit" in e for e in errs)


def test_full_copy_rejects_non_local_and_acs():
    errs = validate_full_copy_request(**_ok_kwargs(local_postgres_url=NEON, tables=["historical_candles"]))
    assert any("non-local" in e for e in errs)
    assert any("historical_candles" in e or "forbids" in e for e in errs)


def test_full_copy_rejects_missing_backup():
    errs = validate_full_copy_request(**_ok_kwargs(confirm_local_backup=False))
    assert any("confirm-local-backup" in e for e in errs)


def test_full_copy_rejects_fyers_only_policy():
    errs = validate_full_copy_request(**_ok_kwargs(migration_policy="fyers_only"))
    assert any("validated_legacy_backfill_v1" in e for e in errs)


def test_cli_full_execute_without_backup_refuses(capsys):
    code = cli.main(["--full", "--execute"])
    assert code == 2
    payload = __import__("json").loads(capsys.readouterr().out)
    assert payload["status"] == "REFUSED"
    assert payload["wrote"] is False
    assert payload["wrote_postgres"] is False


def test_full_copy_upserts_both_tables_and_reports_exclusions(tmp_path: Path):
    phantom = tmp_path / "phantom_rows_delete_review.json"
    phantom.write_text(
        __import__("json").dumps(
            {
                "items": [
                    {
                        "table": "daily_ohlcv",
                        "symbol": "IRFC-EQ",
                        "trade_date": "2026-08-01",
                        "reason": "weekend phantom",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    pages = {
        "daily_ohlcv": [
            {
                "trade_date": date(2026, 8, 1),
                "symbol": "IRFC-EQ",
                "open": 1,
                "high": 1,
                "low": 1,
                "close": 1,
                "volume": 1,
                "source": "historical_candles",
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
                "symbol": "TCS-EQ",
                "open": 50,
                "high": 40,
                "low": 45,
                "close": 48,
                "volume": 1,
                "source": "FYERS",
                "loaded_at": "2026-08-04T00:00:00+00:00",
            },
            {
                "trade_date": date(2026, 8, 5),
                "symbol": "WIPRO-EQ",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10,
                "volume": 1,
                "source": "FYERS_LIVE_1D",
                "loaded_at": "2026-08-05T00:00:00+00:00",
            },
        ],
        "index_ohlcv": [
            {
                "trade_date": date(2009, 5, 18),
                "symbol": "NIFTY500",
                "open": 3290,
                "high": 3291.50,
                "low": 3280,
                "close": 3293.35,
                "volume": 0,
                "source": "FYERS",
                "loaded_at": "2009-05-18T00:00:00+00:00",
            },
            {
                "trade_date": date(2026, 8, 3),
                "symbol": "NIFTY500",
                "open": 100,
                "high": 110,
                "low": 90,
                "close": 105,
                "volume": 0,
                "source": "FYERS",
                "loaded_at": "2026-08-03T00:00:00+00:00",
            },
        ],
    }

    def fetch_page(url, table, last_date, last_symbol, batch_size):
        if last_date is not None:
            return []
        return pages[table]

    client = InMemoryTursoClient()
    apply_v1_schema(client, execute=True)
    excl = tmp_path / "turso_exclusion_report_full.json"
    result_path = tmp_path / "turso_full_migration_result.json"
    progress = tmp_path / "turso_full_migration_progress.jsonl"
    payload = run_full_v1_copy(
        local_postgres_url=LOCAL,
        turso_client=client,
        exclude_json_paths=[str(phantom)],
        exclusion_report_path=str(excl),
        result_report_path=str(result_path),
        batch_size=500,
        progress_path=str(progress),
        fetch_page=fetch_page,
        now_ist=datetime(2026, 9, 19, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
    )
    assert payload["wrote_postgres"] is False
    assert payload["deleted"] is False
    assert payload["copied"] == 3
    assert payload["excluded_reported"] == 3
    assert payload["migration_policy"] == "validated_legacy_backfill_v1"
    assert payload["copied_by_source"]["FYERS"] == 2
    assert payload["copied_by_source"]["FYERS_LIVE_1D"] == 1
    daily = client.execute("SELECT symbol, source FROM daily_ohlcv ORDER BY symbol")
    index = client.execute("SELECT trade_date, symbol FROM index_ohlcv ORDER BY trade_date")
    assert [r["symbol"] for r in daily] == ["INFY-EQ", "WIPRO-EQ"]
    assert [r["source"] for r in daily] == ["FYERS", "FYERS_LIVE_1D"]
    assert len(index) == 1
    assert index[0]["symbol"] == "NIFTY500"
    assert str(index[0]["trade_date"])[:10] == "2026-08-03"
    payload2 = run_full_v1_copy(
        local_postgres_url=LOCAL,
        turso_client=client,
        exclude_json_paths=[str(phantom)],
        exclusion_report_path=str(excl),
        result_report_path=str(result_path),
        fetch_page=fetch_page,
        now_ist=datetime(2026, 9, 19, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
    )
    assert int(client.execute("SELECT COUNT(*) AS n FROM daily_ohlcv")[0]["n"]) == 2
    assert int(client.execute("SELECT COUNT(*) AS n FROM index_ohlcv")[0]["n"]) == 1
    assert payload2["copied"] == 3
    assert excl.exists() and result_path.exists() and progress.exists()
    assert excl.with_suffix(".jsonl").exists()
    client.close()
