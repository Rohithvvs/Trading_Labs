"""Turso V1 exclusion rules. No live databases."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.services.market_data_ingestion.turso_exclusions import (
    HARDCODED_EXCLUSIONS,
    classify_row_for_turso_copy,
    expected_turso_v1_count,
    load_exclusion_keys,
)
from app.services.market_data_ingestion.turso_migrate import plan_v1_migration

pytestmark = pytest.mark.unit


def test_loads_phantom_file_and_hardcoded_nifty(tmp_path: Path):
    phantom = tmp_path / "phantom_rows_delete_review.json"
    phantom.write_text(
        json.dumps(
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
    keys = load_exclusion_keys([phantom])
    tuples = {(k["table"], k["symbol"], k["trade_date"]) for k in keys}
    assert ("daily_ohlcv", "IRFC-EQ", "2026-08-01") in tuples
    assert ("index_ohlcv", "NIFTY500", "2009-05-18") in tuples
    assert HARDCODED_EXCLUSIONS[0][:3] == ("index_ohlcv", "NIFTY500", "2009-05-18")


def test_classify_skips_exclusion_and_invalid_ohlc_without_delete():
    excluded = {("daily_ohlcv", "IRFC-EQ", "2026-08-01")}
    skip = classify_row_for_turso_copy(
        table="daily_ohlcv",
        row={"symbol": "IRFC-EQ", "trade_date": date(2026, 8, 1), "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
        excluded=excluded,
    )
    assert skip["copy"] is False
    assert skip["action"] == "EXCLUDE_REPORTED"
    gate = classify_row_for_turso_copy(
        table="index_ohlcv",
        row={
            "symbol": "NIFTY500",
            "trade_date": "2009-05-18",
            "open": 3290,
            "high": 3291.50,
            "low": 3280,
            "close": 3293.35,
            "volume": 0,
            "source": "FYERS",
        },
        excluded=set(),
    )
    assert gate["copy"] is False
    assert gate["category"] == "ohlc_gate"
    assert "ohlc_gate" in gate["reason"]
    policy = classify_row_for_turso_copy(
        table="daily_ohlcv",
        row={
            "symbol": "INFY-EQ",
            "trade_date": "2026-08-03",
            "open": 100,
            "high": 110,
            "low": 90,
            "close": 105,
            "volume": 1,
            "source": "historical_candles",
        },
        excluded=set(),
    )
    assert policy["copy"] is True
    assert policy["source"] == "historical_candles"
    assert policy["migration_policy"] == "validated_legacy_backfill_v1"
    ok = classify_row_for_turso_copy(
        table="daily_ohlcv",
        row={
            "symbol": "INFY-EQ",
            "trade_date": "2026-08-03",
            "open": 100,
            "high": 110,
            "low": 90,
            "close": 105,
            "volume": 1,
            "source": "FYERS",
        },
        excluded=set(),
    )
    assert ok["copy"] is True


def test_expected_count_formula():
    result = expected_turso_v1_count(
        source_valid_rows=1000,
        repaired_weekday_replacements=28,
    )
    assert result["minus_saturday_phantoms"] == 48
    assert result["minus_nifty500_invalid"] == 1
    assert result["expected_turso_v1_count"] == 1000 - 48 - 1 + 28


def test_plan_reports_exclusions(tmp_path: Path):
    phantom = tmp_path / "phantom_rows_delete_review.json"
    phantom.write_text(
        json.dumps({"items": [{"table": "daily_ohlcv", "symbol": "IRFC-EQ", "trade_date": "2026-08-01"}]}),
        encoding="utf-8",
    )
    plan = plan_v1_migration(
        source_url=None,
        exclude_json_paths=[str(phantom)],
    )
    assert plan["wrote"] is False
    assert plan["deleted"] is False
    assert plan["exclusion_count"] >= 2
    reasons = {e["symbol"]: e["reason"] for e in plan["exclusions"]}
    assert "IRFC-EQ" in reasons
    assert "NIFTY500" in reasons
