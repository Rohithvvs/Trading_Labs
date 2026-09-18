import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..core.deps import require_feature
from ..models.auth import User
from ..services.latest_scan_service import LatestScanService
from ..services.scanner_cache_service import scanner_cache_service, wants_force_refresh
from ..config.settings import settings
from ..utils import get_logger
from ..observability.scan_diagnostics import log_dashboard_request
from ..observability.metrics import (
    record_scanner_cache_force_refresh,
    record_scanner_cache_hit,
    record_scanner_cache_miss,
    record_unified_latest_fallback,
)

router = APIRouter(prefix="/scanner", tags=["scanner"])
_stats_logger = get_logger("app.routes.scanner.statistics")
logger = get_logger("app.routes.scanner")


CACHE_KEY_SCANNER_LATEST = "scanner:latest:v1"
ENDPOINT_SCANNER_LATEST = "/scanner/latest"


@router.get("/statistics")
async def get_scanner_statistics(
    _: User = Depends(require_feature("advanced_scanner")),
):
    """Scanner statistics from the latest completed scan.

    Never returns fake/hardcoded values.
    """
    from ..db.scan_store import load_latest_scan

    production: dict = {}
    try:
        latest = await load_latest_scan()
        if latest:
            shortlisted = latest.get("shortlisted_symbols") or []
            buy_c = latest.get("buy_candidate_symbols") or []
            watch_c = latest.get("watch_candidate_symbols") or []
            data_valid = latest.get("data_valid_symbols") or []
            eligible = latest.get("eligible_symbols") or []
            production = {
                "available": True,
                "total_scanned": latest.get("scanned_symbols", 0),
                "data_valid": len(data_valid) if isinstance(data_valid, list) else data_valid,
                "trend_matched": len(eligible) if isinstance(eligible, list) else eligible,
                "favorites": len(shortlisted),
                "buy_ideas": len(buy_c),
                "watch_ideas": len(watch_c),
                "rejected": max(len(shortlisted) - len(buy_c) - len(watch_c), 0),
                "scanned_at": (
                    latest.get("last_scan_completed_at")
                    or latest.get("scanned_at")
                    or None
                ),
            }
        else:
            production = {"available": False, "message": "No completed scan found"}
    except Exception as exc:
        _stats_logger.warning("Scanner statistics failed | err=%s", exc, exc_info=True)
        production = {"available": False, "message": str(exc)}

    return {"production": production}




@router.get("/results")
async def get_scanner_results(
    force: bool = Query(default=False, description="Force refresh cache"),
    _: User = Depends(require_feature("advanced_scanner")),
):
    """Latest completed scanner results (analysis / ScreenerResponse shape)."""
    from ..db.scan_store import load_latest_scan

    try:
        data = await load_latest_scan()
        if not data:
            return {"available": False, "message": "No completed scan found"}
        return {"available": True, **data}
    except Exception as exc:
        logger.exception("GET /scanner/results failed | err=%s", exc)
        return {
            "available": False,
            "message": "Failed to load scanner results",
            "shortlisted_symbols": [],
            "buy_candidate_symbols": [],
            "watch_candidate_symbols": [],
            "all_analyzed_stocks": [],
            "scanned_symbols": 0,
        }


@router.get("/latest")
async def get_latest_completed_scan(
    request: Request,
    force: bool = Query(default=False, description="Force refresh cache"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_feature("advanced_scanner")),
):
    import time
    from ..services.diagnostics_service import diagnostics

    start_t = time.perf_counter()
    force_refresh = wants_force_refresh(force, request.headers.get("cache-control"))
    cache_enabled = settings.is_scanner_latest_cache_enabled()

    # Record force once at the route boundary (covers unified + legacy; no double-count).
    if force_refresh and cache_enabled:
        record_scanner_cache_force_refresh(ENDPOINT_SCANNER_LATEST)

    if settings.is_scanner_unified_latest_enabled():
        try:
            service = LatestScanService(db)
            payload, cache_status = await service.get_latest_scan(
                format_type="dashboard",
                force=force_refresh,
                cache_enabled=cache_enabled,
            )
            return Response(
                content=payload,
                media_type="application/json",
                headers={"X-Cache-Status": cache_status},
            )
        except Exception as exc:
            record_unified_latest_fallback(ENDPOINT_SCANNER_LATEST)
            logger.error(
                "Unified GET /scanner/latest failed, falling back to legacy path | err=%s",
                exc,
                exc_info=True,
            )

    async def produce_json() -> str:
        service = LatestScanService(db)
        result = await service.get_latest_completed_scan()
        duration_ms = int((time.perf_counter() - start_t) * 1000)

        if not result:
            diagnostics.record_dashboard_snapshot(
                {
                    "response_time_ms": duration_ms,
                    "snapshot_id": None,
                    "record_count": 0,
                }
            )
            log_dashboard_request(
                scan_id=None,
                endpoint=ENDPOINT_SCANNER_LATEST,
                returned_records=0,
                query_duration_ms=duration_ms,
            )
            empty_json = json.dumps(
                {
                    "message": "No completed scans found",
                    "buy_candidates": [],
                    "watch_candidates": [],
                    "rejected_candidates": [],
                }
            )
            if cache_enabled:
                await scanner_cache_service.set_latest_scan(
                    CACHE_KEY_SCANNER_LATEST, empty_json, ttl_seconds=10
                )
            return empty_json

        record_count = (
            len(result.get("buy_candidates", []))
            + len(result.get("watch_candidates", []))
            + len(result.get("rejected_candidates", []))
        )
        diagnostics.record_dashboard_snapshot(
            {
                "response_time_ms": duration_ms,
                "snapshot_id": result.get("scan_id") or result.get("snapshot_id", "unknown"),
                "record_count": record_count,
            }
        )
        log_dashboard_request(
            scan_id=result.get("scan_id") or result.get("scan_timestamp"),
            endpoint=ENDPOINT_SCANNER_LATEST,
            returned_records=record_count,
            query_duration_ms=duration_ms,
        )
        serialized_payload = json.dumps(result)
        if cache_enabled:
            await scanner_cache_service.set_latest_scan(
                CACHE_KEY_SCANNER_LATEST, serialized_payload
            )
        return serialized_payload

    payload, cache_status = await scanner_cache_service.resolve_latest_scan(
        CACHE_KEY_SCANNER_LATEST,
        produce_json,
        force=force_refresh,
        cache_enabled=cache_enabled,
    )

    if cache_status == "HIT":
        record_scanner_cache_hit(ENDPOINT_SCANNER_LATEST)
        duration_ms = int((time.perf_counter() - start_t) * 1000)
        try:
            parsed = json.loads(payload) if isinstance(payload, str) else {}
        except Exception:
            parsed = {}
        logger.info(
            "Loading latest scan... | endpoint=/scanner/latest | "
            "User ID: n/a | Latest Scan ID: %s | Completed At: %s | "
            "Returned Rows: %s | Cache Hit/Miss: HIT | duration_ms=%d",
            parsed.get("scan_id"),
            parsed.get("last_scan_completed_at") or parsed.get("scan_timestamp"),
            (
                len(parsed.get("buy_candidates") or [])
                + len(parsed.get("watch_candidates") or [])
                + len(parsed.get("rejected_candidates") or [])
            ),
            duration_ms,
        )
        logger.debug("GET /scanner/latest Cache HIT | duration_ms=%d", duration_ms)
    elif cache_status in ("MISS", "FALLBACK"):
        record_scanner_cache_miss(ENDPOINT_SCANNER_LATEST)
        logger.info(
            "Loading latest scan... | endpoint=/scanner/latest | Cache Hit/Miss: %s",
            cache_status,
        )

    return Response(
        content=payload,
        media_type="application/json",
        headers={"X-Cache-Status": cache_status},
    )


@router.get("/strategies")
async def list_scanner_strategies(
    _: User = Depends(require_feature("advanced_scanner")),
):
    from ..services.strategies.ltm.identity import DISPLAY_NAME, SHORT_NAME, STRATEGY_ID

    return {
        "strategies": [
            {"id": "production", "display_name": "Production", "short_name": "PROD"},
            {"id": STRATEGY_ID, "display_name": DISPLAY_NAME, "short_name": SHORT_NAME},
        ]
    }


@router.get("/ltm/latest")
async def get_ltm_latest(
    _: User = Depends(require_feature("advanced_scanner")),
):
    from ..services.strategies.ltm import persistence
    from ..services.strategies.ltm.identity import DISPLAY_NAME, STRATEGY_ID

    row = await persistence.load_latest(STRATEGY_ID)
    if not row or not row.payload:
        raise HTTPException(
            status_code=404,
            detail={"available": False, "message": "No LTM scan yet", "strategy_id": STRATEGY_ID},
        )
    body = dict(row.payload)
    body.setdefault("strategy_id", STRATEGY_ID)
    body.setdefault("display_name", DISPLAY_NAME)
    body["status"] = row.status
    if row.status != "completed":
        body["recommendations_final"] = False
    return body


@router.post("/ltm/runs")
async def start_ltm_run(
    _: User = Depends(require_feature("advanced_scanner")),
    mode: str | None = Query(default=None),
):
    from ..services.strategies.ltm.scan_service import start_scan_background

    result = await start_scan_background(mode=mode)
    if result.get("error_code") == "LTM_SCAN_IN_PROGRESS":
        raise HTTPException(status_code=409, detail=result)
    return result


@router.get("/ltm/runs/{scan_id}")
async def get_ltm_run(
    scan_id: uuid.UUID,
    _: User = Depends(require_feature("advanced_scanner")),
):
    from ..services.strategies.ltm import persistence

    run = await persistence.get_run(scan_id)
    if not run:
        raise HTTPException(status_code=404, detail={"message": "Scan run not found"})
    return {
        "scan_id": str(run.scan_id),
        "strategy_id": run.strategy_id,
        "status": run.status,
        "progress_pct": run.progress_pct,
        "stage": run.stage,
        "error_code": run.error_code,
        "recommendations_final": run.status == "completed",
        "payload": run.payload if run.status == "completed" else None,
    }


@router.get("/ltm/symbols/{symbol}")
async def get_ltm_symbol(
    symbol: str,
    window: str = Query(default="3Y"),
    _: User = Depends(require_feature("advanced_scanner")),
):
    from datetime import date as date_cls

    from ..services.strategies.ltm import persistence
    from ..services.strategies.ltm.analytics import build_symbol_dashboard, parse_window
    from ..services.strategies.ltm.identity import STRATEGY_ID

    row = await persistence.load_latest(STRATEGY_ID)
    if not row or not row.payload:
        raise HTTPException(status_code=404, detail={"message": "No LTM scan yet"})
    payload = row.payload
    recs = payload.get("recommendations") or []
    match = next((r for r in recs if str(r.get("symbol", "")).upper() == symbol.upper()), None)
    if not match:
        raise HTTPException(status_code=404, detail={"message": "Symbol not in last LTM scan"})
    eval_raw = payload.get("evaluation_date")
    try:
        asof = date_cls.fromisoformat(str(eval_raw)[:10]) if eval_raw else date_cls.today()
    except ValueError:
        asof = date_cls.today()
    blotter = payload.get("blotter") or []
    if not blotter:
        bt = match.get("backtest_1y") or {}
        blotter = list(bt.get("trades") or [])
        for t in blotter:
            if isinstance(t, dict) and not t.get("symbol"):
                t["symbol"] = match["symbol"]
    metrics = payload.get("book_metrics") if isinstance(payload.get("book_metrics"), dict) else {}
    dashboard = build_symbol_dashboard(
        symbol=match["symbol"],
        blotter=blotter,
        equity_curve=payload.get("equity_curve") or [],
        index_curve=payload.get("index_curve") or [],
        asof=asof,
        window=parse_window(window),
        initial_capital=float(
            payload.get("initial_capital")
            or metrics.get("initial_capital")
            or 100000
        ),
    )
    return {
        "strategy_id": STRATEGY_ID,
        "symbol": match["symbol"],
        "window": dashboard["window"],
        "technicals": match.get("technicals"),
        "backtest": match.get("backtest_1y"),
        "dashboard": dashboard,
        "book_metrics": payload.get("book_metrics"),
        "equity_curve": payload.get("equity_curve"),
        "signal": match.get("signal"),
        "limitations": payload.get("limitations"),
    }


