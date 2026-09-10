"""FastAPI HTTP Routes for QuantConnect LEAN Backtesting Engine."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

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

router = APIRouter(prefix="/backtests", tags=["lean-backtesting"])


@router.get("/engines")
async def get_available_engines():
    """List available backtesting engines and their capabilities."""
    return {
        "engines": [
            {
                "id": "LEAN",
                "name": "QuantConnect LEAN Engine",
                "description": "Professional event-driven backtesting engine with strict daily bar alignment and multi-asset portfolio accounting",
                "is_default": True,
                "supports_portfolio": True,
                "supports_tradingview_validation": True,
            },
            {
                "id": "EXISTING",
                "name": "Trading Labs Standard Engine",
                "description": "Legacy single-asset backtesting engine with realistic statutory cost profiles",
                "is_default": False,
                "supports_portfolio": False,
                "supports_tradingview_validation": False,
            },
        ],
        "default_engine": "LEAN",
    }


@router.post("", response_model=LeanJobRecord)
async def create_backtest_job(request: LeanBacktestRequest):
    """Start an asynchronous backtesting job."""
    try:
        job = await LeanBacktestService.create_and_start_job(request)
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
    symbol: str = Query(default="RELIANCE"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    strategy_id: str = Query(default="09_52w_breakout"),
):
    """Run bar-level validation comparing LEAN vs TradingView."""
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
