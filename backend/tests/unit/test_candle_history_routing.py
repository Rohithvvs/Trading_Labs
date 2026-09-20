"""Nova vs Turso routing guards. No live connections."""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.services.market_data_ingestion import history_backend as hb
from backend.app.services.market_data_ingestion.repository import _use_turso_history

pytestmark = pytest.mark.unit


def test_repository_helper_defaults_to_postgres(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(hb, "uses_turso", lambda: False)
    assert _use_turso_history() is False


def test_default_uses_postgres(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CANDLE_HISTORY_BACKEND", raising=False)
    monkeypatch.setattr(hb, "candle_history_backend", lambda: hb.POSTGRES)
    assert hb.uses_postgres() is True
    assert hb.uses_turso() is False
    hb.assert_not_writing_candles_to_wrong_backend(want_turso=False)
    with pytest.raises(RuntimeError, match="Turso candle write"):
        hb.assert_not_writing_candles_to_wrong_backend(want_turso=True)


def test_turso_flag_blocks_postgres_writes(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(hb, "candle_history_backend", lambda: hb.TURSO)
    assert hb.uses_turso() is True
    hb.assert_not_writing_candles_to_wrong_backend(want_turso=True)
    with pytest.raises(RuntimeError, match="Postgres candle write"):
        hb.assert_not_writing_candles_to_wrong_backend(want_turso=False)


@pytest.mark.asyncio
async def test_fetch_equity_history_routes_to_postgres(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(hb, "uses_turso", lambda: False)
    fake = AsyncMock(return_value=[{"symbol": "INFY-EQ", "trade_date": date(2024, 1, 1)}])
    with patch(
        "backend.app.services.market_data_ingestion.repository.fetch_equity_history",
        new=fake,
    ):
        rows = await hb.fetch_equity_history("INFY-EQ")
    assert rows[0]["symbol"] == "INFY-EQ"
    fake.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_equity_history_routes_to_turso(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(hb, "uses_turso", lambda: True)
    fake = AsyncMock(return_value=[{"symbol": "INFY-EQ"}])
    postgres = AsyncMock(side_effect=AssertionError("postgres repository must not run"))
    with (
        patch(
            "backend.app.services.market_data_ingestion.turso_repository.fetch_equity_history",
            new=fake,
        ),
        patch(
            "backend.app.services.market_data_ingestion.repository.fetch_equity_history",
            new=postgres,
        ),
    ):
        rows = await hb.fetch_equity_history("INFY-EQ")
    assert rows[0]["symbol"] == "INFY-EQ"
    fake.assert_awaited_once()
    postgres.assert_not_called()
