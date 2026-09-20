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
from ....services.market_data_ingestion.validators.ohlcv_gate import validate_ohlcv_bar
from ....utils.datetime_utils import ensure_utc, to_ist

logger = logging.getLogger("app.strategies.ltm.backfill")

_CHUNK = 800


def _session_date(value: date | datetime) -> date:
    """NSE cash session date in IST. Naive timestamps are treated as UTC."""
    if isinstance(value, datetime):
        ist = to_ist(ensure_utc(value))
        return ist.date() if ist is not None else value.date()
    return value


async def strategy_session_count() -> int:
    from ...market_data_ingestion.history_backend import uses_turso

    if uses_turso():
        from ...market_data_ingestion import turso_repository as turso

        return await turso.fetch_distinct_session_count()
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
        stmt = stmt.order_by(HistoricalCandle.symbol.asc(), HistoricalCandle.timestamp.asc())
        rows = (await db.execute(stmt)).all()

    # Last timestamp per IST session wins (first-seen previously could keep an
    # incomplete/intraday print). Invalid OHLC is dropped; upsert gate is the backstop.
    by_key: dict[tuple[date, str], dict[str, Any]] = {}
    skipped = 0
    for ts, symbol, o, h, low, c, vol in rows:
        session = _session_date(ts)
        bar = {
            "trade_date": session,
            "symbol": symbol,
            "open": o,
            "high": h,
            "low": low,
            "close": c,
            "volume": int(vol or 0),
            "source": "historical_candles",
        }
        if validate_ohlcv_bar(bar):
            skipped += 1
            continue
        by_key[(session, str(symbol))] = bar
    payload = list(by_key.values())
    if skipped:
        logger.warning(
            "LTM backfill skipped invalid ACS 1D bars | skipped=%s | kept=%s",
            skipped,
            len(payload),
        )

    total = 0
    for i in range(0, len(payload), _CHUNK):
        n, _ = await upsert_daily_bars(payload[i : i + _CHUNK])
        total += n
    logger.info("LTM backfill daily_ohlcv from candles | rows=%s", total)
    return total


async def ensure_strategy_daily_ready(symbols: list[str] | None = None, *, min_sessions: int = 253) -> int:
    """If strategy daily history is too short, copy from Production candles."""
    from ...market_data_ingestion.history_backend import uses_turso

    have = await strategy_session_count()
    if have >= min_sessions:
        return 0
    if uses_turso():
        raise RuntimeError(
            f"Turso daily candle history has insufficient sessions ({have} < {min_sessions}). "
            "Refusing fallback to Postgres."
        )
    return await backfill_daily_ohlcv_from_candles(symbols)
