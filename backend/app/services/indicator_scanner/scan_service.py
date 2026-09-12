"""Server-side indicator scan over the configured NSE universe."""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import uuid
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from typing import Any

from ...config.settings import settings
from ..strategy_tester.indicators import BarSeries
from ..strategy_tester.scan_service import (
    ensure_universe_market_data,
    load_universe,
    prepare_scan_market_data,
)
from .compiler import CompiledIndicator, compile_source
from .evaluator import BarData, EvalResult, evaluate_indicator
from .filters import row_matches, validate_filters
from .limits import DEFAULT_UNIVERSE_ID, HISTORY_BUFFER_BARS, SCAN_CONCURRENCY, SCAN_RATE_LIMIT_PER_MINUTE
from . import persistence
from .symbols import map_benchmark_symbol, normalize_timeframe

logger = logging.getLogger("app.indicator_scanner")

_cancel_requested: set[uuid.UUID] = set()
_active_scans: set[uuid.UUID] = set()
_rate: dict[str, deque[float]] = defaultdict(deque)
_PROGRESS_EVERY = 12


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def request_cancel(run_id: uuid.UUID) -> None:
    _cancel_requested.add(run_id)


def check_rate_limit(user_id: uuid.UUID | None) -> bool:
    key = str(user_id or "anon")
    now = _utc().timestamp()
    bucket = _rate[key]
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= SCAN_RATE_LIMIT_PER_MINUTE:
        return False
    bucket.append(now)
    return True


def _ist_today() -> date:
    return datetime.now(timezone(timedelta(hours=5, minutes=30))).date()


def indicator_end_date(scan_date: date | None) -> date:
    """Pin the 1D evaluation bar. Honor an explicit as-of (e.g. TradingView 28 Aug)."""
    try:
        from ...services.market_data_ingestion.calendar_utils import expected_last_completed_session

        last = expected_last_completed_session()
    except Exception:
        last = _ist_today()
    if scan_date is None:
        return last
    if scan_date > last:
        return last
    return scan_date


def clip_series_to(series: BarSeries | None, end: date) -> BarSeries | None:
    if series is None or not series.dates:
        return None
    idx = series.index_on_or_before(end)
    if idx is None:
        return None
    n = idx + 1
    return BarSeries(
        dates=list(series.dates[:n]),
        open=list(series.open[:n]),
        high=list(series.high[:n]),
        low=list(series.low[:n]),
        close=list(series.close[:n]),
        volume=list(series.volume[:n]),
    )


def bars_from_series(series: BarSeries | None) -> BarData | None:
    if series is None or not series.dates:
        return None
    return BarData(
        dates=list(series.dates),
        open=list(series.open),
        high=list(series.high),
        low=list(series.low),
        close=list(series.close),
        volume=list(series.volume),
    )


def public_error(exc: Exception) -> str:
    text = str(exc)
    if "traceback" in text.lower() or "file \"" in text.lower():
        return "Scan failed while calculating the indicator."
    return text[:400]


def scan_status_payload(run) -> dict[str, Any]:
    elapsed = None
    if run.started_at:
        end = run.completed_at or run.cancelled_at or _utc()
        started = run.started_at if run.started_at.tzinfo else run.started_at.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        elapsed = max(0, int((end - started).total_seconds()))
    summary = run.summary if isinstance(run.summary, dict) else {}
    return {
        "id": str(run.id),
        "scan_id": run.public_scan_id,
        "indicator_id": str(run.indicator_id) if run.indicator_id else None,
        "indicator_name": run.indicator_name,
        "universe": run.universe,
        "universe_size": run.universe_size,
        "universe_label": f"{run.universe_size} Stocks" if run.universe_size else "755 Stocks",
        "timeframe": run.timeframe,
        "status": run.status,
        "stage": run.stage,
        "progress_pct": run.progress_pct,
        "processed_count": run.processed_count,
        "total_count": run.total_count,
        "success_count": run.success_count,
        "failed_count": run.failed_count,
        "skipped_count": run.skipped_count,
        "matched_count": run.matched_count,
        "as_of": run.as_of,
        "benchmark_symbol": run.benchmark_symbol,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "elapsed_seconds": elapsed,
        "error_code": run.error_code,
        "error_detail": run.error_detail,
        "summary": summary,
        "outputs": (run.indicator_snapshot or {}).get("outputs") or [],
        "filters": run.filters or [],
    }


async def start_scan_background(
    *,
    user_id: uuid.UUID | None,
    compiled: CompiledIndicator,
    indicator_id: uuid.UUID | None,
    universe_id: str,
    timeframe: str,
    filters: list[dict[str, Any]],
    sort: dict[str, Any] | None,
    input_overrides: dict[str, Any] | None,
    scan_date: date | None,
) -> dict[str, Any]:
    active = await persistence.find_active_scan(user_id)
    if active:
        started = active.started_at
        if started is not None and started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        age = (_utc() - started).total_seconds() if started else 0
        processed = int(getattr(active, "processed_count", 0) or 0)
        orphaned = active.id not in _active_scans and age > 20
        idle_hung = processed == 0 and age > 30
        if orphaned or idle_hung:
            request_cancel(active.id)
            await persistence.update_scan(
                active.id,
                status="failed",
                stage="failed",
                error_code="SCAN_INTERRUPTED",
                error_detail="Previous scan was interrupted. Start a new scan.",
                completed_at=_utc(),
            )
        else:
            return {
                "error_code": "INDICATOR_SCAN_IN_PROGRESS",
                "scan_id": active.public_scan_id,
                "id": str(active.id),
                "status": active.status,
            }
    if not check_rate_limit(user_id):
        return {
            "error_code": "RATE_LIMITED",
            "message": "Too many scans. Wait a minute before starting another scan.",
        }
    instruments = await load_universe("ALL_755")
    public_id = await persistence.next_public_scan_id()
    snapshot = compiled.to_definition_json()
    snapshot["source_code"] = compiled.source
    snapshot["input_overrides"] = input_overrides or {}
    bench = compiled.required_symbols[0] if compiled.required_symbols else None
    run = await persistence.create_scan(
        user_id=user_id,
        public_scan_id=public_id,
        indicator_id=indicator_id,
        indicator_name=compiled.title,
        indicator_snapshot=snapshot,
        universe=universe_id or DEFAULT_UNIVERSE_ID,
        universe_size=len(instruments),
        timeframe=normalize_timeframe(timeframe),
        filters=filters,
        sort=sort,
        input_overrides=input_overrides,
        scan_date=scan_date.isoformat() if scan_date else None,
        benchmark_symbol=bench,
    )
    if indicator_id:
        await persistence.touch_last_used(indicator_id)
    asyncio.create_task(
        _runner(run.id, compiled, instruments, filters, input_overrides, scan_date)
    )
    return scan_status_payload(run)


async def _runner(
    run_id: uuid.UUID,
    compiled: CompiledIndicator,
    instruments: list[dict[str, str | None]],
    filters: list[dict[str, Any]],
    input_overrides: dict[str, Any] | None,
    scan_date: date | None,
) -> None:
    _active_scans.add(run_id)
    try:
        await execute_scan(
            run_id=run_id,
            compiled=compiled,
            instruments=instruments,
            filters=filters,
            input_overrides=input_overrides,
            scan_date=scan_date,
        )
    except Exception as exc:
        logger.exception("Indicator scan failed | run_id=%s | err=%s", run_id, exc)
        await persistence.update_scan(
            run_id,
            status="failed",
            stage="failed",
            error_code="INDICATOR_SCAN_FAILED",
            error_detail=public_error(exc),
            completed_at=_utc(),
            progress_pct=100,
        )
    finally:
        _active_scans.discard(run_id)
        _cancel_requested.discard(run_id)


async def execute_scan(
    *,
    run_id: uuid.UUID,
    compiled: CompiledIndicator,
    instruments: list[dict[str, str | None]],
    filters: list[dict[str, Any]],
    input_overrides: dict[str, Any] | None,
    scan_date: date | None,
) -> None:
    total = len(instruments)
    await persistence.update_scan(
        run_id,
        status="running",
        stage="preparing",
        total_count=total,
        processed_count=0,
        progress_pct=0,
    )
    if run_id in _cancel_requested:
        await _mark_cancelled(run_id)
        return

    end_date = indicator_end_date(scan_date)
    logger.info("INDICATOR_SCAN_AS_OF | run_id=%s | scan_date=%s | end_date=%s", run_id, scan_date, end_date)
    warmup = max(compiled.required_bars, HISTORY_BUFFER_BARS)
    from_date = end_date - timedelta(days=max(warmup * 2, 420))
    symbols = [str(item["symbol"]) for item in instruments if item.get("symbol")]
    store_symbols = [str(item.get("store_symbol") or item["symbol"]) for item in instruments if item.get("symbol")]
    company_map = {str(item["symbol"]): item.get("company") for item in instruments}

    await persistence.update_scan(run_id, stage="loading_benchmark")
    try:
        ensure_result = await asyncio.wait_for(ensure_universe_market_data(store_symbols), timeout=12)
    except asyncio.TimeoutError:
        ensure_result = {"status": "TIMEOUT"}
        logger.warning("INDICATOR_SCAN_ENSURE_TIMEOUT | run_id=%s", run_id)
    logger.info(
        "INDICATOR_SCAN_MARKET_DATA | run_id=%s | status=%s | universe=%s",
        run_id,
        ensure_result.get("status"),
        len(symbols),
    )
    if run_id in _cancel_requested:
        await _mark_cancelled(run_id)
        return

    await persistence.update_scan(run_id, stage="loading_market_data")
    need_benchmark = bool(compiled.required_symbols)
    series_by_symbol, benchmark_series, data_source = await prepare_scan_market_data(
        symbols,
        from_date=from_date,
        to_date=end_date,
        need_benchmark=need_benchmark,
    )
    if run_id in _cancel_requested:
        await _mark_cancelled(run_id)
        return
    clipped: dict[str, BarSeries] = {}
    for symbol, series in series_by_symbol.items():
        cut = clip_series_to(series, end_date)
        if cut is not None:
            clipped[symbol] = cut
    series_by_symbol = clipped
    benchmark_series = clip_series_to(benchmark_series, end_date)

    benchmark_map: dict[str, BarData] = {}
    bench_bars = bars_from_series(benchmark_series)
    if bench_bars is not None:
        aliases = set(compiled.required_symbols)
        aliases.add(map_benchmark_symbol(next(iter(compiled.required_symbols), "NSE:CNX500")))
        aliases.add("NSE:CNX500")
        aliases.add("NIFTY500")
        aliases.add(str(getattr(settings, "strategy_index_store_symbol", None) or "NIFTY500"))
        for alias in aliases:
            if alias:
                benchmark_map[alias] = bench_bars
                benchmark_map[alias.upper()] = bench_bars

    await persistence.update_scan(run_id, stage="scanning")
    sem = asyncio.Semaphore(SCAN_CONCURRENCY)
    results: list[dict[str, Any]] = []
    success = failed = skipped = matched = 0
    as_of_counts: dict[str, int] = {}

    async def _one(index: int, symbol: str) -> dict[str, Any]:
        async with sem:
            series = series_by_symbol.get(symbol)
            bars = bars_from_series(series)
            if bars is None:
                return {
                    "symbol": symbol,
                    "display_name": company_map.get(symbol),
                    "exchange": "NSE",
                    "timeframe": "1D",
                    "status": "insufficient_history",
                    "matched": False,
                    "outputs": {},
                    "ohlcv": {},
                    "error_detail": "No daily OHLCV available.",
                    "bar_count": 0,
                }
            eval_result = await asyncio.to_thread(
                evaluate_indicator,
                compiled,
                bars,
                benchmark_by_symbol=benchmark_map,
                input_overrides=input_overrides,
            )
            return _row_from_eval(symbol, company_map.get(symbol), eval_result, filters)

    pending: list[asyncio.Task] = []
    for index, symbol in enumerate(symbols, start=1):
        if run_id in _cancel_requested:
            for task in pending:
                task.cancel()
            await _mark_cancelled(run_id, processed_count=index - 1, total_count=total)
            return
        pending.append(asyncio.create_task(_one(index, symbol)))
        if len(pending) >= SCAN_CONCURRENCY or index == total:
            chunk = await asyncio.gather(*pending, return_exceptions=True)
            pending = []
            for item in chunk:
                if isinstance(item, Exception):
                    logger.warning("Indicator symbol failed | err=%s", item)
                    failed += 1
                    continue
                results.append(item)
                if item["status"] == "ok":
                    success += 1
                elif item["status"] == "insufficient_history":
                    skipped += 1
                else:
                    failed += 1
                if item.get("matched"):
                    matched += 1
                if item.get("as_of"):
                    as_of_counts[item["as_of"]] = as_of_counts.get(item["as_of"], 0) + 1
            processed = len(results)
            await persistence.update_scan(
                run_id,
                status="running",
                stage="scanning",
                processed_count=processed,
                total_count=total,
                progress_pct=int(processed / total * 100) if total else 100,
                success_count=success,
                failed_count=failed,
                skipped_count=skipped,
                matched_count=matched,
            )

    await persistence.update_scan(run_id, stage="applying_filters", progress_pct=99)
    await persistence.save_results(run_id, results)
    as_of = max(as_of_counts, key=as_of_counts.get) if as_of_counts else None  # type: ignore[arg-type]
    summary = {
        "universe_size": total,
        "scanned": len(results),
        "success": success,
        "failed": failed,
        "skipped": skipped,
        "matched": matched,
        "as_of": as_of,
        "data_source": data_source,
        "required_bars": compiled.required_bars,
        "benchmark_symbol": compiled.required_symbols[0] if compiled.required_symbols else None,
        "scan_date_counts": as_of_counts,
        "disclaimer": "For research and paper-trading only. Not investment advice.",
    }
    await persistence.update_scan(
        run_id,
        status="completed",
        stage="completed",
        processed_count=total,
        total_count=total,
        progress_pct=100,
        success_count=success,
        failed_count=failed,
        skipped_count=skipped,
        matched_count=matched,
        as_of=as_of,
        summary=summary,
        completed_at=_utc(),
        error_code=None,
        error_detail=None,
    )


def _row_from_eval(
    symbol: str,
    company: str | None,
    result: EvalResult,
    filters: list[dict[str, Any]],
) -> dict[str, Any]:
    matched = False
    if result.status == "ok":
        matched = row_matches(result.outputs, filters) if filters else True
    return {
        "symbol": symbol,
        "display_name": company,
        "exchange": "NSE",
        "timeframe": "1D",
        "as_of": result.as_of.isoformat() if result.as_of else None,
        "status": result.status,
        "matched": matched,
        "outputs": result.outputs,
        "ohlcv": result.ohlcv,
        "error_detail": result.error_detail,
        "bar_count": result.bar_count,
    }


async def _mark_cancelled(run_id: uuid.UUID, processed_count: int = 0, total_count: int = 0) -> None:
    await persistence.update_scan(
        run_id,
        status="cancelled",
        stage="cancelled",
        processed_count=processed_count,
        total_count=total_count,
        cancelled_at=_utc(),
        completed_at=_utc(),
        progress_pct=int(processed_count / total_count * 100) if total_count else 0,
    )


def paginate_results(
    rows: list[Any],
    *,
    page: int,
    page_size: int,
    search: str | None,
    matched_only: bool,
    sort_field: str | None,
    sort_dir: str,
    output_names: list[str],
) -> tuple[list[dict[str, Any]], int]:
    items: list[dict[str, Any]] = []
    needle = (search or "").strip().upper()
    for row in rows:
        if matched_only and not row.matched:
            continue
        if needle and needle not in (row.symbol or "").upper() and needle not in (row.display_name or "").upper():
            continue
        items.append(result_payload(row))
    field = sort_field or "symbol"

    def key(item: dict[str, Any]):
        if field in {"symbol", "display_name", "as_of", "status"}:
            return str(item.get(field) or "")
        outputs = item.get("outputs") or {}
        if field in outputs:
            value = outputs[field]
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, (int, float)):
                return float(value)
            return str(value or "")
        ohlcv = item.get("ohlcv") or {}
        if field in ohlcv and isinstance(ohlcv[field], (int, float)):
            return float(ohlcv[field])
        return 0

    reverse = (sort_dir or "desc").lower() != "asc"
    items.sort(key=key, reverse=reverse)
    total = len(items)
    start = max(0, (page - 1) * page_size)
    return items[start : start + page_size], total


def result_payload(row) -> dict[str, Any]:
    return {
        "symbol": row.symbol,
        "display_name": row.display_name,
        "exchange": row.exchange,
        "timeframe": row.timeframe,
        "as_of": row.as_of,
        "status": row.status,
        "matched": row.matched,
        "outputs": row.outputs or {},
        "ohlcv": row.ohlcv or {},
        "error_detail": row.error_detail,
        "bar_count": row.bar_count,
    }


def results_to_csv(rows: list[dict[str, Any]], output_names: list[str]) -> str:
    buf = io.StringIO()
    headers = ["symbol", "display_name", "exchange", "as_of", "status", "matched"] + output_names + ["open", "high", "low", "close", "volume"]
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        item = {
            "symbol": row.get("symbol"),
            "display_name": row.get("display_name"),
            "exchange": row.get("exchange"),
            "as_of": row.get("as_of"),
            "status": row.get("status"),
            "matched": 1 if row.get("matched") else 0,
        }
        outputs = row.get("outputs") or {}
        for name in output_names:
            value = outputs.get(name)
            if isinstance(value, bool):
                item[name] = 1 if value else 0
            else:
                item[name] = value
        ohlcv = row.get("ohlcv") or {}
        item.update({k: ohlcv.get(k) for k in ("open", "high", "low", "close", "volume")})
        writer.writerow(item)
    return buf.getvalue()


def compile_or_raise(source: str) -> CompiledIndicator:
    return compile_source(source)
