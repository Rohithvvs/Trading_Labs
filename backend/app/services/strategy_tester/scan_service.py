"""Async Strategy Tester run: full universe, batched OHLCV, isolated per-stock errors."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from ...config.settings import ROOT_DIR, settings
from ...models.strategy_market_data import DailyOhlcv
from ...services.market_data_ingestion.repository import (
    fetch_daily_ohlcv_for_symbols,
    fetch_index_history,
    iter_symbol_chunks,
)
from ...services.universe_csv import is_dummy_universe_symbol, load_unique_nifty500_csv_rows
from ...services.universe_service import UniverseService
from ...utils.symbol import canonical_symbol, ohlcv_symbol_variants
from . import persistence
from .analytics import summarize_results
from .engine import StrategyEvaluationResult, evaluate_stock
from .indicators import BarSeries
from .schema import (
    CALCULATION_VERSION,
    DEFAULT_UNIVERSE,
    StrategyConfigError,
    StrategyDefinitionConfig,
    required_warmup,
    uses_benchmark,
)
from .signals import BUY, REJECT, WATCH

logger = logging.getLogger("app.strategy_tester")

_cancel_requested: set[uuid.UUID] = set()
_active_runs: set[uuid.UUID] = set()
_PROGRESS_EVERY = 12
_FILL_HISTORY_TIMEOUT_S = 12.0
_PROBE_HISTORY_TIMEOUT_S = 8.0
_LIVE_QUOTE_TIMEOUT_S = 90.0
_FILL_PROBE_NAMES = ("RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK")
# NIFTY 500 membership is 500+ names; the live Trading Labs universe is 755.
# A truncated stocks_master (historically 65 names) must not become the scan set.
_MIN_FULL_UNIVERSE = 500
_NIFTY500_UNIVERSE_CODES = {"ALL_755", "ALL", "ALL_STOCKS", "NIFTY500", "NIFTY_500"}


def request_cancel(run_id: uuid.UUID) -> None:
    _cancel_requested.add(run_id)


def is_cancel_requested(run_id: uuid.UUID) -> bool:
    return run_id in _cancel_requested


async def start_test_background(
    *,
    user_id: uuid.UUID | None,
    config: StrategyDefinitionConfig,
    start_date: date,
    end_date: date,
    initial_capital: float,
    strategy_definition_id: uuid.UUID | None = None,
    strategy_version: int = 1,
) -> dict[str, Any]:
    if start_date > end_date:
        raise StrategyConfigError("start_date must be on or before end_date")
    active = await persistence.find_active_run(user_id)
    if active:
        return {
            "error_code": "STRATEGY_TEST_IN_PROGRESS",
            "run_id": active.public_run_id,
            "id": str(active.id),
            "status": active.status,
        }
    instruments = await load_universe(config.universe)
    public_id = await persistence.next_public_run_id()
    snapshot = config.to_snapshot()
    snapshot["initial_capital"] = initial_capital
    snapshot["start_date"] = start_date.isoformat()
    snapshot["end_date"] = end_date.isoformat()
    run = await persistence.create_run(
        user_id=user_id,
        public_run_id=public_id,
        strategy_definition_id=strategy_definition_id,
        strategy_name=config.name,
        strategy_version=strategy_version,
        strategy_snapshot=snapshot,
        universe=config.universe,
        universe_size=len(instruments),
        timeframe=config.timeframe,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        calculation_version=CALCULATION_VERSION,
    )
    asyncio.create_task(_runner(run.id, config, instruments, start_date, end_date, initial_capital))
    return run_status_payload(run)


async def _runner(
    run_id: uuid.UUID,
    config: StrategyDefinitionConfig,
    instruments: list[dict[str, str | None]],
    start_date: date,
    end_date: date,
    initial_capital: float,
) -> None:
    _active_runs.add(run_id)
    try:
        await execute_run(
            run_id=run_id,
            config=config,
            instruments=instruments,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
        )
    except Exception as exc:
        logger.exception("Strategy test run failed | run_id=%s | err=%s", run_id, exc)
        await persistence.update_run(
            run_id,
            status="failed",
            stage="failed",
            error_code="STRATEGY_TEST_FAILED",
            error_detail=_public_error(exc),
            completed_at=_utc(),
            progress_pct=100,
        )
    finally:
        _active_runs.discard(run_id)
        _cancel_requested.discard(run_id)


async def execute_run(
    *,
    run_id: uuid.UUID,
    config: StrategyDefinitionConfig,
    instruments: list[dict[str, str | None]],
    start_date: date,
    end_date: date,
    initial_capital: float,
) -> None:
    total = len(instruments)
    await persistence.update_run(
        run_id,
        status="running",
        stage="loading_universe",
        total_count=total,
        processed_count=0,
        progress_pct=0,
        data_timestamp=_utc(),
    )
    if is_cancel_requested(run_id):
        await _mark_cancelled(run_id)
        return

    symbols = [str(item["symbol"]) for item in instruments if item.get("symbol")]
    store_symbols = [
        str(item.get("store_symbol") or item["symbol"])
        for item in instruments
        if item.get("symbol")
    ]
    company_map = {str(item["symbol"]): item.get("company") for item in instruments}
    warmup = required_warmup(config)
    from_date = start_date - timedelta(days=max(warmup * 2, 420))

    await persistence.update_run(run_id, stage="ensuring_market_data")
    ensure_result = await ensure_universe_market_data(store_symbols)
    logger.info(
        "STRATEGY_TESTER_MARKET_DATA_ENSURED | run_id=%s | status=%s | universe=%s",
        run_id,
        ensure_result.get("status"),
        len(symbols),
    )

    await persistence.update_run(run_id, stage="loading_market_data")
    series_by_symbol, benchmark_series, data_source = await prepare_scan_market_data(
        symbols,
        from_date=from_date,
        to_date=end_date,
        need_benchmark=uses_benchmark(config),
    )
    logger.info(
        "STRATEGY_TESTER_BARS_LOADED | run_id=%s | universe=%s | with_bars=%s | source=%s",
        run_id,
        len(symbols),
        len(series_by_symbol),
        data_source,
    )

    await persistence.update_run(run_id, stage="evaluating")
    results: list[StrategyEvaluationResult] = []
    buy = watch = reject = 0
    for index, symbol in enumerate(symbols, start=1):
        if is_cancel_requested(run_id):
            await _mark_cancelled(
                run_id,
                processed_count=index - 1,
                total_count=total,
                buy_count=buy,
                watch_count=watch,
                reject_count=reject,
            )
            return
        try:
            row = evaluate_stock(
                symbol=symbol,
                company=company_map.get(symbol),
                series=series_by_symbol.get(symbol),
                strategy=config,
                start_date=start_date,
                end_date=end_date,
                benchmark=benchmark_series,
            )
        except Exception as exc:
            logger.warning("Strategy tester skipped symbol | symbol=%s | err=%s", symbol, exc)
            row = evaluate_stock(
                symbol=symbol,
                company=company_map.get(symbol),
                series=None,
                strategy=config,
                start_date=start_date,
                end_date=end_date,
                benchmark=benchmark_series,
            )
            row.status = "error"
            row.error_detail = str(exc)
            row.primary_failure_reason = "evaluation_error"
        results.append(row)
        if row.signal == BUY:
            buy += 1
        elif row.signal == WATCH:
            watch += 1
        elif row.signal == REJECT:
            reject += 1
        if index % _PROGRESS_EVERY == 0 or index == total:
            await persistence.update_run(
                run_id,
                status="running",
                stage="evaluating",
                processed_count=index,
                total_count=total,
                progress_pct=int(index / total * 100) if total else 100,
                current_symbol=symbol,
                buy_count=buy,
                watch_count=watch,
                reject_count=reject,
            )

    await persistence.update_run(run_id, stage="aggregating", processed_count=total, progress_pct=99)
    with_ret = [r for r in results if r.return_pct is not None]
    ordered = sorted(with_ret, key=lambda r: float(r.return_pct or 0), reverse=True)
    rank_map = {r.symbol: i + 1 for i, r in enumerate(ordered)}
    no_ret = [r for r in results if r.return_pct is None]
    for i, r in enumerate(no_ret, start=len(ordered) + 1):
        rank_map[r.symbol] = i

    summary = summarize_results(results, config, universe_size=total)
    summary["initial_capital"] = initial_capital
    summary["calculation_version"] = CALCULATION_VERSION
    summary["data_source"] = data_source
    eval_dates = [r.evaluation_date.isoformat() for r in results if r.evaluation_date]
    date_counts: dict[str, int] = {}
    for day in eval_dates:
        date_counts[day] = date_counts.get(day, 0) + 1
    scan_as_of = max(date_counts, key=date_counts.get) if date_counts else None  # type: ignore[arg-type]
    summary["scan_as_of"] = scan_as_of
    summary["scan_date_counts"] = date_counts
    summary["scan_date_mismatch"] = len(date_counts) > 1
    if scan_as_of and end_date.isoformat() != scan_as_of:
        summary["scan_bar_note"] = (
            f"Evaluated last bar {scan_as_of}. TradingView Pine Screener uses the last 1D candle; "
            "compare Close and Prior 252 High on this Scan Date."
        )
    payload_rows = []
    for r in results:
        payload_rows.append(r.to_row(rank=rank_map.get(r.symbol)))
    await persistence.save_results(run_id, payload_rows)
    await persistence.save_filter_stats(run_id, summary.get("filter_analytics") or [], summary.get("filter_funnel") or [])
    await persistence.update_run(
        run_id,
        status="completed",
        stage="completed",
        processed_count=total,
        total_count=total,
        progress_pct=100,
        current_symbol=None,
        buy_count=summary.get("buy") or 0,
        watch_count=summary.get("watch") or 0,
        reject_count=summary.get("reject") or 0,
        summary=summary,
        completed_at=_utc(),
        error_code=None,
        error_detail=None,
    )


async def load_universe(universe: str) -> list[dict[str, str | None]]:
    """Load the live 755-name NIFTY 500 universe (stocks_master), never a truncated subset.

    ALL_755 / NIFTY500 always resolve to active NIFTY 500 membership. If the
    database is truncated (the historical 65-name workstation bug), membership
    is completed from the bundled NIFTY 500 CSV so a scan still covers the
    full live universe.
    """
    code = (universe or DEFAULT_UNIVERSE).upper().replace(" ", "")
    rows: list[dict[str, str | None]] = []
    seen: set[str] = set()

    instruments = await UniverseService.list_active_instruments("NIFTY500")
    if not instruments and code in _NIFTY500_UNIVERSE_CODES:
        # All-active is the same 755-name live set when NIFTY500 flags are missing.
        try:
            instruments = await UniverseService.list_active_instruments(None)
        except Exception:
            logger.exception("Strategy tester all-active universe load failed")
            instruments = []

    for inst in instruments:
        symbol = canonical_symbol(inst.symbol) or inst.symbol
        if not symbol or symbol in seen:
            continue
        if is_dummy_universe_symbol(symbol):
            continue
        seen.add(symbol)
        store = getattr(inst, "universe_symbol", None) or f"{symbol}-EQ"
        rows.append({"symbol": symbol, "company": inst.company_name, "store_symbol": store})

    if len(rows) < _MIN_FULL_UNIVERSE:
        csv_added = _merge_csv_universe(rows, seen)
        logger.warning(
            "STRATEGY_TESTER_UNIVERSE_BACKFILLED | db=%s | csv_added=%s | total=%s | universe=%s",
            len(rows) - csv_added,
            csv_added,
            len(rows),
            code,
        )

    logger.info("STRATEGY_TESTER_UNIVERSE_LOADED | universe=%s | count=%s", code, len(rows))
    if not rows:
        logger.warning("Strategy tester universe is empty | universe=%s", code)
    return rows


def _merge_csv_universe(rows: list[dict[str, str | None]], seen: set[str]) -> int:
    csv_path = ROOT_DIR / getattr(settings, "nifty500_csv_path", "ind_nifty500list.csv")
    if not csv_path.exists():
        csv_path = ROOT_DIR / "ind_nifty500list.csv"
    try:
        csv_rows = load_unique_nifty500_csv_rows(csv_path)
    except TypeError:
        csv_rows = []
    except Exception:
        logger.exception("Strategy tester CSV universe load failed")
        csv_rows = []
    added = 0
    for item in csv_rows:
        symbol = item.get("canonical_symbol") or canonical_symbol(item.get("symbol") or "")
        if not symbol or symbol in seen:
            continue
        if is_dummy_universe_symbol(symbol):
            continue
        seen.add(symbol)
        rows.append({"symbol": symbol, "company": item.get("company_name"), "store_symbol": f"{symbol}-EQ"})
        added += 1
    return added


async def load_bar_series(
    symbols: list[str],
    *,
    from_date: date,
    to_date: date,
    session_dates: set[date] | None = None,
) -> dict[str, BarSeries]:
    if not symbols:
        return {}
    query_symbols: list[str] = []
    seen_query: set[str] = set()
    for s in symbols:
        for variant in ohlcv_symbol_variants(s):
            if variant not in seen_query:
                seen_query.add(variant)
                query_symbols.append(variant)
    rows = await fetch_daily_ohlcv_for_symbols(
        query_symbols,
        columns=(
            DailyOhlcv.trade_date,
            DailyOhlcv.symbol,
            DailyOhlcv.open,
            DailyOhlcv.high,
            DailyOhlcv.low,
            DailyOhlcv.close,
            DailyOhlcv.volume,
        ),
        from_date=from_date,
        to_date=to_date,
    )
    buckets: dict[str, list[tuple]] = defaultdict(list)
    for trade_date, symbol, open_px, high, low, close, volume in rows:
        canon = canonical_symbol(symbol) or symbol
        buckets[canon].append((trade_date, open_px, high, low, close, volume))
    out: dict[str, BarSeries] = {}
    for symbol, items in buckets.items():
        items.sort(key=lambda row: row[0])
        out[symbol] = _series_from_rows(items, session_dates=session_dates)
    return out


def _tuple_cloned(current: tuple, previous: tuple) -> bool:
    return all(_same_px(_num(current[i]), _num(previous[i])) for i in range(1, 6))


def _series_from_rows(
    items: list[tuple],
    *,
    session_dates: set[date] | None = None,
    apply_holiday_calendar: bool = True,
) -> BarSeries:
    from ...services.market_data_ingestion.nse_sessions import filter_session_ohlcv_rows

    ordered, _stats = filter_session_ohlcv_rows(
        items,
        session_dates=session_dates,
        apply_holiday_calendar=apply_holiday_calendar,
    )
    return BarSeries(
        dates=[row[0] for row in ordered],
        open=[_num(row[1]) for row in ordered],
        high=[_num(row[2]) for row in ordered],
        low=[_num(row[3]) for row in ordered],
        close=[_num(row[4]) for row in ordered],
        volume=[_num(row[5]) for row in ordered],
    )


async def prepare_scan_market_data(
    symbols: list[str],
    *,
    from_date: date,
    to_date: date,
    need_benchmark: bool,
    fill_timeout_s: float | None = None,
    overlay_live: bool = True,
) -> tuple[dict[str, BarSeries], BarSeries | None, str]:
    """Load the 755-name live OHLCV store, fill gaps, overlay today's FYERS bar."""
    from ...services.market_data_ingestion.nse_sessions import nse_session_dates

    benchmark_series = await load_benchmark_series(from_date=from_date, to_date=to_date)
    session_dates = nse_session_dates(
        from_date,
        to_date,
        index_dates=benchmark_series.dates if benchmark_series is not None else None,
    )
    if need_benchmark and benchmark_series is None:
        logger.warning("Strategy tester benchmark index series unavailable; market-gate filters will be unevaluable")
    if not need_benchmark:
        # Index was loaded only to pin the NSE cash session calendar.
        pass

    series_by_symbol = await load_bar_series(
        symbols, from_date=from_date, to_date=to_date, session_dates=session_dates
    )
    sources = ["daily_ohlcv"]
    filled = await fill_missing_from_historical_candles(
        symbols,
        series_by_symbol,
        from_date=from_date,
        to_date=to_date,
        session_dates=session_dates,
    )
    if filled:
        sources.append("historical_candles")

    from ...utils.datetime_utils import ist_now as _ist_now

    if overlay_live and to_date >= _ist_now().date():
        series_by_symbol, benchmark_series, live_source = await overlay_live_session(
            series_by_symbol,
            symbols,
            end_date=to_date,
            benchmark=benchmark_series,
            fill_timeout_s=fill_timeout_s,
        )
        if live_source and live_source != "stored_eod":
            sources.append(live_source)
    return series_by_symbol, benchmark_series, "+".join(sources)


async def ensure_universe_market_data(
    symbols: list[str],
    *,
    target_date: date | None = None,
    max_duration_s: float = 45.0,
) -> dict[str, Any]:
    """Refresh the strategy-grade daily_ohlcv store for the live 755-name universe."""
    try:
        from ...services.market_data_ingestion.ensure import ensure_latest_market_data

        budget = max(5.0, float(max_duration_s))
        return await asyncio.wait_for(
            ensure_latest_market_data(
                symbols=symbols or None,
                target_date=target_date,
                trigger_source="SCANNER",
                max_duration_s=budget,
            ),
            timeout=budget + 5.0,
        )
    except asyncio.TimeoutError:
        logger.warning("STRATEGY_TESTER_ENSURE_TIMEOUT | universe=%s", len(symbols))
        return {"status": "TIMEOUT", "error": "ensure_outer_timeout"}
    except Exception as exc:
        logger.warning("STRATEGY_TESTER_ENSURE_FAILED | err=%s", type(exc).__name__)
        return {"status": "FAILED", "error": type(exc).__name__}


def _same_px(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return False
    return abs(float(left) - float(right)) < 1e-6


def is_cloned_session_bar(series: BarSeries, bar: dict[str, float]) -> bool:
    """True when `bar` is the previous session stamped onto a new date.

    Weekend FYERS quotes still carry Thursday's OHLC. Stamping them as Friday
    makes `ta.highest(high, 252)[1]` include Thursday's breakout high, so the
    52W scan collapses to names that closed *at* that high (LAURUSLABS-only).
    """
    if not series.dates:
        return False
    close = _num(bar.get("close"))
    if close is None or close <= 0:
        return False
    open_px = _num(bar.get("open"))
    high = _num(bar.get("high"))
    low = _num(bar.get("low"))
    volume = _num(bar.get("volume"))
    if open_px is None:
        open_px = close
    if high is None:
        high = close
    if low is None:
        low = close
    if volume is None:
        volume = 0.0
    prev_close = series.close[-1]
    if (
        _same_px(close, prev_close)
        and _same_px(open_px, series.open[-1])
        and _same_px(high, series.high[-1])
        and _same_px(low, series.low[-1])
        and _same_px(volume, series.volume[-1])
    ):
        return True
    if (
        _same_px(open_px, close)
        and _same_px(high, close)
        and _same_px(low, close)
        and float(volume) == 0.0
        and _same_px(close, prev_close)
    ):
        return True
    return False


def apply_live_bar(series: BarSeries, session: date, bar: dict[str, float]) -> BarSeries:
    """Replace or append today's live 1D bar. Does not invent a series from scratch."""
    open_px = _num(bar.get("open"))
    high = _num(bar.get("high"))
    low = _num(bar.get("low"))
    close = _num(bar.get("close"))
    volume = _num(bar.get("volume"))
    if close is None or close <= 0:
        return series
    if open_px is None:
        open_px = close
    if high is None:
        high = close
    if low is None:
        low = close
    if volume is None:
        volume = 0.0
    payload = {"open": open_px, "high": high, "low": low, "close": close, "volume": volume}
    if series.dates and series.dates[-1] == session:
        i = len(series.dates) - 1
        series.open[i] = open_px
        series.high[i] = high
        series.low[i] = low
        series.close[i] = close
        series.volume[i] = volume
        series.cache.clear()
        return series
    if series.dates and series.dates[-1] > session:
        return series
    if series.dates and is_cloned_session_bar(series, payload):
        return series
    series.dates.append(session)
    series.open.append(open_px)
    series.high.append(high)
    series.low.append(low)
    series.close.append(close)
    series.volume.append(volume)
    series.cache.clear()
    return series


def _symbol_last_date(series_by_symbol: dict[str, BarSeries], symbol: str) -> date | None:
    canon = canonical_symbol(symbol) or symbol
    series = series_by_symbol.get(canon)
    if series is None or not series.dates:
        return None
    return series.dates[-1]


def _fill_probe_symbols(symbols: list[str], series_by_symbol: dict[str, BarSeries]) -> list[str]:
    have = {canonical_symbol(s) or s for s in series_by_symbol}
    probe: list[str] = []
    for name in _FILL_PROBE_NAMES:
        if name in have or name in series_by_symbol:
            probe.append(name)
    if len(probe) >= 2:
        return probe[:3]
    for symbol in symbols:
        canon = canonical_symbol(symbol) or symbol
        if canon not in probe:
            probe.append(canon)
        if len(probe) >= 3:
            break
    return probe[:3]


async def _has_genuine_completed_session(
    series_by_symbol: dict[str, BarSeries],
    probe: list[str],
    target: date,
) -> bool:
    """True only if FYERS history has a real target session, not a cloned previous bar."""
    if not probe:
        return False
    try:
        from ...services.strategies.breakout52w.session_overlay import fetch_missing_completed_bars

        by_session, _index_by, _persist, _index_persist = await asyncio.wait_for(
            fetch_missing_completed_bars(probe, target, target),
            timeout=_PROBE_HISTORY_TIMEOUT_S,
        )
    except Exception:
        logger.info("STRATEGY_TESTER_FILL_PROBE_FAILED | target=%s | probe=%s", target.isoformat(), probe)
        return False
    bars = by_session.get(target) or {}
    for symbol, bar in bars.items():
        canon = canonical_symbol(symbol) or symbol
        series = series_by_symbol.get(canon)
        payload = {
            "open": bar.get("open") or bar.get("close"),
            "high": bar["high"],
            "low": bar["low"],
            "close": bar["close"],
            "volume": bar.get("volume") or 0.0,
        }
        if series is None or len(series) == 0:
            if payload["close"]:
                return True
            continue
        if not is_cloned_session_bar(series, payload):
            return True
    return False


async def fill_missing_completed_bar_series(
    series_by_symbol: dict[str, BarSeries],
    symbols: list[str],
    *,
    end_date: date,
    benchmark: BarSeries | None,
    timeout_s: float | None = None,
) -> tuple[dict[str, BarSeries], BarSeries | None, str]:
    """Bring stored EOD up to the last completed NSE session (same bar Pine Screener uses after close).

    Fill is per-symbol. A single liquid name that already has Friday must not skip
    Thursday names — that mixed tape is why Labs BUY lists diverged from TradingView.
    """
    try:
        from ...services.market_data_ingestion.calendar_utils import expected_last_completed_session
        from ...services.strategies.breakout52w.session_overlay import fetch_missing_completed_bars
    except Exception:
        logger.exception("STRATEGY_TESTER_COMPLETED_FILL_IMPORT_FAILED")
        return series_by_symbol, benchmark, "stored_eod"

    target = expected_last_completed_session()
    if target > end_date:
        target = end_date

    stale: list[str] = []
    gap_from = target
    newest: date | None = None
    for symbol in symbols:
        last = _symbol_last_date(series_by_symbol, symbol)
        if last is not None:
            newest = last if newest is None else max(newest, last)
        if last is None or last < target:
            stale.append(symbol)
            start = last + timedelta(days=1) if last is not None else target
            if start < gap_from:
                gap_from = start

    bench_last = benchmark.dates[-1] if benchmark is not None and benchmark.dates else None
    bench_stale = bench_last is None or bench_last < target
    if not stale and not bench_stale:
        return series_by_symbol, benchmark, "stored_eod"

    logger.info(
        "STRATEGY_TESTER_FILL_COMPLETED | stored_newest=%s | stale=%s | target=%s | gap_from=%s | end_date=%s",
        newest.isoformat() if newest else None,
        len(stale),
        target.isoformat(),
        gap_from.isoformat(),
        end_date.isoformat(),
    )
    probe = _fill_probe_symbols(stale or symbols, series_by_symbol)
    if not await _has_genuine_completed_session(series_by_symbol, probe, target):
        logger.info(
            "STRATEGY_TESTER_FILL_SKIP_NO_NEW_SESSION | target=%s | stored_newest=%s | stale=%s",
            target.isoformat(),
            newest.isoformat() if newest else None,
            len(stale),
        )
        return series_by_symbol, benchmark, "stored_eod"
    try:
        fill_timeout = _FILL_HISTORY_TIMEOUT_S if timeout_s is None else timeout_s
        by_session, index_by, persist, index_persist = await asyncio.wait_for(
            fetch_missing_completed_bars(stale, gap_from, target),
            timeout=fill_timeout,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "STRATEGY_TESTER_FILL_TIMEOUT | stale=%s | target=%s | timeout_s=%s",
            len(stale),
            target.isoformat(),
            _FILL_HISTORY_TIMEOUT_S if timeout_s is None else timeout_s,
        )
        return series_by_symbol, benchmark, "stored_eod"
    except Exception:
        logger.exception("STRATEGY_TESTER_COMPLETED_HISTORY_FAILED")
        return series_by_symbol, benchmark, "stored_eod"
    if not by_session and not index_by:
        logger.warning(
            "STRATEGY_TESTER_COMPLETED_HISTORY_EMPTY | stored_newest=%s | stale=%s | target=%s",
            newest.isoformat() if newest else None,
            len(stale),
            target.isoformat(),
        )
        return series_by_symbol, benchmark, "stored_eod"

    applied = 0
    for session in sorted(by_session):
        if session > end_date:
            continue
        for symbol, bar in by_session[session].items():
            canon = canonical_symbol(symbol) or symbol
            existing = series_by_symbol.get(canon)
            if existing is None or len(existing) == 0:
                continue
            payload = {
                "open": bar.get("open") or bar["close"],
                "high": bar["high"],
                "low": bar["low"],
                "close": bar["close"],
                "volume": bar.get("volume") or 0.0,
            }
            series_by_symbol[canon] = apply_live_bar(existing, session, payload)
            applied += 1
        idx_close = index_by.get(session)
        if idx_close is not None and idx_close > 0 and benchmark is not None and len(benchmark) > 0:
            apply_live_bar(
                benchmark,
                session,
                {"open": idx_close, "high": idx_close, "low": idx_close, "close": idx_close, "volume": 0.0},
            )
    logger.info(
        "STRATEGY_TESTER_FILL_COMPLETED_APPLIED | sessions=%s | bars=%s | index=%s",
        len(by_session),
        applied,
        len(index_by),
    )
    try:
        from ...services.market_data_ingestion.repository import upsert_daily_bars, upsert_index_bars

        if persist:
            keep = []
            for row in persist:
                session = row.get("trade_date")
                canon = canonical_symbol(str(row.get("symbol") or "")) or str(row.get("symbol") or "")
                series = series_by_symbol.get(canon)
                if series is None or not series.dates or session not in series.dates:
                    continue
                keep.append(row)
            if keep:
                await upsert_daily_bars(keep)
        if index_persist:
            keep_idx = []
            for row in index_persist:
                session = row.get("trade_date")
                if benchmark is None or not benchmark.dates or session not in benchmark.dates:
                    continue
                keep_idx.append(row)
            if keep_idx:
                await upsert_index_bars(keep_idx)
    except Exception:
        logger.exception("STRATEGY_TESTER_COMPLETED_PERSIST_FAILED")
    return series_by_symbol, benchmark, "completed_history"


async def overlay_live_session(
    series_by_symbol: dict[str, BarSeries],
    symbols: list[str],
    *,
    end_date: date,
    benchmark: BarSeries | None,
    fill_timeout_s: float | None = None,
) -> tuple[dict[str, BarSeries], BarSeries | None, str]:
    """Fill last completed NSE session, then overlay today's live 1D bar (Pine Screener candle)."""
    series_by_symbol, benchmark, fill_source = await fill_missing_completed_bar_series(
        series_by_symbol,
        symbols,
        end_date=end_date,
        benchmark=benchmark,
        timeout_s=fill_timeout_s,
    )
    try:
        from ...services.market_data_ingestion.calendar_utils import expected_last_completed_session
        from ...services.strategies.breakout52w.session_overlay import (
            fetch_live_session_bars,
            should_overlay_session,
        )
    except Exception:
        logger.exception("STRATEGY_TESTER_LIVE_OVERLAY_IMPORT_FAILED")
        return series_by_symbol, benchmark, fill_source

    session = should_overlay_session([], None)
    if session is None:
        # Overlay helper can fail while the cash session is already open. If the
        # caller asked for today's 1D bar (Pine Screener), still fetch live quotes.
        try:
            from ...services.market_data_ingestion.nse_sessions import is_nse_cash_session
            from ...services.trading_hours_service import OPEN_TIME, TradingHoursService, trading_hours

            th = trading_hours if trading_hours is not None else TradingHoursService()
            ist = th.now_ist()
            if is_nse_cash_session(end_date) and end_date == ist.date() and ist.time() >= OPEN_TIME:
                session = end_date
        except Exception:
            logger.warning("STRATEGY_TESTER_LIVE_SESSION_FALLBACK_FAILED", exc_info=True)
    if session is None or session > end_date:
        # Weekend/holiday: do not stamp last quotes onto a new date (that cloned
        # Thursday onto Friday and froze the scanner on 755 FYERS quote calls).
        return series_by_symbol, benchmark, fill_source
    quote_timeout = _LIVE_QUOTE_TIMEOUT_S if fill_timeout_s is None else min(_LIVE_QUOTE_TIMEOUT_S, float(fill_timeout_s))
    try:
        bars, index_close = await asyncio.wait_for(
            fetch_live_session_bars(symbols),
            timeout=quote_timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("STRATEGY_TESTER_LIVE_QUOTES_TIMEOUT | session=%s | universe=%s", session, len(symbols))
        return series_by_symbol, benchmark, fill_source
    except Exception:
        logger.exception("STRATEGY_TESTER_LIVE_QUOTES_FAILED")
        return series_by_symbol, benchmark, fill_source
    if not bars:
        logger.warning("STRATEGY_TESTER_LIVE_SESSION_EMPTY | session=%s | universe=%s", session, len(symbols))
        return series_by_symbol, benchmark, fill_source

    applied = 0
    persist: list[dict[str, Any]] = []
    for symbol, bar in bars.items():
        canon = canonical_symbol(symbol) or symbol
        existing = series_by_symbol.get(canon)
        if existing is None or len(existing) == 0:
            continue
        series_by_symbol[canon] = apply_live_bar(existing, session, bar)
        updated = series_by_symbol[canon]
        if not updated.dates or updated.dates[-1] != session:
            continue
        applied += 1
        persist.append(
            {
                "trade_date": session,
                "symbol": f"{canon}-EQ" if not canon.endswith("-EQ") else canon,
                "open": float(bar.get("open") or bar["close"]),
                "high": float(bar["high"]),
                "low": float(bar["low"]),
                "close": float(bar["close"]),
                "volume": int(bar.get("volume") or 0),
                "source": "FYERS_LIVE_1D",
            }
        )
    index_applied = False
    if index_close is not None and index_close > 0 and benchmark is not None and len(benchmark) > 0:
        apply_live_bar(benchmark, session, {"open": index_close, "high": index_close, "low": index_close, "close": index_close, "volume": 0.0})
        index_applied = bool(benchmark.dates and benchmark.dates[-1] == session)
    logger.info(
        "STRATEGY_TESTER_LIVE_SESSION | session=%s | quotes=%s | applied=%s | cloned_skipped=%s",
        session,
        len(bars),
        applied,
        max(0, len(bars) - applied),
    )
    if applied == 0:
        return series_by_symbol, benchmark, fill_source
    try:
        from ...services.market_data_ingestion.repository import upsert_daily_bars, upsert_index_bars

        if persist:
            await upsert_daily_bars(persist)
        if index_applied and index_close is not None and index_close > 0:
            await upsert_index_bars(
                [
                    {
                        "trade_date": session,
                        "symbol": getattr(settings, "strategy_index_store_symbol", None) or "NIFTY500",
                        "open": float(index_close),
                        "high": float(index_close),
                        "low": float(index_close),
                        "close": float(index_close),
                        "volume": 0,
                        "source": "FYERS_LIVE_1D",
                    }
                ]
            )
    except Exception:
        logger.exception("STRATEGY_TESTER_LIVE_1D_PERSIST_FAILED | session=%s", session)
    return series_by_symbol, benchmark, "live_session"


async def fill_missing_from_historical_candles(
    symbols: list[str],
    series_by_symbol: dict[str, BarSeries],
    *,
    from_date: date,
    to_date: date,
    session_dates: set[date] | None = None,
) -> int:
    """Fill names the strategy-grade store missed from the Production 1D candle table."""
    missing = [s for s in symbols if s not in series_by_symbol or len(series_by_symbol.get(s) or []) == 0]
    if not missing:
        return 0
    try:
        from sqlalchemy import select

        from ...db.session import AsyncSessionLocal
        from ...models.market_data import HistoricalCandle
        from ...services.market_data_ingestion.repository import extend_scan_statement_timeout
    except Exception:
        logger.exception("STRATEGY_TESTER_CANDLE_FALLBACK_IMPORT_FAILED")
        return 0

    query_symbols: list[str] = []
    seen_query: set[str] = set()
    for s in missing:
        for variant in ohlcv_symbol_variants(s):
            if variant not in seen_query:
                seen_query.add(variant)
                query_symbols.append(variant)

    rows: list[Any] = []
    try:
        async with AsyncSessionLocal() as db:
            await extend_scan_statement_timeout(db)
            for chunk in iter_symbol_chunks(query_symbols):
                stmt = select(
                    HistoricalCandle.timestamp,
                    HistoricalCandle.symbol,
                    HistoricalCandle.open,
                    HistoricalCandle.high,
                    HistoricalCandle.low,
                    HistoricalCandle.close,
                    HistoricalCandle.volume,
                ).where(
                    HistoricalCandle.symbol.in_(chunk),
                    HistoricalCandle.resolution.in_(("1D", "D", "1d")),
                )
                rows.extend((await db.execute(stmt)).all())
    except Exception:
        logger.exception("STRATEGY_TESTER_CANDLE_FALLBACK_FAILED | missing=%s", len(missing))
        return 0

    buckets: dict[str, list[tuple]] = defaultdict(list)
    for ts, symbol, open_px, high, low, close, volume in rows:
        session = ts.date() if hasattr(ts, "date") else ts
        if session < from_date or session > to_date:
            continue
        canon = canonical_symbol(symbol) or symbol
        buckets[canon].append((session, open_px, high, low, close, volume))

    filled = 0
    for symbol, items in buckets.items():
        if symbol in series_by_symbol and len(series_by_symbol[symbol]) > 0:
            continue
        items.sort(key=lambda row: row[0])
        series_by_symbol[symbol] = _series_from_rows(items, session_dates=session_dates)
        filled += 1
    if filled:
        logger.info("STRATEGY_TESTER_CANDLE_FALLBACK | missing=%s | filled=%s", len(missing), filled)
    return filled


async def load_benchmark_series(
    *,
    from_date: date,
    to_date: date,
) -> BarSeries | None:
    """Benchmark index bars (NIFTY 500) for market-gate filters, from the strategy index store."""
    symbol = getattr(settings, "strategy_index_store_symbol", None) or "NIFTY500"
    rows = await fetch_index_history(symbol, from_date=from_date)
    rows = [r for r in rows if r.get("trade_date") and r["trade_date"] <= to_date]
    if not rows:
        return None
    tuples = [
        (r["trade_date"], r.get("open"), r.get("high"), r.get("low"), r.get("close"), r.get("volume"))
        for r in rows
    ]
    return _series_from_rows(tuples, apply_holiday_calendar=False)


def run_status_payload(run) -> dict[str, Any]:
    elapsed = None
    if run.started_at:
        end = run.completed_at or run.cancelled_at or _utc()
        started = run.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        elapsed = max(0, int((end - started).total_seconds()))
    summary = run.summary if isinstance(run.summary, dict) else {}
    return {
        "id": str(run.id),
        "run_id": run.public_run_id,
        "strategy_name": run.strategy_name,
        "strategy_version": run.strategy_version,
        "strategy_snapshot": run.strategy_snapshot,
        "universe": run.universe,
        "universe_size": run.universe_size,
        "universe_label": f"{run.universe_size} Stocks" if run.universe_size else "755 Stocks",
        "timeframe": run.timeframe,
        "start_date": run.start_date.isoformat() if run.start_date else None,
        "end_date": run.end_date.isoformat() if run.end_date else None,
        "initial_capital": run.initial_capital,
        "calculation_version": run.calculation_version,
        "data_timestamp": run.data_timestamp.isoformat() if run.data_timestamp else None,
        "status": run.status,
        "stage": run.stage,
        "progress_pct": run.progress_pct,
        "processed_count": run.processed_count,
        "total_count": run.total_count,
        "buy": run.buy_count,
        "watch": run.watch_count,
        "reject": run.reject_count,
        "current_symbol": run.current_symbol,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "cancelled_at": run.cancelled_at.isoformat() if run.cancelled_at else None,
        "elapsed_seconds": elapsed,
        "error_code": run.error_code,
        "error_detail": run.error_detail,
        "summary": summary,
    }


def history_row(run) -> dict[str, Any]:
    summary = run.summary if isinstance(run.summary, dict) else {}
    return {
        "id": str(run.id),
        "run_id": run.public_run_id,
        "strategy": run.strategy_name,
        "strategy_name": run.strategy_name,
        "run_date": run.started_at.isoformat() if run.started_at else None,
        "stocks": run.universe_size or run.total_count,
        "buy": run.buy_count,
        "watch": run.watch_count,
        "reject": run.reject_count,
        "top_return": summary.get("top_return"),
        "worst_return": summary.get("worst_return"),
        "status": run.status,
        "universe": run.universe,
        "timeframe": run.timeframe,
    }


def result_payload(row) -> dict[str, Any]:
    indicators = row.indicators or {}
    return {
        "rank": row.rank,
        "symbol": row.symbol,
        "company": row.company,
        "status": row.status,
        "signal": row.signal,
        "entry_price": row.entry_price,
        "exit_price": row.exit_price,
        "return_pct": row.return_pct,
        "return_bucket": row.return_bucket,
        "return_formula": row.return_formula,
        "rsi": indicators.get("rsi_14"),
        "sma_20": indicators.get("sma_20"),
        "sma_50": indicators.get("sma_50"),
        "sma_200": indicators.get("sma_200"),
        "volume": indicators.get("volume"),
        "avg_volume": indicators.get("avg_volume_20") or indicators.get("avg_volume"),
        "close": indicators.get("close") or row.exit_price,
        "high_252": indicators.get("high_252"),
        "nifty500_close": indicators.get("nifty500_close"),
        "nifty500_sma_50": indicators.get("nifty500_sma_50"),
        "evaluation_date": _evaluation_date(indicators),
        "indicators": indicators,
        "filters_passed": len(row.passed_filters or []),
        "filters_failed": len(row.failed_filters or []),
        "passed_filters": row.passed_filters or [],
        "failed_filters": row.failed_filters or [],
        "filter_details": row.filter_details or [],
        "primary_failure_reason": row.primary_failure_reason,
        "error_detail": row.error_detail,
        "candle_count": row.candle_count,
    }


async def _mark_cancelled(run_id: uuid.UUID, **progress: Any) -> None:
    fields = {
        "status": "cancelled",
        "stage": "cancelled",
        "cancelled_at": _utc(),
        "completed_at": _utc(),
    }
    fields.update(progress)
    await persistence.update_run(run_id, **fields)


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n != n:
        return None
    return n


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _public_error(exc: BaseException) -> str:
    raw = str(exc)
    lowered = raw.lower()
    if "statement timeout" in lowered:
        return "Daily history query timed out."
    if "sql:" in lowered or len(raw) > 280:
        return "Strategy test failed while loading market data."
    return raw


def parse_run_dates(start_raw: Any, end_raw: Any) -> tuple[date, date]:
    today = _ist_today()
    start = _parse_date(start_raw) or (today - timedelta(days=365))
    end = _parse_date(end_raw) or today
    if end < today:
        # Pine Screener has no as-of picker; a leftover window end scans a different 1D bar.
        logger.info("STRATEGY_TESTER_END_DATE_ADVANCED | requested=%s | ist_today=%s", end.isoformat(), today.isoformat())
        end = today
    return start, end


def _ist_today() -> date:
    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist).date()


def _evaluation_date(indicators: dict[str, Any]) -> str | None:
    raw = indicators.get("evaluation_date")
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date().isoformat()
    if isinstance(raw, date):
        return raw.isoformat()
    text = str(raw).strip()
    return text[:10] if text else None


def _parse_date(raw: Any) -> date | None:
    if raw in (None, ""):
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    text = str(raw)[:10]
    return date.fromisoformat(text)
