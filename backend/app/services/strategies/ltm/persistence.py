"""Namespaced LTM book state and scan-run persistence. Never writes Production scan_results."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from ....db.session import AsyncSessionLocal
from ....models.ltm_strategy import LtmBookState, StrategyScanLatest, StrategyScanRun
from .identity import DEFAULT_CAPITAL, DEFAULT_MODE, STRATEGY_ID


def _utc() -> datetime:
    return datetime.now(timezone.utc)


async def load_book_state(book_id: str = "default") -> LtmBookState:
    async with AsyncSessionLocal() as db:
        row = await db.get(LtmBookState, book_id)
        if row:
            return row
        row = LtmBookState(
            id=book_id,
            strategy_id=STRATEGY_ID,
            mode=DEFAULT_MODE,
            cash=DEFAULT_CAPITAL,
            equity=DEFAULT_CAPITAL,
            initial_capital=DEFAULT_CAPITAL,
            updated_at=_utc(),
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row


async def save_book_state(
    *,
    book_id: str = "default",
    cash: float,
    equity: float,
    session_index: int,
    last_rebalance_index: int | None,
    last_rebalance_date: Any,
    clock_status: str,
    holdings: list[dict[str, Any]],
    mode: str = DEFAULT_MODE,
    survivorship_biased: bool = True,
    initial_capital: float = DEFAULT_CAPITAL,
) -> None:
    async with AsyncSessionLocal() as db:
        row = await db.get(LtmBookState, book_id)
        if row is None:
            row = LtmBookState(id=book_id, strategy_id=STRATEGY_ID)
            db.add(row)
        row.cash = cash
        row.equity = equity
        row.session_index = session_index
        row.last_rebalance_index = last_rebalance_index
        row.last_rebalance_date = last_rebalance_date
        row.clock_status = clock_status
        row.holdings = holdings
        row.mode = mode
        row.survivorship_biased = survivorship_biased
        row.initial_capital = initial_capital
        row.updated_at = _utc()
        await db.commit()


async def create_run(strategy_id: str = STRATEGY_ID) -> StrategyScanRun:
    async with AsyncSessionLocal() as db:
        run = StrategyScanRun(
            scan_id=uuid.uuid4(),
            strategy_id=strategy_id,
            status="queued",
            progress_pct=0,
            stage="queued",
            started_at=_utc(),
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run


async def update_run(
    scan_id: uuid.UUID,
    *,
    status: str | None = None,
    progress_pct: int | None = None,
    stage: str | None = None,
    payload: dict | None = None,
    error_code: str | None = None,
    error_detail: str | None = None,
    finished: bool = False,
    progress_meta: dict | None = None,
) -> StrategyScanRun | None:
    async with AsyncSessionLocal() as db:
        run = await db.get(StrategyScanRun, scan_id)
        if run is None:
            return None
        if status is not None:
            run.status = status
        if progress_pct is not None:
            run.progress_pct = progress_pct
        if stage is not None:
            run.stage = stage
        if payload is not None:
            run.payload = payload
        elif progress_meta and run.status != "completed":
            meta = {}
            if isinstance(run.payload, dict):
                for key in ("current_symbol", "processed_count", "total_count"):
                    if key in run.payload:
                        meta[key] = run.payload[key]
            meta.update(progress_meta)
            run.payload = meta
        if error_code is not None:
            run.error_code = error_code
        if error_detail is not None:
            run.error_detail = error_detail
        if finished:
            run.finished_at = _utc()
        await db.commit()
        await db.refresh(run)
        return run


async def get_run(scan_id: uuid.UUID) -> StrategyScanRun | None:
    async with AsyncSessionLocal() as db:
        return await db.get(StrategyScanRun, scan_id)


async def find_active_run(
    strategy_id: str = STRATEGY_ID,
    *,
    max_age_seconds: int = 3600,
    mark_stale: bool = True,
) -> StrategyScanRun | None:
    async with AsyncSessionLocal() as db:
        stmt = (
            select(StrategyScanRun)
            .where(
                StrategyScanRun.strategy_id == strategy_id,
                StrategyScanRun.status.in_(("queued", "evaluating", "backtesting", "publishing")),
            )
            .order_by(StrategyScanRun.started_at.desc())
            .limit(1)
        )
        run = (await db.execute(stmt)).scalar_one_or_none()
        if run is None:
            return None
        started = run.started_at
        if started is not None:
            age = (_utc() - started.replace(tzinfo=timezone.utc) if started.tzinfo is None else _utc() - started).total_seconds()
            if age > max_age_seconds:
                if not mark_stale:
                    return None
                run.status = "failed"
                run.error_code = "LTM_SCAN_STALE"
                run.error_detail = "Scan left in-progress too long; cleared for retry"
                run.finished_at = _utc()
                await db.commit()
                return None
        return run


async def save_latest(
    strategy_id: str,
    *,
    scan_id: uuid.UUID | None,
    status: str,
    payload: dict | None,
    error_code: str | None = None,
) -> None:
    async with AsyncSessionLocal() as db:
        row = await db.get(StrategyScanLatest, strategy_id)
        if row is None:
            row = StrategyScanLatest(strategy_id=strategy_id)
            db.add(row)
        row.scan_id = scan_id
        row.status = status
        row.error_code = error_code
        now = _utc()
        if status in {"queued", "evaluating"} and (row.started_at is None or status == "queued"):
            row.started_at = now
        if status == "completed":
            row.payload = payload
            row.completed_at = now
            row.computed_at = now
        elif status in {"failed", "blocked_stale"}:
            row.computed_at = now
            # Keep last successful payload so completed_at / results stay truthful.
            if row.completed_at is None:
                row.payload = payload
        else:
            # In-flight: do not clobber last successful results or completed_at.
            if row.completed_at is None:
                row.payload = payload
        await db.commit()


async def load_latest(strategy_id: str = STRATEGY_ID) -> StrategyScanLatest | None:
    async with AsyncSessionLocal() as db:
        return await db.get(StrategyScanLatest, strategy_id)
