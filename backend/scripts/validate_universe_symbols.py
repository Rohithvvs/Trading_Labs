"""Validate canonical symbols for the active 755-stock universe.

Usage (from repo root or backend/):
    python backend/scripts/validate_universe_symbols.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_here = Path(__file__).resolve()
for cand in (_here.parents[1], _here.parents[2], Path.cwd()):
    if (cand / "app" / "db" / "session.py").exists():
        sys.path.insert(0, str(cand))
        break


async def main() -> int:
    from sqlalchemy import func, select

    from app.db.session import AsyncSessionLocal
    from app.models.strategy_market_data import DailyOhlcv
    from app.services.universe_service import UniverseService

    report = await UniverseService.validate_universe("NIFTY500")
    instruments = await UniverseService.list_active_instruments("NIFTY500")
    store_symbols = [item.universe_symbol for item in instruments]
    ohlcv_present = 0
    if store_symbols:
        async with AsyncSessionLocal() as db:
            ohlcv_present = int(
                (
                    await db.execute(
                        select(func.count(func.distinct(DailyOhlcv.symbol))).where(
                            DailyOhlcv.symbol.in_(store_symbols)
                        )
                    )
                ).scalar()
                or 0
            )

    report.historical_data_mappings = ohlcv_present

    print("------------------------------------------------")
    print("UNIVERSE SYMBOL VALIDATION")
    print("------------------------------------------------")
    print(f"Total stocks:              {report.total_stocks}")
    print(f"Symbols present:           {report.symbols_present}")
    print(f"Symbols missing:           {report.symbols_missing}")
    print(f"Duplicates:                {report.duplicates}")
    print(f"Invalid symbols:           {report.invalid_symbols}")
    print(f"Inactive symbols:          {report.inactive_symbols}")
    print(f"Broker mappings missing:   {report.broker_mappings_missing}")
    print(f"Historical data mappings:  {report.historical_data_mappings}")
    print("------------------------------------------------")

    if report.missing:
        print("MISSING")
        for item in report.missing:
            print(
                f"  company={item.get('company_name')!r} stored={item.get('current_stored_identifier')!r} "
                f"canonical={item.get('attempted_canonical_symbol')!r} reason={item.get('reason')} "
                f"fix={item.get('recommended_resolution')}"
            )
    if report.invalid:
        print("INVALID")
        for item in report.invalid:
            print(
                f"  company={item.get('company_name')!r} stored={item.get('current_stored_identifier')!r} "
                f"canonical={item.get('attempted_canonical_symbol')!r} reason={item.get('reason')} "
                f"fix={item.get('recommended_resolution')}"
            )
    if report.duplicate_symbols:
        print("DUPLICATES", report.duplicate_symbols)

    ok = (
        report.symbols_missing == 0
        and report.duplicates == 0
        and report.invalid_symbols == 0
        and report.broker_mappings_missing == 0
        and report.total_stocks == report.symbols_present
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
