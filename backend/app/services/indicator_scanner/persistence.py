"""Indicator definition and scan-run repository."""

from __future__ import annotations

import math
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select

from ...db.session import AsyncSessionLocal
from ...models.indicator_scanner import IndicatorDefinition, IndicatorScanResult, IndicatorScanRun

ACTIVE_STATUSES = ("queued", "running")


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def json_safe(value: Any) -> Any:
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")) or not math.isfinite(value):
            return None
        return value
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def definition_payload(row: IndicatorDefinition) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "name": row.name,
        "description": row.description or "",
        "source_code": row.source_code,
        "script_version": row.script_version,
        "language_mode": row.language_mode,
        "timeframe": row.timeframe,
        "parsed_definition": row.parsed_definition,
        "validation_status": row.validation_status,
        "validation_errors": row.validation_errors or [],
        "required_bars": row.required_bars,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        "is_archived": row.is_archived,
    }


async def create_definition(
    *,
    user_id: uuid.UUID | None,
    name: str,
    description: str,
    source_code: str,
    script_version: int,
    language_mode: str,
    timeframe: str,
    parsed_definition: dict[str, Any],
    validation_status: str,
    validation_errors: list[dict[str, Any]],
    required_bars: int,
) -> IndicatorDefinition:
    async with AsyncSessionLocal() as db:
        row = IndicatorDefinition(
            id=uuid.uuid4(),
            user_id=user_id,
            name=name[:120],
            description=(description or "")[:500],
            source_code=source_code,
            script_version=script_version,
            language_mode=language_mode,
            timeframe=timeframe,
            parsed_definition=json_safe(parsed_definition),
            validation_status=validation_status,
            validation_errors=json_safe(validation_errors),
            required_bars=required_bars,
            created_at=_utc(),
            updated_at=_utc(),
            is_archived=False,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row


async def update_definition(
    definition_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    patch: dict[str, Any],
) -> IndicatorDefinition | None:
    async with AsyncSessionLocal() as db:
        row = await db.get(IndicatorDefinition, definition_id)
        if row is None or row.user_id != user_id or row.is_archived:
            return None
        if "name" in patch and patch["name"]:
            row.name = str(patch["name"]).strip()[:120]
        if "description" in patch:
            row.description = str(patch["description"] or "")[:500]
        if "source_code" in patch:
            row.source_code = str(patch["source_code"])
        if "script_version" in patch:
            row.script_version = int(patch["script_version"])
        if "language_mode" in patch:
            row.language_mode = str(patch["language_mode"])
        if "timeframe" in patch:
            row.timeframe = str(patch["timeframe"])
        if "parsed_definition" in patch:
            row.parsed_definition = json_safe(patch["parsed_definition"])
        if "validation_status" in patch:
            row.validation_status = str(patch["validation_status"])
        if "validation_errors" in patch:
            row.validation_errors = json_safe(patch["validation_errors"])
        if "required_bars" in patch:
            row.required_bars = int(patch["required_bars"])
        row.updated_at = _utc()
        await db.commit()
        await db.refresh(row)
        return row


async def get_definition(definition_id: uuid.UUID) -> IndicatorDefinition | None:
    async with AsyncSessionLocal() as db:
        return await db.get(IndicatorDefinition, definition_id)


async def find_definition_by_name(user_id: uuid.UUID, name: str) -> IndicatorDefinition | None:
    needle = (name or "").strip().lower()
    if not needle:
        return None
    async with AsyncSessionLocal() as db:
        stmt = (
            select(IndicatorDefinition)
            .where(IndicatorDefinition.user_id == user_id)
            .where(IndicatorDefinition.is_archived.is_(False))
            .where(func.lower(IndicatorDefinition.name) == needle)
            .order_by(IndicatorDefinition.updated_at.desc())
            .limit(1)
        )
        return (await db.execute(stmt)).scalars().first()


async def list_definitions(user_id: uuid.UUID, *, include_archived: bool = False) -> list[IndicatorDefinition]:
    async with AsyncSessionLocal() as db:
        stmt = select(IndicatorDefinition).where(IndicatorDefinition.user_id == user_id)
        if not include_archived:
            stmt = stmt.where(IndicatorDefinition.is_archived.is_(False))
        stmt = stmt.order_by(IndicatorDefinition.updated_at.desc())
        return list((await db.execute(stmt)).scalars().all())


async def archive_definition(definition_id: uuid.UUID, *, user_id: uuid.UUID) -> IndicatorDefinition | None:
    async with AsyncSessionLocal() as db:
        row = await db.get(IndicatorDefinition, definition_id)
        if row is None or row.user_id != user_id:
            return None
        row.is_archived = True
        row.updated_at = _utc()
        await db.commit()
        await db.refresh(row)
        return row


async def touch_last_used(definition_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        row = await db.get(IndicatorDefinition, definition_id)
        if row is None:
            return
        row.last_used_at = _utc()
        await db.commit()


async def next_public_scan_id(day: date | None = None) -> str:
    stamp = (day or datetime.now(timezone(timedelta(hours=5, minutes=30))).date()).strftime("%Y%m%d")
    prefix = f"IND-{stamp}-"
    async with AsyncSessionLocal() as db:
        count = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(IndicatorScanRun)
                    .where(IndicatorScanRun.public_scan_id.like(f"{prefix}%"))
                )
            ).scalar()
            or 0
        )
    return f"{prefix}{count + 1:03d}"


async def find_active_scan(user_id: uuid.UUID | None) -> IndicatorScanRun | None:
    async with AsyncSessionLocal() as db:
        stmt = (
            select(IndicatorScanRun)
            .where(IndicatorScanRun.status.in_(ACTIVE_STATUSES))
            .order_by(IndicatorScanRun.started_at.desc())
        )
        if user_id is not None:
            stmt = stmt.where(IndicatorScanRun.user_id == user_id)
        return (await db.execute(stmt.limit(1))).scalars().first()


async def create_scan(
    *,
    user_id: uuid.UUID | None,
    public_scan_id: str,
    indicator_id: uuid.UUID | None,
    indicator_name: str,
    indicator_snapshot: dict[str, Any],
    universe: str,
    universe_size: int,
    timeframe: str,
    filters: list[dict[str, Any]],
    sort: dict[str, Any] | None,
    input_overrides: dict[str, Any] | None,
    scan_date: str | None,
    benchmark_symbol: str | None,
) -> IndicatorScanRun:
    async with AsyncSessionLocal() as db:
        row = IndicatorScanRun(
            id=uuid.uuid4(),
            public_scan_id=public_scan_id,
            user_id=user_id,
            indicator_id=indicator_id,
            indicator_name=indicator_name,
            indicator_snapshot=json_safe(indicator_snapshot),
            universe=universe,
            universe_size=universe_size,
            timeframe=timeframe,
            filters=json_safe(filters),
            sort=json_safe(sort),
            input_overrides=json_safe(input_overrides),
            scan_date=scan_date,
            status="queued",
            stage="queued",
            benchmark_symbol=benchmark_symbol,
            started_at=_utc(),
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row


async def get_scan(scan_id: uuid.UUID) -> IndicatorScanRun | None:
    async with AsyncSessionLocal() as db:
        return await db.get(IndicatorScanRun, scan_id)


async def get_scan_by_public_id(public_id: str) -> IndicatorScanRun | None:
    async with AsyncSessionLocal() as db:
        stmt = select(IndicatorScanRun).where(IndicatorScanRun.public_scan_id == public_id)
        return (await db.execute(stmt)).scalars().first()


async def update_scan(run_id: uuid.UUID, **fields: Any) -> IndicatorScanRun | None:
    async with AsyncSessionLocal() as db:
        row = await db.get(IndicatorScanRun, run_id)
        if row is None:
            return None
        for key, value in fields.items():
            if key == "summary" or key == "filters" or key == "sort":
                value = json_safe(value)
            setattr(row, key, value)
        await db.commit()
        await db.refresh(row)
        return row


async def save_results(run_id: uuid.UUID, rows: list[dict[str, Any]]) -> None:
    async with AsyncSessionLocal() as db:
        for item in rows:
            db.add(
                IndicatorScanResult(
                    id=uuid.uuid4(),
                    run_id=run_id,
                    symbol=str(item["symbol"]),
                    display_name=item.get("display_name") or item.get("company"),
                    exchange=item.get("exchange") or "NSE",
                    timeframe=item.get("timeframe") or "1D",
                    as_of=item.get("as_of"),
                    status=item.get("status") or "ok",
                    matched=bool(item.get("matched")),
                    outputs=json_safe(item.get("outputs") or {}),
                    ohlcv=json_safe(item.get("ohlcv") or {}),
                    error_detail=item.get("error_detail"),
                    bar_count=item.get("bar_count"),
                )
            )
        await db.commit()


async def list_results(run_id: uuid.UUID) -> list[IndicatorScanResult]:
    async with AsyncSessionLocal() as db:
        stmt = select(IndicatorScanResult).where(IndicatorScanResult.run_id == run_id)
        return list((await db.execute(stmt)).scalars().all())


async def get_result(run_id: uuid.UUID, symbol: str) -> IndicatorScanResult | None:
    from ...utils.symbol import canonical_symbol

    raw = (symbol or "").strip().upper()
    canon = canonical_symbol(raw) or raw
    candidates = [c for c in dict.fromkeys([canon, raw, f"{canon}-EQ", f"{raw}-EQ"]) if c]
    async with AsyncSessionLocal() as db:
        stmt = select(IndicatorScanResult).where(
            IndicatorScanResult.run_id == run_id,
            IndicatorScanResult.symbol.in_(candidates),
        )
        return (await db.execute(stmt)).scalars().first()


async def reap_orphaned_scans() -> int:
    """Mark any running/queued indicator scans as failed on server startup."""
    async with AsyncSessionLocal() as db:
        now = _utc()
        stmt = (
            select(IndicatorScanRun)
            .where(IndicatorScanRun.status.in_(("queued", "running", "preparing")))
        )
        runs = (await db.execute(stmt)).scalars().all()
        for r in runs:
            r.status = "failed"
            r.stage = "failed"
            r.error_code = "SCAN_INTERRUPTED"
            r.error_detail = "Server restarted while scan was in progress. Please click Scan to restart."
            r.completed_at = now
        if runs:
            await db.commit()
        return len(runs)
