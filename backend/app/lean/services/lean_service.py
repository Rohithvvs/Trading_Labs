"""LeanBacktestService: Manages asynchronous backtest jobs, persistence, and universe execution."""

from __future__ import annotations

import asyncio
from datetime import datetime
import logging
from typing import Any
import uuid

from ...services.universe_csv import load_unique_nifty500_csv_rows
from ...services.universe_service import UniverseService
from ...utils.datetime_utils import utc_now
from ..adapters.data_adapter import LeanDataAdapter
from ..engine.base import BacktestEngine
from ..engine.lean_engine import LeanBacktestEngine
from ..job_store import load_all, load_job, save_job
from ..models import (
    EngineType,
    LeanBacktestRequest,
    LeanBacktestResult,
    LeanJobRecord,
    LeanJobStatus,
)

logger = logging.getLogger("app.lean.service")

# In-memory cache; disk store survives process restart.
_JOBS: dict[str, LeanJobRecord] = {}
_ACTIVE_TASKS: dict[str, asyncio.Task] = {}
_SEMAPHORE = asyncio.Semaphore(4)
_DISK_LOADED = False


def _ensure_disk_loaded() -> None:
    global _DISK_LOADED
    if _DISK_LOADED:
        return
    for job_id, job in load_all().items():
        _JOBS.setdefault(job_id, job)
    _DISK_LOADED = True


class LeanBacktestService:
    """Orchestrates event-engine backtesting jobs with disk persistence and cancellation."""

    @classmethod
    def get_job(cls, job_id: str) -> LeanJobRecord | None:
        _ensure_disk_loaded()
        job = _JOBS.get(job_id)
        if job is not None:
            return job
        loaded = load_job(job_id)
        if loaded is not None:
            _JOBS[job_id] = loaded
        return loaded

    @classmethod
    def list_jobs(cls, limit: int = 50) -> list[LeanJobRecord]:
        _ensure_disk_loaded()
        records = sorted(_JOBS.values(), key=lambda j: j.created_at, reverse=True)
        return records[:limit]

    @classmethod
    def cancel_job(cls, job_id: str) -> bool:
        job = cls.get_job(job_id)
        if not job:
            return False
        if job.status in {LeanJobStatus.QUEUED, LeanJobStatus.RUNNING}:
            job.status = LeanJobStatus.CANCELLED
            job.stage = "Cancelled"
            job.completed_at = utc_now()
            task = _ACTIVE_TASKS.pop(job_id, None)
            if task and not task.done():
                task.cancel()
            save_job(job)
            return True
        return False

    @classmethod
    async def create_and_start_job(
        cls,
        request: LeanBacktestRequest,
        user_id: str | None = None,
    ) -> LeanJobRecord:
        job_id = f"LEAN-{uuid.uuid4().hex[:12].upper()}"
        
        job = LeanJobRecord(
            jobId=job_id,
            strategyId=request.strategy_id,
            strategyName=request.strategy_name,
            userId=user_id,
            createdAt=utc_now(),
            status=LeanJobStatus.QUEUED,
            progressPct=0,
            stage="Queued",
            request=request,
        )
        _JOBS[job_id] = job
        save_job(job)

        # Launch async execution task
        task = asyncio.create_task(cls._execute_job_task(job))
        _ACTIVE_TASKS[job_id] = task
        return job

    @classmethod
    async def _execute_job_task(cls, job: LeanJobRecord) -> None:
        job_id = job.job_id
        try:
            async with _SEMAPHORE:
                job.status = LeanJobStatus.RUNNING
                job.started_at = utc_now()
                job.stage = "Resolving Universe..."
                job.progress_pct = 5

                # 1. Resolve symbols
                symbols = job.request.symbols
                if len(symbols) == 1 and symbols[0] in {"ALL_755", "ALL", "NIFTY500", "ALL_STOCKS"}:
                    try:
                        csv_rows = load_unique_nifty500_csv_rows(UniverseService._csv_path())
                        symbols = [r["symbol"] for r in csv_rows if r.get("symbol")]
                    except Exception as err:
                        logger.warning("Could not read symbols from CSV: %s", err)
                        symbols = []
                    if not symbols:
                        symbols = await UniverseService.get_all_active_symbols()

                job.stage = f"Loading Historical Data for {len(symbols)} stocks..."
                job.progress_pct = 10

                data_map, bench_bars = await LeanDataAdapter.load_historical_data(
                    symbols=symbols,
                    start_date=job.request.start_date,
                    end_date=job.request.end_date,
                    warmup_sessions=260,
                    benchmark=job.request.benchmark,
                )

                if not data_map:
                    raise ValueError(f"No historical price data found for requested symbols ({len(symbols)} symbols)")

                def progress_cb(pct: int, msg: str):
                    job.progress_pct = pct
                    job.stage = msg
                    save_job(job)

                if job.request.execution_mode == EngineType.EXISTING:
                    raise ValueError("The legacy EXISTING engine is disabled. Use the Labs event engine.")
                engine: BacktestEngine = LeanBacktestEngine()

                job.stage = f"Executing {engine.engine_name} Engine Backtest..."
                result: LeanBacktestResult = await engine.run_backtest(
                    request=job.request,
                    data_map=data_map,
                    benchmark_bars=bench_bars,
                    progress_callback=progress_cb,
                )

                job.result = result
                job.status = LeanJobStatus.COMPLETED
                job.stage = "Completed"
                job.progress_pct = 100
                job.completed_at = utc_now()

        except asyncio.CancelledError:
            logger.info("LEAN_JOB_CANCELLED | job_id=%s", job_id)
            job.status = LeanJobStatus.CANCELLED
            job.stage = "Cancelled by user"
            job.completed_at = utc_now()
        except Exception as exc:
            logger.exception("LEAN_JOB_FAILED | job_id=%s | err=%s", job_id, exc)
            job.status = LeanJobStatus.FAILED
            job.stage = "Failed"
            job.error = str(exc)
            job.completed_at = utc_now()
        finally:
            save_job(job)
            _ACTIVE_TASKS.pop(job_id, None)
