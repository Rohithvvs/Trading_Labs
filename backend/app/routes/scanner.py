import json
import uuid
from types import SimpleNamespace

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


def _progress_fields_from_run(run) -> dict:
    """In-flight progress lives on the run row, not the last completed latest payload."""
    out: dict = {}
    if run is None:
        return out
    meta = run.payload if isinstance(getattr(run, "payload", None), dict) and getattr(run, "status", None) != "completed" else {}
    out["current_symbol"] = meta.get("current_symbol") or ""
    out["processed_count"] = meta.get("processed_count")
    out["total_count"] = meta.get("total_count")
    if meta.get("phase"):
        out["phase"] = meta.get("phase")
    return out


def _strategy_run_body(run) -> dict:
    body = {
        "scan_id": str(run.scan_id),
        "strategy_id": run.strategy_id,
        "status": run.status,
        "progress_pct": run.progress_pct,
        "stage": run.stage,
        "error_code": run.error_code,
        "error_detail": getattr(run, "error_detail", None),
        "started_at": run.started_at.isoformat() if getattr(run, "started_at", None) else None,
        "recommendations_final": run.status == "completed",
        "payload": run.payload if run.status == "completed" else None,
    }
    body.update(_progress_fields_from_run(run))
    return body


def _strategy_latest_body(row, *, strategy_id: str, display_name: str, run=None) -> dict:
    """Envelope for namespaced strategy latest: current run overlay + last completed results."""
    body = dict(row.payload or {})
    body.setdefault("strategy_id", strategy_id)
    body.setdefault("display_name", display_name)
    body["status"] = row.status
    body["run_status"] = row.status
    body["scan_id"] = str(row.scan_id) if row.scan_id else body.get("scan_id")
    body["completed_at"] = row.completed_at.isoformat() if getattr(row, "completed_at", None) else None
    started = getattr(row, "started_at", None) or (getattr(run, "started_at", None) if run else None)
    body["started_at"] = started.isoformat() if started else None
    if run is not None:
        body["progress_pct"] = run.progress_pct
        body["stage"] = run.stage or row.status
        body["error_code"] = run.error_code or row.error_code
        body["error_detail"] = run.error_detail
        body.update(_progress_fields_from_run(run))
    else:
        body["progress_pct"] = 100 if row.status == "completed" else body.get("progress_pct") or 0
        body["stage"] = body.get("stage") or row.status
        body["error_code"] = row.error_code
    if row.status != "completed":
        # Do not present last successful payload as the current completed scan.
        body["recommendations_final"] = False
    return body


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
    from ..services.strategies.ltm.identity import (
        DISPLAY_NAME as LTM_DISPLAY,
        SHORT_NAME as LTM_SHORT,
        STRATEGY_ID as LTM_ID,
    )
    from ..services.strategies.breakout52w.identity import (
        DISPLAY_NAME as W52_DISPLAY,
        SHORT_NAME as W52_SHORT,
        STRATEGY_ID as W52_ID,
    )

    return {
        "strategies": [
            {"id": "production", "display_name": "Production", "short_name": "PROD"},
            {"id": LTM_ID, "display_name": LTM_DISPLAY, "short_name": LTM_SHORT},
            {"id": W52_ID, "display_name": W52_DISPLAY, "short_name": W52_SHORT},
        ]
    }


@router.get("/ltm/latest")
async def get_ltm_latest(
    _: User = Depends(require_feature("advanced_scanner")),
):
    from ..services.strategies.ltm import persistence
    from ..services.strategies.ltm.identity import DISPLAY_NAME, STRATEGY_ID

    row = await persistence.load_latest(STRATEGY_ID)
    run = await persistence.get_run(row.scan_id) if row and row.scan_id else None
    if row is None:
        run = await persistence.find_active_run(mark_stale=False)
        if run is None:
            raise HTTPException(
                status_code=404,
                detail={"available": False, "message": "No LTM scan yet", "strategy_id": STRATEGY_ID},
            )
        row = SimpleNamespace(
            payload={},
            status=run.status,
            scan_id=run.scan_id,
            completed_at=None,
            started_at=run.started_at,
            error_code=run.error_code,
        )
    body = _strategy_latest_body(row, strategy_id=STRATEGY_ID, display_name=DISPLAY_NAME, run=run)
    if body.get("blotter") or body.get("recommendations"):
        from ..services.strategies.ltm.attribution import apply_windowed_attribution

        body = apply_windowed_attribution(body)
    return body


@router.post("/ltm/runs")
async def start_ltm_run(
    _: User = Depends(require_feature("advanced_scanner")),
    mode: str | None = Query(default=None),
    strategy_id: str | None = Query(default=None),
):
    from ..services.strategies.ltm.identity import STRATEGY_ID
    from ..services.strategies.ltm.scan_service import start_scan_background

    if strategy_id and strategy_id != STRATEGY_ID:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "STRATEGY_MISMATCH",
                "message": "This endpoint only runs Long-Term Buy & Hold Momentum.",
                "expected": STRATEGY_ID,
                "got": strategy_id,
            },
        )
    result = await start_scan_background(mode=mode)
    if result.get("error_code") == "LTM_SCAN_IN_PROGRESS":
        raise HTTPException(status_code=409, detail=result)
    result["strategy_id"] = STRATEGY_ID
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
    return _strategy_run_body(run)


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


@router.get("/w52/latest")
async def get_w52_latest(
    _: User = Depends(require_feature("advanced_scanner")),
    period: str = Query(default="3Y"),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
):
    from datetime import date as date_cls

    from ..services.strategies.breakout52w import persistence
    from ..services.strategies.breakout52w.identity import DISPLAY_NAME, STRATEGY_ID
    from ..services.strategies.breakout52w.period import PeriodRequestError
    from ..services.strategies.breakout52w.scan_service import is_scan_active_in_memory

    row = await persistence.load_latest(STRATEGY_ID)
    run = await persistence.get_run(row.scan_id) if row and row.scan_id else None

    # Check for stale/interrupted in-progress runs
    if row and row.status in ("queued", "evaluating", "backtesting", "publishing"):
        if not is_scan_active_in_memory(row.scan_id):
            active_run = await persistence.find_active_run(STRATEGY_ID, max_age_seconds=10, mark_stale=True)
            if active_run is None:
                row = await persistence.load_latest(STRATEGY_ID)
                run = await persistence.get_run(row.scan_id) if row and row.scan_id else None

    if row is None:
        run = await persistence.find_active_run(mark_stale=False)
        if run is None:
            raise HTTPException(
                status_code=404,
                detail={"available": False, "message": "No 52-Week High Breakout scan yet", "strategy_id": STRATEGY_ID},
            )
        row = SimpleNamespace(
            payload={},
            status=run.status,
            scan_id=run.scan_id,
            completed_at=None,
            started_at=run.started_at,
            error_code=run.error_code,
        )
    body = _strategy_latest_body(row, strategy_id=STRATEGY_ID, display_name=DISPLAY_NAME, run=run)
    start = None
    end = None
    try:
        if isinstance(start_date, str) and start_date:
            start = date_cls.fromisoformat(start_date[:10])
        if isinstance(end_date, str) and end_date:
            end = date_cls.fromisoformat(end_date[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail={"message": "start_date and end_date must be YYYY-MM-DD"})
    if body.get("blotter") or body.get("recommendations"):
        from ..services.strategies.breakout52w.attribution import apply_windowed_attribution

        try:
            body = apply_windowed_attribution(body, period=period, start=start, end=end)
        except PeriodRequestError as exc:
            raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc
        logger.info(
            "BACKTEST_REQUEST_ACCEPTED strategy=%s period=%s start_date=%s end_date=%s "
            "trade_count=%s cache_key=%s",
            STRATEGY_ID,
            body.get("attribution_window"),
            body.get("attribution_window_start"),
            body.get("attribution_window_end"),
            body.get("period_trade_count"),
            body.get("cache_key"),
        )
    return body


@router.post("/w52/runs")
async def start_w52_run(
    _: User = Depends(require_feature("advanced_scanner")),
    mode: str | None = Query(default=None),
    strategy_id: str | None = Query(default=None),
):
    from ..services.strategies.breakout52w.identity import STRATEGY_ID
    from ..services.strategies.breakout52w.scan_service import start_scan_background

    if strategy_id and strategy_id != STRATEGY_ID:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "STRATEGY_MISMATCH",
                "message": "This endpoint only runs 52-Week High Breakout.",
                "expected": STRATEGY_ID,
                "got": strategy_id,
            },
        )
    result = await start_scan_background(mode=mode)
    if result.get("error_code") == "W52_SCAN_IN_PROGRESS":
        raise HTTPException(status_code=409, detail=result)
    result["strategy_id"] = STRATEGY_ID
    return result


@router.get("/w52/runs/{scan_id}")
async def get_w52_run(
    scan_id: uuid.UUID,
    _: User = Depends(require_feature("advanced_scanner")),
):
    from ..services.strategies.breakout52w import persistence
    from ..services.strategies.breakout52w.identity import STRATEGY_ID
    from ..services.strategies.breakout52w.scan_service import is_scan_active_in_memory

    run = await persistence.get_run(scan_id)
    if not run:
        raise HTTPException(status_code=404, detail={"message": "Scan run not found"})
    if run.status in ("queued", "evaluating", "backtesting", "publishing") and not is_scan_active_in_memory(scan_id):
        await persistence.find_active_run(STRATEGY_ID, max_age_seconds=10, mark_stale=True)
        run = await persistence.get_run(scan_id) or run
    return _strategy_run_body(run)


@router.get("/w52/performance/{symbol}")
async def get_w52_symbol_performance(
    symbol: str,
    window: str | None = Query(default=None),
    _: User = Depends(require_feature("advanced_scanner")),
):
    from ..services.strategies.breakout52w.performance_store import (
        get_symbol_performance,
        list_symbol_performance,
        row_to_dict,
        strategy_tester_payload,
    )

    if window:
        row = await get_symbol_performance(symbol, window.upper())
        rows = [row] if row is not None else []
    else:
        rows = await list_symbol_performance(symbol)
    if not rows:
        raise HTTPException(
            status_code=404,
            detail={"message": "No stored 52-Week High Breakout tester metrics for this symbol"},
        )
    windows = []
    for row in rows:
        item = row_to_dict(row)
        item.pop("trades", None)
        windows.append(
            {
                "window": item.get("window"),
                "period_start": item.get("period_start"),
                "period_end": item.get("period_end"),
                "status": item.get("status"),
                "strategy_tester": strategy_tester_payload(item),
                **{k: item.get(k) for k in (
                    "total_pnl",
                    "max_drawdown",
                    "total_trades",
                    "profitable_trades",
                    "losing_trades",
                    "breakeven",
                    "profit_factor",
                    "gross_profit",
                    "gross_loss",
                    "commission",
                    "expected_payoff",
                    "largest_profit",
                    "largest_loss",
                    "average_winning_trade",
                    "average_losing_trade",
                    "outlier_pnl",
                )},
                "computed_at": item.get("computed_at"),
            }
        )
    return {"strategy_id": rows[0].strategy_id, "symbol": rows[0].symbol, "windows": windows}


@router.get("/w52/symbols/{symbol}")
async def get_w52_symbol(
    symbol: str,
    window: str = Query(default="3Y"),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    execution_profile: str | None = Query(default=None),
    historical_fill_mode: str | None = Query(default=None),
    refresh: bool = Query(default=False),
    _: User = Depends(require_feature("advanced_scanner")),
):
    from datetime import date as date_cls

    from ..services.strategies.breakout52w import persistence
    from ..services.strategies.breakout52w.analytics import parse_window
    from ..services.strategies.breakout52w.identity import STRATEGY_ID
    from ..services.strategies.breakout52w.window_backtest import run_symbol_window_backtest

    row = await persistence.load_latest(STRATEGY_ID)
    payload = row.payload if (row and row.payload) else {}
    recs = payload.get("recommendations") or []
    match = next((r for r in recs if str(r.get("symbol", "")).upper() == symbol.upper()), None)
    if not match:
        match = {"symbol": symbol.upper(), "signal": "WATCH", "technicals": {}}
    eval_raw = payload.get("evaluation_date")
    try:
        asof = date_cls.fromisoformat(str(eval_raw)[:10]) if eval_raw else date_cls.today()
    except ValueError:
        asof = date_cls.today()
    metrics = payload.get("book_metrics") if isinstance(payload.get("book_metrics"), dict) else {}
    start = None
    end = None
    try:
        if isinstance(start_date, str) and start_date:
            start = date_cls.fromisoformat(start_date[:10])
        if isinstance(end_date, str) and end_date:
            end = date_cls.fromisoformat(end_date[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail={"message": "start_date and end_date must be YYYY-MM-DD"})
    from ..services.strategies.breakout52w.identity import ATTRIBUTION_PERIODS
    from ..services.strategies.breakout52w.period import PeriodRequestError
    from ..services.strategies.breakout52w.performance_store import load_stored_dashboard, persist_dashboard

    raw_win = str(window or "3Y").upper()
    allowed = set(ATTRIBUTION_PERIODS) | {"1Y", "3Y", "5Y", "8Y", "ALL", "CUSTOM"}
    win = raw_win if raw_win in allowed else parse_window(window)
    if start and end and raw_win == "CUSTOM":
        win = "CUSTOM"
    profile = (execution_profile or "KERNEL").strip().upper()
    if profile in {"TV_TEST", "TEST_TAPE"}:
        profile = "TV_TESTER"
    from ..services.strategies.breakout52w.execution import TV_TESTER_CAPITAL

    capital = float(payload.get("initial_capital") or metrics.get("initial_capital") or 100000)
    if profile == "TV_TESTER":
        capital = float(TV_TESTER_CAPITAL)
    dashboard = None
    if win != "CUSTOM" and not refresh and not start and not end:
        dashboard = await load_stored_dashboard(
            match["symbol"],
            win,
            signal=match.get("signal"),
            technicals=match.get("technicals"),
            asof=asof,
            execution_profile=profile,
        )
        stored_profile = str(((dashboard or {}).get("execution") or {}).get("profile") or "KERNEL").upper()
        if dashboard is not None and stored_profile != profile:
            dashboard = None
    try:
        if dashboard is None:
            dashboard = await run_symbol_window_backtest(
                match["symbol"],
                win,
                asof=asof,
                start=start,
                end=end,
                initial_capital=capital,
                signal=match.get("signal"),
                technicals=match.get("technicals"),
                execution_profile=profile,
                historical_fill_mode=historical_fill_mode,
            )
            if win != "CUSTOM":
                try:
                    await persist_dashboard(dashboard)
                except Exception:
                    logger.exception("W52_PERF_PERSIST_FAILED symbol=%s window=%s", match["symbol"], win)
    except PeriodRequestError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc
    return {
        "strategy_id": STRATEGY_ID,
        "symbol": match["symbol"],
        "window": dashboard["window"],
        "technicals": match.get("technicals"),
        "backtest": None,
        "dashboard": dashboard,
        "equity_curve": dashboard.get("equity_curve") or [],
        "signal": match.get("signal"),
        "limitations": payload.get("limitations"),
        "coverage": dashboard.get("coverage"),
        "replay_kind": dashboard.get("replay_kind") or "symbol_window",
        "data_hash": dashboard.get("data_hash"),
        "persisted": bool(dashboard.get("persisted")),
        "strategy_tester": dashboard.get("strategy_tester"),
    }


