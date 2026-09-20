"""CLI parsing and dry-run behavior. Never opens Turso or local Postgres."""
from __future__ import annotations

import json

import pytest

from app.cli import turso_cli as cli
from app.cli import turso_migrate_daily_ohlcv as migrate_cli
from app.cli import turso_validate_daily_ohlcv as validate_cli
from app.services.market_data_ingestion.turso_migrate import (
    plan_v1_migration,
    refuse_live_migration,
)

pytestmark = pytest.mark.unit


def test_parser_defaults_are_dry_run():
    p = cli.build_parser()
    args = p.parse_args(["schema-apply"])
    assert args.execute is False
    args2 = p.parse_args(["migrate", "--limit", "10", "--symbols", "INFY-EQ"])
    assert args2.execute is False
    assert args2.limit == 10
    args3 = p.parse_args(["validate"])
    assert args3.live is False


def test_schema_apply_dry_run(capsys):
    code = cli.main(["schema-apply"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "DRY_RUN"
    assert payload["wrote"] is False


def test_schema_apply_execute_uses_injected_client(monkeypatch, capsys):
    from app.db.turso import InMemoryTursoClient, apply_v1_schema

    client = InMemoryTursoClient()
    apply_v1_schema(client, execute=True)
    monkeypatch.setattr("app.db.turso.connect_turso", lambda settings: client)
    code = cli.main(["schema-apply", "--execute"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["wrote"] is True
    assert payload["postgres_untouched"] is True
    assert "daily_ohlcv" in payload["tables"]
    assert "historical_candles" not in payload["tables"]


def test_migrate_execute_requires_backup_flag(capsys):
    code = cli.main(["migrate", "--execute"])
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "REFUSED"
    assert "confirm-local-backup" in payload["reason"]


def test_migrate_execute_with_backup_still_refuses_without_local_source(capsys):
    code = cli.main(["migrate", "--execute", "--confirm-local-backup"])
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["wrote"] is False
    assert payload["status"] == "REFUSED"
    assert "LOCAL_POSTGRES_DATABASE_URL" in payload["reason"]


def test_dedicated_migrate_cli_parser_has_source_inspect():
    args = migrate_cli.build_parser().parse_args(["--source-inspect", "--json"])
    assert args.source_inspect is True
    assert args.json is True


def test_dedicated_migrate_cli_dry_run(capsys):
    code = migrate_cli.main(["--dry-run", "--limit", "5", "--batch-size", "50"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["wrote"] is False
    assert payload["batch_size"] == 50
    assert payload["limit"] == 5


def test_dedicated_migrate_cli_refuses_without_backup(capsys):
    code = migrate_cli.main(["--execute"])
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert "confirm-local-backup" in payload["reason"]


def test_refuse_live_migration_requires_local_postgres_url():
    msg = refuse_live_migration(
        execute=True, confirm_local_backup=True, local_postgres_url=""
    )
    assert msg is not None
    assert "LOCAL_POSTGRES_DATABASE_URL" in msg
    assert "DATABASE_URL" in msg


def test_refuse_live_migration_phase_gate_when_source_set():
    msg = refuse_live_migration(
        execute=True,
        confirm_local_backup=True,
        local_postgres_url="postgresql://localhost:5432/trading_data",
    )
    assert msg is not None
    assert "will not open" in msg


def test_dedicated_validate_cli_json(capsys):
    code = validate_cli.main(["--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True


def test_migrate_dry_run_plans_v1_tables(capsys):
    code = cli.main(["migrate", "--dry-run"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["wrote"] is False
    assert "daily_ohlcv" in payload["tables"]
    assert "index_ohlcv" in payload["tables"]
    assert "historical_candles" not in payload["tables"]
    assert "adtv_20" in payload["daily_columns"]
    assert "delivery_qty" in payload["daily_columns"]


def test_migrate_rejects_historical_candles():
    with pytest.raises(ValueError, match="historical_candles"):
        plan_v1_migration(source_url=None, tables=["historical_candles"])


def test_validate_static_ok(capsys):
    code = cli.main(["validate"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["live_compare"] is False


def test_validate_live_skipped(capsys):
    code = cli.main(["validate", "--live"])
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["skipped"] is True
    assert payload["live_compare"] is False
