"""Pre-scan market data and access token synchronization service.

Ensures that whenever a user runs a scan (especially for the first time in a day):
1. A valid FYERS access token exists (auto-generates headless via TOTP if expired/missing).
2. Any missing completed trading sessions (e.g. earlier days this week) are fetched from FYERS
   and saved to the database (daily_ohlcv and index_ohlcv).
3. If the NSE cash market has opened today, the latest live 1D bar (Open, High, Low, LTP, Volume)
   is fetched from FYERS and stored in the database.
4. Subsequent scans on the same day reuse the stored data and perform fast live quote refreshes.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from ..config.settings import settings
from ..db.session import AsyncSessionLocal

logger = logging.getLogger("app.daily_scan_sync")

IST = ZoneInfo("Asia/Kolkata")

_LAST_COMPLETED_SYNC_DAY: date | None = None
_LAST_LIVE_QUOTE_SYNC_TIME: float = 0.0
_HISTORY_FULL_PASSES: dict[date, int] = {}
_LIVE_QUOTE_REFRESH_MIN_INTERVAL_S = 15.0
# One history call per symbol covers the whole missing range. The outer scan
# wait is the hard cap so a slow FYERS pass cannot pin the process the way
# IND-20260925-009 did. A later quote day must not hide an earlier hole, and
# a short budget must not mark that hole done.
_HISTORY_BATCH = 50
_HISTORY_BUDGET_S = 150.0
_HISTORY_FULL_PASSES_PER_DAY = 2
_COVERAGE_LOOKBACK_DAYS = 45
_MIN_COVERED_SYMBOLS = 500
_UPSERT_CHUNK = 500
# Outer wait used by every scan entry. Kept above the history budget so a
# finished pass can record whether the hole is actually closed.
DAILY_SYNC_TIMEOUT_S = 180.0


def _now_ist() -> datetime:
    return datetime.now(IST)


def _coerce_session_counts(session_counts: dict[Any, int] | None) -> dict[date, int]:
    out: dict[date, int] = {}
    for key, value in (session_counts or {}).items():
        if isinstance(key, datetime):
            parsed = key.date()
        elif isinstance(key, date):
            parsed = key
        else:
            parsed = date.fromisoformat(str(key)[:10])
        out[parsed] = int(value or 0)
    return out


def _trading_days_inclusive(start: date, end: date) -> list[date]:
    from .trading_hours_service import TradingHoursService, trading_hours

    if start > end:
        return []
    hours = trading_hours if trading_hours is not None else TradingHoursService()
    days: list[date] = []
    cur = start
    while cur <= end:
        if hours.is_trading_day(datetime(cur.year, cur.month, cur.day)):
            days.append(cur)
        cur += timedelta(days=1)
    return days


def _missing_history_range(
    history_end: date,
    session_counts: dict[Any, int],
    min_covered_symbols: int,
) -> tuple[date | None, date | None]:
    """First and last trading day after the newest covered session.

    ``MAX(trade_date)`` stays on a later quote day while earlier sessions are
    empty. Coverage looks through the recent window and ignores holes that
    sit behind a fully stored session.
    """
    counts = _coerce_session_counts(session_counts)
    since = history_end - timedelta(days=_COVERAGE_LOOKBACK_DAYS)
    days = _trading_days_inclusive(since, history_end)
    covered = [day for day in days if counts.get(day, 0) >= min_covered_symbols]
    if covered:
        anchor = covered[-1]
        missing = [day for day in days if day > anchor]
    else:
        missing = [day for day in days if counts.get(day, 0) < min_covered_symbols]
    if not missing:
        return None, None
    return missing[0], missing[-1]


def plan_daily_scan_sync(
    now: datetime,
    latest_stored: date | None,
    session_counts: dict[Any, int] | None = None,
    *,
    min_covered_symbols: int = _MIN_COVERED_SYMBOLS,
) -> dict[str, Any]:
    """Decide the cheapest Fyers refresh that still stores the scan session.

    The latest session uses batched quotes. Older missing sessions use history,
    and only up to the day before the quote session so the same day is not
    downloaded twice. When session counts are provided, a later stored day does
    not hide an earlier empty session.
    """
    from .market_data_ingestion.calendar_utils import expected_last_completed_session
    from .market_data_ingestion.nse_sessions import is_nse_cash_session
    from .trading_hours_service import CLOSE_TIME, OPEN_TIME

    if now.tzinfo is None:
        now = now.replace(tzinfo=IST)
    else:
        now = now.astimezone(IST)
    today = now.date()
    target = expected_last_completed_session(now)
    session_started = is_nse_cash_session(today) and now.time() >= OPEN_TIME
    quote_session = today if session_started else None
    quote_source = "FYERS" if session_started and now.time() >= CLOSE_TIME else "FYERS_LIVE_1D"
    history_end = target
    if quote_session is not None and quote_session == target:
        history_end = target - timedelta(days=1)
    history_from: date | None = None
    history_to: date | None = None
    if session_counts is not None:
        history_from, history_to = _missing_history_range(
            history_end, session_counts, min_covered_symbols
        )
    elif latest_stored is None or latest_stored < history_end:
        history_from = (latest_stored + timedelta(days=1)) if latest_stored else (history_end - timedelta(days=10))
        if history_from <= history_end:
            history_to = history_end
    elif latest_stored < target and quote_session is None:
        history_from = latest_stored + timedelta(days=1)
        history_to = target
    return {
        "today": today,
        "target_completed": target,
        "quote_session": quote_session,
        "quote_source": quote_source,
        "history_from": history_from,
        "history_to": history_to,
    }


async def ensure_fyers_token_for_scanner() -> bool:
    """Ensure a valid, active FYERS access token is available. Auto-refreshes if needed."""
    try:
        from .fyers_service import FyersService
        svc = FyersService()
        if svc.is_fyers_sdk_available() and svc.has_fyers_credentials():
            return True

        logger.info("DAILY_SCAN_SYNC | Fyers token missing or expired; attempting auto-generation...")
        from .token_scanner_bootstrap_service import check_todays_valid_token, ensure_daily_access_token, BootstrapResult
        async with AsyncSessionLocal() as db:
            check = await check_todays_valid_token(db)
            if check["valid"] and check.get("token"):
                return True
            res = BootstrapResult()
            tok = await ensure_daily_access_token(db, res)
            if tok:
                logger.info("DAILY_SCAN_SYNC | Fyers token auto-generated and validated successfully.")
                return True
            logger.warning("DAILY_SCAN_SYNC | Fyers token auto-generation failed: %s", res.error)
            return False
    except Exception as exc:
        logger.warning("DAILY_SCAN_SYNC | Token assurance error: %s", exc)
        return False


def _store_symbol(symbol: str) -> str:
    text = str(symbol or "").strip()
    if not text:
        return text
    return text if text.endswith("-EQ") else f"{text}-EQ"


async def sync_daily_market_data_for_scan(
    symbols: list[str],
    *,
    force_history: bool = False,
    progress_callback: Any | None = None,
    history_budget_s: float | None = None,
) -> dict[str, Any]:
    """Sync missing daily OHLCV and today's forming bar from FYERS into the candle store.

    Writes go through the daily repository, which uses Turso when
    ``CANDLE_HISTORY_BACKEND=turso``. The first scan of an IST day fills every
    uncovered completed session in the recent window, then stores today's bar.
    Later scans that day reuse the stored sessions.
    """
    global _LAST_COMPLETED_SYNC_DAY, _LAST_LIVE_QUOTE_SYNC_TIME
    import time
    t0 = time.time()
    result: dict[str, Any] = {
        "status": "ok",
        "token_ready": False,
        "completed_synced": False,
        "live_synced": False,
        "completed_sessions": [],
        "rows_upserted": 0,
    }

    # 1. Ensure token
    token_ok = await ensure_fyers_token_for_scanner()
    result["token_ready"] = token_ok
    if not token_ok:
        logger.warning("DAILY_SCAN_SYNC | Skipping FYERS sync because token could not be obtained.")
        result["status"] = "skipped_no_token"
        return result

    from .market_data_ingestion.repository import (
        equity_session_counts,
        max_equity_trade_date,
        symbols_on_trade_date,
        upsert_daily_bars,
        upsert_index_bars,
    )
    from .strategies.breakout52w.session_overlay import (
        fetch_missing_completed_bars,
        fetch_live_session_bars,
    )

    async def _upsert_daily(rows: list[dict[str, Any]]) -> int:
        saved = 0
        for offset in range(0, len(rows), _UPSERT_CHUNK):
            accepted, _rejected = await upsert_daily_bars(rows[offset : offset + _UPSERT_CHUNK])
            saved += int(accepted or 0)
            await asyncio.sleep(0)
        return saved

    now = _now_ist()
    latest_stored = await max_equity_trade_date()
    coverage_since = now.date() - timedelta(days=_COVERAGE_LOOKBACK_DAYS + 5)
    session_counts: dict[date, int] | None
    try:
        session_counts = await equity_session_counts(coverage_since)
    except Exception as exc:
        session_counts = None
        logger.warning("DAILY_SCAN_SYNC | Session coverage unavailable: %s", exc)
    plan = plan_daily_scan_sync(now, latest_stored, session_counts)
    today_ist = plan["today"]
    target_completed = plan["target_completed"]
    result["target_completed"] = target_completed.isoformat()
    result["history_from"] = plan["history_from"].isoformat() if plan["history_from"] else None
    result["history_to"] = plan["history_to"].isoformat() if plan["history_to"] else None
    needs_history_sync = bool(plan["history_from"]) and (
        force_history or _LAST_COMPLETED_SYNC_DAY != today_ist
    )

    # Quotes first. One batched call stores today's OHLC without a per-symbol
    # history download, which is what exhausted the hosted server.
    time_since_last_quote = time.time() - _LAST_LIVE_QUOTE_SYNC_TIME
    quote_due = plan["quote_session"] is not None and (
        force_history
        or needs_history_sync
        or time_since_last_quote >= _LIVE_QUOTE_REFRESH_MIN_INTERVAL_S
        or latest_stored is None
        or latest_stored < plan["quote_session"]
    )
    quote_session = plan["quote_session"]
    quote_count = (session_counts or {}).get(quote_session, 0) if quote_session else 0
    quote_stored = quote_count >= _MIN_COVERED_SYMBOLS or (
        session_counts is None and latest_stored is not None and quote_session is not None and latest_stored >= quote_session
    )
    if (
        quote_due
        and plan["quote_source"] == "FYERS"
        and quote_stored
        and not force_history
    ):
        # Session is already closed and stored. Do not download it again.
        quote_due = False
    elif (
        quote_due
        and _LAST_LIVE_QUOTE_SYNC_TIME
        and not needs_history_sync
        and quote_stored
        and time_since_last_quote < _LIVE_QUOTE_REFRESH_MIN_INTERVAL_S
        and not force_history
    ):
        quote_due = False

    if quote_due:
        logger.info(
            "DAILY_SCAN_SYNC | Fetching latest 1D quotes for session %s from FYERS (%s symbols)...",
            plan["quote_session"],
            len(symbols),
        )
        try:
            live_bars, index_close = await fetch_live_session_bars(symbols)
            if live_bars:
                live_persist = [
                    {
                        "trade_date": plan["quote_session"],
                        "symbol": _store_symbol(sym),
                        "open": float(b.get("open") or b["close"]),
                        "high": float(b["high"]),
                        "low": float(b["low"]),
                        "close": float(b["close"]),
                        "volume": int(b.get("volume") or 0),
                        "source": plan["quote_source"],
                    }
                    for sym, b in live_bars.items()
                ]
                result["rows_upserted"] += await _upsert_daily(live_persist)
                logger.info(
                    "DAILY_SCAN_SYNC | Upserted %s quote bars for %s source=%s",
                    len(live_persist),
                    plan["quote_session"],
                    plan["quote_source"],
                )
            if index_close is not None and index_close > 0:
                await upsert_index_bars(
                    [
                        {
                            "trade_date": plan["quote_session"],
                            "symbol": getattr(settings, "strategy_index_store_symbol", None) or "NIFTY500",
                            "open": float(index_close),
                            "high": float(index_close),
                            "low": float(index_close),
                            "close": float(index_close),
                            "volume": 0,
                            "source": plan["quote_source"],
                        }
                    ]
                )
            result["live_synced"] = True
            _LAST_LIVE_QUOTE_SYNC_TIME = time.time()
        except Exception as exc:
            logger.warning("DAILY_SCAN_SYNC | Failed fetching live session quotes: %s", exc)

    if needs_history_sync and plan["history_from"] and plan["history_to"]:
        gap_from = plan["history_from"]
        gap_to = plan["history_to"]
        logger.info(
            "DAILY_SCAN_SYNC | Older sessions missing: latest_in_db=%s target=%s gap=%s..%s. Bounded FYERS history...",
            latest_stored,
            target_completed,
            gap_from,
            gap_to,
        )
        budget_s = _HISTORY_BUDGET_S if history_budget_s is None else max(1.0, float(history_budget_s))
        deadline = time.monotonic() + budget_s
        sessions: set[date] = set()
        present: set[str] = set()
        try:
            present = await symbols_on_trade_date(gap_to)
        except Exception as exc:
            logger.warning("DAILY_SCAN_SYNC | Could not list symbols on %s: %s", gap_to, exc)
        pending = [
            sym
            for sym in symbols
            if _store_symbol(sym) not in present and str(sym) not in present
        ]
        result["history_symbols"] = len(pending)
        result["history_already_stored"] = len(symbols) - len(pending)
        if not pending:
            result["completed_synced"] = True
            _LAST_COMPLETED_SYNC_DAY = today_ist
        else:
            rows_before = result["rows_upserted"]
            finished = False
            try:
                for offset in range(0, len(pending), _HISTORY_BATCH):
                    if time.monotonic() >= deadline:
                        result["history_budget"] = True
                        logger.warning(
                            "DAILY_SCAN_SYNC | History budget reached after %s/%s symbols. "
                            "Remaining names stay for the next scan.",
                            offset,
                            len(pending),
                        )
                        break
                    chunk = pending[offset : offset + _HISTORY_BATCH]
                    _by_session, _index_by, persist, index_persist = await fetch_missing_completed_bars(
                        chunk, gap_from, gap_to
                    )
                    if persist:
                        result["rows_upserted"] += await _upsert_daily(persist)
                    if index_persist:
                        await upsert_index_bars(index_persist)
                    sessions.update(_by_session)
                    if progress_callback is not None:
                        progress_callback(
                            {
                                "stage": "Fetching missing daily candles...",
                                "done": min(offset + len(chunk), len(pending)),
                                "total": len(pending),
                            }
                        )
                    await asyncio.sleep(0)
                else:
                    finished = True
                result["completed_sessions"] = [d.isoformat() for d in sorted(sessions)]
                if finished:
                    passes = _HISTORY_FULL_PASSES.get(today_ist, 0) + 1
                    _HISTORY_FULL_PASSES[today_ist] = passes
                    still_missing = False
                    try:
                        refreshed = await equity_session_counts(coverage_since)
                        follow = plan_daily_scan_sync(now, latest_stored, refreshed)
                        still_missing = bool(follow["history_from"])
                    except Exception as exc:
                        logger.warning("DAILY_SCAN_SYNC | Coverage recheck failed: %s", exc)
                    wrote = result["rows_upserted"] - rows_before
                    if not still_missing or wrote == 0 or passes >= _HISTORY_FULL_PASSES_PER_DAY:
                        result["completed_synced"] = True
                        _LAST_COMPLETED_SYNC_DAY = today_ist
                    else:
                        result["completed_synced"] = False
            except Exception as exc:
                logger.warning("DAILY_SCAN_SYNC | Failed fetching completed sessions: %s", exc)

    result["duration_ms"] = int((time.time() - t0) * 1000)
    return result
