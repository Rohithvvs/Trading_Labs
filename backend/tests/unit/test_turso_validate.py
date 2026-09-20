"""In-memory validation mismatch detection. No live databases."""
from __future__ import annotations

from datetime import date

import pytest

from backend.app.services.market_data_ingestion.turso_validate import compare_history_snapshots

pytestmark = pytest.mark.unit


def _bar(symbol: str, day: str, close: float, volume: int = 1) -> dict:
    d = date.fromisoformat(day)
    return {
        "trade_date": d,
        "symbol": symbol,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": volume,
    }


def test_validation_ok_on_matching_snapshots():
    rows = [_bar("INFY-EQ", "2024-01-02", 100.0), _bar("INFY-EQ", "2024-01-03", 101.0)]
    result = compare_history_snapshots(local_daily=rows, turso_daily=rows)
    assert result["ok"] is True
    assert result["mismatch_codes"] == []
    assert result["daily_row_count"]["local"] == 2


def test_validation_detects_row_count_and_missing_symbol():
    local = [_bar("INFY-EQ", "2024-01-02", 100.0), _bar("TCS-EQ", "2024-01-02", 50.0)]
    turso = [_bar("INFY-EQ", "2024-01-02", 100.0)]
    result = compare_history_snapshots(local_daily=local, turso_daily=turso)
    assert result["ok"] is False
    assert "daily_row_count" in result["mismatch_codes"]
    assert "missing_symbols" in result["mismatch_codes"]
    assert "TCS-EQ" in result["missing_symbols"]


def test_validation_detects_close_mismatch_beyond_tolerance():
    local = [_bar("INFY-EQ", "2024-01-02", 100.0)]
    turso = [_bar("INFY-EQ", "2024-01-02", 100.5)]
    result = compare_history_snapshots(
        local_daily=local, turso_daily=turso, close_tolerance=1e-6, sample_size=10
    )
    assert result["ok"] is False
    assert "sample_ohlcv" in result["mismatch_codes"]


def test_validation_allows_float_noise_within_tolerance():
    local = [_bar("INFY-EQ", "2024-01-02", 100.0)]
    turso = [_bar("INFY-EQ", "2024-01-02", 100.0 + 1e-9)]
    result = compare_history_snapshots(
        local_daily=local, turso_daily=turso, close_tolerance=1e-6, sample_size=10
    )
    assert result["ok"] is True


def test_validation_detects_duplicate_pk():
    rows = [_bar("INFY-EQ", "2024-01-02", 100.0), _bar("INFY-EQ", "2024-01-02", 101.0)]
    result = compare_history_snapshots(local_daily=rows, turso_daily=rows)
    assert result["ok"] is False
    assert "duplicate_pk" in result["mismatch_codes"]
