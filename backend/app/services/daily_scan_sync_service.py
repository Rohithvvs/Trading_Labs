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
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from ..config.settings import settings
from ..db.session import AsyncSessionLocal

logger = logging.getLogger("app.daily_scan_sync")

IST = ZoneInfo("Asia/Kolkata")

_LAST_COMPLETED_SYNC_DAY: date | None = None
_LAST_LIVE_QUOTE_SYNC_TIME: float = 0.0
_LIVE_QUOTE_REFRESH_MIN_INTERVAL_S = 15.0
# Per-symbol history for the whole universe is what restarted Render mid-scan
# (IND-20260925-009). Quotes cover the latest session in a few batched calls.
_HISTORY_BATCH = 40
_HISTORY_BUDGET_S = 20.0
_UPSERT_CHUNK = 200


def _now_ist() -> datetime:
    return datetime.now(IST)


def plan_daily_scan_sync(now: datetime, latest_stored: date | None) -> dict[str, Any]:
    """Decide the cheapest Fyers refresh that still stores the scan session.

    The latest session uses batched quotes. Older missing sessions use history,
    and only up to the day before the quote session so the same day is not
    downloaded twice.
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
    if latest_stored is None or latest_stored < history_end:
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


async def sync_daily_market_data_for_scan(
    symbols: list[str],
    *,
    force_history: bool = False,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    """Sync missing daily OHLCV and today's forming bar from FYERS into the database."""
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
        max_equity_trade_date,
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
    plan = plan_daily_scan_sync(now, latest_stored)
    today_ist = plan["today"]
    target_completed = plan["target_completed"]
    result["target_completed"] = target_completed.isoformat()
    needs_history_sync = bool(plan["history_from"]) and (
        force_history or _LAST_COMPLETED_SYNC_DAY != today_ist or latest_stored is None or latest_stored < target_completed
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
    if (
        quote_due
        and plan["quote_source"] == "FYERS"
        and latest_stored is not None
        and latest_stored >= plan["quote_session"]
        and not force_history
    ):
        # Session is already closed and stored. Do not download it again.
        quote_due = False
    elif (
        quote_due
        and _LAST_LIVE_QUOTE_SYNC_TIME
        and not needs_history_sync
        and latest_stored
        and latest_stored >= plan["quote_session"]
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
                        "symbol": sym,
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
        deadline = time.monotonic() + _HISTORY_BUDGET_S
        sessions: set[date] = set()
        try:
            for offset in range(0, len(symbols), _HISTORY_BATCH):
                if time.monotonic() >= deadline:
                    result["history_budget"] = True
                    logger.warning(
                        "DAILY_SCAN_SYNC | History budget reached after %s symbols. Scan continues with stored bars.",
                        offset,
                    )
                    break
                chunk = symbols[offset : offset + _HISTORY_BATCH]
                _by_session, _index_by, persist, index_persist = await fetch_missing_completed_bars(
                    chunk, gap_from, gap_to
                )
                if persist:
                    result["rows_upserted"] += await _upsert_daily(persist)
                if index_persist:
                    await upsert_index_bars(index_persist)
                sessions.update(_by_session)
                await asyncio.sleep(0)
            else:
                result["completed_synced"] = True
                _LAST_COMPLETED_SYNC_DAY = today_ist
            result["completed_sessions"] = [d.isoformat() for d in sorted(sessions)]
        except Exception as exc:
            logger.warning("DAILY_SCAN_SYNC | Failed fetching completed sessions: %s", exc)

    result["duration_ms"] = int((time.time() - t0) * 1000)
    return result
