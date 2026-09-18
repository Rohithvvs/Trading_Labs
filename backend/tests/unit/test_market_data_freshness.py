"""Freshness gate unit tests (mocked repository / universe)."""
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.services.market_data_ingestion.freshness import evaluate_freshness
from app.services.market_data_ingestion.calendar_utils import expected_last_completed_session
from app.services.trading_hours_service import TradingHoursService
from datetime import datetime
from zoneinfo import ZoneInfo


def test_expected_session_after_close_trading_day():
    th = TradingHoursService()
    # Wednesday 2026-08-05 17:00 IST after close
    now = datetime(2026, 8, 5, 17, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    if th.is_trading_day(now):
        assert expected_last_completed_session(now) == date(2026, 8, 5)


def test_expected_session_before_open_uses_previous():
    th = TradingHoursService()
    now = datetime(2026, 8, 5, 8, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    if th.is_trading_day(now):
        d = expected_last_completed_session(now)
        assert d < date(2026, 8, 5)


@pytest.mark.asyncio
async def test_freshness_blocks_when_gate_on_and_incomplete(monkeypatch):
    monkeypatch.setenv("STRATEGY_MARKET_DATA_GATE_ENABLED", "true")
    with (
        patch(
            "app.services.market_data_ingestion.freshness.expected_last_completed_session",
            return_value=date(2026, 8, 5),
        ),
        patch(
            "app.services.market_data_ingestion.freshness.repository.symbols_present_on",
            new=AsyncMock(return_value={"AAA-EQ"}),
        ),
        patch(
            "app.services.market_data_ingestion.freshness.repository.index_present",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.services.market_data_ingestion.freshness.repository.max_equity_trade_date",
            new=AsyncMock(return_value=date(2026, 8, 5)),
        ),
        patch(
            "app.services.market_data_ingestion.freshness.repository.max_index_trade_date",
            new=AsyncMock(return_value=date(2026, 8, 5)),
        ),
    ):
        res = await evaluate_freshness(active_symbols=["AAA-EQ", "BBB-EQ", "CCC-EQ"] * 40)
        assert res.ok is False
        assert res.code == "MARKET_DATA_STALE"
        assert res.reason == "equity_incomplete"


@pytest.mark.asyncio
async def test_freshness_pass_when_complete(monkeypatch):
    monkeypatch.setenv("STRATEGY_MARKET_DATA_GATE_ENABLED", "true")
    symbols = [f"S{i}-EQ" for i in range(100)]
    with (
        patch(
            "app.services.market_data_ingestion.freshness.expected_last_completed_session",
            return_value=date(2026, 8, 5),
        ),
        patch(
            "app.services.market_data_ingestion.freshness.repository.symbols_present_on",
            new=AsyncMock(return_value=set(symbols)),
        ),
        patch(
            "app.services.market_data_ingestion.freshness.repository.index_present",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.services.market_data_ingestion.freshness.repository.max_equity_trade_date",
            new=AsyncMock(return_value=date(2026, 8, 5)),
        ),
        patch(
            "app.services.market_data_ingestion.freshness.repository.max_index_trade_date",
            new=AsyncMock(return_value=date(2026, 8, 5)),
        ),
    ):
        res = await evaluate_freshness(active_symbols=symbols)
        assert res.ok is True
        assert res.code == "OK"


@pytest.mark.asyncio
async def test_gate_disabled_does_not_block(monkeypatch):
    monkeypatch.setenv("STRATEGY_MARKET_DATA_GATE_ENABLED", "false")
    with (
        patch(
            "app.services.market_data_ingestion.freshness.expected_last_completed_session",
            return_value=date(2026, 8, 5),
        ),
        patch(
            "app.services.market_data_ingestion.freshness.repository.symbols_present_on",
            new=AsyncMock(return_value=set()),
        ),
        patch(
            "app.services.market_data_ingestion.freshness.repository.index_present",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "app.services.market_data_ingestion.freshness.repository.max_equity_trade_date",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.market_data_ingestion.freshness.repository.max_index_trade_date",
            new=AsyncMock(return_value=None),
        ),
    ):
        res = await evaluate_freshness(active_symbols=["AAA-EQ"])
        assert res.ok is True  # fail-open
        assert res.gate_enabled is False
