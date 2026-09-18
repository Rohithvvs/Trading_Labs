"""Daily update pipeline tests — delegates to ensure_latest_market_data."""
from unittest.mock import AsyncMock, patch

import pytest

from app.services.market_data_ingestion.pipelines import daily_update as du


@pytest.mark.asyncio
async def test_daily_update_skipped_locked():
    with patch.object(
        du,
        "ensure_latest_market_data",
        new=AsyncMock(return_value={"status": "SKIPPED_LOCKED", "exit_code": 3}),
    ):
        result = await du.run_daily_update(trigger_source="CLI")
        assert result["status"] == "SKIPPED_LOCKED"
        assert result["exit_code"] == 3


@pytest.mark.asyncio
async def test_daily_update_maps_already_fresh_to_success():
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
                "rows_failed": 0,
            }
        ),
    ):
        result = await du.run_daily_update(trigger_source="CLI")
        assert result["status"] == "SUCCESS"
        assert result["exit_code"] == 0


def test_zero_traded_delivery_null():
    from app.services.market_data_ingestion.derived import compute_delivery_pct

    assert compute_delivery_pct(5, 0) is None
