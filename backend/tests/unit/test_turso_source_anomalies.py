"""Anomaly-report tests. Mocks/fakes only — no live Postgres or Turso."""
from __future__ import annotations

from datetime import date

import pytest

from app.cli import turso_migrate_daily_ohlcv as migrate_cli
from app.services.market_data_ingestion.turso_source_anomalies import (
    ANOMALY_LINE,
    classify_violations,
    run_source_anomalies,
)
from app.services.market_data_ingestion.turso_source_preflight import PreflightError

pytestmark = pytest.mark.unit

LOCAL_URL = "postgresql+asyncpg://user:secret@localhost:5432/trading_data"
NEON_URL = "postgresql+asyncpg://user:secret@ep-example.neon.tech/neondb"


def test_classify_open_and_close_outside():
    types, diffs = classify_violations(open_=12.0, high=10.0, low=9.0, close=8.5)
    assert "open_outside" in types
    assert "close_outside" in types
    assert types.count("high_lt_low") == 0
    assert diffs["open_minus_high"] == pytest.approx(2.0)
    assert diffs["low_minus_open"] == pytest.approx(-3.0)
    assert diffs["close_minus_high"] == pytest.approx(-1.5)
    assert diffs["low_minus_close"] == pytest.approx(0.5)


def test_classify_high_lt_low():
    types, diffs = classify_violations(open_=5.0, high=4.0, low=6.0, close=5.0)
    assert "high_lt_low" in types
    assert diffs["high_minus_low"] == pytest.approx(-2.0)


def test_anomalies_require_local_url():
    with pytest.raises(PreflightError, match="LOCAL_POSTGRES_DATABASE_URL"):
        run_source_anomalies(local_postgres_url="", fetchall=lambda s, p: [])


def test_anomalies_refuse_neon_host():
    with pytest.raises(PreflightError, match="non-local"):
        run_source_anomalies(local_postgres_url=NEON_URL, fetchall=lambda s, p: [])


def test_anomalies_report_neighbors_and_summaries():
    invalid = {
        "trade_date": date(2024, 1, 3),
        "symbol": "INFY-EQ",
        "open": 12.0,
        "high": 10.0,
        "low": 9.0,
        "close": 8.5,
        "volume": 100,
        "delivery_qty": 40,
        "delivery_pct": 40.0,
        "turnover": 850.0,
        "adtv_20": 1.0,
        "source": "FYERS",
        "loaded_at": date(2026, 9, 18),
    }
    prev = {
        "trade_date": date(2024, 1, 2),
        "symbol": "INFY-EQ",
        "open": 9.5,
        "high": 10.0,
        "low": 9.0,
        "close": 10.0,
        "volume": 90,
    }
    nxt = {
        "trade_date": date(2024, 1, 4),
        "symbol": "INFY-EQ",
        "open": 8.8,
        "high": 9.0,
        "low": 8.0,
        "close": 8.9,
        "volume": 80,
    }

    def fetchall(sql: str, params):
        sql_l = sql.lower()
        if "high < low" in sql_l and "select trade_date" in sql_l and "limit 1" not in sql_l:
            return [invalid]
        if "order by trade_date desc" in sql_l:
            return [prev]
        if "order by trade_date asc" in sql_l:
            return [nxt]
        raise AssertionError(sql)

    payload = run_source_anomalies(
        local_postgres_url=LOCAL_URL,
        tables=["daily_ohlcv"],
        fetchall=fetchall,
    )
    assert payload["wrote"] is False
    assert payload["turso_connected"] is False
    assert payload["final_line"] == ANOMALY_LINE
    assert "secret" not in payload["source_target"]
    assert payload["external_verification"]["invoked"] is False
    row = payload["anomalies"][0]
    assert row["symbol"] == "INFY-EQ"
    assert row["multiple_violation_types"] is True
    assert "open_outside" in row["failure_types"]
    assert "close_outside" in row["failure_types"]
    assert row["previous_close"] == pytest.approx(10.0)
    assert row["pct_change_prev_close_to_open"] == pytest.approx(20.0)
    assert row["pct_change_close_to_next_open"] == pytest.approx((8.8 - 8.5) / 8.5 * 100.0)
    assert payload["summaries"]["by_symbol"][0]["key"] == "INFY-EQ"
    assert payload["summaries"]["by_year"][0]["key"] == "2024"
    assert payload["summaries"]["by_source"][0]["key"] == "FYERS"
    assert payload["summaries"]["by_loaded_at_date"][0]["key"] == "2026-09-18"
    types = {item["key"] for item in payload["summaries"]["by_violation_type"]}
    assert "open_outside" in types
    assert "close_outside" in types


def test_anomalies_reject_historical_candles():
    with pytest.raises(PreflightError, match="historical_candles"):
        run_source_anomalies(
            local_postgres_url=LOCAL_URL,
            tables=["historical_candles"],
            fetchall=lambda s, p: [],
        )


def test_cli_source_anomalies_missing_url(monkeypatch, capsys):
    monkeypatch.setattr(
        type(migrate_cli.settings),
        "local_postgres_source_url",
        lambda self: "",
    )
    code = migrate_cli.main(["--source-anomalies", "--json"])
    assert code == 2
    out = capsys.readouterr().out
    assert ANOMALY_LINE in out
    assert "LOCAL_POSTGRES_DATABASE_URL" in out


def test_cli_source_anomalies_json_and_output(monkeypatch, capsys, tmp_path):
    fake = {
        "ok": True,
        "wrote": False,
        "turso_connected": False,
        "mode": "source-anomalies",
        "source_target": "localhost:5432/trading_data",
        "anomaly_count": 0,
        "anomalies": [],
        "summaries": {},
        "filters": {},
        "external_verification": {"invoked": False},
        "final_line": ANOMALY_LINE,
    }
    monkeypatch.setattr(migrate_cli, "run_source_anomalies", lambda **kwargs: fake)
    report = tmp_path / "anomalies.json"
    code = migrate_cli.main(
        ["--source-anomalies", "--json", "--output", str(report)]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert ANOMALY_LINE in out
    assert "secret" not in out
    assert report.is_file()
    text = report.read_text(encoding="utf-8")
    assert "secret" not in text
    assert ANOMALY_LINE in text


def test_cli_parser_has_source_anomalies():
    args = migrate_cli.build_parser().parse_args(
        ["--source-anomalies", "--json", "--output", "report.json"]
    )
    assert args.source_anomalies is True
    assert args.output == "report.json"
