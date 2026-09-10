"""Repair cloned last-session rows and thin daily histories before a scan."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any, Iterable

from ...utils.symbol import canonical_symbol
from .nse_sessions import is_nse_cash_session, nth_session_ending, session_on_or_before

logger = logging.getLogger("app.market_data_ingestion.session_repair")

THIN_HISTORY_SYMBOLS = ("STLTECH", "GSPL", "CIGNITITEC")
_MIN_VALID_BARS = 253
_THIN_LOOKBACK_CALENDAR_DAYS = 900
_REPAIR_CONCURRENCY = 4
_SESSION_FETCH_TIMEOUT_S = 300.0
_THIN_FETCH_TIMEOUT_S = 180.0


def _store_symbol(symbol: str) -> str:
    canon = canonical_symbol(symbol) or (symbol or "").strip().upper()
    if not canon:
        return symbol
    if canon.endswith("-EQ"):
        return canon
    return f"{canon}-EQ"


async def delete_cloned_session_rows(session: date, previous: date) -> int:
    """Remove OHLCV rows on `session` that are exact copies of `previous`."""
    from .repository import delete_cloned_daily_bars

    deleted = await delete_cloned_daily_bars(session, previous)
    if deleted:
        logger.info(
            "SESSION_REPAIR_DELETED_CLONES | session=%s | previous=%s | rows=%s",
            session.isoformat(),
            previous.isoformat(),
            deleted,
        )
    return deleted


async def fetch_and_upsert_session(symbols: list[str], session: date) -> dict[str, Any]:
    """Replace a session with FYERS 1D history (real EOD, not a live-quote clone)."""
    from ..strategies.breakout52w.session_overlay import fetch_missing_completed_bars
    from .repository import upsert_daily_bars, upsert_index_bars

    unique = list(dict.fromkeys(_store_symbol(s) for s in symbols if s))
    by_session, index_by, persist, index_persist = await asyncio.wait_for(
        fetch_missing_completed_bars(unique, session, session),
        timeout=_SESSION_FETCH_TIMEOUT_S,
    )
    kept: list[dict[str, Any]] = []
    for row in persist:
        if row.get("trade_date") != session:
            continue
        if row.get("close") in (None, 0, 0.0):
            continue
        kept.append(row)
    inserted = 0
    if kept:
        inserted, _ = await upsert_daily_bars(kept)
    if index_persist:
        await upsert_index_bars(index_persist)
    logger.info(
        "SESSION_REPAIR_UPSERT_SESSION | session=%s | fetched=%s | upserted=%s | index=%s",
        session.isoformat(),
        len(persist),
        inserted,
        len(index_by),
    )
    return {
        "session": session.isoformat(),
        "fetched": len(persist),
        "upserted": inserted,
        "index_bars": len(index_by),
        "symbols_with_session": len((by_session.get(session) or {})),
    }


async def backfill_symbol_history(
    symbol: str,
    *,
    end: date,
    min_bars: int = _MIN_VALID_BARS,
) -> dict[str, Any]:
    """Pull a long FYERS 1D history for a name with too few valid sessions."""
    from .providers.fyers_eod import FyersEodProvider
    from .repository import equity_date_span, upsert_daily_bars

    store = _store_symbol(symbol)
    start = nth_session_ending(end, min_bars + 40)
    # Floor at a multi-year window so IPO-age names still get every session.
    floor = end - timedelta(days=_THIN_LOOKBACK_CALENDAR_DAYS)
    if start > floor:
        start = floor
    provider = FyersEodProvider()
    rows = await asyncio.wait_for(
        provider.fetch_daily_range(store, start, end),
        timeout=_THIN_FETCH_TIMEOUT_S,
    )
    valid = [row for row in rows if row.get("trade_date") and is_nse_cash_session(row["trade_date"])]
    upserted = 0
    if valid:
        payload = []
        for row in valid:
            payload.append(
                {
                    "trade_date": row["trade_date"],
                    "symbol": store,
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": row.get("volume") or 0,
                    "source": row.get("source") or "FYERS",
                }
            )
        upserted, _ = await upsert_daily_bars(payload)
    _min, _max, count = await equity_date_span(store)
    logger.info(
        "SESSION_REPAIR_BACKFILL | symbol=%s | fetched=%s | valid=%s | upserted=%s | store_count=%s",
        store,
        len(rows),
        len(valid),
        upserted,
        count,
    )
    return {
        "symbol": store,
        "fetched": len(rows),
        "valid_sessions": len(valid),
        "upserted": upserted,
        "store_count": count,
    }


async def backfill_thin_histories(
    symbols: Iterable[str],
    *,
    end: date,
    min_bars: int = _MIN_VALID_BARS,
) -> list[dict[str, Any]]:
    unique = list(dict.fromkeys(canonical_symbol(s) or s for s in symbols if s))
    results: list[dict[str, Any]] = []
    sem = asyncio.Semaphore(_REPAIR_CONCURRENCY)

    async def one(sym: str) -> dict[str, Any]:
        async with sem:
            try:
                return await backfill_symbol_history(sym, end=end, min_bars=min_bars)
            except Exception as exc:
                logger.warning("SESSION_REPAIR_BACKFILL_FAILED | symbol=%s | err=%s", sym, type(exc).__name__)
                return {"symbol": _store_symbol(sym), "error": type(exc).__name__}

    if unique:
        results = list(await asyncio.gather(*(one(s) for s in unique)))
    return results


async def repair_scan_market_history(
    symbols: list[str],
    *,
    end: date,
    min_bars: int = _MIN_VALID_BARS,
    skip_thin: bool = False,
) -> dict[str, Any]:
    """Drop cloned last-session rows, fetch real EOD, backfill thin names."""
    try:
        from .calendar_utils import expected_last_completed_session

        last = expected_last_completed_session()
    except Exception:
        last = session_on_or_before(end)
    if end < last:
        last = session_on_or_before(end)
    deleted = 0
    prev = session_on_or_before(last - timedelta(days=1))
    try:
        cur = last
        for _ in range(6):
            prev_sess = session_on_or_before(cur - timedelta(days=1))
            deleted += await delete_cloned_session_rows(cur, prev_sess)
            cur = prev_sess
    except Exception:
        logger.exception("SESSION_REPAIR_DELETE_CLONES_FAILED | session=%s", last.isoformat())
    session_refill: dict[str, Any] = {}
    if deleted:
        try:
            session_refill = await asyncio.wait_for(fetch_and_upsert_session(symbols, last), timeout=25.0)
        except asyncio.TimeoutError:
            session_refill = {"error": "timeout"}
            logger.warning("SESSION_REPAIR_REFILL_LAST_SESSION_TIMEOUT | session=%s", last.isoformat())
        except Exception:
            logger.warning("SESSION_REPAIR_REFILL_LAST_SESSION_FAILED | session=%s", last.isoformat(), exc_info=True)
            session_refill = {"error": "refill_failed"}
    extra = [
        canonical_symbol(s) or s
        for s in symbols
        if (canonical_symbol(s) or s) in set(THIN_HISTORY_SYMBOLS)
    ]
    thin_targets = list(dict.fromkeys([*THIN_HISTORY_SYMBOLS, *extra]))
    thin_results: list[dict[str, Any]] = []
    if not skip_thin:
        thin_results = await backfill_thin_histories(thin_targets, end=last, min_bars=min_bars)
    return {
        "end_session": last.isoformat(),
        "previous_session": prev.isoformat(),
        "cloned_rows_deleted": deleted,
        "last_session_refill": session_refill,
        "thin_history": thin_results,
    }
