"""Migration-only Turso source policy. No live databases."""
from __future__ import annotations

from datetime import date, datetime

import pytest
from zoneinfo import ZoneInfo

from app.services.market_data_ingestion.source_policy import classify_daily_index_source
from app.services.market_data_ingestion.turso_exclusions import classify_row_for_turso_copy
from app.services.market_data_ingestion.turso_migration_policy import (
    MIGRATION_POLICY,
    classify_live_1d_finalization,
    classify_migration_source,
    resolve_duplicate_key,
)

pytestmark = pytest.mark.unit

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 9, 19, 10, 0, tzinfo=IST)


def test_runtime_policy_still_rejects_legacy_sources():
    assert classify_daily_index_source("historical_candles")["decision"] == "reject"
    assert classify_daily_index_source("FYERS_LIVE_1D")["decision"] == "reject"
    assert classify_daily_index_source("FYERS")["decision"] == "accept"


def test_migration_policy_accepts_validated_legacy_sources():
    assert classify_migration_source("FYERS")["decision"] == "accept"
    assert classify_migration_source("historical_candles")["decision"] == "accept"
    assert classify_migration_source("FYERS_LIVE_1D")["decision"] == "accept"
    assert classify_migration_source("ACS")["decision"] == "reject"
    assert classify_migration_source("")["reason"] == "missing_source"


def test_live_1d_next_day_rule():
    prior = classify_live_1d_finalization(date(2026, 9, 18), now=NOW)
    assert prior["copy"] is True
    assert prior["decision"] == "finalized"
    today = classify_live_1d_finalization(date(2026, 9, 19), now=NOW)
    assert today["copy"] is False
    assert today["decision"] == "in_progress"
    after_close = classify_live_1d_finalization(
        date(2026, 9, 19), now=datetime(2026, 9, 19, 17, 0, tzinfo=IST)
    )
    assert after_close["copy"] is False


def test_classify_copies_legacy_and_excludes_in_progress_live():
    hist = classify_row_for_turso_copy(
        table="daily_ohlcv",
        row={
            "symbol": "INFY-EQ",
            "trade_date": "2025-06-18",
            "open": 100,
            "high": 110,
            "low": 90,
            "close": 105,
            "volume": 1,
            "source": "historical_candles",
        },
        excluded=set(),
        now_ist=NOW,
    )
    assert hist["copy"] is True
    assert hist["source"] == "historical_candles"
    live_ok = classify_row_for_turso_copy(
        table="daily_ohlcv",
        row={
            "symbol": "INFY-EQ",
            "trade_date": "2026-09-18",
            "open": 100,
            "high": 110,
            "low": 90,
            "close": 105,
            "volume": 1,
            "source": "FYERS_LIVE_1D",
        },
        excluded=set(),
        now_ist=NOW,
    )
    assert live_ok["copy"] is True
    live_today = classify_row_for_turso_copy(
        table="daily_ohlcv",
        row={
            "symbol": "INFY-EQ",
            "trade_date": "2026-09-19",
            "open": 100,
            "high": 110,
            "low": 90,
            "close": 105,
            "volume": 1,
            "source": "FYERS_LIVE_1D",
        },
        excluded=set(),
        now_ist=NOW,
    )
    assert live_today["copy"] is False
    assert live_today["category"] == "live_1d_in_progress"


def test_duplicate_precedence_fyers_wins_same_rank_unresolved():
    fyers = {"source": "FYERS", "symbol": "INFY-EQ", "trade_date": "2026-01-02"}
    live = {"source": "FYERS_LIVE_1D", "symbol": "INFY-EQ", "trade_date": "2026-01-02"}
    acs = {"source": "historical_candles", "symbol": "INFY-EQ", "trade_date": "2026-01-02"}
    won = resolve_duplicate_key([acs, live, fyers])
    assert won["copy"] is True
    assert won["row"]["source"] == "FYERS"
    tied = resolve_duplicate_key([dict(fyers), dict(fyers)])
    assert tied["copy"] is False
    assert tied["category"] == "duplicate_unresolved"


def test_policy_name():
    assert MIGRATION_POLICY == "validated_legacy_backfill_v1"
