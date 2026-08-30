"""Strategy Tester HTTP API. Execution is async; this module never blocks on the universe scan."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from typing import Any

from pydantic import BaseModel, Field

from ..core.deps import require_feature
from ..models.auth import User
from ..services.strategy_tester import persistence
from ..services.strategy_tester.export import filter_stats_to_csv, results_to_csv, results_to_xlsx_bytes
from ..services.strategy_tester.indicators import rsi, sma
from ..services.strategy_tester.presets import catalog, preset_by_id
from ..services.strategy_tester.scan_service import (
    history_row,
    load_bar_series,
    load_universe,
    parse_run_dates,
    request_cancel,
    result_payload,
    run_status_payload,
    start_test_background,
)
from ..services.strategy_tester.schema import StrategyConfigError, parse_strategy_config
from ..utils.symbol import canonical_symbol

router = APIRouter(prefix="/strategy-tests", tags=["strategy-tester"])
logger = logging.getLogger("app.strategy_tester.api")


class StrategyConfigBody(BaseModel):
    name: str | None = None
    description: str | None = None
    universe: str | None = None
    timeframe: str | None = None
    filters: Any = None
    root: dict | None = None
    entry_conditions: dict | None = None
    position_rules: dict | None = None
    signal_rules: dict | None = None
    side: str | None = None
    initial_capital: float | None = None
    preset_id: str | None = None
    source: dict | None = None
    start_date: date | None = None
    end_date: date | None = None
    strategy_id: uuid.UUID | None = None

    def merged(self) -> dict:
        data = self.model_dump(exclude_none=True)
        preset_id = data.pop("preset_id", None)
        if preset_id:
            preset = preset_by_id(str(preset_id))
            if not preset:
                raise HTTPException(status_code=404, detail={"message": "Unknown preset"})
            merged = dict(preset)
            merged.update(data)
            return merged
        return data


class CreateRunBody(StrategyConfigBody):
    initial_capital: float = Field(default=100_000)


class SaveStrategyBody(StrategyConfigBody):
    pass


def _config_from_body(body: StrategyConfigBody):
    try:
        return parse_strategy_config(body.merged())
    except HTTPException:
        raise
    except StrategyConfigError as exc:
        merged = body.merged()
        logger.warning(
            "strategy_config_rejected | err=%s | name=%s | filters=%s",
            exc,
            merged.get("name"),
            merged.get("filters"),
        )
        raise HTTPException(status_code=422, detail={"message": str(exc)}) from exc
    except Exception as exc:
        logger.warning("strategy_config_unexpected_error | err=%s", exc)
        raise HTTPException(status_code=422, detail={"message": str(exc)}) from exc


@router.get("/catalog")
async def get_catalog(_: User = Depends(require_feature("advanced_scanner"))):
    data = catalog()
    instruments = await load_universe("ALL_755")
    data["universe_count"] = len(instruments)
    data["universe_label"] = f"{len(instruments)} Stocks" if instruments else "755 Stocks"
    data["universe_symbols"] = [
        {"symbol": str(item["symbol"]), "company": item.get("company") or ""}
        for item in instruments
        if item.get("symbol")
    ]
    return data


@router.get("/strategies")
async def list_strategies(user: User = Depends(require_feature("advanced_scanner"))):
    rows = await persistence.list_definitions(user.id)
    return {
        "strategies": [
            {
                "id": str(row.id),
                "name": row.name,
                "description": row.description,
                "version": row.version,
                "is_preset": row.is_preset,
                "preset_id": row.preset_id,
                "config": row.config,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ]
    }


@router.post("/strategies")
async def save_strategy(body: SaveStrategyBody, user: User = Depends(require_feature("advanced_scanner"))):
    config = _config_from_body(body)
    row = await persistence.create_definition(
        user_id=user.id,
        name=config.name,
        description=config.description,
        config=config.to_snapshot(),
        is_preset=False,
        preset_id=body.preset_id,
    )
    return {"id": str(row.id), "name": row.name, "version": row.version, "config": row.config}


@router.put("/strategies/{strategy_id}")
async def update_strategy(
    strategy_id: uuid.UUID,
    body: SaveStrategyBody,
    user: User = Depends(require_feature("advanced_scanner")),
):
    config = _config_from_body(body)
    row = await persistence.update_definition(
        strategy_id,
        user_id=user.id,
        patch={"name": config.name, "description": config.description, "config": config.to_snapshot()},
    )
    if row is None:
        raise HTTPException(status_code=404, detail={"message": "Strategy not found"})
    return {"id": str(row.id), "name": row.name, "version": row.version, "config": row.config}


@router.get("/history")
async def get_history(
    user: User = Depends(require_feature("advanced_scanner")),
    limit: int = Query(default=25, ge=1, le=100),
):
    rows = await persistence.list_history(user.id, limit=limit)
    return {"runs": [history_row(row) for row in rows]}


@router.post("")
async def create_run(body: CreateRunBody, user: User = Depends(require_feature("advanced_scanner"))):
    config = None
    version = 1
    definition_id = body.strategy_id
    if definition_id:
        saved = await persistence.get_definition(definition_id)
        if saved is None:
            raise HTTPException(status_code=404, detail={"message": "Strategy not found"})
        snapshot = dict(saved.config or {})
        snapshot.update({k: v for k, v in body.merged().items() if k not in {"preset_id"}})
        snapshot.setdefault("name", saved.name)
        try:
            config = parse_strategy_config(snapshot)
        except StrategyConfigError as exc:
            raise HTTPException(status_code=422, detail={"message": str(exc)}) from exc
        version = saved.version
    else:
        config = _config_from_body(body)
    start, end = parse_run_dates(body.start_date, body.end_date)
    result = await start_test_background(
        user_id=user.id,
        config=config,
        start_date=start,
        end_date=end,
        initial_capital=float(body.initial_capital or config.initial_capital),
        strategy_definition_id=definition_id,
        strategy_version=version,
    )
    if result.get("error_code") == "STRATEGY_TEST_IN_PROGRESS":
        raise HTTPException(status_code=409, detail=result)
    return result


@router.get("/{run_id}")
async def get_run(run_id: str, _: User = Depends(require_feature("advanced_scanner"))):
    run = await _load_run(run_id)
    return run_status_payload(run)


@router.get("/{run_id}/status")
async def get_run_status(run_id: str, _: User = Depends(require_feature("advanced_scanner"))):
    run = await _load_run(run_id)
    return run_status_payload(run)


@router.get("/{run_id}/summary")
async def get_run_summary(run_id: str, _: User = Depends(require_feature("advanced_scanner"))):
    run = await _load_run(run_id)
    body = run_status_payload(run)
    body["summary"] = run.summary or {}
    return body


@router.get("/{run_id}/filter-analytics")
async def get_filter_analytics(run_id: str, _: User = Depends(require_feature("advanced_scanner"))):
    run = await _load_run(run_id)
    stats = await persistence.list_filter_stats(run.id)
    summary = run.summary if isinstance(run.summary, dict) else {}
    return {
        "run_id": run.public_run_id,
        "independent": [
            {
                "filter_id": item.filter_id,
                "label": item.label,
                "passed": item.passed,
                "failed": item.failed,
                "skipped": item.skipped,
                "pass_pct": item.pass_pct,
                "fail_pct": item.fail_pct,
            }
            for item in stats
        ],
        "funnel": summary.get("filter_funnel") or [],
    }


@router.get("/{run_id}/results")
async def get_run_results(
    run_id: str,
    _: User = Depends(require_feature("advanced_scanner")),
    signal: str | None = Query(default=None),
    return_bucket: str | None = Query(default=None),
    search: str | None = Query(default=None),
    sort: str = Query(default="return_pct"),
    direction: str = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=755),
):
    run = await _load_run(run_id)
    offset = (page - 1) * page_size
    rows, total = await persistence.list_results(
        run.id,
        signal=signal,
        return_bucket=return_bucket,
        search=search,
        sort=sort,
        direction=direction,
        offset=offset,
        limit=page_size,
    )
    return {
        "run_id": run.public_run_id,
        "total": total,
        "page": page,
        "page_size": page_size,
        "results": [result_payload(row) for row in rows],
    }


@router.get("/{run_id}/results/{symbol}")
async def get_result_detail(
    run_id: str,
    symbol: str,
    _: User = Depends(require_feature("advanced_scanner")),
):
    run = await _load_run(run_id)
    row = await persistence.get_result(run.id, symbol)
    if row is None:
        raise HTTPException(status_code=404, detail={"message": "Symbol not in this run"})
    return result_payload(row)


@router.get("/{run_id}/results/{symbol}/candles")
async def get_result_candles(
    run_id: str,
    symbol: str,
    _: User = Depends(require_feature("advanced_scanner")),
):
    run = await _load_run(run_id)
    canon = canonical_symbol(symbol) or symbol
    start_date = run.start_date or (date.today() - timedelta(days=365))
    end_date = run.end_date or date.today()
    from_date = start_date - timedelta(days=400)

    series_map = await load_bar_series([canon], from_date=from_date, to_date=end_date)
    series = series_map.get(canon)
    if not series or len(series) == 0:
        return {"symbol": canon, "candles": []}

    sma20 = sma(series.close, 20)
    sma50 = sma(series.close, 50)
    sma200 = sma(series.close, 200)
    rsi14 = rsi(series.close, 14)

    candles = []
    for i, d in enumerate(series.dates):
        if d < start_date:
            continue
        candles.append(
            {
                "date": d.isoformat(),
                "open": series.open[i],
                "high": series.high[i],
                "low": series.low[i],
                "close": series.close[i],
                "volume": series.volume[i],
                "sma_20": sma20[i] if i < len(sma20) else None,
                "sma_50": sma50[i] if i < len(sma50) else None,
                "sma_200": sma200[i] if i < len(sma200) else None,
                "rsi": rsi14[i] if i < len(rsi14) else None,
            }
        )
    return {
        "symbol": canon,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "candles": candles,
    }


@router.get("/{run_id}/results/{symbol}/history")
async def get_result_history(
    run_id: str,
    symbol: str,
    _: User = Depends(require_feature("advanced_scanner")),
):
    canon = canonical_symbol(symbol) or symbol
    history = await persistence.get_symbol_run_history(canon)
    return {"symbol": canon, "history": history}


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str, _: User = Depends(require_feature("advanced_scanner"))):
    run = await _load_run(run_id)
    if run.status not in {"queued", "running"}:
        raise HTTPException(status_code=409, detail={"message": "Run is not cancellable", "status": run.status})
    request_cancel(run.id)
    await persistence.update_run(run.id, status="cancelled", stage="cancelling")
    return {"run_id": run.public_run_id, "status": "cancelled"}


@router.get("/{run_id}/export")
async def export_run(
    run_id: str,
    _: User = Depends(require_feature("advanced_scanner")),
    format: str = Query(default="csv"),
):
    run = await _load_run(run_id)
    if run.status != "completed":
        raise HTTPException(status_code=409, detail={"message": "Export is available after the run completes"})
    rows = await persistence.all_result_rows(run.id)
    stats = await persistence.list_filter_stats(run.id)
    fmt = format.lower()
    filename_base = f"{run.public_run_id}-{run.strategy_name.replace(' ', '_')}"
    if fmt in {"xlsx", "excel", "xls"}:
        payload = results_to_xlsx_bytes(rows, stats, run.summary or {})
        return Response(
            content=payload,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}.xlsx"'},
        )
    csv_body = results_to_csv(rows)
    extra = filter_stats_to_csv(stats)
    body = csv_body + "\n# Filter analytics\n" + extra
    return StreamingResponse(
        iter([body]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename_base}.csv"'},
    )


async def _load_run(run_id: str):
    run = await persistence.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail={"message": "Strategy test run not found"})
    return run
