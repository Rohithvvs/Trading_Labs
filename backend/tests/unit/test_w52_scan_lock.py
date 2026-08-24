import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.strategies.breakout52w.identity import STRATEGY_ID
from app.services.strategies.breakout52w.scan_service import start_scan_background


def test_start_persists_queued_before_worker():
    created = SimpleNamespace(
        scan_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        status="queued",
        started_at=None,
    )
    save_latest = AsyncMock()

    async def _run():
        with (
            patch(
                "app.services.strategies.breakout52w.scan_service.persistence.find_active_run",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.strategies.breakout52w.scan_service.persistence.create_run",
                new=AsyncMock(return_value=created),
            ),
            patch(
                "app.services.strategies.breakout52w.scan_service.persistence.save_latest",
                new=save_latest,
            ),
            patch("asyncio.create_task", side_effect=lambda coro: coro.close()),
        ):
            result = await start_scan_background()
        assert result["status"] == "queued"
        assert result["scan_id"] == created.scan_id
        assert result["strategy_id"] == STRATEGY_ID
        save_latest.assert_awaited()
        kwargs = save_latest.await_args.kwargs
        assert kwargs["status"] == "queued"
        assert kwargs["payload"]["recommendations_final"] is False
        assert kwargs["payload"]["scan_id"] == created.scan_id

    asyncio.run(_run())


def test_second_start_returns_in_progress():
    active = SimpleNamespace(scan_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", status="evaluating")

    async def _run():
        with patch(
            "app.services.strategies.breakout52w.scan_service.persistence.find_active_run",
            new=AsyncMock(return_value=active),
        ):
            result = await start_scan_background()
        assert result["error_code"] == "W52_SCAN_IN_PROGRESS"
        assert result["scan_id"] == str(active.scan_id)
        assert result["status"] == "evaluating"
        assert result["strategy_id"] == STRATEGY_ID

    asyncio.run(_run())
