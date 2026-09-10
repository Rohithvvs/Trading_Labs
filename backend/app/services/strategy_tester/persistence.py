"""Strategy Tester repository. Snapshots strategy config onto each run."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import case, func, select

from ...db.session import AsyncSessionLocal
from ...models.strategy_tester import (
    StrategyDefinition,
    StrategyFilterResult,
    StrategyTestResult,
    StrategyTestRun,
)

ACTIVE_STATUSES = ("queued", "running")


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _json_safe(value: Any) -> Any:
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return value
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    return value


async def next_public_run_id(day: date | None = None) -> str:
    stamp = (day or _utc().date()).strftime("%Y%m%d")
    prefix = f"STR-{stamp}-"
    async with AsyncSessionLocal() as db:
        count = int(
            (
                await db.execute(
                    select(func.count()).select_from(StrategyTestRun).where(StrategyTestRun.public_run_id.like(f"{prefix}%"))
                )
            ).scalar()
            or 0
        )
    return f"{prefix}{count + 1:03d}"


async def create_definition(
    *,
    user_id: uuid.UUID | None,
    name: str,
    description: str,
    config: dict[str, Any],
    is_preset: bool = False,
    preset_id: str | None = None,
) -> StrategyDefinition:
    async with AsyncSessionLocal() as db:
        row = StrategyDefinition(
            id=uuid.uuid4(),
            user_id=user_id,
            name=name,
            description=description,
            version=1,
            is_preset=is_preset,
            preset_id=preset_id,
            config=_json_safe(config),
            created_at=_utc(),
            updated_at=_utc(),
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row


async def update_definition(definition_id: uuid.UUID, *, user_id: uuid.UUID, patch: dict[str, Any]) -> StrategyDefinition | None:
    async with AsyncSessionLocal() as db:
        row = await db.get(StrategyDefinition, definition_id)
        if row is None or row.user_id != user_id:
            return None
        if "name" in patch and patch["name"]:
            row.name = str(patch["name"]).strip()
        if "description" in patch:
            row.description = str(patch["description"] or "")
        if "config" in patch and isinstance(patch["config"], dict):
            row.config = _json_safe(patch["config"])
            row.version = int(row.version or 1) + 1
        row.updated_at = _utc()
        await db.commit()
        await db.refresh(row)
        return row


async def get_definition(definition_id: uuid.UUID) -> StrategyDefinition | None:
    async with AsyncSessionLocal() as db:
        return await db.get(StrategyDefinition, definition_id)


async def find_definition_by_name(user_id: uuid.UUID, name: str) -> StrategyDefinition | None:
    needle = (name or "").strip().lower()
    if not needle:
        return None
    async with AsyncSessionLocal() as db:
        stmt = (
            select(StrategyDefinition)
            .where(StrategyDefinition.user_id == user_id)
            .where(StrategyDefinition.is_preset.is_(False))
            .where(func.lower(StrategyDefinition.name) == needle)
            .order_by(StrategyDefinition.updated_at.desc())
            .limit(1)
        )
        return (await db.execute(stmt)).scalars().first()


async def list_definitions(user_id: uuid.UUID | None) -> list[StrategyDefinition]:
    async with AsyncSessionLocal() as db:
        stmt = select(StrategyDefinition).order_by(StrategyDefinition.updated_at.desc())
        if user_id is not None:
            stmt = stmt.where(
                (StrategyDefinition.user_id == user_id) | (StrategyDefinition.is_preset.is_(True))
            )
        return list((await db.scalars(stmt)).all())


async def find_active_run(user_id: uuid.UUID | None = None) -> StrategyTestRun | None:
    async with AsyncSessionLocal() as db:
        stmt = (
            select(StrategyTestRun)
            .where(StrategyTestRun.status.in_(ACTIVE_STATUSES))
            .order_by(StrategyTestRun.started_at.desc())
        )
        if user_id is not None:
            stmt = stmt.where(StrategyTestRun.user_id == user_id)
        return (await db.scalars(stmt.limit(1))).first()


async def create_run(
    *,
    user_id: uuid.UUID | None,
    public_run_id: str,
    strategy_definition_id: uuid.UUID | None,
    strategy_name: str,
    strategy_version: int,
    strategy_snapshot: dict[str, Any],
    universe: str,
    universe_size: int,
    timeframe: str,
    start_date: date,
    end_date: date,
    initial_capital: float,
    calculation_version: str,
) -> StrategyTestRun:
    async with AsyncSessionLocal() as db:
        run = StrategyTestRun(
            id=uuid.uuid4(),
            public_run_id=public_run_id,
            user_id=user_id,
            strategy_definition_id=strategy_definition_id,
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            strategy_snapshot=_json_safe(strategy_snapshot),
            universe=universe,
            universe_size=universe_size,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            calculation_version=calculation_version,
            status="queued",
            stage="queued",
            progress_pct=0,
            total_count=universe_size,
            started_at=_utc(),
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run


async def get_run(run_id: uuid.UUID | str) -> StrategyTestRun | None:
    async with AsyncSessionLocal() as db:
        if isinstance(run_id, str) and not _looks_uuid(run_id):
            stmt = select(StrategyTestRun).where(StrategyTestRun.public_run_id == run_id)
            return (await db.scalars(stmt)).first()
        key = uuid.UUID(str(run_id))
        return await db.get(StrategyTestRun, key)


async def update_run(run_id: uuid.UUID, **fields: Any) -> StrategyTestRun | None:
    async with AsyncSessionLocal() as db:
        run = await db.get(StrategyTestRun, run_id)
        if run is None:
            return None
        for key, value in fields.items():
            if hasattr(run, key):
                setattr(run, key, value)
        await db.commit()
        await db.refresh(run)
        return run


async def save_results(run_id: uuid.UUID, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    async with AsyncSessionLocal() as db:
        for row in rows:
            db.add(
                StrategyTestResult(
                    id=uuid.uuid4(),
                    run_id=run_id,
                    symbol=row["symbol"],
                    company=row.get("company"),
                    status=row.get("status") or "ok",
                    signal=row.get("signal"),
                    entry_price=row.get("entry_price"),
                    exit_price=row.get("exit_price"),
                    return_pct=row.get("return_pct"),
                    return_bucket=row.get("return_bucket"),
                    return_formula=row.get("return_formula"),
                    rank=row.get("rank"),
                    indicators=_json_safe(row.get("indicators") or {}),
                    passed_filters=_json_safe(row.get("passed_filters") or []),
                    failed_filters=_json_safe(row.get("failed_filters") or []),
                    filter_details=_json_safe(row.get("filter_details") or []),
                    primary_failure_reason=row.get("primary_failure_reason"),
                    error_detail=row.get("error_detail"),
                    candle_count=row.get("candle_count"),
                )
            )
        await db.commit()


async def save_filter_stats(run_id: uuid.UUID, independent: list[dict[str, Any]], funnel: list[dict[str, Any]]) -> None:
    funnel_by_id = {step.get("filter_id"): step for step in funnel if step.get("filter_id")}
    async with AsyncSessionLocal() as db:
        for item in independent:
            step = funnel_by_id.get(item.get("filter_id")) or {}
            db.add(
                StrategyFilterResult(
                    id=uuid.uuid4(),
                    run_id=run_id,
                    filter_id=str(item.get("filter_id") or ""),
                    label=str(item.get("label") or ""),
                    passed=int(item.get("passed") or 0),
                    failed=int(item.get("failed") or 0),
                    skipped=int(item.get("skipped") or 0),
                    pass_pct=item.get("pass_pct"),
                    fail_pct=item.get("fail_pct"),
                    funnel_remaining=step.get("remaining"),
                    funnel_step=step.get("step"),
                )
            )
        await db.commit()


async def list_results(
    run_id: uuid.UUID,
    *,
    signal: str | None = None,
    return_bucket: str | None = None,
    search: str | None = None,
    sort: str = "return_pct",
    direction: str = "desc",
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[StrategyTestResult], int]:
    async with AsyncSessionLocal() as db:
        stmt = select(StrategyTestResult).where(StrategyTestResult.run_id == run_id)
        count_stmt = select(func.count()).select_from(StrategyTestResult).where(StrategyTestResult.run_id == run_id)
        if signal and signal.upper() != "ALL":
            stmt = stmt.where(StrategyTestResult.signal == signal.upper())
            count_stmt = count_stmt.where(StrategyTestResult.signal == signal.upper())
        if return_bucket and return_bucket.upper() != "ALL":
            stmt = stmt.where(StrategyTestResult.return_bucket == return_bucket.upper())
            count_stmt = count_stmt.where(StrategyTestResult.return_bucket == return_bucket.upper())
        if search:
            like = f"%{search.strip().upper()}%"
            stmt = stmt.where(
                func.upper(StrategyTestResult.symbol).like(like)
                | func.upper(func.coalesce(StrategyTestResult.company, "")).like(like)
            )
            count_stmt = count_stmt.where(
                func.upper(StrategyTestResult.symbol).like(like)
                | func.upper(func.coalesce(StrategyTestResult.company, "")).like(like)
            )
        sort_map = {
            "return_pct": StrategyTestResult.return_pct,
            "symbol": StrategyTestResult.symbol,
            "signal": StrategyTestResult.signal,
            "entry_price": StrategyTestResult.entry_price,
            "exit_price": StrategyTestResult.exit_price,
            "rank": StrategyTestResult.rank,
        }
        col = sort_map.get(sort, StrategyTestResult.return_pct)
        signal_priority = case(
            (func.upper(StrategyTestResult.signal) == "BUY", 1),
            (func.upper(StrategyTestResult.signal) == "WATCH", 2),
            (func.upper(StrategyTestResult.signal) == "REJECT", 3),
            else_=4,
        )
        if signal is None or signal.upper() == "ALL":
            if sort == "signal":
                if direction.lower() == "asc":
                    stmt = stmt.order_by(signal_priority.asc(), StrategyTestResult.return_pct.desc())
                else:
                    stmt = stmt.order_by(signal_priority.desc(), StrategyTestResult.return_pct.desc())
            else:
                stmt = stmt.order_by(
                    signal_priority.asc(),
                    col.asc() if direction.lower() == "asc" else col.desc(),
                )
        else:
            stmt = stmt.order_by(col.asc() if direction.lower() == "asc" else col.desc())
        total = int((await db.execute(count_stmt)).scalar() or 0)
        rows = list((await db.scalars(stmt.offset(offset).limit(limit))).all())
        return rows, total


async def get_result(run_id: uuid.UUID, symbol: str) -> StrategyTestResult | None:
    async with AsyncSessionLocal() as db:
        stmt = select(StrategyTestResult).where(
            StrategyTestResult.run_id == run_id,
            func.upper(StrategyTestResult.symbol) == symbol.upper(),
        )
        return (await db.scalars(stmt.limit(1))).first()


async def list_filter_stats(run_id: uuid.UUID) -> list[StrategyFilterResult]:
    async with AsyncSessionLocal() as db:
        stmt = (
            select(StrategyFilterResult)
            .where(StrategyFilterResult.run_id == run_id)
            .order_by(StrategyFilterResult.funnel_step.asc())
        )
        return list((await db.scalars(stmt)).all())


async def list_history(user_id: uuid.UUID | None, *, limit: int = 25) -> list[StrategyTestRun]:
    async with AsyncSessionLocal() as db:
        stmt = select(StrategyTestRun).order_by(StrategyTestRun.started_at.desc()).limit(limit)
        if user_id is not None:
            stmt = stmt.where(StrategyTestRun.user_id == user_id)
        return list((await db.scalars(stmt)).all())


async def all_result_rows(run_id: uuid.UUID) -> list[StrategyTestResult]:
    async with AsyncSessionLocal() as db:
        signal_priority = case(
            (func.upper(StrategyTestResult.signal) == "BUY", 1),
            (func.upper(StrategyTestResult.signal) == "WATCH", 2),
            (func.upper(StrategyTestResult.signal) == "REJECT", 3),
            else_=4,
        )
        stmt = (
            select(StrategyTestResult)
            .where(StrategyTestResult.run_id == run_id)
            .order_by(signal_priority.asc(), StrategyTestResult.return_pct.desc())
        )
        return list((await db.scalars(stmt)).all())


async def get_symbol_run_history(symbol: str, *, limit: int = 20) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as db:
        stmt = (
            select(StrategyTestResult, StrategyTestRun)
            .join(StrategyTestRun, StrategyTestResult.run_id == StrategyTestRun.id)
            .where(func.upper(StrategyTestResult.symbol) == symbol.upper())
            .order_by(StrategyTestRun.started_at.desc())
            .limit(limit)
        )
        rows = (await db.execute(stmt)).all()
        return [
            {
                "run_id": run.public_run_id,
                "strategy_name": run.strategy_name,
                "date": run.started_at.isoformat() if run.started_at else None,
                "signal": res.signal,
                "entry_price": res.entry_price,
                "exit_price": res.exit_price,
                "return_pct": res.return_pct,
                "status": res.status,
            }
            for res, run in rows
        ]


def _looks_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False
