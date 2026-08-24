"""Period-isolation validation for the 52-Week High Breakout boards.

Runs against a persisted latest scan when DATABASE_URL is available.
Always prints explicit processed / successful / failed / skipped counts.
Does not change strategy parameters.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PERIODS = ("1D", "1W", "1M", "1Y", "3Y", "5Y", "7Y", "8Y", "18Y")


async def _load_latest() -> dict | None:
    from app.services.strategies.breakout52w import persistence
    from app.services.strategies.breakout52w.identity import STRATEGY_ID

    row = await persistence.load_latest(STRATEGY_ID)
    if row is None or not row.payload:
        return None
    return dict(row.payload)


def _summarize(period: str, payload: dict) -> dict:
    acc = payload.get("period_accounting") or {}
    avg = payload.get("universe_average") or {}
    top = [r.get("symbol") for r in (payload.get("top5_positive") or [])]
    least = [r.get("symbol") for r in (payload.get("least5") or [])]
    return {
        "period": period,
        "start_date": payload.get("requested_start") or payload.get("attribution_window_start"),
        "end_date": payload.get("requested_end") or payload.get("attribution_window_end"),
        "trade_count": payload.get("period_trade_count"),
        "average_return": avg.get("average_return"),
        "median_return": acc.get("median_return"),
        "processed": acc.get("processed"),
        "successful": acc.get("successful"),
        "failed": acc.get("failed"),
        "skipped": acc.get("skipped"),
        "insufficient_history": acc.get("insufficient_history"),
        "no_trades": acc.get("no_trades"),
        "stocks_with_trades": acc.get("stocks_with_trades"),
        "winning_names": acc.get("winning_names"),
        "losing_names": acc.get("losing_names"),
        "cache_key": payload.get("cache_key"),
        "result_identity": payload.get("result_identity"),
        "top_stocks": top,
        "worst_stocks": least,
    }


async def main() -> int:
    from app.services.strategies.breakout52w.attribution import apply_windowed_attribution

    payload = None
    if os.environ.get("DATABASE_URL") or os.environ.get("SKIP_DB") != "1":
        try:
            payload = await _load_latest()
        except Exception as exc:  # pragma: no cover - live DB optional
            print(f"latest scan unavailable: {exc}")
    if not payload:
        print("No persisted 52W scan; period isolation unit tests remain the source of truth.")
        return 0

    rows = []
    identities = []
    for period in PERIODS:
        out = apply_windowed_attribution(payload, period=period)
        summary = _summarize(period, out)
        rows.append(summary)
        identities.append((period, summary["result_identity"], summary["trade_count"]))
        print(json.dumps(summary, default=str))

    unique_keys = {row["cache_key"] for row in rows}
    print(f"distinct_cache_keys={len(unique_keys)} expected={len(PERIODS)}")
    if len(unique_keys) != len(PERIODS):
        print("WARNING: cache keys collided across periods")
    # Diagnostics only: identical trade sets across 1D vs 18Y are suspicious.
    by_id = {}
    for period, ident, count in identities:
        by_id.setdefault((ident, count), []).append(period)
    for (_ident, count), periods in by_id.items():
        if len(periods) > 1 and count:
            print(f"WARNING: identical trade set for {periods} trade_count={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
