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
    load_bar_series,
    load_universe,
    prepare_scan_market_data,
)
from ..universe_csv import is_dummy_universe_symbol
from .compiler import CompiledIndicator, compile_source
from .entry_conditions import (
    CONDITIONS_OUTPUT_KEY,
    all_required_conditions_passed,
    attach_entry_conditions,
    conditions_for_detail,
    entry_condition_defs,
    is_aggregate_signal_filter,
    usable_condition_rows,
)
from .scan_analytics import (
    RETURN_OUTPUT_KEY,
    build_indicator_scan_analytics,
    row_return_pct,
    row_signal,
    signal_sort_rank,
)
from .evaluator import BarData, EvalResult, evaluate_indicator
from .filters import row_matches, validate_filters
from .limits import DEFAULT_UNIVERSE_ID, HISTORY_BUFFER_BARS, SCAN_CONCURRENCY, SCAN_RATE_LIMIT_PER_MINUTE
from .scan_data_quality import validate_and_sanitize_universe
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


def current_scan_session(now: datetime | None = None) -> date:
    """Scanner as-of date: IST trading day from midnight, else last completed session."""
    try:
        from ..trading_hours_service import TradingHoursService, trading_hours

        th = trading_hours if trading_hours is not None else TradingHoursService()
        ist = th._to_ist(now)
        if th.is_trading_day(ist):
            return ist.date()
    except Exception:
        logger.warning("INDICATOR_SCAN_SESSION_TODAY_FAILED", exc_info=True)

    try:
        from ...services.market_data_ingestion.calendar_utils import expected_last_completed_session

        return expected_last_completed_session(now)
    except Exception:
        return _ist_today()


def pine_screener_bar(now: datetime | None = None) -> date:
    """1D session TradingView Pine Screener evaluates.

    After 09:15 IST on a cash session this is *today* (forming candle).
    Before open / on weekends / holidays it is the last completed session.
    """
    try:
        from ..strategies.breakout52w.session_overlay import should_overlay_session

        live_today = should_overlay_session([], now)
        if live_today is not None:
            return live_today
    except Exception:
        logger.warning("INDICATOR_SCAN_OVERLAY_SESSION_FAILED", exc_info=True)

    try:
        from ..trading_hours_service import OPEN_TIME, TradingHoursService, trading_hours

        th = trading_hours if trading_hours is not None else TradingHoursService()
        ist = th._to_ist(now)
        if th.is_trading_day(ist) and ist.time() >= OPEN_TIME:
            return ist.date()
    except Exception:
        logger.warning("INDICATOR_SCAN_TRADING_HOURS_FAILED", exc_info=True)

    try:
        from ...services.market_data_ingestion.calendar_utils import expected_last_completed_session

        return expected_last_completed_session(now)
    except Exception:
        return _ist_today()


def indicator_end_date(scan_date: date | None, now: datetime | None = None) -> date:
    """Last 1D NSE session on or before the requested as-of date.

    Today on a trading day is offered from midnight IST (the scanner date picker).
    Weekends and holidays clamp to the last completed cash session.
    Historical dates on or before that cap are honored.
    """
    effective_current = current_scan_session(now)
    if scan_date is None or scan_date > effective_current:
        return effective_current
    return scan_date


def resolve_available_scan_end(
    requested_end: date,
    series_by_symbol: dict[str, Any],
    *,
    min_coverage: float = 0.05,
) -> tuple[date, str | None]:
    """Use the last stored 1D session when the requested bar is missing for (almost) everyone.

    After 09:15 IST the scanner prefers today's forming candle. If live overlay / EOD
    load did not produce that bar, evaluating it would skip the whole universe and
    look like a broken scan. Fall back to the latest stored session instead.
    """
    dated = [s.dates[-1] for s in series_by_symbol.values() if s is not None and getattr(s, "dates", None)]
    if not dated:
        return requested_end, None
    have_target = sum(1 for day in dated if day >= requested_end)
    if have_target / len(dated) >= min_coverage:
        return requested_end, None
    latest = max(dated)
    if latest >= requested_end:
        return requested_end, None
    note = (
        f"Requested scan bar {requested_end.isoformat()} is not in daily OHLCV "
        f"(latest stored session {latest.isoformat()}). "
        "Evaluating the last available 1D session so the scan is not empty."
    )
    return latest, note


def last_bar_covers_scan(last_bar: date, end_date: date, now: datetime | None = None) -> bool:
    """True when the latest stored bar can be evaluated for `end_date`.

    Before 09:15 IST the forming 1D candle does not exist yet, so yesterday's
    completed session is the correct tape. After open, names missing today's
    bar are skipped so the scan does not mix sessions.
    """
    if last_bar >= end_date:
        return True
    try:
        from ..trading_hours_service import OPEN_TIME, TradingHoursService, trading_hours
        from ...services.market_data_ingestion.calendar_utils import expected_last_completed_session

        th = trading_hours if trading_hours is not None else TradingHoursService()
        ist = th._to_ist(now)
        if not (end_date == ist.date() and th.is_trading_day(ist) and ist.time() < OPEN_TIME):
            return False
        return last_bar >= expected_last_completed_session(now)
    except Exception:
        return False


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


CURRENT_DATA_FETCH_TIMEOUT_S = 45.0
ENSURE_TIMEOUT_S = 20.0
REPAIR_TIMEOUT_S = 40.0


def _ensure_target_date(end_date: date) -> date:
    """EOD store target: last completed session, unless the scan is historical."""
    try:
        from ...services.market_data_ingestion.calendar_utils import expected_last_completed_session

        completed = expected_last_completed_session()
        if end_date > completed:
            return completed
        return end_date
    except Exception:
        return end_date


async def fetch_current_indicator_market_data(
    symbols: list[str],
    store_symbols: list[str],
    *,
    from_date: date,
    end_date: date,
    need_benchmark: bool,
    min_bars: int,
) -> tuple[dict[str, BarSeries], BarSeries | None, str, dict[str, Any]]:
    """Fetch latest EOD + the Pine Screener 1D bar, then return series ready to scan.

    One live-quote overlay only. A second FYERS quote pass on 755 names was doubling
    scan time (the 6-minute runs) without changing the last 1D bar.
    """
    from ...services.market_data_ingestion.session_repair import repair_scan_market_history

    report: dict[str, Any] = {}
    try:
        report["ensure"] = await ensure_universe_market_data(
            store_symbols or symbols,
            target_date=_ensure_target_date(end_date),
            max_duration_s=ENSURE_TIMEOUT_S,
        )
    except Exception as exc:
        report["ensure"] = {"status": "FAILED", "error": type(exc).__name__}
        logger.warning("INDICATOR_SCAN_ENSURE_FAILED | err=%s", type(exc).__name__)

    try:
        report["repair"] = await asyncio.wait_for(
            repair_scan_market_history(
                store_symbols or symbols,
                end=end_date,
                min_bars=max(min_bars, 253),
                skip_thin=True,
            ),
            timeout=REPAIR_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        report["repair"] = {"error": "timeout"}
        logger.warning("INDICATOR_SCAN_REPAIR_TIMEOUT")
    except Exception as exc:
        report["repair"] = {"error": type(exc).__name__}
        logger.warning("INDICATOR_SCAN_REPAIR_FAILED | err=%s", type(exc).__name__)

    series_by_symbol, benchmark_series, data_source = await prepare_scan_market_data(
        symbols,
        from_date=from_date,
        to_date=end_date,
        need_benchmark=need_benchmark,
        fill_timeout_s=CURRENT_DATA_FETCH_TIMEOUT_S,
        overlay_live=True,
    )
    report["data_source"] = data_source
    return series_by_symbol, benchmark_series, data_source, report


def public_error(exc: Exception) -> str:
    text = str(exc)
    if "traceback" in text.lower() or "file \"" in text.lower():
        return "Scan failed while calculating the indicator."
    return text[:400]


async def ensure_summary_analytics(run):
    """Fill Top 5 / funnel stats for completed runs that were stored before analytics existed."""
    summary = dict(run.summary or {}) if isinstance(getattr(run, "summary", None), dict) else {}
    if getattr(run, "status", None) != "completed":
        return run
    if summary.get("top_positive") and summary.get("top_negative"):
        return run
    rows = await persistence.list_results(run.id)
    raw = [
        {
            "symbol": row.symbol,
            "display_name": row.display_name,
            "status": row.status,
            "matched": row.matched,
            "outputs": row.outputs or {},
            "ohlcv": row.ohlcv or {},
        }
        for row in rows
    ]
    snapshot = run.indicator_snapshot if isinstance(getattr(run, "indicator_snapshot", None), dict) else {}
    defs = snapshot.get("entry_conditions") if isinstance(snapshot.get("entry_conditions"), list) else None
    analytics = build_indicator_scan_analytics(
        raw,
        universe_size=int(getattr(run, "universe_size", 0) or len(raw)),
        condition_defs=defs,
    )
    summary.update(analytics)
    updated = await persistence.update_scan(run.id, summary=summary)
    return updated or run


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
        "entry_conditions": (run.indicator_snapshot or {}).get("entry_conditions") or [],
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
        if active.id in _active_scans:
            return {
                "error_code": "INDICATOR_SCAN_IN_PROGRESS",
                "scan_id": active.public_scan_id,
                "id": str(active.id),
                "status": active.status,
            }
        # Only declare orphaned/interrupted if the scan task is NOT running in this server process
        if active.id not in _active_scans and age > 120:
        # Only declare orphaned/interrupted if the scan has exceeded 10 minutes (600s)
        if active.id not in _active_scans and age > 600:
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
    snapshot = attach_entry_conditions(compiled.to_definition_json(), compiled)
    snapshot["source_code"] = compiled.source
    snapshot["input_overrides"] = input_overrides or {}
    snapshot["entry_conditions"] = snapshot.get("entry_conditions") or entry_condition_defs(compiled)
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

    requested_date = scan_date
    end_date = indicator_end_date(scan_date)
    pine_target = end_date
    logger.info("INDICATOR_SCAN_AS_OF | run_id=%s | scan_date=%s | end_date=%s", run_id, scan_date, end_date)
    from ...services.market_data_ingestion.nse_sessions import (
        is_nse_cash_session,
        nth_session_ending,
        nse_session_dates,
        session_on_or_before,
    )

    # session_on_or_before must not rewind today's live cash session to yesterday.
    if not is_nse_cash_session(end_date):
        end_date = session_on_or_before(end_date)
    needed = max(int(compiled.required_bars or 1), HISTORY_BUFFER_BARS)
    from_date = nth_session_ending(end_date, needed)
    instruments = [
        item
        for item in instruments
        if item.get("symbol") and not is_dummy_universe_symbol(str(item.get("symbol")))
    ]
    total = len(instruments)
    await persistence.update_scan(run_id, total_count=total, universe_size=total)
    symbols = [str(item["symbol"]) for item in instruments if item.get("symbol")]
    store_symbols = [str(item.get("store_symbol") or item["symbol"]) for item in instruments if item.get("symbol")]
    company_map = {str(item["symbol"]): item.get("company") for item in instruments}

    await persistence.update_scan(run_id, stage="fetching_current_data", progress_pct=2)
    need_benchmark = bool(compiled.required_symbols)
    series_by_symbol, benchmark_series, data_source, fetch_report = await fetch_current_indicator_market_data(
        symbols,
        store_symbols,
        from_date=from_date,
        end_date=end_date,
        need_benchmark=need_benchmark,
        min_bars=max(int(compiled.required_bars or 1), 1),
    )
    ensure_result = fetch_report.get("ensure") if isinstance(fetch_report.get("ensure"), dict) else {}
    repair_report = fetch_report.get("repair") if isinstance(fetch_report.get("repair"), dict) else {}
    logger.info(
        "INDICATOR_SCAN_MARKET_DATA | run_id=%s | status=%s | universe=%s | source=%s",
        run_id,
        ensure_result.get("status"),
        len(symbols),
        data_source,
    )
    if run_id in _cancel_requested:
        await _mark_cancelled(run_id)
        return
    fallback_note: str | None
    resolved_end, fallback_note = resolve_available_scan_end(end_date, series_by_symbol)
    if resolved_end != end_date:
        logger.warning(
            "INDICATOR_SCAN_FALLBACK_AS_OF | run_id=%s | requested=%s | available=%s",
            run_id,
            end_date,
            resolved_end,
        )
        end_date = resolved_end
        from_date = nth_session_ending(end_date, needed)
    max_available_date = max(
        (s.dates[-1] for s in series_by_symbol.values() if s is not None and s.dates),
        default=None,
    )
    if max_available_date is None or max_available_date < end_date:
        logger.warning(
            "INDICATOR_SCAN_TARGET_BAR_MISSING | target_end=%s latest_stored=%s — names without this bar skip",
            end_date,
            max_available_date,
        )
    clipped: dict[str, BarSeries] = {}
    for symbol, series in series_by_symbol.items():
        cut = clip_series_to(series, end_date)
        if cut is not None:
            clipped[symbol] = cut
    series_by_symbol = clipped
    benchmark_series = clip_series_to(benchmark_series, end_date)
    session_dates = nse_session_dates(
        from_date,
        end_date,
        index_dates=benchmark_series.dates if benchmark_series is not None else None,
    )
    # Index tape often lacks today's forming 1D bar. If we drop it here, live overlay
    # is stripped and every name is evaluated on yesterday — the 89 vs 108 mismatch.
    if is_nse_cash_session(end_date):
        session_dates = set(session_dates or [])
        session_dates.add(end_date)
    series_by_symbol, benchmark_series, quality = validate_and_sanitize_universe(
        series_by_symbol,
        end_session=end_date,
        session_dates=session_dates or None,
        min_bars=max(int(compiled.required_bars or 1), 1),
        benchmark=benchmark_series,
    )
    ca_symbols = list(dict.fromkeys(str(item.get("symbol")) for item in quality.split_like if item.get("symbol")))
    live_session = is_nse_cash_session(end_date)
    if ca_symbols and not live_session:
        from ...services.market_data_ingestion.session_repair import backfill_thin_histories

        try:
            ca_repair = await backfill_thin_histories(ca_symbols, end=end_date, min_bars=max(compiled.required_bars, 253))
            repair_report = {**repair_report, "corporate_action_refetch": ca_repair}
            reloaded = await load_bar_series(
                ca_symbols, from_date=from_date, to_date=end_date, session_dates=session_dates or None
            )
            for symbol, series in reloaded.items():
                cut = clip_series_to(series, end_date)
                if cut is not None:
                    series_by_symbol[symbol] = cut
            series_by_symbol, benchmark_series, quality = validate_and_sanitize_universe(
                series_by_symbol,
                end_session=end_date,
                session_dates=session_dates or None,
                min_bars=max(int(compiled.required_bars or 1), 1),
                benchmark=benchmark_series,
            )
        except Exception as exc:
            logger.warning("INDICATOR_SCAN_CA_REFETCH_FAILED | err=%s", type(exc).__name__)
            repair_report = {**repair_report, "corporate_action_refetch_error": type(exc).__name__}

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
            if bars.dates and not last_bar_covers_scan(bars.dates[-1], end_date):
                return {
                    "symbol": symbol,
                    "display_name": company_map.get(symbol),
                    "exchange": "NSE",
                    "timeframe": "1D",
                    "as_of": bars.dates[-1].isoformat(),
                    "status": "insufficient_history",
                    "matched": False,
                    "outputs": {},
                    "ohlcv": {},
                    "error_detail": f"Latest available bar ({bars.dates[-1].isoformat()}) is before scan date ({end_date.isoformat()}).",
                    "bar_count": len(bars),
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
                    if item.get("as_of"):
                        as_of_counts[item["as_of"]] = as_of_counts.get(item["as_of"], 0) + 1
                elif item["status"] == "insufficient_history":
                    skipped += 1
                else:
                    failed += 1
                if item.get("matched"):
                    matched += 1
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
    as_of = max(as_of_counts, key=as_of_counts.get) if as_of_counts else end_date.isoformat()
    calendar_requested = requested_date.isoformat() if requested_date else pine_target.isoformat()
    pine_screener_as_of = pine_target.isoformat()
    analytics = build_indicator_scan_analytics(
        results,
        universe_size=total,
        condition_defs=entry_condition_defs(compiled),
    )
    summary = {
        "universe_size": total,
        "scanned": len(results),
        "success": success,
        "failed": failed,
        "skipped": skipped,
        "matched": matched,
        **analytics,
        "as_of": as_of,
        "scan_as_of": as_of,
        "requested_as_of": pine_screener_as_of,
        "calendar_requested_as_of": calendar_requested,
        "data_source": data_source,
        "required_bars": compiled.required_bars,
        "benchmark_symbol": compiled.required_symbols[0] if compiled.required_symbols else None,
        "scan_date_counts": as_of_counts,
        "data_quality": quality.to_dict(),
        "market_data_repair": repair_report,
        "disclaimer": "For research and paper-trading only. Not investment advice.",
    }
    closed_request = requested_date is not None and not is_nse_cash_session(requested_date)
    if fallback_note:
        summary["scan_bar_note"] = fallback_note
    elif closed_request and as_of != calendar_requested:
        summary["scan_bar_note"] = (
            f"NSE cash market was closed on {calendar_requested}. "
            f"Scan bar is the last 1D session {as_of}."
        )
    elif as_of != pine_screener_as_of:
        try:
            from ..trading_hours_service import OPEN_TIME, TradingHoursService, trading_hours

            th = trading_hours if trading_hours is not None else TradingHoursService()
            ist = th._to_ist(None)
            if is_nse_cash_session(end_date) and end_date == ist.date() and ist.time() < OPEN_TIME:
                summary["scan_bar_note"] = (
                    f"NSE cash session {pine_screener_as_of} has not opened yet (09:15 IST). "
                    f"Scan bar is the last completed session {as_of}."
                )
        except Exception:
            pass
    if "scan_bar_note" not in summary and (as_of != pine_screener_as_of or len(as_of_counts) > 1):
        summary["scan_bar_warning"] = (
            f"Requested Pine Screener bar {pine_screener_as_of} but most names evaluated on {as_of}. "
            "Lists will not match TradingView until every symbol has that 1D bar."
        )
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
    conditions = list(result.conditions or [])
    extra_filters = [item for item in (filters or []) if not is_aggregate_signal_filter(item)]
    if result.status == "ok":
        if conditions:
            matched = all_required_conditions_passed(conditions)
            if matched and extra_filters:
                # Pine Screener: user column filters on the last 1D bar (EMA 20 = 1 matches nothing).
                matched = row_matches(result.outputs, extra_filters)
        elif extra_filters:
            matched = row_matches(result.outputs, extra_filters)
        elif filters:
            matched = row_matches(result.outputs, filters)
        else:
            matched = True
        # plotshape/alertcondition are the Pine Screener boolean columns. A match
        # requires the shape to be true on this bar (ta.crossover is one-bar only).
        bool_outs = [value for value in (result.outputs or {}).values() if isinstance(value, bool)]
        if matched and bool_outs and not any(bool_outs):
            matched = False
    outputs = dict(result.outputs or {})
    if conditions:
        outputs[CONDITIONS_OUTPUT_KEY] = conditions
    if result.return_pct is not None:
        outputs[RETURN_OUTPUT_KEY] = result.return_pct
    return {
        "symbol": symbol,
        "display_name": company,
        "exchange": "NSE",
        "timeframe": "1D",
        "as_of": result.as_of.isoformat() if result.as_of else None,
        "status": result.status,
        "matched": matched,
        "outputs": outputs,
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
    signal: str | None = None,
    return_bucket: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    items: list[dict[str, Any]] = []
    needle = (search or "").strip().upper()
    wanted = (signal or "").strip().upper()
    bucket = (return_bucket or "").strip().upper()
    for row in rows:
        payload = result_payload(row)
        row_signal_value = str(payload.get("signal") or "")
        if matched_only and wanted not in {"FAILED", "SKIPPED", "REJECT", "ALL", ""}:
            if not row.matched:
                continue
        if wanted in {"MATCH", "MATCHED"} and row_signal_value != "MATCH":
            continue
        if wanted in {"SKIPPED"} and row_signal_value != "SKIPPED":
            continue
        if wanted in {"FAILED", "REJECT"} and row_signal_value not in {"REJECT", "FAILED"}:
            continue
        if needle and needle not in (row.symbol or "").upper() and needle not in (row.display_name or "").upper():
            continue
        pct = payload.get("return_pct")
        if bucket == "POSITIVE" and not (isinstance(pct, (int, float)) and pct > 0):
            continue
        if bucket == "NEGATIVE" and not (isinstance(pct, (int, float)) and pct < 0):
            continue
        if bucket == "FLAT" and not (isinstance(pct, (int, float)) and pct == 0):
            continue
        items.append(payload)
    field = sort_field or "signal"
    group_by_signal = wanted in {"", "ALL"}

    def secondary(item: dict[str, Any]):
        pct = item.get("return_pct")
        if field in {"return_pct", "rank"} and isinstance(pct, (int, float)):
            return float(pct)
        if field in {"symbol", "display_name", "as_of", "status", "company"}:
            return str(item.get(field) or item.get("display_name") or "")
        if field in {"filters_passed", "filters_failed"} and isinstance(item.get(field), (int, float)):
            return float(item.get(field) or 0)
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
        return -float(pct) if isinstance(pct, (int, float)) else 0.0

    reverse = (sort_dir or "desc").lower() != "asc"
    if group_by_signal:
        items.sort(
            key=lambda item: (
                signal_sort_rank(str(item.get("signal") or "")),
                -float(item["return_pct"]) if isinstance(item.get("return_pct"), (int, float)) else 0.0,
                str(item.get("symbol") or ""),
            )
        )
    elif field == "signal":
        items.sort(
            key=lambda item: (
                signal_sort_rank(str(item.get("signal") or "")),
                -float(item["return_pct"]) if isinstance(item.get("return_pct"), (int, float)) else 0.0,
            )
        )
    else:
        items.sort(key=secondary, reverse=reverse)
    total = len(items)
    start = max(0, (page - 1) * page_size)
    ranked: list[dict[str, Any]] = []
    for index, item in enumerate(items[start : start + page_size], start=start + 1):
        item = dict(item)
        item["rank"] = index
        ranked.append(item)
    return ranked, total


def result_payload(row) -> dict[str, Any]:
    outputs = dict(row.outputs or {})
    stored = outputs.pop(CONDITIONS_OUTPUT_KEY, None)
    return_pct = row_return_pct(outputs, row.ohlcv or {})
    outputs.pop(RETURN_OUTPUT_KEY, None)
    conditions = usable_condition_rows(stored if isinstance(stored, list) else None)
    payload = {
        "symbol": row.symbol,
        "display_name": row.display_name,
        "company": row.display_name,
        "exchange": row.exchange,
        "timeframe": row.timeframe,
        "as_of": row.as_of,
        "evaluation_date": row.as_of,
        "status": row.status,
        "matched": row.matched,
        "signal": row_signal({"status": row.status, "matched": row.matched}),
        "outputs": outputs,
        "ohlcv": row.ohlcv or {},
        "error_detail": row.error_detail,
        "bar_count": row.bar_count,
        "return_pct": return_pct,
        "filter_results": [{"name": item["name"], "passed": bool(item.get("passed"))} for item in conditions],
        "filters_passed": sum(1 for item in conditions if item.get("passed")),
        "filters_failed": sum(1 for item in conditions if not item.get("passed")),
        "passed_filters": [item["name"] for item in conditions if item.get("passed")],
        "failed_filters": [item["name"] for item in conditions if not item.get("passed")],
    }
    close = outputs.get("Close")
    ohlcv = payload["ohlcv"] or {}
    if close is None:
        close = ohlcv.get("close")
    payload["close"] = close if isinstance(close, (int, float)) else None
    payload["exit_price"] = payload["close"]
    close_t252 = outputs.get("Close t-252")
    payload["entry_price"] = close_t252 if isinstance(close_t252, (int, float)) else None
    failed_names = payload["failed_filters"]
    payload["primary_failure_reason"] = (
        None
        if row.matched
        else (row.error_detail or (failed_names[0] if failed_names else "Did not match strategy conditions"))
    )
    return payload


def _filter_label(item: dict[str, Any]) -> str:
    field = str(item.get("field") or "").strip()
    op = str(item.get("operator") or "=").strip()
    if op in {"is_true", "is_false", "is_null", "is_not_null"}:
        return f"{field} {op.replace('_', ' ')}"
    if op == "between":
        return f"{field} between {item.get('low')} and {item.get('high')}"
    value = item.get("value")
    if value is None or value == "":
        return field
    return f"{field} {op} {value}"


def symbol_detail_payload(run, row) -> dict[str, Any]:
    """Stock-details view for one indicator-scan row.

    Matching uses the logical AND of every strategy entry condition from this
    run. Overview lists those same per-run conditions, including older scans
    that only stored the collapsed Signal = 1 filter.
    """
    payload = result_payload(row)
    outputs = payload.get("outputs") or {}
    stored = (row.outputs or {}).get(CONDITIONS_OUTPUT_KEY) if isinstance(row.outputs, dict) else None
    filters = run.filters or []
    snapshot = run.indicator_snapshot if isinstance(getattr(run, "indicator_snapshot", None), dict) else {}
    filter_results = conditions_for_detail(
        source_code=snapshot.get("source_code") if snapshot else None,
        outputs=outputs,
        ohlcv=payload.get("ohlcv") or (row.ohlcv if isinstance(getattr(row, "ohlcv", None), dict) else {}),
        stored=stored if isinstance(stored, list) else None,
        filters=filters,
    )
    close = outputs.get("Close")
    close_t252 = outputs.get("Close t-252")
    momentum = outputs.get("Momentum 252")
    ohlcv = payload.get("ohlcv") or {}
    if close is None:
        close = ohlcv.get("close")
    return_pct = None
    if isinstance(momentum, (int, float)):
        return_pct = float(momentum) * 100.0
    elif isinstance(close, (int, float)) and isinstance(close_t252, (int, float)) and close_t252:
        return_pct = (float(close) / float(close_t252) - 1.0) * 100.0
    payload.update(
        {
            "scan_id": run.public_scan_id,
            "indicator_id": str(run.indicator_id) if run.indicator_id else None,
            "indicator_name": run.indicator_name,
            "filters": filters,
            "filter_results": filter_results,
            "signal": "MATCH" if row.matched else "REJECT",
            "company": row.display_name,
            "entry_price": close_t252 if isinstance(close_t252, (int, float)) else None,
            "exit_price": close if isinstance(close, (int, float)) else None,
            "return_pct": return_pct,
            "close": close if isinstance(close, (int, float)) else None,
            "evaluation_date": row.as_of,
            "source": "indicator_scanner",
        }
    )
    return payload


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
