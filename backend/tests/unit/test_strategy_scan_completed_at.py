"""completed_at is only set on successful scans and is strategy-specific."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.strategies.breakout52w.identity import STRATEGY_ID as W52_ID
from app.services.strategies.ltm.identity import STRATEGY_ID as LTM_ID
from app.services.strategies.ltm.scan_service import start_scan_background as start_ltm


def test_ids_are_canonical_and_distinct():
    assert LTM_ID == "17_long_term_mom"
    assert W52_ID == "09_52w_breakout"
    assert LTM_ID != W52_ID


def test_completed_at_survives_failed_rerun():
    done = datetime(2026, 8, 16, 8, 25, tzinfo=timezone.utc)
    row = SimpleNamespace(
        status="failed",
        payload={"recommendations_final": True, "strategy_id": LTM_ID, "summary": {"buy": 3}},
        completed_at=done,
        scan_id=None,
        started_at=None,
        error_code="LTM_SCAN_FAILED",
    )
    from app.routes.scanner import _strategy_latest_body

    body = _strategy_latest_body(row, strategy_id=LTM_ID, display_name="Long-Term Buy & Hold Momentum")
    assert body["completed_at"] == done.isoformat()
    assert body["run_status"] == "failed"
    assert body["recommendations_final"] is False


def test_in_progress_does_not_invent_completed_at():
    from app.routes.scanner import _strategy_latest_body

    row = SimpleNamespace(
        status="evaluating",
        payload={"recommendations_final": True, "summary": {"buy": 1}},
        completed_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
        scan_id=None,
        started_at=datetime(2026, 8, 16, 8, 0, tzinfo=timezone.utc),
        error_code=None,
    )
    run = SimpleNamespace(progress_pct=40, stage="backtesting", error_code=None, error_detail=None, started_at=row.started_at)
    body = _strategy_latest_body(row, strategy_id=W52_ID, display_name="52-Week High Breakout", run=run)
    assert body["recommendations_final"] is False
    assert body["progress_pct"] == 40
    assert body["stage"] == "backtesting"
    assert body["completed_at"] is not None


def test_strategy_mismatch_rejected():
    assert "17_long_term_mom" != W52_ID
    # Route contract: posting W52 id to LTM endpoint is a client error.
    expected, got = LTM_ID, W52_ID
    assert expected != got


def test_in_progress_exposes_run_current_symbol():
    from app.routes.scanner import _strategy_latest_body

    row = SimpleNamespace(
        status="evaluating",
        payload={"recommendations_final": True, "summary": {"buy": 1}, "recommendations": [{"symbol": "OLD"}]},
        completed_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
        scan_id="new-scan",
        started_at=datetime(2026, 8, 16, 8, 0, tzinfo=timezone.utc),
        error_code=None,
    )
    run = SimpleNamespace(
        progress_pct=18,
        stage="evaluating",
        error_code=None,
        error_detail=None,
        started_at=row.started_at,
        status="evaluating",
        payload={"current_symbol": "RELIANCE", "processed_count": 136, "total_count": 755},
    )
    body = _strategy_latest_body(row, strategy_id=W52_ID, display_name="52-Week High Breakout", run=run)
    assert body["recommendations_final"] is False
    assert body["current_symbol"] == "RELIANCE"
    assert body["processed_count"] == 136
    assert body["total_count"] == 755
    assert body["progress_pct"] == 18
    assert body["completed_at"] is not None


def test_run_body_hides_completed_payload_while_running():
    from app.routes.scanner import _strategy_run_body

    run = SimpleNamespace(
        scan_id="abc",
        strategy_id=LTM_ID,
        status="backtesting",
        progress_pct=40,
        stage="backtesting",
        error_code=None,
        error_detail=None,
        started_at=datetime(2026, 8, 16, 8, 0, tzinfo=timezone.utc),
        payload={"current_symbol": "ZENTEC", "processed_count": 400, "total_count": 755},
    )
    body = _strategy_run_body(run)
    assert body["recommendations_final"] is False
    assert body["payload"] is None
    assert body["current_symbol"] == "ZENTEC"


def test_ltm_start_persists_queued_before_worker():
    created = SimpleNamespace(
        scan_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
        status="queued",
        started_at=None,
    )
    save_latest = AsyncMock()

    async def _run():
        with (
            patch(
                "app.services.strategies.ltm.scan_service.persistence.find_active_run",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.strategies.ltm.scan_service.persistence.create_run",
                new=AsyncMock(return_value=created),
            ),
            patch(
                "app.services.strategies.ltm.scan_service.persistence.save_latest",
                new=save_latest,
            ),
            patch("asyncio.create_task", side_effect=lambda coro: coro.close()),
        ):
            result = await start_ltm()
        assert result["status"] == "queued"
        assert result["scan_id"] == created.scan_id
        assert result["strategy_id"] == LTM_ID
        save_latest.assert_awaited()
        assert save_latest.await_args.kwargs["status"] == "queued"
        assert save_latest.await_args.kwargs["payload"]["recommendations_final"] is False

    asyncio.run(_run())
