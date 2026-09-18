"""Scanner blocks when gate enabled and stale."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.scan_execution_service import ScanExecutionService, LockAcquisitionError


@pytest.mark.asyncio
async def test_execute_scan_blocks_on_stale(monkeypatch):
    lock = MagicMock()
    lock.acquire = AsyncMock(return_value=True)
    lock.release = AsyncMock()
    lock.start_heartbeat = MagicMock()
    lock.worker_id = "t"

    class FakeFresh:
        ok = False

        def to_dict(self):
            return {
                "code": "MARKET_DATA_STALE",
                "reason": "equity_incomplete",
                "message": "stale",
                "expected_trade_date": "2026-08-05",
                "equity_coverage_ratio": 0.5,
                "index_present": True,
                "remediation": "run daily-update",
                "missing_symbols_sample": [],
                "missing_symbol_count": 10,
                "latest_equity_trade_date": None,
                "latest_index_trade_date": None,
                "gate_enabled": True,
                "ok": False,
            }

    with (
        patch("app.services.scan_execution_service.DistributedLockService", return_value=lock),
        patch(
            "app.services.market_data_ingestion.ensure.ensure_latest_market_data",
            new=AsyncMock(
                return_value={
                    "status": "SUCCESS",
                    "data_date": "2026-08-05",
                    "fetched": {},
                    "duration_ms": 10,
                }
            ),
        ),
        patch(
            "app.services.market_data_ingestion.freshness.evaluate_freshness",
            new=AsyncMock(return_value=FakeFresh()),
        ),
    ):
        import os

        os.environ["STRATEGY_MARKET_DATA_GATE_ENABLED"] = "true"
        from app.schemas import ScreenerRequest, AnalysisMode

        with pytest.raises(RuntimeError, match="MARKET_DATA_STALE"):
            await ScanExecutionService.execute_scan(
                ScreenerRequest(mode=AnalysisMode.swing),
                progress_queue=None,
                trigger_source="test",
            )
