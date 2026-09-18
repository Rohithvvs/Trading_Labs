"""Fetch today's forming 1D bars (TradingView Pine candle) into daily_ohlcv.

Usage (from backend/):
    python -m scripts.fetch_w52_live_1d
    python -m scripts.fetch_w52_live_1d --date 2026-08-21
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.strategies.breakout52w.indicators import prior_high_252, vol_sma20
from app.services.strategies.breakout52w.signal import screener_pass
from app.utils.symbol import canonical_symbol

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("fetch_w52_live_1d")

TV_NAMES = ("ACMESOLAR", "IIFL", "JINDALSAW", "NETWEB", "WELCORP")


async def _persist_live(session: date, bars: dict[str, dict[str, float]], index_close: float | None) -> int:
    from app.config.settings import settings
    from app.services.market_data_ingestion.repository import upsert_daily_bars, upsert_index_bars

    rows = [
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
    written = 0
    if rows:
        written, _ = await upsert_daily_bars(rows)
    if index_close is not None and index_close > 0:
        await upsert_index_bars(
            [
                {
                    "trade_date": session,
                    "symbol": settings.strategy_index_store_symbol,
                    "open": float(index_close),
                    "high": float(index_close),
                    "low": float(index_close),
                    "close": float(index_close),
                    "volume": 0,
                    "source": "FYERS_LIVE_1D",
                }
            ]
        )
    return written


async def _history_fill(symbols: list[str], session: date) -> int:
    """FYERS 1D history for today — often includes the forming daily candle."""
    from app.services.market_data_ingestion.providers.fyers_eod import FyersEodProvider
    from app.services.market_data_ingestion.repository import upsert_daily_bars, upsert_index_bars
    from app.config.settings import settings

    fyers = FyersEodProvider()
    sem = asyncio.Semaphore(6)
    persist: list[dict] = []

    async def one(sym: str) -> None:
        async with sem:
            try:
                rows = await fyers.fetch_daily_range(sym, session, session)
            except Exception:
                logger.warning("HISTORY_FAILED symbol=%s", sym)
                return
            persist.extend(rows)

    await asyncio.gather(*(one(s) for s in symbols))
    written = 0
    if persist:
        for row in persist:
            row["source"] = row.get("source") or "FYERS"
        written, _ = await upsert_daily_bars(persist)
    try:
        idx_rows = await fyers.fetch_index_range(session, session)
        if idx_rows:
            await upsert_index_bars(idx_rows)
    except Exception:
        logger.exception("INDEX_HISTORY_FAILED")
    logger.info("HISTORY_UPSERT session=%s rows=%s", session, written)
    return written


async def _verify_tv_names(session: date, live: dict[str, dict[str, float]]) -> None:
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.strategy_market_data import DailyOhlcv, IndexOhlcv
    from app.config.settings import settings

    by_canon = {canonical_symbol(s): (s, bar) for s, bar in live.items()}
    async with AsyncSessionLocal() as db:
        idx_rows = (
            await db.execute(
                select(IndexOhlcv.trade_date, IndexOhlcv.close)
                .where(IndexOhlcv.symbol == settings.strategy_index_store_symbol)
                .order_by(IndexOhlcv.trade_date.asc())
            )
        ).all()
        index = {d: float(c) for d, c in idx_rows if d <= session}
        if session in live and settings.strategy_index_provider_symbol:
            pass

        print(f"\nTradingView names vs stored+live 1D bar {session.isoformat()}:")
        for name in TV_NAMES:
            match = by_canon.get(name)
            store_sym = match[0] if match else None
            if store_sym is None:
                rows = (
                    await db.execute(
                        select(DailyOhlcv.symbol)
                        .where(DailyOhlcv.symbol.like(f"{name}%"))
                        .limit(5)
                    )
                ).all()
                store_sym = rows[0][0] if rows else None
            if store_sym is None:
                print(f"  {name}: NOT IN LIVE QUOTES OR DB")
                continue
            hist = (
                await db.execute(
                    select(DailyOhlcv.trade_date, DailyOhlcv.high, DailyOhlcv.volume, DailyOhlcv.close)
                    .where(DailyOhlcv.symbol == store_sym, DailyOhlcv.trade_date <= session)
                    .order_by(DailyOhlcv.trade_date.asc())
                )
            ).all()
            dates = [r[0] for r in hist]
            highs = [float(r[1]) for r in hist]
            vols = [float(r[2] or 0) for r in hist]
            closes = [float(r[3]) for r in hist]
            bar = match[1] if match else None
            if bar is not None:
                if dates and dates[-1] == session:
                    highs[-1] = float(bar["high"])
                    vols[-1] = float(bar["volume"])
                    closes[-1] = float(bar["close"])
                else:
                    dates.append(session)
                    highs.append(float(bar["high"]))
                    vols.append(float(bar["volume"]))
                    closes.append(float(bar["close"]))
            t = len(closes) - 1
            ph = prior_high_252(highs, t)
            vsma = vol_sma20(vols, t)
            close = closes[t] if t >= 0 else None
            vol = vols[t] if t >= 0 else None
            ok = screener_pass(
                market_ok_flag=True,
                close=close,
                prior_high=ph,
                volume=vol,
                vol_sma=vsma,
            )
            print(
                f"  {name} ({store_sym}) close={close} prior252={ph} vol={vol} "
                f"sma20={vsma} pass={ok}"
            )


async def main(session: date) -> int:
    from app.services.strategies.breakout52w.session_overlay import fetch_live_session_bars
    from app.services.universe_service import UniverseService

    symbols = await UniverseService.get_active_nifty500_symbols()
    if not symbols:
        logger.error("No NIFTY500 symbols in stock_master")
        return 1
    logger.info("UNIVERSE symbols=%s session=%s", len(symbols), session)
    want = [s for s in symbols if canonical_symbol(s) in TV_NAMES]
    hist_n = await _history_fill(want or TV_NAMES, session)
    bars, idx = await fetch_live_session_bars(symbols)
    live_n = await _persist_live(session, bars, idx)
    logger.info("LIVE_UPSERT session=%s quotes=%s persisted=%s index=%s", session, len(bars), live_n, idx)
    await _verify_tv_names(session, bars)
    print(f"\nFetched 1D bars for {session}: tv_history={hist_n} live_quotes={len(bars)} persisted={live_n}")
    print("Re-run 52-Week High Breakout in Scanner to refresh the name list.")
    return 0 if bars or hist_n else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (default: today IST)")
    args = parser.parse_args()
    if args.date:
        target = date.fromisoformat(args.date)
    else:
        target = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    raise SystemExit(asyncio.run(main(target)))
