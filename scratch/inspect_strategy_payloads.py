"""Inspect stored LTM/52W blotters and equity curves for sanity."""
from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import text
from app.db.session import AsyncSessionLocal


IDS = ["17_long_term_mom", "09_52w_breakout"]


def inspect(sid: str, payload: dict) -> None:
    print("\n" + "=" * 80)
    print(sid, payload.get("display_name"), "eval", payload.get("evaluation_date"), "mode", payload.get("mode"))
    print("clock", payload.get("clock_status"), "warmup", payload.get("warmup"),
          "sessions_to_rebalance", payload.get("sessions_to_rebalance"),
          "last_rebalance", payload.get("last_rebalance_date"),
          "data_source", payload.get("data_source"))
    print("summary", payload.get("summary"))
    print("book_metrics", json.dumps(payload.get("book_metrics") or {}, default=str, indent=2))
    print("holdings", payload.get("holdings"))
    print("entries last", payload.get("entries"))
    print("exits last", payload.get("exits"))

    curve = payload.get("equity_curve") or []
    print(f"curve n={len(curve)}")
    if curve:
        print(" first", curve[0])
        print(" last ", curve[-1])
        mid = curve[len(curve) // 2]
        print(" mid  ", mid)
        # cash/equity stats
        invested_days = 0
        min_cash = None
        max_eq = None
        for p in curve:
            eq = float(p.get("equity") or 0)
            cash = float(p.get("cash") or 0)
            if eq > cash + 1:
                invested_days += 1
            min_cash = cash if min_cash is None else min(min_cash, cash)
            max_eq = eq if max_eq is None else max(max_eq, eq)
        print(f" invested_days={invested_days}/{len(curve)} min_cash={min_cash:.2f} max_equity={max_eq:.2f}")
        clocks = Counter(p.get("clock_status") for p in curve)
        print(" clock_status counts", dict(clocks))

    blotter = payload.get("blotter") or []
    print(f"blotter n={len(blotter)}")
    reasons = Counter(t.get("reason") for t in blotter)
    print(" reasons", dict(reasons))
    opens = [t for t in blotter if t.get("open")]
    closed = [t for t in blotter if not t.get("open")]
    print(f" open={len(opens)} closed={len(closed)}")
    for t in blotter:
        print(
            f"  {t.get('symbol'):12} {t.get('entry_date')} -> {t.get('exit_date')} "
            f"open={t.get('open')} pnl={t.get('pnl_pct')} reason={t.get('reason')} "
            f"entry={t.get('entry_price')} exit={t.get('exit_price')} shares={t.get('shares')}"
        )


async def main() -> None:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT strategy_id, status, completed_at, payload
                    FROM strategy_scan_latest
                    WHERE strategy_id = ANY(:ids)
                    """
                ),
                {"ids": IDS},
            )
        ).mappings().all()
    by = {r["strategy_id"]: r["payload"] for r in rows}
    for sid in IDS:
        inspect(sid, by.get(sid) or {})


if __name__ == "__main__":
    asyncio.run(main())
