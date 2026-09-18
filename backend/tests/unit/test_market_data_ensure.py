"""ensure_latest_market_data fast path + fetch path (mocked)."""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest

from app.services.market_data_ingestion import ensure as ens


@pytest.fixture(autouse=True)
def _clear_universe_cache():
    ens._UNIVERSE_CACHE = None
    yield
    ens._UNIVERSE_CACHE = None


@pytest.mark.asyncio
async def test_ensure_already_fresh_fast_path():
    session = date(2026, 8, 7)
    symbols = ["AAA-EQ", "BBB-EQ"]
    present = set(symbols)

    with (
        patch.object(ens, "expected_last_completed_session", return_value=session),
        patch(
            "app.services.universe_service.UniverseService.get_active_nifty500_symbols",
            new=AsyncMock(return_value=symbols),
        ),
        patch.object(
            ens.repository,
            "session_coverage_snapshot",
            new=AsyncMock(
                return_value={
                    "present": present,
                    "with_delivery": present,
                    "with_adtv": present,
                    "present_count": 2,
                    "delivery_count": 2,
                    "adtv_count": 2,
                    "universe_count": 2,
                    "index_present": True,
                    "max_equity_date": session,
                }
            ),
        ),
        patch.object(ens, "acquire_market_data_load_lock", new=AsyncMock()) as lock_mock,
    ):
        result = await ens.ensure_latest_market_data(trigger_source="SCANNER")
        assert result["status"] == "ALREADY_FRESH"
        assert result["exit_code"] == 0
        assert result["fetched"]["ohlcv"] is False
        assert result["duration_ms"] is not None
        lock_mock.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_fetches_when_index_missing():
    session = date(2026, 8, 7)
    symbols = ["AAA-EQ"]
    present = set(symbols)
    lease = MagicMock()
    lease.acquired = True
    lease.release = AsyncMock()

    with (
        patch.object(ens, "expected_last_completed_session", return_value=session),
        patch(
            "app.services.universe_service.UniverseService.get_active_nifty500_symbols",
            new=AsyncMock(return_value=symbols),
        ),
        patch(
            "app.services.universe_service.UniverseService.touch_lifecycle",
            new=AsyncMock(),
        ),
        patch.object(
            ens.repository,
            "session_coverage_snapshot",
            new=AsyncMock(
                side_effect=[
                    # initial snapshot — index missing → slow path
                    {
                        "present": present,
                        "with_delivery": present,
                        "with_adtv": present,
                        "present_count": 1,
                        "delivery_count": 1,
                        "adtv_count": 1,
                        "universe_count": 1,
                        "index_present": False,
                        "max_equity_date": session,
                    },
                    # under lock
                    {
                        "present": present,
                        "with_delivery": present,
                        "with_adtv": present,
                        "present_count": 1,
                        "delivery_count": 1,
                        "adtv_count": 1,
                        "universe_count": 1,
                        "index_present": False,
                        "max_equity_date": session,
                    },
                    # final snapshot
                    {
                        "present": present,
                        "with_delivery": present,
                        "with_adtv": present,
                        "present_count": 1,
                        "delivery_count": 1,
                        "adtv_count": 1,
                        "universe_count": 1,
                        "index_present": True,
                        "max_equity_date": session,
                    },
                ]
            ),
        ),
        patch.object(ens.repository, "index_present", new=AsyncMock(return_value=False)),
        patch.object(ens.repository, "symbols_present_on", new=AsyncMock(return_value=present)),
        patch.object(
            ens.repository, "symbols_with_delivery_on", new=AsyncMock(return_value=present)
        ),
        patch.object(ens.repository, "symbols_with_adtv_on", new=AsyncMock(return_value=present)),
        patch.object(ens, "acquire_market_data_load_lock", new=AsyncMock(return_value=lease)),
        patch.object(ens.load_tracking, "start_load", new=AsyncMock(return_value=uuid.uuid4())),
        patch.object(ens.load_tracking, "finish_load", new=AsyncMock()),
        patch.object(
            ens.FyersEodProvider,
            "fetch_index_range",
            new=AsyncMock(
                return_value=[
                    {
                        "trade_date": session,
                        "symbol": "NIFTY500",
                        "open": 1,
                        "high": 1,
                        "low": 1,
                        "close": 1,
                    }
                ]
            ),
        ),
        patch.object(ens.repository, "upsert_index_bars", new=AsyncMock(return_value=1)),
        patch.object(
            ens.NseDeliveryProvider, "fetch_session_delivery", new=AsyncMock(return_value={})
        ),
        patch.object(ens.repository, "update_delivery_for_session", new=AsyncMock(return_value=0)),
        patch.object(ens.repository, "update_adtv_for_session", new=AsyncMock(return_value=0)),
    ):
        result = await ens.ensure_latest_market_data(trigger_source="CLI", write_load_log=True)
        assert result["status"] in {"SUCCESS", "PARTIAL", "ALREADY_FRESH"}
        assert result.get("fetched", {}).get("index") is True or result["status"] == "SUCCESS"
        lease.release.assert_awaited()


@pytest.mark.asyncio
async def test_daily_update_delegates_to_ensure():
    from app.services.market_data_ingestion.pipelines import daily_update as du

    with patch.object(
        du,
        "ensure_latest_market_data",
        new=AsyncMock(
            return_value={
                "status": "ALREADY_FRESH",
                "exit_code": 0,
                "data_date": "2026-08-07",
                "rows_fetched": 0,
                "rows_upserted": 0,
            }
        ),
    ) as m:
        result = await du.run_daily_update(trigger_source="CLI")
        assert result["status"] == "SUCCESS"
        m.assert_awaited_once()
