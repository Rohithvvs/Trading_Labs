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


def _now_ist() -> datetime:
    return datetime.now(IST)


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

    from .market_data_ingestion.calendar_utils import expected_last_completed_session
    from .market_data_ingestion.nse_sessions import is_nse_cash_session
    from .market_data_ingestion.repository import (
        max_equity_trade_date,
        upsert_daily_bars,
        upsert_index_bars,
    )
    from .strategies.breakout52w.session_overlay import (
        fetch_missing_completed_bars,
        fetch_live_session_bars,
    )
    from .trading_hours_service import OPEN_TIME

    today_ist = _now_ist().date()
    target_completed = expected_last_completed_session()

    # 2. Check if completed history needs sync (First scan of the day catch-up)
    needs_history_sync = force_history or (_LAST_COMPLETED_SYNC_DAY != today_ist)
    if not needs_history_sync:
        latest_stored = await max_equity_trade_date()
        if latest_stored is None or latest_stored < target_completed:
            needs_history_sync = True

    if needs_history_sync:
        latest_stored = await max_equity_trade_date()
        if latest_stored is None or latest_stored < target_completed:
            gap_from = (latest_stored + timedelta(days=1)) if latest_stored else (target_completed - timedelta(days=10))
            logger.info(
                "DAILY_SCAN_SYNC | Missing completed sessions detected: latest_in_db=%s, target=%s, gap_from=%s. Fetching from FYERS...",
                latest_stored,
                target_completed,
                gap_from,
            )
            try:
                by_session, index_by, persist, index_persist = await fetch_missing_completed_bars(
                    symbols, gap_from, target_completed
                )
                if persist:
                    n_up, _ = await upsert_daily_bars(persist)
                    result["rows_upserted"] += n_up
                    logger.info("DAILY_SCAN_SYNC | Upserted %s daily bars for completed sessions %s", n_up, list(by_session.keys()))
                if index_persist:
                    await upsert_index_bars(index_persist)
                result["completed_synced"] = True
                result["completed_sessions"] = [d.isoformat() for d in sorted(by_session.keys())]
                _LAST_COMPLETED_SYNC_DAY = today_ist
            except Exception as exc:
                logger.warning("DAILY_SCAN_SYNC | Failed fetching completed sessions: %s", exc)

    # 3. Check today's forming live 1D bar
    now = _now_ist()
    market_open_today = is_nse_cash_session(today_ist) and now.time() >= OPEN_TIME
    time_since_last_quote = time.time() - _LAST_LIVE_QUOTE_SYNC_TIME

    if market_open_today and (time_since_last_quote >= _LIVE_QUOTE_REFRESH_MIN_INTERVAL_S or needs_history_sync):
        logger.info("DAILY_SCAN_SYNC | Fetching today's forming 1D bars (session %s) from FYERS...", today_ist)
        try:
            live_bars, index_close = await fetch_live_session_bars(symbols)
            if live_bars:
                live_persist = [
                    {
                        "trade_date": today_ist,
                        "symbol": sym,
                        "open": float(b.get("open") or b["close"]),
                        "high": float(b["high"]),
                        "low": float(b["low"]),
                        "close": float(b["close"]),
                        "volume": int(b.get("volume") or 0),
                        "source": "FYERS_LIVE_1D",
                    }
                    for sym, b in live_bars.items()
                ]
                n_up, _ = await upsert_daily_bars(live_persist)
                result["rows_upserted"] += n_up
                logger.info("DAILY_SCAN_SYNC | Upserted %s live bars for today (%s)", n_up, today_ist)

            if index_close is not None and index_close > 0:
                await upsert_index_bars(
                    [
                        {
                            "trade_date": today_ist,
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
            result["live_synced"] = True
            _LAST_LIVE_QUOTE_SYNC_TIME = time.time()
        except Exception as exc:
            logger.warning("DAILY_SCAN_SYNC | Failed fetching live session quotes: %s", exc)

    result["duration_ms"] = int((time.time() - t0) * 1000)
    return result
