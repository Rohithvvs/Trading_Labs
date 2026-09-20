"""Writer inventory and repair-plan CLIs. No live databases."""
from __future__ import annotations

import json

import pytest

from app.cli import ohlcv_repair_plan as repair_cli
from app.cli import ohlcv_writer_audit as writer_cli
from app.services.market_data_ingestion.writer_inventory import DAILY_INDEX_WRITERS

pytestmark = pytest.mark.unit


def test_writer_audit_lists_historical_candles_and_live_1d(capsys):
    code = writer_cli.main([])
    assert code == 0
    out = capsys.readouterr().out
    payload = json.loads(out[out.index("{") : out.rindex("}") + 1])
    assert payload["wrote"] is False
    assert payload["db_connected"] is False
    sources = {w["source"] for w in payload["writers"]}
    assert "historical_candles" in sources
    assert "FYERS_LIVE_1D" in sources
    assert "FYERS" in sources
    assert "WRITER AUDIT COMPLETE — NO DATA WAS WRITTEN" in out


def test_inventory_marks_acs_copy_as_writer():
    acs = [w for w in DAILY_INDEX_WRITERS if "candle_backfill.py" in w["path"]]
    assert acs and acs[0]["writes"] is True
    assert acs[0]["source"] == "historical_candles"


def test_repair_plan_dry_run_from_anomaly_json(tmp_path, capsys):
    report = tmp_path / "anomalies.json"
    report.write_text(
        json.dumps(
            {
                "anomalies": [
                    {
                        "table": "daily_ohlcv",
                        "symbol": "IRFC-EQ",
                        "trade_date": "2026-08-01",
                    },
                    {
                        "table": "daily_ohlcv",
                        "symbol": "IRFC-EQ",
                        "trade_date": "2026-08-01",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    code = repair_cli.main(["--dry-run", "--from-anomaly-json", str(report)])
    assert code == 0
    out = capsys.readouterr().out
    payload = json.loads(out[out.index("{") : out.rindex("}") + 1])
    assert payload["wrote"] is False
    assert payload["provider_called"] is False
    assert payload["key_count"] == 1
    assert payload["keys"][0]["symbol"] == "IRFC-EQ"
    assert "REPAIR PLAN DRY-RUN — NO DATA WAS WRITTEN" in out


def test_repair_execute_refused(capsys):
    code = repair_cli.main(["--execute", "--confirm-local-backup"])
    assert code == 2
    out = capsys.readouterr().out
    payload = json.loads(out[out.index("{") : out.rindex("}") + 1])
    assert payload["wrote"] is False
    assert payload["status"] == "REFUSED"
