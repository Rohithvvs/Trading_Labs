"""data_load_log lifecycle helpers."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select

from ...db.session import AsyncSessionLocal
from ...models.strategy_market_data import DataLoadLog


def _utc_now() -> datetime:
    """Naive UTC wall clock (matches DateTime(timezone=True) stored/returned consistently after normalize)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _as_utc_naive(dt: datetime | None) -> datetime | None:
    """Normalize DB-returned aware datetimes so duration math never mixes tz-aware and naive."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


async def start_load(
    load_type: str,
    trigger_source: str,
    *,
    data_date: date | None = None,
    range_from: date | None = None,
    range_to: date | None = None,
    provider: str | None = None,
) -> uuid.UUID:
    run_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        row = DataLoadLog(
            id=run_id,
            load_type=load_type,
            trigger_source=trigger_source,
            status="RUNNING",
            data_date=data_date,
            range_from=range_from,
            range_to=range_to,
            started_at=_utc_now(),
            provider=provider,
            rows_fetched=0,
            rows_inserted=0,
            rows_updated=0,
            rows_failed=0,
            rows_skipped=0,
        )
        db.add(row)
        await db.commit()
    return run_id


async def finish_load(
    run_id: uuid.UUID,
    status: str,
    *,
    rows_fetched: int = 0,
    rows_inserted: int = 0,
    rows_updated: int = 0,
    rows_failed: int = 0,
    rows_skipped: int = 0,
    error_summary: str | None = None,
    details_json: dict[str, Any] | None = None,
) -> None:
    ended = _utc_now()
    async with AsyncSessionLocal() as db:
        row = await db.get(DataLoadLog, run_id)
        if not row:
            return
        started = _as_utc_naive(row.started_at) or ended
        row.status = status
        row.ended_at = ended
        row.duration_ms = max(0, int((ended - started).total_seconds() * 1000))
        row.rows_fetched = rows_fetched
        row.rows_inserted = rows_inserted
        row.rows_updated = rows_updated
        row.rows_failed = rows_failed
        row.rows_skipped = rows_skipped
        row.error_summary = error_summary
        row.details_json = details_json
        await db.commit()


async def record_skipped_locked(load_type: str, trigger_source: str) -> uuid.UUID:
    run_id = uuid.uuid4()
    now = _utc_now()
    async with AsyncSessionLocal() as db:
        row = DataLoadLog(
            id=run_id,
            load_type=load_type,
            trigger_source=trigger_source,
            status="SKIPPED_LOCKED",
            started_at=now,
            ended_at=now,
            duration_ms=0,
            error_summary="another FULL or DAILY market-data load is already running",
        )
        db.add(row)
        await db.commit()
    return run_id


async def latest_loads(limit: int = 10) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.scalars(
                select(DataLoadLog).order_by(DataLoadLog.started_at.desc()).limit(limit)
            )
        ).all()
        return [
            {
                "id": str(r.id),
                "load_type": r.load_type,
                "trigger_source": r.trigger_source,
                "status": r.status,
                "data_date": r.data_date.isoformat() if r.data_date else None,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "ended_at": r.ended_at.isoformat() if r.ended_at else None,
                "duration_ms": r.duration_ms,
                "rows_fetched": r.rows_fetched,
                "rows_inserted": r.rows_inserted,
                "rows_updated": r.rows_updated,
                "rows_failed": r.rows_failed,
                "rows_skipped": r.rows_skipped,
                "error_summary": r.error_summary,
            }
            for r in rows
        ]
