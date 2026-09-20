"""Source-read-only preflight tests. Mocks/fakes only — no live Postgres or Turso."""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from app.cli import turso_migrate_daily_ohlcv as migrate_cli
from app.db.urls import is_local_postgres_url
from app.services.market_data_ingestion.turso_migrate import EXPECTED_DAILY_COLUMNS, EXPECTED_INDEX_COLUMNS
from app.services.market_data_ingestion.turso_source_preflight import (
    FAILED_LINE,
    FINAL_FAILED_LINE,
    FINAL_PASSED_LINE,
    PASSED_LINE,
    PreflightError,
    run_final_source_preflight,
    run_source_preflight,
)

pytestmark = pytest.mark.unit

LOCAL_URL = "postgresql+asyncpg://user:secret@localhost:5432/trading_data"
NEON_URL = "postgresql+asyncpg://user:secret@ep-example.neon.tech/neondb"


def _ok_fetchall(sql: str, params):
    sql_l = sql.lower()
    if "information_schema.tables" in sql_l:
        return [{"exists": True}]
    if "information_schema.columns" in sql_l:
        table = params.get("table")
        cols = EXPECTED_DAILY_COLUMNS if table == "daily_ohlcv" else EXPECTED_INDEX_COLUMNS
        return [{"column_name": c} for c in cols]
    if "group by trade_date, symbol" in sql_l:
        return [{"duplicate_groups": 0, "extra_rows": 0}]
    return [
        {
            "n": 1000,
            "symbols": 10,
            "min_d": date(2008, 7, 22),
            "max_d": date(2026, 8, 17),
            **{f"null_{c}": 0 for c in ("trade_date", "symbol", "open", "high", "low", "close", "volume")},
            "high_lt_low": 0,
            "open_outside": 0,
            "close_outside": 0,
            "neg_volume": 0,
        }
    ]


def test_is_local_postgres_url():
    assert is_local_postgres_url(LOCAL_URL) is True
    assert is_local_postgres_url("postgresql://127.0.0.1:5432/trading_data") is True
    assert is_local_postgres_url(NEON_URL) is False
    assert is_local_postgres_url("") is False


def test_preflight_requires_local_postgres_url():
    with pytest.raises(PreflightError, match="LOCAL_POSTGRES_DATABASE_URL"):
        run_source_preflight(local_postgres_url="", fetchall=_ok_fetchall)


def test_preflight_never_falls_back_and_refuses_neon_host():
    with pytest.raises(PreflightError, match="non-local"):
        run_source_preflight(local_postgres_url=NEON_URL, fetchall=_ok_fetchall)


def test_preflight_pass_with_fake_source():
    payload = run_source_preflight(
        local_postgres_url=LOCAL_URL,
        symbols=["RELIANCE-EQ"],
        limit=100,
        batch_size=50,
        fetchall=_ok_fetchall,
    )
    assert payload["ok"] is True
    assert payload["wrote"] is False
    assert payload["turso_connected"] is False
    assert "secret" not in payload["source_target"]
    assert "localhost:5432/trading_data" in payload["source_target"]
    assert payload["final_line"] == PASSED_LINE
    assert payload["filters"]["symbols"] == ["RELIANCE-EQ"]
    assert payload["tables"][0]["expected_batches"] == 2  # min(1000, 100) / 50
    names = {t["table"] for t in payload["tables"]}
    assert names == {"daily_ohlcv", "index_ohlcv"}


def test_preflight_fails_missing_table():
    def fetchall(sql, params):
        if "information_schema.tables" in sql.lower():
            return [{"exists": False}]
        raise AssertionError("no further queries when table missing")

    payload = run_source_preflight(local_postgres_url=LOCAL_URL, fetchall=fetchall)
    assert payload["ok"] is False
    assert payload["wrote"] is False
    assert payload["final_line"] == FAILED_LINE
    assert any("missing table" in f for f in payload["failures"])


def test_preflight_fails_invalid_ohlc_and_duplicates():
    def fetchall(sql, params):
        sql_l = sql.lower()
        if "information_schema.tables" in sql_l:
            return [{"exists": True}]
        if "information_schema.columns" in sql_l:
            table = params.get("table")
            cols = EXPECTED_DAILY_COLUMNS if table == "daily_ohlcv" else EXPECTED_INDEX_COLUMNS
            return [{"column_name": c} for c in cols]
        if "group by trade_date, symbol" in sql_l:
            return [{"duplicate_groups": 3, "extra_rows": 4}]
        row = _ok_fetchall(sql, params)[0]
        row["high_lt_low"] = 2
        row["neg_volume"] = 1
        return [row]

    payload = run_source_preflight(local_postgres_url=LOCAL_URL, fetchall=fetchall)
    assert payload["ok"] is False
    joined = " ".join(payload["failures"])
    assert "duplicate" in joined
    assert "high_lt_low" in joined
    assert "neg_volume" in joined or "negative_volume" in joined


def test_preflight_rejects_historical_candles():
    with pytest.raises(PreflightError, match="historical_candles"):
        run_source_preflight(
            local_postgres_url=LOCAL_URL,
            tables=["historical_candles"],
            fetchall=_ok_fetchall,
        )


def test_cli_source_inspect_missing_url(monkeypatch, capsys):
    monkeypatch.setattr(
        type(migrate_cli.settings),
        "local_postgres_source_url",
        lambda self: "",
    )
    code = migrate_cli.main(["--source-inspect"])
    assert code == 2
    out = capsys.readouterr().out
    assert FAILED_LINE in out
    assert "LOCAL_POSTGRES_DATABASE_URL" in out


def test_cli_source_inspect_uses_injected_result(monkeypatch, capsys):
    fake = {
        "ok": True,
        "wrote": False,
        "turso_connected": False,
        "source_target": "localhost:5432/trading_data",
        "tables": [],
        "filters": {},
        "failures": [],
        "final_line": PASSED_LINE,
    }
    monkeypatch.setattr(migrate_cli, "run_source_preflight", lambda **kwargs: fake)
    code = migrate_cli.main(["--source-inspect", "--json"])
    assert code == 0
    out = capsys.readouterr().out
    assert PASSED_LINE in out
    assert "secret" not in out


def _final_fetchall_factory(*, extra_invalid=None, repair_source="FYERS"):
    phantom = {
        "trade_date": date(2026, 8, 1),
        "symbol": "IRFC-EQ",
        "open": 100,
        "high": 90,
        "low": 102,
        "close": 100,
        "volume": 1,
        "source": "historical_candles",
    }
    nifty = {
        "trade_date": date(2009, 5, 18),
        "symbol": "NIFTY500",
        "open": 3290,
        "high": 3291.50,
        "low": 3280,
        "close": 3293.35,
        "volume": 0,
        "source": "FYERS",
    }
    invalid = {
        "daily_ohlcv": [phantom] + (extra_invalid or []),
        "index_ohlcv": [nifty],
    }
    repair = {
        "trade_date": date(2026, 8, 12),
        "symbol": "APLAPOLLO-EQ",
        "open": 100,
        "high": 110,
        "low": 90,
        "close": 105,
        "volume": 1,
        "source": repair_source,
    }

    def fetchall(sql, params):
        sql_l = sql.lower()
        if "source_counts" in sql_l:
            if "from index_ohlcv" in sql_l:
                return [{"source": "FYERS", "n": 10}]
            return [{"source": "FYERS", "n": 999}, {"source": "historical_candles", "n": 1}]
        if "non_fyers_count" in sql_l:
            return [{"n": 0 if "from index_ohlcv" in sql_l else 1}]
        if "non_fyers_keys" in sql_l:
            if "from index_ohlcv" in sql_l:
                return []
            return [{"trade_date": phantom["trade_date"], "symbol": phantom["symbol"], "source": phantom["source"]}]
        if "live_1d_in_progress" in sql_l:
            return [{"n": 0}]
        if "live_1d_finalized" in sql_l:
            return [{"n": 0 if "from index_ohlcv" in sql_l else 0}]
        if "invalid_ohlc_keys" in sql_l:
            table = "index_ohlcv" if "from index_ohlcv" in sql_l else "daily_ohlcv"
            return invalid[table]
        if "repair_keys" in sql_l:
            return [repair]
        return _ok_fetchall(sql, params)

    return fetchall


def test_final_preflight_passes_expected_exclusions_and_repaired_keys(tmp_path, monkeypatch):
    import app.services.market_data_ingestion.turso_source_preflight as preflight

    monkeypatch.setattr(preflight, "PHANTOM_COUNT", 1)
    monkeypatch.setattr(preflight, "NIFTY_INVALID_COUNT", 1)
    phantom = tmp_path / "phantom_rows_delete_review.json"
    phantom.write_text(
        __import__("json").dumps(
            {
                "items": [
                    {
                        "table": "daily_ohlcv",
                        "symbol": "IRFC-EQ",
                        "trade_date": "2026-08-01",
                        "calendar_status": "WEEKEND_NON_TRADING_DAY",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "repair_manifest_v2.json"
    manifest.write_text(
        __import__("json").dumps(
            {
                "items": [
                    {
                        "table": "daily_ohlcv",
                        "symbol": "APLAPOLLO-EQ",
                        "trade_date": "2026-08-12",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    payload = run_final_source_preflight(
        local_postgres_url=LOCAL_URL,
        exclude_json_paths=[str(phantom)],
        repair_manifest_path=str(manifest),
        fetchall=_final_fetchall_factory(),
    )
    assert payload["ok"] is True
    assert payload["wrote"] is False
    assert payload["turso_connected"] is False
    assert payload["final_line"] == FINAL_PASSED_LINE
    assert payload["exclusions"]["saturday_phantoms"]["found"] == 1
    assert payload["exclusions"]["nifty500_2009_05_18"]["found"] == 1
    assert payload["exclusions"]["untracked_material_invalid"]["count"] == 0
    assert payload["repair_manifest"]["repaired_count"] == 1
    assert payload["expected_copy"]["policy"] == "validated_legacy_backfill_v1"
    assert payload["migration_policy"] == "validated_legacy_backfill_v1"
    assert payload["non_fyers"]["total"] == 1


def test_final_preflight_fails_untracked_invalid(tmp_path, monkeypatch):
    import app.services.market_data_ingestion.turso_source_preflight as preflight

    monkeypatch.setattr(preflight, "PHANTOM_COUNT", 1)
    monkeypatch.setattr(preflight, "NIFTY_INVALID_COUNT", 1)
    phantom = tmp_path / "phantom_rows_delete_review.json"
    phantom.write_text(
        __import__("json").dumps(
            {
                "items": [
                    {
                        "table": "daily_ohlcv",
                        "symbol": "IRFC-EQ",
                        "trade_date": "2026-08-01",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    extra = {
        "trade_date": date(2026, 8, 3),
        "symbol": "TCS-EQ",
        "open": 10,
        "high": 9,
        "low": 8,
        "close": 11,
        "volume": 1,
        "source": "FYERS",
    }
    payload = run_final_source_preflight(
        local_postgres_url=LOCAL_URL,
        exclude_json_paths=[str(phantom)],
        fetchall=_final_fetchall_factory(extra_invalid=[extra]),
    )
    assert payload["ok"] is False
    assert payload["wrote"] is False
    assert payload["final_line"] == FINAL_FAILED_LINE
    assert payload["exclusions"]["untracked_material_invalid"]["count"] == 1


def test_cli_final_preflight_uses_injected_result(monkeypatch, capsys, tmp_path):
    fake = {
        "ok": True,
        "wrote": False,
        "turso_connected": False,
        "source_target": "localhost:5432/trading_data",
        "tables": [],
        "failures": [],
        "final_line": FINAL_PASSED_LINE,
    }
    monkeypatch.setattr(migrate_cli, "run_final_source_preflight", lambda **kwargs: fake)
    out_path = tmp_path / "final_source_preflight.json"
    code = migrate_cli.main(
        ["--final-preflight", "--json", "--output", str(out_path), "--exclude-json", "phantom_rows_delete_review.json"]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert FINAL_PASSED_LINE in out
    assert out_path.exists()
