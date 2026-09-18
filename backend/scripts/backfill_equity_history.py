"""Serial daily OHLCV backfill for a long calendar window.

Resumes from existing daily_ohlcv min/max per symbol. One symbol at a time
so FYERS history rate limits do not burn the remaining universe.

Usage (from backend/):
    python -m scripts.backfill_equity_history --years 18
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.market_data_ingestion.calendar_utils import expected_last_completed_session
from app.services.market_data_ingestion.derived import attach_adtv_20_series, compute_turnover
from app.services.market_data_ingestion.pipelines.full_load import missing_ohlcv_ranges
from app.services.market_data_ingestion.providers.fyers_eod import FyersEodProvider
from app.services.market_data_ingestion import repository
from app.services.fyers_service import FyersRateLimitError
from app.services.universe_service import UniverseService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("backfill_equity_history")


async def _upsert_rows(sym: str, rows: list[dict], range_from: date, start: date) -> int:
    if not rows:
        return 0
    for bar in rows:
        turn = compute_turnover(bar["close"], bar["volume"])
        bar["turnover"] = float(turn) if turn is not None else None
    if range_from > start:
        prior = await repository.fetch_recent_equity_before(sym, range_from, limit=19)
        attach_adtv_20_series(prior + rows)
    else:
        attach_adtv_20_series(rows)
    written = 0
    chunk = 500
    for i in range(0, len(rows), chunk):
        n, _ = await repository.upsert_daily_bars(rows[i : i + chunk])
        written += n
    return written


async def backfill_symbol(
    fyers: FyersEodProvider,
    sym: str,
    start: date,
    end: date,
) -> str:
    min_d, max_d, _count = await repository.equity_date_span(sym)
    windows = missing_ohlcv_ranges(start, end, min_d, max_d)
    if not windows:
        return "skip"
    upserted = 0
    for range_from, range_to in windows:
        attempt = 0
        while True:
            attempt += 1
            try:
                rows = await fyers.fetch_daily_range(sym, range_from, range_to)
                upserted += await _upsert_rows(sym, rows, range_from, start)
                break
            except FyersRateLimitError:
                wait_s = min(180, 30 * attempt)
                logger.warning("RATE_LIMIT | symbol=%s | sleep_s=%s | attempt=%s", sym, wait_s, attempt)
                await asyncio.sleep(wait_s)
                if attempt >= 8:
                    return "rate_limit"
        await asyncio.sleep(0.35)
    logger.info("SYMBOL_OK | symbol=%s | upserted=%s | windows=%s", sym, upserted, len(windows))
    return "ok"


async def run(*, years: int, symbols: list[str] | None) -> int:
    end = expected_last_completed_session()
    start = end - timedelta(days=int(years * 365) + 30)
    universe = symbols or await UniverseService.get_active_nifty500_symbols()
    logger.info("BACKFILL_START | years=%s | symbols=%s | from=%s | to=%s", years, len(universe), start, end)
    fyers = FyersEodProvider()
    counts = {"ok": 0, "skip": 0, "rate_limit": 0, "fail": 0}
    for i, sym in enumerate(universe, start=1):
        try:
            status = await backfill_symbol(fyers, sym, start, end)
        except Exception as exc:
            status = "fail"
            logger.warning("SYMBOL_FAIL | symbol=%s | err=%s", sym, type(exc).__name__)
        counts[status] = counts.get(status, 0) + 1
        if i % 10 == 0 or status != "skip":
            logger.info("PROGRESS | %s/%s | last=%s:%s | %s", i, len(universe), sym, status, counts)
        if status == "rate_limit":
            logger.warning("Cooling 90s after persistent rate limit")
            await asyncio.sleep(90)
    logger.info("BACKFILL_END | %s", counts)
    return 0 if counts.get("fail", 0) == 0 and counts.get("rate_limit", 0) == 0 else 4


def main() -> int:
    p = argparse.ArgumentParser(description="Serial multi-year daily OHLCV backfill")
    p.add_argument("--years", type=int, default=18)
    p.add_argument("--symbols", type=str, default="", help="Comma-separated subset")
    args = p.parse_args()
    symbols = [x.strip().upper() for x in args.symbols.split(",") if x.strip()] or None
    return asyncio.run(run(years=args.years, symbols=symbols))


if __name__ == "__main__":
    raise SystemExit(main())
