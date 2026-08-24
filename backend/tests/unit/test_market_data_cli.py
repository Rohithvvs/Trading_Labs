"""CLI parsing and exit-code wiring tests."""
from unittest.mock import AsyncMock, patch

from app.cli import market_data_cli as cli


def test_parser_commands():
    p = cli.build_parser()
    args = p.parse_args(["daily-update", "--force"])
    assert args.command == "daily-update"
    assert args.force is True
    args2 = p.parse_args(["verify", "--json"])
    assert args2.json is True
    args3 = p.parse_args(["full-load", "--years", "18", "--skip-delivery"])
    assert args3.years == 18
    assert args3.skip_delivery is True


def test_main_locked_exit(monkeypatch):
    async def fake_daily(**kwargs):
        return {"status": "SKIPPED_LOCKED", "exit_code": 3}

    with patch(
        "app.services.market_data_ingestion.pipelines.daily_update.run_daily_update",
        new=fake_daily,
    ):
        code = cli.main(["daily-update"])
        assert code == 3
