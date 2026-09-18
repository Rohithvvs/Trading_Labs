"""Copy Production daily candles into strategy-grade daily_ohlcv so LTM can run."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select

from ....db.session import AsyncSessionLocal
from ....models.market_data import HistoricalCandle
from ....models.strategy_market_data import DailyOhlcv
from ....services.market_data_ingestion.repository import upsert_daily_bars

logger = logging.getLogger("app.strategies.ltm.backfill")

_CHUNK = 800


def _session_date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


async def strategy_session_count() -> int:
    async with AsyncSessionLocal() as db:
        n = await db.scalar(select(func.count(func.distinct(DailyOhlcv.trade_date))))
        return int(n or 0)


async def backfill_daily_ohlcv_from_candles(symbols: list[str] | None = None) -> int:
    """Idempotent copy of 1D historical_candles → daily_ohlcv. Returns rows upserted."""
    async with AsyncSessionLocal() as db:
        stmt = select(
            HistoricalCandle.timestamp,
            HistoricalCandle.symbol,
            HistoricalCandle.open,
            HistoricalCandle.high,
            HistoricalCandle.low,
            HistoricalCandle.close,
            HistoricalCandle.volume,
        ).where(HistoricalCandle.resolution.in_(("1D", "D", "1d")))
        if symbols:
            stmt = stmt.where(HistoricalCandle.symbol.in_(symbols))
        rows = (await db.execute(stmt)).all()

    payload: list[dict[str, Any]] = []
    seen: set[tuple[date, str]] = set()
    for ts, symbol, o, h, low, c, vol in rows:
        session = _session_date(ts)
        key = (session, str(symbol))
        if key in seen:
            continue
        seen.add(key)
        payload.append(
            {
                "trade_date": session,
                "symbol": symbol,
                "open": o,
                "high": h,
                "low": low,
                "close": c,
                "volume": int(vol or 0),
                "source": "historical_candles",
            }
        )

    total = 0
    for i in range(0, len(payload), _CHUNK):
        n, _ = await upsert_daily_bars(payload[i : i + _CHUNK])
        total += n
    logger.info("LTM backfill daily_ohlcv from candles | rows=%s", total)
    return total


async def ensure_strategy_daily_ready(symbols: list[str] | None = None, *, min_sessions: int = 253) -> int:
    """If strategy daily history is too short, copy from Production candles."""
    have = await strategy_session_count()
    if have >= min_sessions:
        return 0
    return await backfill_daily_ohlcv_from_candles(symbols)
