"""Fingerprint repair tests. In-memory store only — no Postgres."""
from __future__ import annotations

from datetime import date

import pytest

from app.cli import ohlcv_repair_plan as repair_cli
from app.cli.ohlcv_repair_plan import EXECUTE_DISABLED
from app.services.market_data_ingestion.repair_apply import (
    MemoryRepairStore,
    RepairError,
    apply_manifest_repairs,
)
from app.services.market_data_ingestion.repair_manifest import fingerprint_ohlcv

pytestmark = pytest.mark.unit

LOCAL_URL = "postgresql://postgres:x@localhost:5432/trading_data"


def _item(**overrides):
    old = {
        "open": 100,
        "high": 108,
        "low": 102,
        "close": 100,
        "volume": 800,
        "source": "historical_candles",
    }
    item = {
        "table": "daily_ohlcv",
        "symbol": "IRFC-EQ",
        "trade_date": "2026-08-01",
        "expected_current_source": "historical_candles",
        "expected_old_fingerprint": fingerprint_ohlcv(old),
        "expected_old_values": old,
        "proposed_new_values": {
            "open": 101,
            "high": 110,
            "low": 99,
            "close": 105,
            "volume": 2_000_000,
            "source": "FYERS",
            "trade_date": "2026-08-01",
            "symbol": "IRFC-EQ",
        },
        "reason": "replace_invalid_acs_derived_daily_bar",
    }
    item.update(overrides)
    return item


def test_dry_run_matches_and_does_not_update():
    store = MemoryRepairStore(
        {
            ("daily_ohlcv", "IRFC-EQ", "2026-08-01"): {
                "open": 100,
                "high": 108,
                "low": 102,
                "close": 100,
                "volume": 800,
                "source": "historical_candles",
            }
        }
    )
    payload = apply_manifest_repairs(
        {"items": [_item()]},
        local_postgres_url=LOCAL_URL,
        approved_run_id="DRY",
        confirm_local_backup=False,
        execute=False,
        store=store,
    )
    assert payload["wrote"] is False
    assert payload["results"][0]["status"] == "MATCHED_FOR_REPAIR"
    assert store.rows[("daily_ohlcv", "IRFC-EQ", "2026-08-01")]["source"] == "historical_candles"


def test_execute_updates_on_fingerprint_match():
    store = MemoryRepairStore(
        {
            ("daily_ohlcv", "IRFC-EQ", "2026-08-01"): {
                "open": 100,
                "high": 108,
                "low": 102,
                "close": 100,
                "volume": 800,
                "source": "historical_candles",
            }
        }
    )
    payload = apply_manifest_repairs(
        {"items": [_item()]},
        local_postgres_url=LOCAL_URL,
        approved_run_id="LIMITED-3",
        confirm_local_backup=True,
        execute=True,
        store=store,
    )
    assert payload["wrote"] is True
    assert store.committed is True
    assert store.rows[("daily_ohlcv", "IRFC-EQ", "2026-08-01")]["source"] == "FYERS"
    assert store.rows[("daily_ohlcv", "IRFC-EQ", "2026-08-01")]["close"] == 105


def test_already_repaired_fyers_row_is_skipped_not_mismatch():
    new = {
        "open": 101,
        "high": 110,
        "low": 99,
        "close": 105,
        "volume": 2_000_000,
        "source": "FYERS",
    }
    store = MemoryRepairStore({("daily_ohlcv", "IRFC-EQ", "2026-08-01"): dict(new)})
    payload = apply_manifest_repairs(
        {"items": [_item()]},
        local_postgres_url=LOCAL_URL,
        approved_run_id="FULL-25",
        confirm_local_backup=True,
        execute=True,
        store=store,
    )
    assert payload["results"][0]["status"] == "ALREADY_REPAIRED"
    assert payload["results"][0]["updated"] is False
    assert store.committed is True
    assert store.rolled_back is False


def test_mismatch_rolls_back():
    store = MemoryRepairStore(
        {
            ("daily_ohlcv", "IRFC-EQ", "2026-08-01"): {
                "open": 1,
                "high": 2,
                "low": 1,
                "close": 2,
                "volume": 9,
                "source": "FYERS",
            }
        }
    )
    with pytest.raises(RepairError, match="fingerprint"):
        apply_manifest_repairs(
            {"items": [_item()]},
            local_postgres_url=LOCAL_URL,
            approved_run_id="LIMITED-3",
            confirm_local_backup=True,
            execute=True,
            store=store,
        )
    assert store.rolled_back is True
    assert store.rows[("daily_ohlcv", "IRFC-EQ", "2026-08-01")]["source"] == "FYERS"


def test_refuses_non_local_and_historical_candles_table():
    with pytest.raises(RepairError, match="non-local"):
        apply_manifest_repairs(
            {"items": [_item()]},
            local_postgres_url="postgresql://user:x@ep-example.neon.tech/db",
            approved_run_id="X",
            confirm_local_backup=True,
            execute=True,
            store=MemoryRepairStore(),
        )
    store = MemoryRepairStore({("historical_candles", "IRFC-EQ", "2026-08-01"): {}})
    with pytest.raises(RepairError, match="not eligible"):
        apply_manifest_repairs(
            {"items": [_item(table="historical_candles")]},
            local_postgres_url=LOCAL_URL,
            approved_run_id="X",
            confirm_local_backup=True,
            execute=True,
            store=store,
        )


def test_execute_without_flags_still_refused(capsys):
    code = repair_cli.main(["--execute"])
    assert code == 2
    out = capsys.readouterr().out
    assert EXECUTE_DISABLED in out
    assert "wrote" in out
