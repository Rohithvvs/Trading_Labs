"""Pine-compatible Indicator Scanner HTTP API."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..core.deps import require_feature
from ..models.auth import User
from ..services.indicator_scanner.compiler import compile_source
from ..services.indicator_scanner.errors import PineCompileError
from ..services.indicator_scanner.filters import validate_filters
from ..services.indicator_scanner.limits import LANGUAGE_MODE
from ..services.indicator_scanner.template import BREAKOUT_SCAN_SOURCE, BREAKOUT_SCAN_TITLE, SUPPORTED_SYNTAX_HELP
from ..services.indicator_scanner import persistence
from ..services.indicator_scanner.scan_service import (
    paginate_results,
    request_cancel,
    results_to_csv,
    scan_status_payload,
    start_scan_background,
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
        "parsed_definition": compiled.to_definition_json(),
        "supported_syntax": SUPPORTED_SYNTAX_HELP,
        "disclaimer": "For research and paper-trading only. Not investment advice.",
    }


def _owned(row, user: User):
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail={"message": "Indicator not found"})
    return row


@router.get("/template")
async def get_template(_: User = Depends(require_feature("advanced_scanner"))):
    payload = _compile_payload(BREAKOUT_SCAN_SOURCE, "1D")
    payload["source_code"] = BREAKOUT_SCAN_SOURCE
    payload["name"] = BREAKOUT_SCAN_TITLE
    payload["description"] = "Daily 52-week high breakout with volume and NIFTY 500 market gate."
    return payload


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
            return persistence.definition_payload(row)
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
    return persistence.definition_payload(row)


@router.get("")
async def list_indicators(user: User = Depends(require_feature("advanced_scanner"))):
    rows = await persistence.list_definitions(user.id)
    return {"indicators": [persistence.definition_payload(row) for row in rows]}


@router.get("/{indicator_id}")
async def get_indicator(indicator_id: uuid.UUID, user: User = Depends(require_feature("advanced_scanner"))):
    row = _owned(await persistence.get_definition(indicator_id), user)
    return persistence.definition_payload(row)


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
    return persistence.definition_payload(row)


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
    return persistence.definition_payload(row)


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


def _scan_owned(run, user: User):
    if run is None or run.user_id != user.id:
        raise HTTPException(status_code=404, detail={"message": "Scan not found"})
    return run


@scan_router.get("/{scan_id}")
async def get_scan(scan_id: str, user: User = Depends(require_feature("advanced_scanner"))):
    run = await _load_scan(scan_id)
    return scan_status_payload(_scan_owned(run, user))


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
):
    run = _scan_owned(await _load_scan(scan_id), user)
    rows = await persistence.list_results(run.id)
    output_names = [o.get("name") for o in (run.indicator_snapshot or {}).get("outputs") or [] if o.get("name")]
    page_rows, total = paginate_results(
        rows,
        page=page,
        page_size=page_size,
        search=search,
        matched_only=matched_only,
        sort_field=sort or (run.sort or {}).get("field"),
        sort_dir=direction or (run.sort or {}).get("direction") or "desc",
        output_names=output_names,
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
    run = _scan_owned(await _load_scan(scan_id), user)
    request_cancel(run.id)
    return {"scan_id": run.public_scan_id, "status": "cancelling"}


async def _load_scan(scan_id: str):
    try:
        uid = uuid.UUID(scan_id)
        run = await persistence.get_scan(uid)
        if run:
            return run
    except ValueError:
        pass
    return await persistence.get_scan_by_public_id(scan_id)
