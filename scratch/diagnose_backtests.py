"""Diagnose data coverage and LTM rebalance selections without writing scan state."""
from __future__ import annotations

import asyncio
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import func, select, text
from app.db.session import AsyncSessionLocal
from app.models.strategy_market_data import DailyOhlcv, IndexOhlcv
from app.models.market_data import HistoricalCandle
from app.services.universe_service import UniverseService
from app.services.strategies.ltm.book_engine import clock_status, evaluate_session, replay_book
from app.services.strategies.ltm.identity import RESEARCH_BPS


async def coverage() -> None:
    async with AsyncSessionLocal() as db:
        daily = (
            await db.execute(
                select(
                    func.min(DailyOhlcv.trade_date),
                    func.max(DailyOhlcv.trade_date),
                    func.count(),
                    func.count(func.distinct(DailyOhlcv.symbol)),
                    func.count(func.distinct(DailyOhlcv.trade_date)),
                )
            )
        ).one()
        high_ok = (
            await db.execute(
                select(func.count()).where(DailyOhlcv.high.is_not(None), DailyOhlcv.volume.is_not(None))
            )
        ).scalar()
        idx = (
            await db.execute(
                select(
                    func.min(IndexOhlcv.trade_date),
                    func.max(IndexOhlcv.trade_date),
                    func.count(),
                ).where(IndexOhlcv.symbol == "NIFTY500")
            )
        ).one()
        candles = (
            await db.execute(
                select(
                    func.min(HistoricalCandle.timestamp),
                    func.max(HistoricalCandle.timestamp),
                    func.count(),
                    func.count(func.distinct(HistoricalCandle.symbol)),
                ).where(HistoricalCandle.resolution.in_(("1D", "D", "1d")))
            )
        ).one()
        by_year = (
            await db.execute(
                text(
                    """
                    SELECT date_trunc('month', trade_date)::date AS m,
                           COUNT(*) AS rows,
                           COUNT(DISTINCT symbol) AS syms,
                           COUNT(*) FILTER (WHERE high IS NOT NULL AND volume IS NOT NULL) AS hlv
                    FROM daily_ohlcv
                    GROUP BY 1
                    ORDER BY 1
                    """
                )
            )
        ).all()
    print("daily_ohlcv", daily, "rows_with_high_vol", high_ok)
    print("index_ohlcv NIFTY500", idx)
    print("historical_candles daily", candles)
    print("monthly daily_ohlcv:")
    for m, rows, syms, hlv in by_year:
        print(f"  {m} rows={rows} symbols={syms} hlv={hlv}")


async def ltm_rebalances() -> None:
    from app.services.strategies.ltm.scan_service import _load_matrix

    symbols = await UniverseService.get_active_nifty500_symbols()
    print(f"\nuniverse={len(symbols)}")
    dates, matrix, index, source = await _load_matrix(symbols)
    print(f"LTM dates={len(dates)} source={source} first={dates[0]} last={dates[-1]} index={len(index)}")
    # coverage at first/last
    first, last = dates[0], dates[-1]
    have_first = sum(1 for s in symbols if first in matrix.get(s, {}))
    have_last = sum(1 for s in symbols if last in matrix.get(s, {}))
    print(f"symbols with close on first {first}: {have_first}/{len(symbols)}")
    print(f"symbols with close on last  {last}: {have_last}/{len(symbols)}")

    last_reb = None
    for i, dt in enumerate(dates):
        status, since, fire = clock_status(i, last_reb)
        if not fire:
            continue
        prev_t = dates[i - 252] if i >= 252 else None
        closes_t = {s: matrix.get(s, {}).get(dt) for s in symbols}
        closes_prev = {s: (matrix.get(s, {}).get(prev_t) if prev_t else None) for s in symbols}
        ev = evaluate_session(
            session_index=i,
            last_rebalance_index=last_reb,
            closes_t=closes_t,
            closes_t_minus_252=closes_prev,
            universe=set(symbols),
        )
        fails = Counter(r.get("first_failure") or "SELECTED" for r in ev["rows"])
        selected = [s for s, _m, _r in ev["selected"]]
        print(f"REBALANCE {dt} idx={i} selected={len(selected)} {selected[:10]}")
        print("  failures", dict(fails))
        last_reb = i

    replay = replay_book(dates, matrix, set(symbols), mode="A", initial_capital=100_000.0, bps=RESEARCH_BPS)
    print(f"replay trades={len(replay['trades'])} cohorts={len(replay['cohorts'])} curve={len(replay['equity_curve'])}")
    for c in replay["cohorts"]:
        print(f"  cohort {c['date']} selected={len(c['selected'])} entries={len(c['entries'])} exits={len(c['exits'])}")


async def main() -> None:
    await coverage()
    await ltm_rebalances()


if __name__ == "__main__":
    asyncio.run(main())
