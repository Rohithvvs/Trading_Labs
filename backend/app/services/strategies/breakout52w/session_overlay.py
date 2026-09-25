"""Overlay the 1D bar TradingView Pine Screener is looking at.

Pine Screener on the 1D timeframe uses the *current* daily candle: last price
as close and session volume so far. A scan at 13:04 IST therefore lists
today's breakouts (ACMESOLAR / IIFL / JINDALSAW / …), not yesterday's
completed EOD names.

We therefore overlay live FYERS quotes onto today's session while the cash
market is open. If quotes fail, fall back to the last completed EOD bar
rather than inventing prints.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any

from ....config.settings import settings

logger = logging.getLogger("app.strategies.w52.session")

_QUOTE_CHUNK = 50
_HISTORY_CONCURRENCY = 15


def _num(*values: Any) -> float | None:
    for raw in values:
        if raw is None or raw == "":
            continue
        try:
            n = float(raw)
        except (TypeError, ValueError):
            continue
        if n == n:  # not NaN
            return n
    return None


def parse_quote_bar(value: dict[str, Any]) -> dict[str, float] | None:
    close = _num(value.get("lp"), value.get("ltp"), value.get("close"))
    high = _num(value.get("high_price"), value.get("high"), value.get("h"), value.get("hp"), close)
    low = _num(value.get("low_price"), value.get("low"), value.get("l"), value.get("lw"), close)
    open_px = _num(value.get("open_price"), value.get("open"), value.get("o"), close)
    volume = _num(value.get("volume"), value.get("volume_traded"), value.get("v"), value.get("vol"))
    if close is None or close <= 0:
        return None
    if high is None:
        high = close
    if low is None:
        low = close
    if open_px is None:
        open_px = close
    if volume is None:
        volume = 0.0
    return {"open": open_px, "high": high, "low": low, "close": close, "volume": volume}


def apply_session_bars(
    dates: list[date],
    high_m: dict[str, dict[date, float]],
    low_m: dict[str, dict[date, float]],
    close_m: dict[str, dict[date, float]],
    vol_m: dict[str, dict[date, float]],
    index: dict[date, float],
    *,
    session: date,
    equity_bars: dict[str, dict[str, float]],
    index_close: float | None,
) -> tuple[list[date], dict, dict, dict, dict, dict[date, float]]:
    """Append or replace `session` with live daily bars. Does not invent missing names."""
    out_dates = list(dates)
    if not out_dates or out_dates[-1] < session:
        out_dates.append(session)
    elif out_dates[-1] > session:
        return dates, high_m, low_m, close_m, vol_m, index
    for sym, bar in equity_bars.items():
        high_m.setdefault(sym, {})[session] = float(bar["high"])
        low_m.setdefault(sym, {})[session] = float(bar["low"])
        close_m.setdefault(sym, {})[session] = float(bar["close"])
        vol_m.setdefault(sym, {})[session] = float(bar["volume"])
    if index_close is not None and index_close > 0:
        index[session] = float(index_close)
    return out_dates, high_m, low_m, close_m, vol_m, index


def _hours():
    from ...trading_hours_service import TradingHoursService, trading_hours

    return trading_hours if trading_hours is not None else TradingHoursService()


def _session_date(now: datetime | None = None) -> date | None:
    th = _hours()
    ist = th._to_ist(now)
    if not th.is_trading_day(ist):
        return None
    from ...trading_hours_service import OPEN_TIME

    if ist.time() < OPEN_TIME:
        return None
    return ist.date()


def cash_session_complete(now: datetime | None = None) -> bool:
    """True after 15:30 IST on a trading day."""
    from ...trading_hours_service import CLOSE_TIME

    th = _hours()
    ist = th._to_ist(now)
    if not th.is_trading_day(ist):
        return False
    return ist.time() > CLOSE_TIME


def drop_open_session_bar(dates: list[date], now: datetime | None = None) -> list[date]:
    """Remove today's date from the calendar while the cash session is still open."""
    session = _session_date(now)
    if session is None or cash_session_complete(now):
        return dates
    if dates and dates[-1] == session:
        return dates[:-1]
    return dates


def should_overlay_session(dates: list[date], now: datetime | None = None) -> date | None:
    """Overlay today's forming (or just-closed) 1D bar — same candle Pine Screener uses."""
    session = _session_date(now)
    if session is None:
        return None
    if dates and dates[-1] > session:
        return None
    return session


async def fetch_missing_completed_bars(
    symbols: list[str],
    range_from: date,
    range_to: date,
) -> tuple[dict[date, dict[str, dict[str, float]]], dict[date, float], list[dict[str, Any]], list[dict[str, Any]]]:
    """FYERS 1D history for completed sessions the EOD store has not loaded yet."""
    from ...market_data_ingestion.providers.fyers_eod import FyersEodProvider

    provider = FyersEodProvider()
    sem = asyncio.Semaphore(_HISTORY_CONCURRENCY)
    unique = list(dict.fromkeys(s for s in symbols if s))
    by_session: dict[date, dict[str, dict[str, float]]] = {}
    persist: list[dict[str, Any]] = []

    async def one(sym: str) -> None:
        async with sem:
            try:
                rows = await provider.fetch_daily_range(sym, range_from, range_to)
            except Exception:
                logger.warning("W52_COMPLETED_HISTORY_FAILED symbol=%s from=%s to=%s", sym, range_from, range_to)
                return
            for row in rows:
                session = row["trade_date"]
                by_session.setdefault(session, {})[sym] = {
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume") or 0),
                }
                persist.append(row)

    await asyncio.gather(*(one(sym) for sym in unique))
    index_by: dict[date, float] = {}
    index_persist: list[dict[str, Any]] = []
    try:
        idx_rows = await provider.fetch_index_range(range_from, range_to)
        for row in idx_rows:
            index_by[row["trade_date"]] = float(row["close"])
            index_persist.append(row)
    except Exception:
        logger.exception("W52_COMPLETED_INDEX_FAILED from=%s to=%s", range_from, range_to)
    logger.info(
        "W52_COMPLETED_HISTORY sessions=%s symbols_filled=%s index=%s",
        sorted(d.isoformat() for d in by_session),
        sum(len(v) for v in by_session.values()),
        sorted(d.isoformat() for d in index_by),
    )
    return by_session, index_by, persist, index_persist


async def fill_missing_completed_sessions(
    dates: list[date],
    high_m: dict[str, dict[date, float]],
    low_m: dict[str, dict[date, float]],
    close_m: dict[str, dict[date, float]],
    vol_m: dict[str, dict[date, float]],
    index: dict[date, float],
    symbols: list[str],
    now: datetime | None = None,
) -> tuple[list[date], dict, dict, dict, dict, dict[date, float], str]:
    """Bring matrices up to Pine Screener's last confirmed daily bar."""
    from ...market_data_ingestion.calendar_utils import expected_last_completed_session

    target = expected_last_completed_session(now)
    last = dates[-1] if dates else None
    if last is not None and last >= target:
        return dates, high_m, low_m, close_m, vol_m, index, "stored_eod"
    gap_from = last + timedelta(days=1) if last is not None else target
    logger.info(
        "W52_FILL_COMPLETED_SESSION stored_last=%s target=%s gap_from=%s",
        last.isoformat() if last else None,
        target.isoformat(),
        gap_from.isoformat(),
    )
    by_session, index_by, persist, index_persist = await fetch_missing_completed_bars(
        symbols, gap_from, target
    )
    if not by_session:
        logger.warning("W52_FILL_COMPLETED_EMPTY stored_last=%s target=%s", last, target)
        return dates, high_m, low_m, close_m, vol_m, index, "stored_eod"
    for session in sorted(by_session):
        dates, high_m, low_m, close_m, vol_m, index = apply_session_bars(
            dates,
            high_m,
            low_m,
            close_m,
            vol_m,
            index,
            session=session,
            equity_bars=by_session[session],
            index_close=index_by.get(session),
        )
    try:
        from ...market_data_ingestion.repository import upsert_daily_bars, upsert_index_bars

        if persist:
            await upsert_daily_bars(persist)
        if index_persist:
            await upsert_index_bars(index_persist)
    except Exception:
        logger.exception("W52_FILL_COMPLETED_PERSIST_FAILED")
    return dates, high_m, low_m, close_m, vol_m, index, "completed_history"


async def fetch_live_session_bars(symbols: list[str]) -> tuple[dict[str, dict[str, float]], float | None]:
    """Batch FYERS quotes → {symbol: {high,low,close,volume}}, index close."""
    from ...fyers_service import FyersService

    svc = FyersService()
    client = await asyncio.to_thread(svc._client)
    unique = list(dict.fromkeys(s for s in symbols if s))
    index_provider = getattr(settings, "strategy_index_provider_symbol", None) or "NSE:NIFTY500-INDEX"
    want = unique + [index_provider]
    equity: dict[str, dict[str, float]] = {}
    index_close: float | None = None
    reverse = {svc._normalize_symbol(s): s for s in unique}
    reverse[svc._normalize_symbol(index_provider)] = index_provider

    chunks = [want[i : i + _QUOTE_CHUNK] for i in range(0, len(want), _QUOTE_CHUNK)]
    sem = asyncio.Semaphore(4)

    async def fetch_chunk(chunk: list[str]) -> list[dict[str, Any]]:
        async with sem:
            fyers_syms = [svc._normalize_symbol(s) for s in chunk]
            resp = None
            for attempt in range(1, 4):
                try:
                    resp = await asyncio.to_thread(
                        client.quotes, data={"symbols": ",".join(fyers_syms)}
                    )
                    if isinstance(resp, dict) and resp.get("s") == "ok" and resp.get("d"):
                        break
                    if isinstance(resp, dict) and resp.get("code") == 429:
                        await asyncio.sleep(0.4 * attempt)
                except Exception:
                    if attempt == 3:
                        logger.warning("W52_LIVE_QUOTES_FAILED chunk_len=%s", len(chunk))
                    await asyncio.sleep(0.3)
                await asyncio.sleep(0.1)
            rows = (resp or {}).get("d") if isinstance(resp, dict) else None
            return rows if isinstance(rows, list) else []

    chunk_results = await asyncio.gather(*(fetch_chunk(c) for c in chunks), return_exceptions=True)
    for rows in chunk_results:
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            value = row.get("v") if isinstance(row.get("v"), dict) else row
            nsym = str(row.get("n") or value.get("symbol") or "")
            local = reverse.get(nsym)
            bar = parse_quote_bar(value)
            if not local or not bar:
                continue
            if local == index_provider:
                index_close = bar["close"]
            else:
                equity[local] = bar

    logger.info(
        "W52_LIVE_SESSION_BARS symbols=%s got=%s index=%s",
        len(unique),
        len(equity),
        index_close,
    )
    return equity, index_close


async def overlay_current_session(
    dates: list[date],
    high_m: dict[str, dict[date, float]],
    low_m: dict[str, dict[date, float]],
    close_m: dict[str, dict[date, float]],
    vol_m: dict[str, dict[date, float]],
    index: dict[date, float],
    symbols: list[str],
    now: datetime | None = None,
) -> tuple[list[date], dict, dict, dict, dict, dict[date, float], str]:
    dates, high_m, low_m, close_m, vol_m, index, source = await fill_missing_completed_sessions(
        dates, high_m, low_m, close_m, vol_m, index, symbols, now
    )
    session = should_overlay_session(dates, now)
    if session is None:
        trimmed = drop_open_session_bar(dates, now)
        return trimmed, high_m, low_m, close_m, vol_m, index, source
    bars, idx = await fetch_live_session_bars(symbols)
    if not bars:
        if dates and dates[-1] == session:
            logger.warning(
                "W52_LIVE_SESSION_EMPTY session=%s — using stored 1D bar already in daily_ohlcv",
                session,
            )
            return dates, high_m, low_m, close_m, vol_m, index, source if source != "stored_eod" else "stored_live_1d"
        logger.warning(
            "W52_LIVE_SESSION_EMPTY session=%s — keeping last completed EOD %s (Pine 1D bar unavailable)",
            session,
            dates[-1] if dates else None,
        )
        trimmed = drop_open_session_bar(dates, now)
        return trimmed, high_m, low_m, close_m, vol_m, index, source
    dates, high_m, low_m, close_m, vol_m, index = apply_session_bars(
        dates,
        high_m,
        low_m,
        close_m,
        vol_m,
        index,
        session=session,
        equity_bars=bars,
        index_close=idx,
    )
    try:
        persist = [
            {
                "trade_date": session,
                "symbol": sym,
                "open": float(bar.get("open") or bar["close"]),
                "high": float(bar["high"]),
                "low": float(bar["low"]),
                "close": float(bar["close"]),
                "volume": int(bar.get("volume") or 0),
                "source": "FYERS_LIVE_1D",
            }
            for sym, bar in bars.items()
        ]
        from ...market_data_ingestion.repository import upsert_daily_bars, upsert_index_bars
        from ....config.settings import settings as _settings

        if persist:
            await upsert_daily_bars(persist)
        if idx is not None and idx > 0:
            await upsert_index_bars(
                [
                    {
                        "trade_date": session,
                        "symbol": _settings.strategy_index_store_symbol,
                        "open": float(idx),
                        "high": float(idx),
                        "low": float(idx),
                        "close": float(idx),
                        "volume": 0,
                        "source": "FYERS_LIVE_1D",
                    }
                ]
            )
        logger.info("W52_LIVE_1D_PERSISTED session=%s symbols=%s", session, len(persist))
    except Exception:
        logger.exception("W52_LIVE_1D_PERSIST_FAILED session=%s", session)
    return dates, high_m, low_m, close_m, vol_m, index, "live_session"
