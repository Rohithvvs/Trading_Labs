"""Repair manifest builder tests. No database."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.cli import ohlcv_repair_plan as repair_cli
from app.cli.ohlcv_repair_plan import EXECUTE_DISABLED
from app.services.market_data_ingestion.repair_manifest import (
    ManifestError,
    build_phantom_delete_review,
    build_repair_manifest,
)

pytestmark = pytest.mark.unit


def _repairable_row(**overrides):
    row = {
        "table": "daily_ohlcv",
        "symbol": "IRFC-EQ",
        "trade_date": "2026-08-01",
        "verdict": "REPAIRABLE",
        "matching_date": True,
        "source_policy_allows_replacement": True,
        "ohlc_gate": {"decision": "accept", "severity": "ok", "material_reasons": []},
        "original": {
            "open": 100,
            "high": 108,
            "low": 102,
            "close": 100,
            "volume": 800,
            "source": "historical_candles",
        },
        "fyers_bar": {
            "trade_date": "2026-08-01",
            "symbol": "IRFC-EQ",
            "open": 101,
            "high": 110,
            "low": 99,
            "close": 105,
            "volume": 2000000,
            "source": "FYERS",
        },
    }
    row.update(overrides)
    return row


def test_manifest_only_repairable_and_sorted():
    preview = {
        "rows": [
            _repairable_row(symbol="BEL-EQ", trade_date="2026-08-25"),
            _repairable_row(symbol="ADANIENT-EQ"),
            _repairable_row(verdict="NO_FYERS_BAR", matching_date=False),
            _repairable_row(symbol="IRFC-EQ"),
        ]
    }
    created = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
    m1 = build_repair_manifest(preview, source_checksum="abc", created_at=created)
    m2 = build_repair_manifest(preview, source_checksum="abc", created_at=created)
    assert m1["item_count"] == 3
    assert [i["symbol"] for i in m1["items"]] == ["ADANIENT-EQ", "BEL-EQ", "IRFC-EQ"]
    assert m1 == m2
    assert all(i["repair_status"] == "PENDING_APPROVAL" for i in m1["items"])
    assert all(i["proposed_new_values"]["source"] == "FYERS" for i in m1["items"])
    dumped = json.dumps(m1)
    assert "FYERS_ACCESS_TOKEN" not in dumped
    assert "postgresql://" not in dumped
    assert "token" not in dumped.lower() or "historical" in dumped.lower()


def test_manifest_rejects_malformed_and_empty():
    with pytest.raises(ManifestError):
        build_repair_manifest({"no_rows": True})
    with pytest.raises(ManifestError, match="no REPAIRABLE"):
        build_repair_manifest({"rows": [_repairable_row(verdict="NO_FYERS_BAR")]})


def test_manifest_rejects_non_fyers_source():
    with pytest.raises(ManifestError, match="no REPAIRABLE"):
        build_repair_manifest(
            {
                "rows": [
                    _repairable_row(fyers_bar=_repairable_row()["fyers_bar"] | {"source": "FYERS_LIVE_1D"})
                ]
            }
        )


def test_phantom_review_excludes_repairable_and_does_not_delete():
    preview = {
        "rows": [
            _repairable_row(),
            {
                "table": "daily_ohlcv",
                "symbol": "IRFC-EQ",
                "trade_date": "2026-08-01",
                "day_of_week": "Saturday",
                "calendar_status": "WEEKEND_NON_TRADING_DAY",
                "verdict": "NON_TRADING_DAY_PHANTOM",
                "original": {
                    "open": 100,
                    "high": 108,
                    "low": 102,
                    "close": 100,
                    "volume": 800,
                    "source": "historical_candles",
                    "loaded_at": "2026-08-15T12:20:00",
                },
            },
        ]
    }
    review = build_phantom_delete_review(preview, created_at=datetime(2026, 9, 19, tzinfo=timezone.utc))
    assert review["deleted"] is False
    assert review["wrote"] is False
    assert review["item_count"] == 1
    assert review["items"][0]["trade_date"] == "2026-08-01"
    assert review["items"][0]["delete_status"] == "REVIEW_ONLY_NO_DELETE"
    assert review["items"][0]["original"]["source"] == "historical_candles"
    assert review["items"][0]["original"]["loaded_at"]
    assert review["items"][0]["calendar_status"] == "WEEKEND_NON_TRADING_DAY"
    assert "reason" in review["items"][0]
    dumped = json.dumps(review)
    assert "FYERS_ACCESS_TOKEN" not in dumped
    assert "postgresql://" not in dumped
    review2 = build_phantom_delete_review(preview, created_at=datetime(2026, 9, 19, tzinfo=timezone.utc))
    assert review == review2
    manifest = build_repair_manifest(preview, created_at=datetime(2026, 9, 19, tzinfo=timezone.utc))
    assert all(i["symbol"] != "IRFC-EQ" or i["trade_date"] != "2026-08-01" or i.get("proposed_new_values") for i in manifest["items"])
    assert all(i["repair_status"] == "PENDING_APPROVAL" for i in manifest["items"])
    assert not any(i["trade_date"] == "2026-08-01" and i["symbol"] == "IRFC-EQ" and "FYERS" != i["proposed_new_values"]["source"] for i in manifest["items"])


def test_cli_build_manifest(tmp_path, capsys):
    preview = tmp_path / "preview.json"
    preview.write_text(json.dumps({"rows": [_repairable_row()]}), encoding="utf-8")
    out = tmp_path / "manifest.json"
    code = repair_cli.main(
        ["--build-manifest", "--from-preview-json", str(preview), "--output", str(out)]
    )
    assert code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["item_count"] == 1
    assert payload["items"][0]["reason"] == "replace_invalid_acs_derived_daily_bar"
    assert "MANIFEST WRITTEN" in capsys.readouterr().out


def test_cli_execute_stub_refuses_without_db(capsys):
    code = repair_cli.main(
        [
            "--execute",
            "--confirm-local-backup",
            "--manifest",
            "repair_manifest.json",
            "--approved-repair-run-id",
            "run-1",
        ]
    )
    assert code == 2
    out = capsys.readouterr().out
    payload = json.loads(out[out.index("{") : out.rindex("}") + 1])
    assert payload["wrote"] is False
    assert "manifest file not found" in payload["reason"]
