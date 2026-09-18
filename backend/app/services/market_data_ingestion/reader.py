"""Strategy data reader — equity history, delivery, index series from strategy tables."""
from __future__ import annotations

from datetime import date
from typing import Any

from ...config.settings import settings
from . import repository
from .derived import adtv_20, weekly_ohlcv


async def get_equity_history(
    symbol: str,
    *,
    from_date: date | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    return await repository.fetch_equity_history(symbol, from_date=from_date, limit=limit)


async def get_index_history(
    symbol: str | None = None,
    *,
    from_date: date | None = None,
) -> list[dict[str, Any]]:
    sym = symbol or settings.strategy_index_store_symbol
    return await repository.fetch_index_history(sym, from_date=from_date)


async def get_weekly_ohlcv(symbol: str, *, from_date: date | None = None) -> list[dict[str, Any]]:
    daily = await get_equity_history(symbol, from_date=from_date)
    return weekly_ohlcv(daily)


async def get_adtv_20(symbol: str) -> float | None:
    """Prefer stored ``adtv_20`` on the latest bar; fall back to on-the-fly calc."""
    daily = await get_equity_history(symbol)
    if not daily:
        return None
    latest = daily[-1].get("adtv_20")
    if latest is not None:
        try:
            return float(latest)
        except (TypeError, ValueError):
            pass
    return adtv_20(daily[-20:])
