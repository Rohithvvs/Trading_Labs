"""Ensure latest strategy-grade market data before scanners / daily ops.

``ensure_latest_market_data()`` is the single auto-fetch entry point:

- Fast path when expected session already has OHLCV, index, delivery, adtv_20
- Otherwise fetch only missing pieces (FYERS OHLCV/index, NSE delivery)
- Recompute adtv_20 for affected rows
- Idempotent and safe to call on every scan

Weekly bars are never stored — strategies derive them via ``weekly_ohlcv``.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime, timedelta
from typing import Any

from ...config.settings import settings
from .calendar_utils import expected_last_completed_session
from .derived import compute_adtv_20_for_bar, compute_delivery_pct, compute_turnover
from . import load_tracking
from . import repository
from .locks import acquire_market_data_load_lock
from .providers.fyers_eod import FyersEodProvider
from .providers.nse_delivery import NseDeliveryProvider
from .validators.completeness import session_completeness

logger = logging.getLogger("app.market_data_ingestion.ensure")

# Delivery is softer than OHLCV: still try to fill, but don't treat modest gaps as hard fail for "fresh".
_DELIVERY_SOFT_THRESHOLD = 0.90
_ADTV_SOFT_THRESHOLD = 0.95

# Short process cache so scanner fast-path avoids reloading 755 symbols every call.
_UNIVERSE_CACHE: tuple[float, list[str]] | None = None
_UNIVERSE_CACHE_TTL_S = 120.0

# Scanner pre-flight budget: must finish (or abort) before frontend stream stall (90s)
# and leave room for heartbeat/progress. CLI/SCHEDULE use a larger budget.
_SCANNER_ENSURE_BUDGET_S = 45.0
_CLI_ENSURE_BUDGET_S = 900.0
# Cap how many missing OHLCV symbols the scanner path will chase live via FYERS.
# Remaining gaps stay for the daily job; scanners still score the full data-valid set.
_SCANNER_MAX_OHLCV_FETCH = 40


async def _get_universe(symbols: list[str] | None) -> list[str]:
    global _UNIVERSE_CACHE
    if symbols is not None:
        return list(symbols)
    now = time.time()
    if _UNIVERSE_CACHE is not None:
        ts, cached = _UNIVERSE_CACHE
        if now - ts < _UNIVERSE_CACHE_TTL_S and cached:
            return list(cached)
    from ...services.universe_service import UniverseService

    loaded = await UniverseService.get_active_nifty500_symbols()
    _UNIVERSE_CACHE = (now, list(loaded))
    return list(loaded)


def _iter_calendar_days(start: date, end: date) -> list[date]:
    if start > end:
        return []
    out: list[date] = []
    cur = start
    while cur <= end:
        out.append(cur)
        cur += timedelta(days=1)
    return out


def _trading_days_between(start: date, end: date) -> list[date]:
    """Inclusive trading days in [start, end]; weekends-only fallback if calendar fails."""
    days = _iter_calendar_days(start, end)
    if not days:
        return []
    try:
        from ..trading_hours_service import TradingHoursService, trading_hours

        th = trading_hours if trading_hours is not None else TradingHoursService()
        return [
            d
            for d in days
            if th.is_trading_day(datetime(d.year, d.month, d.day))
        ]
    except Exception:
        return [d for d in days if d.weekday() < 5]


async def _snapshot(
    expected: date,
    symbols: list[str],
    *,
    index_symbol: str,
    include_symbol_sets: bool = False,
) -> dict[str, Any]:
    raw = await repository.session_coverage_snapshot(
        expected,
        symbols,
        index_symbol=index_symbol,
        include_symbol_sets=include_symbol_sets,
    )
    present = raw["present"]
    with_deliv = raw["with_delivery"]
    with_adtv = raw["with_adtv"]
    idx_ok = bool(raw["index_present"])
    n = len(symbols) or 1
    present_n = int(raw.get("present_count") or 0)
    deliv_n = int(raw.get("delivery_count") or 0)
    adtv_n = int(raw.get("adtv_count") or 0)
    # Delivery/adtv ratios among symbols that already have OHLCV
    base = present_n or 1
    deliv_among = deliv_n / base
    adtv_among = adtv_n / base
    coverage = present_n / n
    missing_ohlcv: list[str] = []
    missing_delivery: list[str] = []
    missing_adtv: list[str] = []
    if include_symbol_sets:
        missing_ohlcv = [s for s in symbols if s not in present]
        present_list = [s for s in symbols if s in present]
        missing_delivery = [s for s in present_list if s not in with_deliv]
        missing_adtv = [s for s in present_list if s not in with_adtv]
    else:
        # Synthetic missing count only (no names) for fast-path decisions
        missing_ohlcv = [f"__missing_{i}" for i in range(max(0, n - present_n))]
    return {
        "present": present,
        "index_present": idx_ok,
        "equity_coverage": coverage,
        "missing_ohlcv": missing_ohlcv,
        "delivery_coverage": deliv_among if present_n else 0.0,
        "missing_delivery": missing_delivery,
        "adtv_coverage": adtv_among if present_n else 0.0,
        "missing_adtv": missing_adtv,
        "present_count": present_n,
        "delivery_count": deliv_n,
        "adtv_count": adtv_n,
        "max_equity_date": raw.get("max_equity_date"),
    }


def _is_fast_fresh(
    snap: dict[str, Any],
    *,
    threshold: float,
    force: bool,
    universe_size: int,
    has_date_gap: bool,
) -> bool:
    """True when latest session is good enough to skip network I/O.

    Allows a small permanent missing-symbol set (invalid/delisted tickers) so the
    scanner is not forced to re-hit FYERS for names that never return data.
    """
    if force or has_date_gap:
        return False
    if not snap["index_present"]:
        return False
    if snap["present_count"] == 0:
        return False
    if snap["delivery_coverage"] < _DELIVERY_SOFT_THRESHOLD:
        return False
    if snap["adtv_coverage"] < _ADTV_SOFT_THRESHOLD:
        return False
    if snap["equity_coverage"] >= threshold:
        return True
    # Tolerate up to ~3% permanently missing (or 25 abs) without re-fetch thrash
    missing_n = len(snap.get("missing_ohlcv") or [])
    tol = max(25, int(0.03 * max(universe_size, 1)))
    return missing_n <= tol and snap["equity_coverage"] >= 0.95


async def ensure_latest_market_data(
    *,
    target_date: date | None = None,
    symbols: list[str] | None = None,
    trigger_source: str = "SCANNER",
    force: bool = False,
    write_load_log: bool | None = None,
    progress_callback: Any | None = None,
    max_duration_s: float | None = None,
) -> dict[str, Any]:
    """Ensure strategy tables have the latest completed session.

    Returns a structured summary including ``status``:
    - ``ALREADY_FRESH`` — nothing fetched (fast path)
    - ``SUCCESS`` / ``PARTIAL`` / ``FAILED`` — after fetch
    - ``SKIPPED_LOCKED`` — another load holds the lock
    - ``TIMEOUT`` — budget exhausted (scanner continues without hanging SSE)

    ``progress_callback`` optional callable(dict) for UI progress during long fetches.
    ``max_duration_s`` hard wall-clock budget (default: 45s for SCANNER, 900s for CLI).
    """
    t0 = time.perf_counter()
    index_symbol = settings.strategy_index_store_symbol
    threshold = float(settings.strategy_market_data_coverage_threshold)
    is_scanner = str(trigger_source or "").upper() in {"SCANNER", "UI", "UI_SCAN"}
    if max_duration_s is None:
        max_duration_s = _SCANNER_ENSURE_BUDGET_S if is_scanner else _CLI_ENSURE_BUDGET_S
    max_duration_s = float(max(5.0, max_duration_s))

    def _budget_left() -> float:
        return max_duration_s - (time.perf_counter() - t0)

    def _budget_exhausted() -> bool:
        return _budget_left() <= 0.5

    async def _progress(stage: str, progress: int, **extra: Any) -> None:
        if not progress_callback:
            return
        try:
            payload = {"stage": stage, "progress": progress, "heartbeat": True, **extra}
            if asyncio.iscoroutinefunction(progress_callback):
                await progress_callback(payload)
            else:
                progress_callback(payload)
        except Exception:
            pass

    # Load log for CLI/schedule always; for scanner only when we actually fetch
    if write_load_log is None:
        write_load_log = trigger_source in {"CLI", "SCHEDULE"}

    try:
        expected = target_date or expected_last_completed_session()
    except Exception as exc:
        logger.error("ENSURE_MARKET_DATA_CALENDAR_FAIL | err=%s", type(exc).__name__)
        return {
            "status": "FAILED",
            "exit_code": 1,
            "error": "calendar_error",
            "duration_ms": int((time.perf_counter() - t0) * 1000),
        }

    from ...services.universe_service import UniverseService

    try:
        universe = await _get_universe(symbols)
    except Exception as exc:
        logger.error("ENSURE_MARKET_DATA_UNIVERSE_FAIL | err=%s", type(exc).__name__)
        return {
            "status": "FAILED",
            "exit_code": 1,
            "error": "universe_unavailable",
            "data_date": expected.isoformat(),
            "duration_ms": int((time.perf_counter() - t0) * 1000),
        }

    if not universe:
        return {
            "status": "FAILED",
            "exit_code": 1,
            "error": "empty_universe",
            "data_date": expected.isoformat(),
            "duration_ms": int((time.perf_counter() - t0) * 1000),
        }

    # --- Fast path: read-only snapshot (single DB round-trip bundle) ---
    try:
        snap = await _snapshot(expected, universe, index_symbol=index_symbol)
        latest_eq = snap.get("max_equity_date")
    except Exception as exc:
        logger.error("ENSURE_MARKET_DATA_DB_FAIL | err=%s", type(exc).__name__)
        return {
            "status": "FAILED",
            "exit_code": 1,
            "error": "db_unavailable",
            "data_date": expected.isoformat(),
            "duration_ms": int((time.perf_counter() - t0) * 1000),
        }

    gap_dates: list[date] = []
    if latest_eq is None:
        gap_dates = _trading_days_between(expected, expected)
    elif latest_eq < expected:
        gap_dates = _trading_days_between(latest_eq + timedelta(days=1), expected)
    elif force:
        gap_dates = _trading_days_between(expected, expected)

    needs_gap = bool(gap_dates)
    # When gap exists, full universe for those dates; else only missing symbols on expected
    fast_ok = _is_fast_fresh(
        snap,
        threshold=threshold,
        force=force,
        universe_size=len(universe),
        has_date_gap=needs_gap,
    )

    if fast_ok:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "ENSURE_MARKET_DATA_ALREADY_FRESH | source=%s | date=%s | equity=%.3f | "
            "index=%s | delivery=%.3f | adtv=%.3f | duration_ms=%s",
            trigger_source,
            expected.isoformat(),
            snap["equity_coverage"],
            snap["index_present"],
            snap["delivery_coverage"],
            snap["adtv_coverage"],
            duration_ms,
        )
        return {
            "status": "ALREADY_FRESH",
            "exit_code": 0,
            "data_date": expected.isoformat(),
            "fetched": {
                "ohlcv": False,
                "delivery": False,
                "index": False,
                "adtv": False,
            },
            "already_present": {
                "equity_coverage": snap["equity_coverage"],
                "index_present": snap["index_present"],
                "delivery_coverage": snap["delivery_coverage"],
                "adtv_coverage": snap["adtv_coverage"],
                "present_count": snap["present_count"],
            },
            "rows_upserted": 0,
            "rows_fetched": 0,
            "duration_ms": duration_ms,
            "completeness": {
                "trade_date": expected.isoformat(),
                "active_count": len(universe),
                "present_count": snap["present_count"],
                "coverage_ratio": snap["equity_coverage"],
                "index_present": snap["index_present"],
                "missing_symbol_count": len(snap["missing_ohlcv"]),
                "success": snap["equity_coverage"] >= threshold and snap["index_present"],
                "threshold": threshold,
            },
        }

    logger.info(
        "ENSURE_MARKET_DATA_START | source=%s | date=%s | force=%s | gap_dates=%s | "
        "missing_ohlcv=%s | index=%s | delivery=%.3f | adtv=%.3f | budget_s=%.0f",
        trigger_source,
        expected.isoformat(),
        force,
        [d.isoformat() for d in gap_dates[:10]],
        len(snap["missing_ohlcv"]),
        snap["index_present"],
        snap["delivery_coverage"],
        snap["adtv_coverage"],
        max_duration_s,
    )
    await _progress(
        f"Ensuring market data (session {expected.isoformat()})...",
        4,
        ensure_phase="start",
        data_date=expected.isoformat(),
    )

    lease = await acquire_market_data_load_lock()
    if not lease.acquired:
        if write_load_log:
            await load_tracking.record_skipped_locked("DAILY", trigger_source)
        logger.warning("ENSURE_MARKET_DATA_SKIPPED_LOCKED | source=%s", trigger_source)
        return {
            "status": "SKIPPED_LOCKED",
            "exit_code": 3,
            "data_date": expected.isoformat(),
            "duration_ms": int((time.perf_counter() - t0) * 1000),
        }

    run_id = None
    nse: NseDeliveryProvider | None = None
    fetched_flags = {"ohlcv": False, "delivery": False, "index": False, "adtv": False}
    total_fetched = 0
    total_upserted = 0
    total_failed = 0
    failed_symbols: list[str] = []
    delivery_updates = 0
    adtv_updates = 0
    sessions_touched: list[date] = []
    timed_out = False

    try:
        await UniverseService.touch_lifecycle(universe, is_nifty500=True)

        if write_load_log or trigger_source in {"CLI", "SCHEDULE"}:
            run_id = await load_tracking.start_load(
                "DAILY", trigger_source, data_date=expected, provider="FYERS+NSE"
            )
            write_load_log = True

        # Re-snapshot under lock (another worker may have filled)
        snap = await _snapshot(
            expected, universe, index_symbol=index_symbol, include_symbol_sets=True
        )
        latest_eq = snap.get("max_equity_date")
        gap_dates = []
        if latest_eq is None:
            gap_dates = _trading_days_between(expected, expected)
        elif latest_eq < expected:
            gap_dates = _trading_days_between(latest_eq + timedelta(days=1), expected)
        elif force:
            gap_dates = _trading_days_between(expected, expected)

        if _is_fast_fresh(
            snap,
            threshold=threshold,
            force=force,
            universe_size=len(universe),
            has_date_gap=bool(gap_dates),
        ):
            duration_ms = int((time.perf_counter() - t0) * 1000)
            if run_id:
                await load_tracking.finish_load(
                    run_id,
                    "SUCCESS",
                    rows_skipped=len(universe),
                    details_json={"already_fresh_under_lock": True},
                )
            logger.info(
                "ENSURE_MARKET_DATA_ALREADY_FRESH | under_lock=1 | source=%s | date=%s | duration_ms=%s",
                trigger_source,
                expected.isoformat(),
                duration_ms,
            )
            return {
                "status": "ALREADY_FRESH",
                "exit_code": 0,
                "data_date": expected.isoformat(),
                "fetched": fetched_flags,
                "rows_upserted": 0,
                "rows_fetched": 0,
                "duration_ms": duration_ms,
                "run_id": str(run_id) if run_id else None,
            }

        if _budget_exhausted():
            timed_out = True
            logger.warning(
                "ENSURE_MARKET_DATA_TIMEOUT | phase=post_snapshot | source=%s | budget_s=%.0f",
                trigger_source,
                max_duration_s,
            )
        else:
            fyers = FyersEodProvider()
            nse = NseDeliveryProvider()
            concurrency = max(1, min(settings.strategy_market_data_load_concurrency, 8))
            sem = asyncio.Semaphore(concurrency)

            # Sessions to process for OHLCV
            # SCANNER path: only repair the expected session (never multi-day full-universe
            # catch-up — that is the job of CLI/SCHEDULE daily update).
            if is_scanner and not force:
                if gap_dates:
                    # Date gap exists: only fetch expected session for a bounded missing set
                    # (or skip OHLCV if already decent coverage — daily job will backfill).
                    ohlcv_sessions = [expected]
                    ohlcv_symbols = list(snap.get("missing_ohlcv") or [])[:_SCANNER_MAX_OHLCV_FETCH]
                    if not ohlcv_symbols and snap["equity_coverage"] < threshold:
                        ohlcv_symbols = list(universe)[:_SCANNER_MAX_OHLCV_FETCH]
                    logger.info(
                        "ENSURE_SCANNER_BOUNDED | gap_dates=%s | ohlcv_cap=%s | symbols=%s",
                        len(gap_dates),
                        _SCANNER_MAX_OHLCV_FETCH,
                        len(ohlcv_symbols),
                    )
                elif snap["missing_ohlcv"] and snap["equity_coverage"] < threshold:
                    missing_n = len(snap["missing_ohlcv"])
                    tol = max(25, int(0.03 * max(len(universe), 1)))
                    if missing_n > tol:
                        ohlcv_sessions = [expected]
                        ohlcv_symbols = list(snap["missing_ohlcv"])[:_SCANNER_MAX_OHLCV_FETCH]
                    else:
                        ohlcv_sessions = []
                        ohlcv_symbols = []
                else:
                    ohlcv_sessions = []
                    ohlcv_symbols = []
            elif gap_dates:
                ohlcv_sessions = gap_dates
                ohlcv_symbols = universe
            elif force:
                ohlcv_sessions = [expected]
                ohlcv_symbols = universe
            elif snap["missing_ohlcv"] and snap["equity_coverage"] < threshold:
                # Only chase missing symbols when coverage is below gate threshold
                # and missing set is large (avoid thrashing invalid tickers every scan)
                missing_n = len(snap["missing_ohlcv"])
                tol = max(25, int(0.03 * max(len(universe), 1)))
                if missing_n > tol:
                    ohlcv_sessions = [expected]
                    ohlcv_symbols = snap["missing_ohlcv"]
                else:
                    ohlcv_sessions = []
                    ohlcv_symbols = []
            else:
                ohlcv_sessions = []
                ohlcv_symbols = []

            # Always include expected for delivery/index/adtv repair even if OHLCV ok
            repair_sessions = list(dict.fromkeys(ohlcv_sessions + [expected]))
            # Scanner: at most the expected session (never walk multi-day gaps here)
            if is_scanner and not force:
                repair_sessions = [expected]

            for session in repair_sessions:
                if _budget_exhausted():
                    timed_out = True
                    logger.warning(
                        "ENSURE_MARKET_DATA_TIMEOUT | phase=session_loop | session=%s | source=%s",
                        session.isoformat(),
                        trigger_source,
                    )
                    break
                sessions_touched.append(session)
                need_ohlcv = session in ohlcv_sessions
                need_index = not await repository.index_present(session, index_symbol) or force
                present_now = await repository.symbols_present_on(session, universe)
                with_deliv = await repository.symbols_with_delivery_on(session, universe)
                with_adtv = await repository.symbols_with_adtv_on(session, universe)
                present_list = [s for s in universe if s in present_now]
                deliv_cov = (
                    sum(1 for s in present_list if s in with_deliv) / len(present_list)
                    if present_list
                    else 0.0
                )
                adtv_cov = (
                    sum(1 for s in present_list if s in with_adtv) / len(present_list)
                    if present_list
                    else 0.0
                )
                need_delivery = force or deliv_cov < _DELIVERY_SOFT_THRESHOLD or not present_list
                need_adtv = force or adtv_cov < _ADTV_SOFT_THRESHOLD

                await _progress(
                    f"Market data session {session.isoformat()}...",
                    4,
                    ensure_phase="session",
                    data_date=session.isoformat(),
                    need_ohlcv=need_ohlcv,
                    need_delivery=need_delivery,
                    need_adtv=need_adtv,
                    need_index=need_index,
                )

                delivery_map: dict[str, Any] = {}
                if (need_delivery or need_ohlcv) and not _budget_exhausted():
                    try:
                        # Bound NSE download so a hung archive cannot freeze the scanner.
                        delivery_map = await asyncio.wait_for(
                            nse.fetch_session_delivery(session),
                            timeout=min(20.0, max(3.0, _budget_left())),
                        )
                        if delivery_map:
                            fetched_flags["delivery"] = True
                    except Exception as exc:
                        logger.warning(
                            "ENSURE_DELIVERY_FAIL | session=%s | err=%s",
                            session.isoformat(),
                            type(exc).__name__,
                        )

                # OHLCV for missing / gap
                session_symbols = (
                    list(ohlcv_symbols)
                    if need_ohlcv and session in ohlcv_sessions
                    else []
                )
                # Also re-fetch symbols present but force
                if force and session == expected:
                    session_symbols = list(universe)
                    if is_scanner:
                        session_symbols = session_symbols[:_SCANNER_MAX_OHLCV_FETCH]

                if session_symbols and not _budget_exhausted():
                    fetched_flags["ohlcv"] = True
                    done_counter = {"n": 0}
                    total_sym = len(session_symbols)
                    logger.info(
                        "ENSURE_OHLCV_FETCH_START | session=%s | symbols=%s | concurrency=%s | budget_left_s=%.1f",
                        session.isoformat(),
                        total_sym,
                        concurrency,
                        _budget_left(),
                    )
                    await _progress(
                        f"Fetching EOD OHLCV 0/{total_sym}...",
                        4,
                        ensure_phase="ohlcv",
                        done=0,
                        remaining=total_sym,
                        total_fetch=total_sym,
                    )

                    async def one(
                        sym: str,
                        _session: date = session,
                        _dmap: dict = delivery_map,
                    ) -> dict[str, Any] | None:
                        if _budget_exhausted():
                            return None
                        async with sem:
                            if _budget_exhausted():
                                return None
                            try:
                                logger.info(
                                    "ENSURE_SYMBOL_FYERS_START | symbol=%s | session=%s",
                                    sym,
                                    _session.isoformat(),
                                )
                                bar = await asyncio.wait_for(
                                    fyers.fetch_daily_session(sym, _session),
                                    timeout=min(25.0, max(5.0, _budget_left())),
                                )
                                logger.info(
                                    "ENSURE_SYMBOL_FYERS_END | symbol=%s | session=%s | ok=%s",
                                    sym,
                                    _session.isoformat(),
                                    bool(bar),
                                )
                                if not bar:
                                    return None
                                drec = nse.lookup(_dmap, symbol=sym) if nse and _dmap else None
                                d_qty = drec.get("delivery_qty") if drec else None
                                traded = drec.get("traded_qty") if drec else None
                                d_pct = drec.get("delivery_pct") if drec else None
                                if d_pct is None and d_qty is not None:
                                    pct = compute_delivery_pct(d_qty, traded)
                                    d_pct = float(pct) if pct is not None else None
                                turn = compute_turnover(bar["close"], bar["volume"])
                                bar["delivery_qty"] = d_qty
                                bar["delivery_pct"] = d_pct
                                bar["turnover"] = float(turn) if turn is not None else None
                                prior = await repository.fetch_recent_equity_before(
                                    sym, _session, limit=19
                                )
                                bar["adtv_20"] = compute_adtv_20_for_bar(prior, bar)
                                return bar
                            except Exception as exc:
                                logger.warning(
                                    "ENSURE_SYMBOL_FAIL | symbol=%s | session=%s | err=%s",
                                    sym,
                                    _session,
                                    type(exc).__name__,
                                )
                                failed_symbols.append(sym)
                                return None
                            finally:
                                done_counter["n"] += 1
                                done = done_counter["n"]
                                if done % 5 == 0 or done == total_sym:
                                    try:
                                        await _progress(
                                            f"Fetching EOD OHLCV {done}/{total_sym}...",
                                            min(5, 4 + int(1 * done / max(1, total_sym))),
                                            ensure_phase="ohlcv",
                                            done=done,
                                            remaining=total_sym - done,
                                            total_fetch=total_sym,
                                            current_symbol=sym,
                                        )
                                    except Exception:
                                        pass

                    # Process in waves so a budget expiry can cancel pending work
                    # instead of waiting on every scheduled hang/timeout.
                    bars: list[dict[str, Any]] = []
                    wave = max(1, concurrency * 2)
                    for wave_start in range(0, len(session_symbols), wave):
                        if _budget_exhausted():
                            timed_out = True
                            logger.warning(
                                "ENSURE_OHLCV_BUDGET | session=%s | done=%s | total=%s",
                                session.isoformat(),
                                wave_start,
                                total_sym,
                            )
                            break
                        wave_syms = session_symbols[wave_start : wave_start + wave]
                        wave_results = await asyncio.gather(*[one(s) for s in wave_syms])
                        bars.extend([r for r in wave_results if r])
                        total_failed += sum(1 for r in wave_results if r is None)
                    total_fetched += len(bars)
                    if bars:
                        n_up, _ = await repository.upsert_daily_bars(bars)
                        total_upserted += n_up
                        fetched_flags["adtv"] = True
                    logger.info(
                        "ENSURE_OHLCV_FETCH_END | session=%s | ok=%s | failed=%s | budget_left_s=%.1f",
                        session.isoformat(),
                        len(bars),
                        total_failed,
                        _budget_left(),
                    )

                # Delivery apply for all present rows on session
                if delivery_map and not _budget_exhausted():
                    try:
                        n = await repository.update_delivery_for_session(
                            session, delivery_map, symbols=universe
                        )
                        delivery_updates += n
                        if n:
                            fetched_flags["delivery"] = True
                    except Exception as exc:
                        logger.warning(
                            "ENSURE_DELIVERY_APPLY_FAIL | session=%s | err=%s",
                            session.isoformat(),
                            type(exc).__name__,
                        )

                # Index
                if need_index and not _budget_exhausted():
                    try:
                        idx_rows = await asyncio.wait_for(
                            fyers.fetch_index_range(session, session),
                            timeout=min(25.0, max(5.0, _budget_left())),
                        )
                        if idx_rows:
                            await repository.upsert_index_bars(idx_rows)
                            fetched_flags["index"] = True
                    except Exception as exc:
                        logger.warning(
                            "ENSURE_INDEX_FAIL | session=%s | err=%s",
                            session.isoformat(),
                            type(exc).__name__,
                        )

                # ADTV repair — single SQL window (NOT N sequential history loads).
                if (need_adtv or need_ohlcv) and not _budget_exhausted():
                    try:
                        await _progress(
                            f"Computing ADTV-20 for {session.isoformat()}...",
                            5,
                            ensure_phase="adtv",
                        )
                        n_adtv = await repository.backfill_adtv_20_for_session(
                            session, symbols=universe
                        )
                        adtv_updates += n_adtv
                        if n_adtv:
                            fetched_flags["adtv"] = True
                        logger.info(
                            "ENSURE_ADTV_SQL | session=%s | updated=%s",
                            session.isoformat(),
                            n_adtv,
                        )
                    except Exception as exc:
                        logger.warning(
                            "ENSURE_ADTV_SQL_FAIL | session=%s | err=%s",
                            session.isoformat(),
                            type(exc).__name__,
                        )

        # Final completeness
        snap_final = await _snapshot(
            expected, universe, index_symbol=index_symbol, include_symbol_sets=True
        )
        comp = session_completeness(
            expected,
            universe,
            snap_final["present"],
            snap_final["index_present"],
            threshold=threshold,
        )

        if timed_out:
            status, exit_code = "TIMEOUT", 5
        elif total_upserted == 0 and total_failed > 0 and not any(fetched_flags.values()):
            status, exit_code = "FAILED", 1
        elif not comp.success or total_failed > 0:
            # OHLCV coverage is hard; delivery soft
            status = "SUCCESS" if comp.success else "PARTIAL"
            exit_code = 0 if comp.success else 4
        else:
            status, exit_code = "SUCCESS", 0

        duration_ms = int((time.perf_counter() - t0) * 1000)
        details = {
            **comp.to_dict(),
            "fetched": fetched_flags,
            "delivery_updates": delivery_updates,
            "adtv_updates": adtv_updates,
            "failed_symbols_sample": failed_symbols[:30],
            "sessions": [d.isoformat() for d in sessions_touched],
            "delivery_coverage": snap_final["delivery_coverage"],
            "adtv_coverage": snap_final["adtv_coverage"],
            "timed_out": timed_out,
            "budget_s": max_duration_s,
            "is_scanner": is_scanner,
        }
        if run_id:
            finish_status = "SUCCESS" if status in {"SUCCESS", "ALREADY_FRESH"} else (
                "PARTIAL" if status in {"PARTIAL", "TIMEOUT"} else "FAILED"
            )
            await load_tracking.finish_load(
                run_id,
                finish_status,
                rows_fetched=total_fetched,
                rows_inserted=total_upserted,
                rows_failed=total_failed,
                error_summary=None if status == "SUCCESS" else f"status={status} coverage={comp.coverage_ratio:.3f}",
                details_json=details,
            )

        logger.info(
            "ENSURE_MARKET_DATA_END | source=%s | status=%s | date=%s | "
            "fetched_ohlcv=%s | delivery=%s | index=%s | adtv=%s | "
            "upserted=%s | delivery_updates=%s | adtv_updates=%s | "
            "equity=%.3f | duration_ms=%s | timed_out=%s",
            trigger_source,
            status,
            expected.isoformat(),
            fetched_flags["ohlcv"],
            fetched_flags["delivery"],
            fetched_flags["index"],
            fetched_flags["adtv"],
            total_upserted,
            delivery_updates,
            adtv_updates,
            comp.coverage_ratio,
            duration_ms,
            timed_out,
        )
        await _progress(
            f"Market data {status}",
            6,
            ensure_phase="end",
            ensure_status=status,
        )
        return {
            "status": status,
            "exit_code": exit_code,
            "data_date": expected.isoformat(),
            "fetched": fetched_flags,
            "already_present": {
                "equity_coverage": snap_final["equity_coverage"],
                "index_present": snap_final["index_present"],
                "delivery_coverage": snap_final["delivery_coverage"],
                "adtv_coverage": snap_final["adtv_coverage"],
            },
            "rows_fetched": total_fetched,
            "rows_upserted": total_upserted,
            "rows_failed": total_failed,
            "delivery_updates": delivery_updates,
            "adtv_updates": adtv_updates,
            "completeness": comp.to_dict(),
            "duration_ms": duration_ms,
            "run_id": str(run_id) if run_id else None,
            "timed_out": timed_out,
        }
    except Exception as exc:
        logger.exception("ENSURE_MARKET_DATA_FAILED | source=%s | error=%s", trigger_source, exc)
        if run_id:
            await load_tracking.finish_load(run_id, "FAILED", error_summary=str(exc)[:500])
        return {
            "status": "FAILED",
            "exit_code": 1,
            "error": str(exc),
            "data_date": expected.isoformat() if expected else None,
            "duration_ms": int((time.perf_counter() - t0) * 1000),
        }
    finally:
        if nse is not None:
            try:
                await nse.aclose()
            except Exception:
                pass
        await lease.release()
