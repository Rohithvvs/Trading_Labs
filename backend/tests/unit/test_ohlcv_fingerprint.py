"""Canonical Decimal fingerprints. No database."""
from __future__ import annotations

import pytest

from app.services.market_data_ingestion.repair_apply import (
    MemoryRepairStore,
    RepairError,
    apply_manifest_repairs,
)
from app.services.market_data_ingestion.repair_manifest import (
    FINGERPRINT_VERSION,
    FingerprintError,
    build_repair_manifest,
    canonical_price,
    fingerprint_ohlcv,
)

pytestmark = pytest.mark.unit

LOCAL_URL = "postgresql://postgres:x@localhost:5432/trading_data"


def test_canonical_price_equalizes_scale():
    assert canonical_price("2016.9") == "2016.90000000"
    assert canonical_price("2016.90000000") == "2016.90000000"
    assert canonical_price("904.0") == "904.00000000"
    assert canonical_price("904.00000000") == "904.00000000"
    assert fingerprint_ohlcv(
        {"open": "2016.9", "high": "2018.8", "low": "2004.5", "close": "2004.2", "volume": 140416, "source": "historical_candles"}
    ) == fingerprint_ohlcv(
        {
            "open": "2016.90000000",
            "high": "2018.80000000",
            "low": "2004.50000000",
            "close": "2004.20000000",
            "volume": "140416",
            "source": "historical_candles",
        }
    )


def test_real_numeric_and_volume_and_source_changes_fail():
    base = {
        "open": "2016.9",
        "high": "2018.8",
        "low": "2004.5",
        "close": "2004.2",
        "volume": 140416,
        "source": "historical_candles",
    }
    fp = fingerprint_ohlcv(base)
    changed_px = dict(base, open="2016.91")
    changed_vol = dict(base, volume=140417)
    changed_src = dict(base, source="FYERS")
    assert fingerprint_ohlcv(changed_px) != fp
    assert fingerprint_ohlcv(changed_vol) != fp
    assert fingerprint_ohlcv(changed_src) != fp
    assert fingerprint_ohlcv(dict(base, source="FYERS_LIVE_1D")) != fp
    assert fingerprint_ohlcv(dict(base, source="historical_candles")) == fp


def test_invalid_decimal_rejected():
    bad = {"open": "NaN", "high": 1, "low": 1, "close": 1, "volume": 1, "source": "FYERS"}
    with pytest.raises(FingerprintError):
        fingerprint_ohlcv(bad)
    with pytest.raises(FingerprintError):
        fingerprint_ohlcv({"open": "Infinity", "high": 1, "low": 1, "close": 1, "volume": 1, "source": "FYERS"})
    with pytest.raises(FingerprintError):
        fingerprint_ohlcv({"open": 1, "high": 1, "low": 1, "close": 1, "volume": "1.5", "source": "FYERS"})


def test_fingerprint_is_deterministic_and_versioned():
    vals = {"open": "407.0", "high": "410.65", "low": "405.95", "close": "410.7", "volume": 7073360, "source": "FYERS_LIVE_1D"}
    a = fingerprint_ohlcv(vals)
    b = fingerprint_ohlcv(vals)
    assert a == b
    assert a.startswith(FINGERPRINT_VERSION + "|")
    assert a.split("|")[1] == "407.00000000"


def test_v2_manifest_includes_version():
    preview = {
        "rows": [
            {
                "table": "daily_ohlcv",
                "symbol": "APLAPOLLO-EQ",
                "trade_date": "2026-08-12",
                "verdict": "REPAIRABLE",
                "matching_date": True,
                "source_policy_allows_replacement": True,
                "ohlc_gate": {"decision": "accept"},
                "original": {
                    "open": "2016.9",
                    "high": "2018.8",
                    "low": "2004.5",
                    "close": "2004.2",
                    "volume": 140416,
                    "source": "historical_candles",
                },
                "fyers_bar": {
                    "open": "2016.9",
                    "high": "2018.8",
                    "low": "1991.3",
                    "close": "1997.1",
                    "volume": 714770,
                    "source": "FYERS",
                    "trade_date": "2026-08-12",
                    "symbol": "APLAPOLLO-EQ",
                },
            }
        ]
    }
    manifest = build_repair_manifest(preview)
    assert manifest["fingerprint_version"] == FINGERPRINT_VERSION
    assert manifest["items"][0]["expected_old_values"]["open"] == "2016.90000000"
    assert manifest["items"][0]["expected_old_fingerprint"].startswith("v2_decimal_8|")


def test_unsupported_fingerprint_version_rejected():
    store = MemoryRepairStore(
        {("daily_ohlcv", "X-EQ", "2026-08-03"): {"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1, "source": "FYERS"}}
    )
    item = {
        "table": "daily_ohlcv",
        "symbol": "X-EQ",
        "trade_date": "2026-08-03",
        "fingerprint_version": "v9_unknown",
        "expected_current_source": "FYERS",
        "expected_old_values": {"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1, "source": "FYERS"},
        "proposed_new_values": {"open": 1, "high": 2, "low": 1, "close": 2, "volume": 1, "source": "FYERS"},
    }
    with pytest.raises(RepairError, match="MANIFEST_FINGERPRINT_VERSION_UNSUPPORTED"):
        apply_manifest_repairs(
            {"fingerprint_version": "v9_unknown", "items": [item]},
            local_postgres_url=LOCAL_URL,
            approved_run_id="DRY",
            confirm_local_backup=False,
            execute=False,
            store=store,
        )


def test_three_modeled_rows_match_after_v2():
    modeled = [
        ("APLAPOLLO-EQ", "2026-08-12", "2016.9", "2018.8", "2004.5", "2004.2", 140416, "historical_candles", "2016.90000000"),
        ("BBOX-EQ", "2026-07-14", "904.0", "904.0", "886.55", "886.5", 31684, "historical_candles", "904.00000000"),
        ("BEL-EQ", "2026-08-25", "407.0", "410.65", "405.95", "410.7", 7073360, "FYERS_LIVE_1D", "407.00000000"),
    ]
    store_rows = {}
    items = []
    for sym, day, o, h, l, c, vol, src, _canon in modeled:
        old = {"open": o, "high": h, "low": l, "close": c, "volume": vol, "source": src}
        store_rows[("daily_ohlcv", sym, day)] = {
            "open": f"{float(o):.8f}" if False else str(__import__("decimal").Decimal(o).quantize(__import__("decimal").Decimal("0.00000001"))),
            "high": str(__import__("decimal").Decimal(h).quantize(__import__("decimal").Decimal("0.00000001"))),
            "low": str(__import__("decimal").Decimal(l).quantize(__import__("decimal").Decimal("0.00000001"))),
            "close": str(__import__("decimal").Decimal(c).quantize(__import__("decimal").Decimal("0.00000001"))),
            "volume": vol,
            "source": src,
        }
        items.append(
            {
                "table": "daily_ohlcv",
                "symbol": sym,
                "trade_date": day,
                "expected_current_source": src,
                "expected_old_values": old,
                "proposed_new_values": {
                    "open": o,
                    "high": "413.25" if sym == "BEL-EQ" else h,
                    "low": "1991.3" if sym == "APLAPOLLO-EQ" else ("859.55" if sym == "BBOX-EQ" else l),
                    "close": "1997.1" if sym == "APLAPOLLO-EQ" else ("869.4" if sym == "BBOX-EQ" else "413.25"),
                    "volume": vol,
                    "source": "FYERS",
                },
            }
        )
    payload = apply_manifest_repairs(
        {"fingerprint_version": FINGERPRINT_VERSION, "items": items},
        local_postgres_url=LOCAL_URL,
        approved_run_id="DRY",
        confirm_local_backup=False,
        execute=False,
        store=MemoryRepairStore(store_rows),
        limit=3,
    )
    assert payload["wrote"] is False
    assert [r["status"] for r in payload["results"]] == ["MATCHED_FOR_REPAIR"] * 3
    assert payload["results"][0]["before"]["fingerprint"] == payload["results"][0]["expected_fingerprint"]


def test_v1_manifest_recalculates_from_old_fields_not_raw_string():
    old = {"open": 2016.9, "high": 2018.8, "low": 2004.5, "close": 2004.2, "volume": 140416, "source": "historical_candles"}
    item = {
        "table": "daily_ohlcv",
        "symbol": "APLAPOLLO-EQ",
        "trade_date": "2026-08-12",
        "expected_current_source": "historical_candles",
        "expected_old_values": old,
        "expected_old_fingerprint": "2016.9|2018.8|2004.5|2004.2|140416|historical_candles",
        "proposed_new_values": {"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1, "source": "FYERS"},
    }
    store = MemoryRepairStore(
        {
            ("daily_ohlcv", "APLAPOLLO-EQ", "2026-08-12"): {
                "open": "2016.90000000",
                "high": "2018.80000000",
                "low": "2004.50000000",
                "close": "2004.20000000",
                "volume": 140416,
                "source": "historical_candles",
            }
        }
    )
    payload = apply_manifest_repairs(
        {"items": [item]},
        local_postgres_url=LOCAL_URL,
        approved_run_id="DRY",
        confirm_local_backup=False,
        execute=False,
        store=store,
    )
    assert payload["results"][0]["status"] == "MATCHED_FOR_REPAIR"
