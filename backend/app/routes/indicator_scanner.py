"""Pine-compatible Indicator Scanner HTTP API."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..core.deps import require_feature
from ..lean.models import EngineType, LeanBacktestRequest, LeanBacktestResult, LeanJobRecord, LeanJobStatus
from ..lean.services.lean_service import LeanBacktestService
from ..models.auth import User
from ..services.indicator_scanner.compiler import compile_source
from ..services.indicator_scanner.entry_conditions import attach_entry_conditions
from ..services.indicator_scanner.errors import PineCompileError
from ..services.indicator_scanner.filters import validate_filters
from ..services.indicator_scanner.limits import LANGUAGE_MODE
from ..services.indicator_scanner.template import BREAKOUT_SCAN_SOURCE, BREAKOUT_SCAN_TITLE, SUPPORTED_SYNTAX_HELP
from ..services.indicator_scanner import persistence
from ..services.indicator_scanner.scan_service import (
    ensure_summary_analytics,
    paginate_results,
    request_cancel,
    results_to_csv,
    scan_status_payload,
    start_scan_background,
    symbol_detail_payload,
)
from ..services.indicator_scanner.symbols import is_supported_timeframe, normalize_timeframe

router = APIRouter(prefix="/indicators", tags=["indicator-scanner"])
scan_router = APIRouter(prefix="/indicator-scans", tags=["indicator-scanner"])


class ValidateBody(BaseModel):
    source_code: str = Field(..., min_length=1, max_length=30_000)
    timeframe: str | None = "1D"


class IndicatorBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = Field(default="", max_length=500)
    source_code: str = Field(..., min_length=1, max_length=30_000)
    timeframe: str | None = "1D"


class ScanBody(BaseModel):
    universe_id: str | None = "nse-755"
    timeframe: str | None = "1D"
    scan_date: date | None = None
    input_overrides: dict[str, Any] | None = None
    filters: list[dict[str, Any]] | None = None
    sort: dict[str, Any] | None = None


class IndicatorBacktestBody(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    initial_capital: float = Field(default=100_000.0, ge=1_000)
    universe_id: str | None = "nse-755"
    engine: str | None = "LEAN"
    symbols: list[str] | None = None
    max_positions: int = Field(default=10, ge=1, le=50)
    parameters: dict[str, Any] | None = None


def _compile_payload(source: str, timeframe: str | None) -> dict[str, Any]:
    try:
        compiled = compile_source(source)
    except PineCompileError as exc:
        return {
            "ok": False,
            "status": "invalid",
            "errors": [exc.issue.to_dict()],
            "warnings": [],
            "inputs": [],
            "outputs": [],
            "required_bars": 0,
            "required_symbols": [],
            "language_mode": LANGUAGE_MODE,
            "timeframe_supported": is_supported_timeframe(timeframe),
        }
    warnings = [w.to_dict() for w in compiled.warnings]
    tf_ok = is_supported_timeframe(timeframe)
    if not tf_ok:
        warnings.append(
            {
                "line": 1,
                "column": 1,
                "severity": "warning",
                "code": "TIMEFRAME_UNSUPPORTED",
                "message": "Weekly and monthly timeframes are not supported yet. Daily (1D) data is available.",
            }
        )
    parsed = attach_entry_conditions(compiled.to_definition_json(), compiled)
    return {
        "ok": True,
        "status": "valid",
        "errors": [],
        "warnings": warnings,
        "title": compiled.title,
        "inputs": [i.to_dict() for i in compiled.inputs],
        "outputs": [o.to_dict() for o in compiled.outputs],
        "required_bars": compiled.required_bars,
        "required_symbols": compiled.required_symbols,
        "language_mode": compiled.language_mode,
        "script_version": compiled.version,
        "overlay": compiled.overlay,
        "timeframe": normalize_timeframe(timeframe),
        "timeframe_supported": tf_ok,
        "parsed_definition": parsed,
        "entry_conditions": parsed.get("entry_conditions") or [],
        "supported_syntax": SUPPORTED_SYNTAX_HELP,
        "disclaimer": "For research and paper-trading only. Not investment advice.",
    }


def _definition_payload(row) -> dict[str, Any]:
    payload = persistence.definition_payload(row)
    parsed = attach_entry_conditions(payload.get("parsed_definition"), source_code=row.source_code)
    payload["parsed_definition"] = parsed
    payload["entry_conditions"] = parsed.get("entry_conditions") or []
    return payload


def _owned(row, user: User):
    if row is None:
        raise HTTPException(status_code=404, detail={"message": "Indicator not found"})
    if row.user_id == user.id or getattr(user, "role", None) == "admin" or row.user_id is None:
        return row
    raise HTTPException(status_code=404, detail={"message": "Indicator not found"})


@router.get("/template")
async def get_template(_: User = Depends(require_feature("advanced_scanner"))):
    payload = _compile_payload(BREAKOUT_SCAN_SOURCE, "1D")
    payload["source_code"] = BREAKOUT_SCAN_SOURCE
    payload["name"] = BREAKOUT_SCAN_TITLE
    payload["description"] = "Daily 52-week high breakout with volume and NIFTY 500 market gate."
    return payload


@router.get("/templates")
async def list_lab_templates(_: User = Depends(require_feature("advanced_scanner"))):
    from ..services.research_lab.seed import template_payloads

    templates = template_payloads()
    return {"templates": templates, "count": len(templates)}


@router.post("/seed-lab")
async def seed_lab_strategies(user: User = Depends(require_feature("advanced_scanner"))):
    from ..services.research_lab.seed import seed_lab_indicators

    return await seed_lab_indicators(user.id)


@router.post("/validate")
async def validate_indicator(body: ValidateBody, _: User = Depends(require_feature("advanced_scanner"))):
    return _compile_payload(body.source_code, body.timeframe)


@router.post("")
async def create_indicator(body: IndicatorBody, user: User = Depends(require_feature("advanced_scanner"))):
    payload = _compile_payload(body.source_code, body.timeframe)
    if not payload["ok"]:
        raise HTTPException(status_code=422, detail={"message": "Indicator validation failed", "errors": payload["errors"]})
    name = body.name.strip()
    patch = {
        "name": name,
        "description": body.description or "",
        "source_code": body.source_code,
        "script_version": int(payload.get("script_version") or 6),
        "language_mode": LANGUAGE_MODE,
        "timeframe": normalize_timeframe(body.timeframe),
        "parsed_definition": payload["parsed_definition"],
        "validation_status": "valid",
        "validation_errors": [],
        "required_bars": int(payload["required_bars"]),
    }
    existing = await persistence.find_definition_by_name(user.id, name)
    if existing is not None:
        row = await persistence.update_definition(existing.id, user_id=user.id, patch=patch)
        if row is not None:
            return _definition_payload(row)
    row = await persistence.create_definition(
        user_id=user.id,
        name=name,
        description=body.description or "",
        source_code=body.source_code,
        script_version=int(payload.get("script_version") or 6),
        language_mode=LANGUAGE_MODE,
        timeframe=normalize_timeframe(body.timeframe),
        parsed_definition=payload["parsed_definition"],
        validation_status="valid",
        validation_errors=[],
        required_bars=int(payload["required_bars"]),
    )
    return _definition_payload(row)


@router.get("")
async def list_indicators(user: User = Depends(require_feature("advanced_scanner"))):
    rows = await persistence.list_definitions(user.id)
    return {"indicators": [_definition_payload(row) for row in rows]}


@router.get("/{indicator_id}")
async def get_indicator(indicator_id: uuid.UUID, user: User = Depends(require_feature("advanced_scanner"))):
    row = _owned(await persistence.get_definition(indicator_id), user)
    return _definition_payload(row)


@router.put("/{indicator_id}")
async def update_indicator(
    indicator_id: uuid.UUID,
    body: IndicatorBody,
    user: User = Depends(require_feature("advanced_scanner")),
):
    existing = _owned(await persistence.get_definition(indicator_id), user)
    payload = _compile_payload(body.source_code, body.timeframe)
    if not payload["ok"]:
        raise HTTPException(status_code=422, detail={"message": "Indicator validation failed", "errors": payload["errors"]})
    row = await persistence.update_definition(
        existing.id,
        user_id=user.id,
        patch={
            "name": body.name.strip(),
            "description": body.description or "",
            "source_code": body.source_code,
            "script_version": int(payload.get("script_version") or 6),
            "language_mode": LANGUAGE_MODE,
            "timeframe": normalize_timeframe(body.timeframe),
            "parsed_definition": payload["parsed_definition"],
            "validation_status": "valid",
            "validation_errors": [],
            "required_bars": int(payload["required_bars"]),
        },
    )
    if row is None:
        raise HTTPException(status_code=404, detail={"message": "Indicator not found"})
    return _definition_payload(row)


@router.post("/{indicator_id}/duplicate")
async def duplicate_indicator(indicator_id: uuid.UUID, user: User = Depends(require_feature("advanced_scanner"))):
    src = _owned(await persistence.get_definition(indicator_id), user)
    row = await persistence.create_definition(
        user_id=user.id,
        name=f"{src.name} (copy)"[:120],
        description=src.description or "",
        source_code=src.source_code,
        script_version=src.script_version,
        language_mode=src.language_mode,
        timeframe=src.timeframe,
        parsed_definition=src.parsed_definition or {},
        validation_status=src.validation_status,
        validation_errors=src.validation_errors or [],
        required_bars=src.required_bars,
    )
    return _definition_payload(row)


@router.delete("/{indicator_id}")
async def archive_indicator(indicator_id: uuid.UUID, user: User = Depends(require_feature("advanced_scanner"))):
    row = await persistence.archive_definition(indicator_id, user_id=user.id)
    if row is None:
        raise HTTPException(status_code=404, detail={"message": "Indicator not found"})
    return {"id": str(row.id), "is_archived": True}


@router.post("/{indicator_id}/scans")
async def start_scan(
    indicator_id: uuid.UUID,
    body: ScanBody,
    user: User = Depends(require_feature("advanced_scanner")),
):
    row = _owned(await persistence.get_definition(indicator_id), user)
    if row.is_archived:
        raise HTTPException(status_code=404, detail={"message": "Indicator not found"})
    if not is_supported_timeframe(body.timeframe):
        raise HTTPException(
            status_code=422,
            detail={"message": "Weekly and monthly timeframes are not supported yet. Daily (1D) data is available."},
        )
    try:
        compiled = compile_source(row.source_code)
        filters = validate_filters(compiled, body.filters)
    except PineCompileError as exc:
        raise HTTPException(status_code=422, detail={"message": exc.issue.message, "errors": [exc.issue.to_dict()]}) from exc
    result = await start_scan_background(
        user_id=user.id,
        compiled=compiled,
        indicator_id=row.id,
        universe_id=body.universe_id or "nse-755",
        timeframe=body.timeframe or "1D",
        filters=filters,
        sort=body.sort,
        input_overrides=body.input_overrides,
        scan_date=body.scan_date,
    )
    if result.get("error_code") == "INDICATOR_SCAN_IN_PROGRESS":
        raise HTTPException(status_code=409, detail=result)
    if result.get("error_code") == "RATE_LIMITED":
        raise HTTPException(status_code=429, detail=result)
    return result


@router.post("/{indicator_id}/backtest", response_model=LeanJobRecord)
async def start_indicator_backtest(
    indicator_id: uuid.UUID,
    body: IndicatorBacktestBody,
    user: User = Depends(require_feature("advanced_scanner")),
):
    """Launch an asynchronous professional backtest of this indicator using LEAN."""
    row = _owned(await persistence.get_definition(indicator_id), user)
    if row.is_archived:
        raise HTTPException(status_code=404, detail={"message": "Indicator not found"})

    from ..services.research_lab.catalog import strategy_id_from_indicator_name

    name_lower = row.name.lower()
    source_lower = str(getattr(row, "source_code", "") or "").lower()
    blob = f"{name_lower} {source_lower}"
    lab_id = strategy_id_from_indicator_name(row.name)
    if lab_id == "09_52w_breakout":
        strat_id = "09_52w_breakout"
    elif lab_id == "17_long_term_mom":
        strat_id = "17_long_term_mom"
    elif lab_id:
        raise HTTPException(
            status_code=400,
            detail={
                "message": (
                    f"{row.name} is a research-lab strategy. Scan it in the Indicator Scanner "
                    "or run the shared 10%×10 book; LEAN does not map this id yet."
                )
            },
        )
    elif "pulse" in blob or ("ta.crossover" in source_lower and "rsi" in source_lower):
        strat_id = "momentum_pulse"
    elif "ltm" in blob or "long term mom" in blob or "momentum 252" in blob:
        strat_id = "17_long_term_mom"
    elif "52" in name_lower or "52w" in name_lower:
        strat_id = "09_52w_breakout"
    elif "sma" in name_lower and "cross" in blob:
        strat_id = "01_sma_cross"
    elif "rsi" in name_lower:
        strat_id = "02_rsi_oversold"
    else:
        raise HTTPException(
            status_code=400,
            detail={
                "message": (
                    "No mapped event-engine strategy for this indicator. "
                    "Name it as 52W/breakout, LTM, pulse, SMA cross, or RSI, "
                    "or scan it in Strategy Tester instead of running a portfolio backtest."
                )
            },
        )

    start_d = body.start_date or date(2020, 1, 1)
    end_d = body.end_date or date.today()
    symbols = body.symbols or (["ALL_755"] if (body.universe_id or "nse-755").lower() in {"nse-755", "all", "all_755"} else ["RELIANCE", "TCS", "INFY"])

    req = LeanBacktestRequest(
        strategyId=strat_id,
        strategyName=row.name,
        symbols=symbols,
        startDate=start_d,
        endDate=end_d,
        initialCapital=body.initial_capital,
        maxPositions=body.max_positions,
        executionMode=EngineType.LEAN if (body.engine or "LEAN").upper() == "LEAN" else EngineType.EXISTING,
        parameters=body.parameters or {},
    )
    return await LeanBacktestService.create_and_start_job(req, user_id=str(user.id))


@router.get("/{indicator_id}/backtests/{job_id}", response_model=LeanJobRecord)
async def get_indicator_backtest_status(
    indicator_id: uuid.UUID,
    job_id: str,
    user: User = Depends(require_feature("advanced_scanner")),
):
    """Retrieve execution status and progress of an indicator LEAN backtest."""
    _owned(await persistence.get_definition(indicator_id), user)
    job = LeanBacktestService.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail={"message": f"Backtest job {job_id} not found"})
    return job


@router.get("/{indicator_id}/backtests/{job_id}/results", response_model=LeanBacktestResult)
async def get_indicator_backtest_results(
    indicator_id: uuid.UUID,
    job_id: str,
    user: User = Depends(require_feature("advanced_scanner")),
):
    """Retrieve normalized backtest results for a completed indicator LEAN backtest."""
    _owned(await persistence.get_definition(indicator_id), user)
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


def _scan_owned(run, user: User):
    if run is None:
        raise HTTPException(status_code=404, detail={"message": "Scan not found"})
    if run.user_id == user.id or getattr(user, "role", None) == "admin" or run.user_id is None:
        return run
    raise HTTPException(status_code=404, detail={"message": "Scan not found"})


@scan_router.get("/{scan_id}")
async def get_scan(scan_id: str, user: User = Depends(require_feature("advanced_scanner"))):
    from datetime import datetime, timezone
    run = _scan_owned(await _load_scan(scan_id), user)
    if run.status in ("running", "preparing", "cancelling"):
        from ..services.indicator_scanner.scan_service import _active_scans
        started = run.started_at
        if started is not None and started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        age = (now - started).total_seconds() if started else 0
        if run.id not in _active_scans and age > 900:
            updated = await persistence.update_scan(
                run.id,
                status="failed",
                stage="failed",
                error_code="SCAN_INTERRUPTED",
                error_detail="Scan process was interrupted or timed out. Please click Scan to restart.",
                completed_at=now,
            )
            if updated:
                run = updated
    run = await ensure_summary_analytics(run)
    return scan_status_payload(run)


@scan_router.get("/{scan_id}/results")
async def get_scan_results(
    scan_id: str,
    user: User = Depends(require_feature("advanced_scanner")),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    search: str | None = None,
    matched_only: bool = Query(default=True),
    sort: str | None = None,
    direction: str = Query(default="desc"),
    signal: str | None = None,
    return_bucket: str | None = None,
):
    run = _scan_owned(await _load_scan(scan_id), user)
    rows = await persistence.list_results(run.id)
    output_names = [o.get("name") for o in (run.indicator_snapshot or {}).get("outputs") or [] if o.get("name")]
    page_rows, total = paginate_results(
        rows,
        page=page,
        page_size=page_size,
        search=search,
        matched_only=matched_only if not signal else False,
        sort_field=sort or "signal",
        sort_dir=direction or "desc",
        output_names=output_names,
        signal=signal,
        return_bucket=return_bucket,
    )
    return {
        "scan_id": run.public_scan_id,
        "page": page,
        "page_size": page_size,
        "total": total,
        "matched_count": run.matched_count,
        "outputs": output_names,
        "results": page_rows,
    }


@scan_router.get("/{scan_id}/results/export")
async def export_scan_results(
    scan_id: str,
    user: User = Depends(require_feature("advanced_scanner")),
    matched_only: bool = Query(default=True),
):
    run = _scan_owned(await _load_scan(scan_id), user)
    rows = await persistence.list_results(run.id)
    output_names = [o.get("name") for o in (run.indicator_snapshot or {}).get("outputs") or [] if o.get("name")]
    payload_rows, _ = paginate_results(
        rows,
        page=1,
        page_size=10_000,
        search=None,
        matched_only=matched_only,
        sort_field=(run.sort or {}).get("field"),
        sort_dir=(run.sort or {}).get("direction") or "desc",
        output_names=output_names,
    )
    csv_text = results_to_csv(payload_rows, output_names)
    return StreamingResponse(
        iter([csv_text]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{run.public_scan_id}.csv"'},
    )


@scan_router.get("/{scan_id}/results/{symbol}")
async def get_scan_result_symbol(
    scan_id: str,
    symbol: str,
    user: User = Depends(require_feature("advanced_scanner")),
):
    run = _scan_owned(await _load_scan(scan_id), user)
    row = await persistence.get_result(run.id, symbol)
    if row is None:
        raise HTTPException(status_code=404, detail={"message": "Symbol was not in this indicator scan."})
    snapshot = dict(run.indicator_snapshot or {})
    if not snapshot.get("source_code") and run.indicator_id:
        definition = await persistence.get_definition(run.indicator_id)
        if definition is not None and definition.source_code:
            snapshot["source_code"] = definition.source_code
            run.indicator_snapshot = snapshot
    return symbol_detail_payload(run, row)


@scan_router.get("/{scan_id}/diagnostics")
async def get_scan_diagnostics(scan_id: str, user: User = Depends(require_feature("advanced_scanner"))):
    run = _scan_owned(await _load_scan(scan_id), user)
    rows = await persistence.list_results(run.id)
    failures = [
        {"symbol": r.symbol, "status": r.status, "error_detail": r.error_detail}
        for r in rows
        if r.status != "ok"
    ]
    return {
        "scan_id": run.public_scan_id,
        "total_symbols": run.total_count,
        "completed": run.processed_count,
        "successful": run.success_count,
        "failed": run.failed_count,
        "skipped": run.skipped_count,
        "matched": run.matched_count,
        "as_of": run.as_of,
        "benchmark_symbol": run.benchmark_symbol,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "failures": failures[:200],
        "summary": run.summary,
        "disclaimer": "For research and paper-trading only. Not investment advice.",
    }


@scan_router.post("/{scan_id}/cancel")
async def cancel_scan(scan_id: str, user: User = Depends(require_feature("advanced_scanner"))):
    from datetime import datetime, timezone
    run = _scan_owned(await _load_scan(scan_id), user)
    request_cancel(run.id)
    now = datetime.now(timezone.utc)
    await persistence.update_scan(
        run.id,
        status="cancelled",
        stage="cancelled",
        completed_at=now,
    )
    return {"scan_id": run.public_scan_id, "status": "cancelled"}


async def _load_scan(scan_id: str):
    try:
        uid = uuid.UUID(scan_id)
        run = await persistence.get_scan(uid)
        if run:
            return run
    except ValueError:
        pass
    return await persistence.get_scan_by_public_id(scan_id)
