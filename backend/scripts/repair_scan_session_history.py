"""Repair cloned last session, thin tapes, and dummy universe rows."""
from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
import sys

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy import text

from app.db.session import AsyncSessionLocal
from app.services.market_data_ingestion.session_repair import (
    THIN_HISTORY_SYMBOLS,
    repair_scan_market_history,
)
from app.services.universe_csv import is_dummy_universe_symbol
from app.services.universe_service import UniverseService


async def deactivate_dummy_symbols() -> int:
    from app.models.stock import StockMaster
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        rows = (await db.scalars(select(StockMaster))).all()
        n = 0
        for row in rows:
            if is_dummy_universe_symbol(row.symbol):
                row.is_active = False
                row.is_nifty500 = False
                n += 1
        if n:
            await db.commit()
        return n


async def main() -> None:
    # Pin to the last 1D session TradingView Pine Screener used (Fri 28 Aug 2026).
    end = date(2026, 8, 28)
    dummy = await deactivate_dummy_symbols()
    print("deactivated_dummy", dummy)
    instruments = await UniverseService.list_active_instruments("NIFTY500")
    symbols = [item.universe_symbol or item.symbol for item in instruments]
    print("universe", len(symbols), "end", end.isoformat())
    report = await repair_scan_market_history(symbols, end=end, min_bars=253)
    print(report)
    async with AsyncSessionLocal() as db:
        for raw in (*THIN_HISTORY_SYMBOLS, "DUMMYALCAR"):
            rows = (
                await db.execute(
                    text(
                        "SELECT COUNT(*) FROM daily_ohlcv WHERE symbol IN (:a, :b)"
                    ),
                    {"a": raw, "b": f"{raw}-EQ"},
                )
            ).scalar()
            print("ohlcv", raw, rows)


if __name__ == "__main__":
    asyncio.run(main())
