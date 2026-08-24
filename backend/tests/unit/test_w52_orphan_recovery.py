import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.strategies.breakout52w import persistence, scan_service
from app.services.strategies.breakout52w.identity import STRATEGY_ID
from app.routes.scanner import _progress_fields_from_run, _strategy_run_body


def test_progress_fields_from_run_cleans_nulls():
    # When payload has no symbol (e.g. portfolio_backtest phase)
    run = SimpleNamespace(
        status="backtesting",
        payload={"phase": "portfolio_backtest"},
    )
    fields = _progress_fields_from_run(run)
    assert fields["current_symbol"] == ""
    assert fields["processed_count"] is None
    assert fields["total_count"] is None
    assert fields["phase"] == "portfolio_backtest"

    # When payload has stock processing info
    run_eval = SimpleNamespace(
        status="evaluating",
        payload={
            "phase": "stock_processing",
            "current_symbol": "RELIANCE-EQ",
            "processed_count": 100,
            "total_count": 755,
        },
    )
    fields_eval = _progress_fields_from_run(run_eval)
    assert fields_eval["current_symbol"] == "RELIANCE-EQ"
    assert fields_eval["processed_count"] == 100
    assert fields_eval["total_count"] == 755
    assert fields_eval["phase"] == "stock_processing"


def test_in_memory_scan_task_tracking():
    # Initially not active
    scan_service._active_scan_task = None
    scan_service._active_scan_id = None
    assert not scan_service.is_scan_active_in_memory()
    assert not scan_service.cancel_active_scan()

    async def _test():
        async def _dummy():
            await asyncio.sleep(10)

        task = asyncio.create_task(_dummy())
        test_id = uuid.uuid4()
        scan_service._active_scan_task = task
        scan_service._active_scan_id = test_id

        assert scan_service.is_scan_active_in_memory()
        assert scan_service.is_scan_active_in_memory(test_id)
        assert not scan_service.is_scan_active_in_memory(uuid.uuid4())

        assert scan_service.cancel_active_scan()
        assert task.cancelling() or task.cancelled()
        try:
            await task
        except asyncio.CancelledError:
            pass

    try:
        asyncio.run(_test())
    finally:
        scan_service._active_scan_task = None
        scan_service._active_scan_id = None



def test_update_run_progress_meta_clears_keys():
    # Simulate DB object
    run = SimpleNamespace(
        scan_id=uuid.uuid4(),
        status="evaluating",
        progress_pct=38,
        stage="evaluating",
        payload={
            "phase": "stock_processing",
            "current_symbol": "ZYDUSWELL-EQ",
            "processed_count": 755,
            "total_count": 755,
        },
        error_code=None,
        error_detail=None,
        finished_at=None,
    )

    mock_db = MagicMock()
    mock_db.get = AsyncMock(return_value=run)
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    class FakeSessionContext:
        async def __aenter__(self):
            return mock_db
        async def __aexit__(self, *args):
            pass

    async def _run():
        with patch("app.services.strategies.breakout52w.persistence.AsyncSessionLocal", return_value=FakeSessionContext()):
            # Transition to portfolio backtest
            updated = await persistence.update_run(
                run.scan_id,
                status="backtesting",
                stage="backtesting",
                progress_pct=40,
                progress_meta={
                    "phase": "portfolio_backtest",
                    "current_symbol": None,
                    "processed_count": None,
                    "total_count": None,
                },
            )
            assert updated.status == "backtesting"
            assert updated.stage == "backtesting"
            assert updated.progress_pct == 40
            assert updated.payload == {"phase": "portfolio_backtest"}
            assert "current_symbol" not in updated.payload
            assert "processed_count" not in updated.payload
            assert "total_count" not in updated.payload

    asyncio.run(_run())
