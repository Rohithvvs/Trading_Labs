"""FastAPI HTTP Routes for QuantConnect LEAN Backtesting Engine."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from ...core.deps import require_feature
from ...models.auth import User
from ..models import (
    EngineType,
    LeanBacktestRequest,
    LeanBacktestResult,
    LeanJobRecord,
    LeanJobStatus,
    LeanValidationReport,
)
from ..services.lean_service import LeanBacktestService
from ..services.validation_service import LeanTradingViewValidationService

router = APIRouter(
    prefix="/backtests",
    tags=["lean-backtesting"],
    dependencies=[Depends(require_feature("advanced_scanner"))],
)


@router.get("/engines")
async def get_available_engines():
    """List available backtesting engines and their capabilities."""
    return {
        "engines": [
            {
                "id": "LEAN",
                "name": "Labs event engine",
                "description": "Event-driven daily-bar portfolio backtest with NSE delivery costs and next-bar-open fills. In-process engine (not the QuantConnect LEAN binary).",
                "is_default": True,
                "supports_portfolio": True,
                "supports_tradingview_validation": True,
            },
        ],
        "default_engine": "LEAN",
    }


@router.post("", response_model=LeanJobRecord)
async def create_backtest_job(request: LeanBacktestRequest, user: User = Depends(require_feature("advanced_scanner"))):
    """Start an asynchronous backtesting job."""
    if request.execution_mode == EngineType.EXISTING:
        raise HTTPException(
            status_code=400,
            detail={"message": "The legacy EXISTING engine is disabled. Use the Labs event engine."},
        )
    try:
        job = await LeanBacktestService.create_and_start_job(request, user_id=str(user.id))
        return job
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc


@router.get("", response_model=list[LeanJobRecord])
async def list_backtest_jobs(limit: int = Query(default=20, ge=1, le=100)):
    """List recent backtesting runs."""
    return LeanBacktestService.list_jobs(limit=limit)


@router.get("/{job_id}", response_model=LeanJobRecord)
async def get_backtest_job_status(job_id: str):
    """Get the current execution status and progress of a backtest job."""
    job = LeanBacktestService.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail={"message": f"Backtest job {job_id} not found"})
    return job


@router.get("/{job_id}/results", response_model=LeanBacktestResult)
async def get_backtest_results(job_id: str):
    """Retrieve normalized backtest results for a completed job."""
    job = LeanBacktestService.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail={"message": f"Backtest job {job_id} not found"})
    if job.status == LeanJobStatus.FAILED:
        raise HTTPException(status_code=400, detail={"message": f"Job failed: {job.error}"})
    if job.status != LeanJobStatus.COMPLETED or not job.result:
        raise HTTPException(
            status_code=409,
            detail={"message": f"Job is not yet completed. Current status: {job.status}", "stage": job.stage},
        )
    return job.result


@router.post("/{job_id}/cancel")
async def cancel_backtest_job(job_id: str):
    """Cancel a queued or running backtest job."""
    success = LeanBacktestService.cancel_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail={"message": f"Backtest job {job_id} not found or already completed"})
    return {"job_id": job_id, "status": "CANCELLED"}


@router.post("/validate-tv", response_model=LeanValidationReport)
async def validate_against_tradingview(
    symbol: str = Query(default="WELCORP"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    strategy_id: str = Query(default="09_52w_breakout"),
):
    """Run bar-level validation comparing LEAN vs a stored TradingView tape."""
    try:
        report = await LeanTradingViewValidationService.validate_symbol(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            strategy_id=strategy_id,
        )
        return report
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc
