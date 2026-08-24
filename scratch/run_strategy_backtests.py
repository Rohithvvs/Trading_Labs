"""Replay LTM + 52W on the shared daily_ohlcv calendar and rank them."""
from __future__ import annotations

import asyncio
import json
import math
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.universe_service import UniverseService
from app.services.strategies.ltm.book_engine import replay_book as ltm_replay
from app.services.strategies.ltm.identity import RESEARCH_BPS
from app.services.strategies.breakout52w.book_engine import replay_book as w52_replay
from app.services.strategies.breakout52w.scan_service import _load_matrices as w52_load


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(n) or math.isinf(n):
        return None
    return n


def _as_date(v: Any) -> date | None:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _trade_ok(t: Any) -> bool:
    px = _num(getattr(t, "exit_price", None))
    entry = _num(getattr(t, "entry_price", None))
    pnl = _num(getattr(t, "pnl_pct", None))
    if entry is None or entry <= 0:
        return False
    if px is not None and px <= 0:
        return False
    if pnl is not None and pnl <= -0.999:
        return False
    return pnl is not None


def book_stats(name: str, replay: dict[str, Any], *, initial: float) -> dict[str, Any]:
    curve = replay.get("equity_curve") or []
    trades = list(replay.get("trades") or [])
    open_tr = list(replay.get("open_trades") or [])
    reasons = Counter(getattr(t, "reason", None) for t in trades + open_tr)

    usable = [t for t in trades if _trade_ok(t)]
    # Prefer real exits + sample-end MTM. Drop bogus zero-price exits.
    pnls = [float(t.pnl_pct) for t in usable]
    for t in open_tr:
        if _trade_ok(t):
            pnls.append(float(t.pnl_pct))
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    n = len(pnls)
    win_rate = (len(wins) / n) if n else None
    if losses and wins:
        pf = abs(sum(wins) / sum(losses))
    elif wins and not losses:
        pf = float("inf")
    else:
        pf = 0.0 if n else None
    avg_trade = (sum(pnls) / n) if n else None
    best = max(pnls) if pnls else None
    worst = min(pnls) if pnls else None

    eq = [_num(p.get("equity")) for p in curve]
    eq = [v for v in eq if v is not None]
    cashs = [_num(p.get("cash")) for p in curve]
    cashs = [v for v in cashs if v is not None]
    avg_cash = (sum(cashs) / len(cashs)) if cashs else None
    expos = []
    for p in curve:
        e = _num(p.get("equity"))
        c = _num(p.get("cash"))
        npos = p.get("n_positions")
        if npos is not None:
            expos.append(1.0 if int(npos) > 0 else 0.0)
        elif e and e > 0 and c is not None:
            expos.append(max(0.0, min(1.0, 1.0 - c / e)))
    avg_exposure = (sum(expos) / len(expos)) if expos else None

    first = eq[0] if eq else initial
    last = eq[-1] if eq else initial
    total_return = (last / first - 1.0) if first else 0.0
    d0 = _as_date(curve[0]["date"]) if curve else None
    d1 = _as_date(curve[-1]["date"]) if curve else None
    days = max((d1 - d0).days, 1) if d0 and d1 else 1
    cagr = (last / first) ** (365.25 / days) - 1.0 if first and last > 0 else 0.0
    peak = first
    max_dd = 0.0
    for v in eq:
        peak = max(peak, v)
        if peak:
            max_dd = min(max_dd, v / peak - 1.0)
    calmar = (cagr / abs(max_dd)) if max_dd < 0 else None

    def clip(x: float) -> float:
        return max(0.0, min(100.0, x))

    cagr_s = clip((cagr / 0.40) * 100.0)
    calmar_s = clip(((calmar or 0.0) / 2.0) * 100.0)
    pf_val = 3.0 if pf == float("inf") else (pf or 0.0)
    pf_s = clip((pf_val / 3.0) * 100.0)
    wr_s = clip(((win_rate or 0.0) / 0.70) * 100.0)
    dd_s = clip((1.0 - (abs(max_dd) - 0.10) / 0.40) * 100.0)
    avg_s = clip(((avg_trade or 0.0) / 0.08) * 100.0)
    score = 0.25 * cagr_s + 0.20 * calmar_s + 0.20 * pf_s + 0.15 * wr_s + 0.15 * dd_s + 0.05 * avg_s
    if score >= 80:
        grade = "A"
    elif score >= 65:
        grade = "B"
    elif score >= 50:
        grade = "C"
    elif score >= 35:
        grade = "D"
    else:
        grade = "F"

    invested = sum(1 for x in expos if x > 0)
    return {
        "strategy": name,
        "score": round(score, 1),
        "grade": grade,
        "trades": n,
        "win_rate": win_rate,
        "pf": pf,
        "avg_trade": avg_trade,
        "cagr": cagr,
        "total_return": total_return,
        "max_dd": max_dd,
        "calmar": calmar,
        "avg_cash": avg_cash,
        "avg_exposure": avg_exposure,
        "best": best,
        "worst": worst,
        "period_start": curve[0]["date"] if curve else None,
        "period_end": curve[-1]["date"] if curve else None,
        "sessions": len(curve),
        "invested_sessions": invested,
        "ending_equity": last,
        "initial": first,
        "reasons": dict(reasons),
        "closed_trades": len(trades),
        "open_trades": len(open_tr),
        "invalid_excluded": sum(1 for t in trades if not _trade_ok(t)),
    }


def _fmt_pct(v: float | None, digits: int = 2) -> str:
    if v is None:
        return "—"
    return f"{v * 100:+.{digits}f}%"


def _fmt_num(v: float | None, digits: int = 2) -> str:
    if v is None:
        return "—"
    if v == float("inf"):
        return "∞"
    return f"{v:.{digits}f}"


def _fmt_cash(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:,.0f}"


def print_table(rows: list[dict[str, Any]]) -> None:
    header = (
        "Rank",
        "Strategy",
        "Score",
        "Grade",
        "Trades",
        "Win rate",
        "PF",
        "Avg trade",
        "CAGR",
        "Total return",
        "Max DD",
        "Calmar",
        "Avg cash",
        "Avg exposur",
        "Best trade",
        "Worst trade",
    )
    table = []
    for i, r in enumerate(rows, 1):
        table.append(
            (
                str(i),
                r["strategy"],
                f"{r['score']:.1f}",
                r["grade"],
                str(r["trades"]),
                _fmt_pct(r["win_rate"], 1),
                _fmt_num(r["pf"], 2),
                _fmt_pct(r["avg_trade"], 2),
                _fmt_pct(r["cagr"], 2),
                _fmt_pct(r["total_return"], 2),
                _fmt_pct(r["max_dd"], 2),
                _fmt_num(r["calmar"], 2),
                _fmt_cash(r["avg_cash"]),
                _fmt_pct(r["avg_exposure"], 1),
                _fmt_pct(r["best"], 2),
                _fmt_pct(r["worst"], 2),
            )
        )
    widths = [max(len(h), *(len(row[i]) for row in table)) for i, h in enumerate(header)]

    def fmt_row(cells: tuple[str, ...]) -> str:
        return " │ ".join(c.rjust(widths[i]) if i != 1 else c.ljust(widths[i]) for i, c in enumerate(cells))

    print(fmt_row(header))
    print("─┼─".join("─" * w for w in widths))
    for row in table:
        print(fmt_row(row))


async def main() -> None:
    symbols = await UniverseService.get_active_nifty500_symbols()
    universe = set(symbols)
    print(f"universe={len(universe)}")

    dates, high_m, low_m, close_m, vol_m, index, source = await w52_load(symbols)
    print(
        f"calendar={len(dates)} source={source} first={dates[0]} last={dates[-1]} "
        f"index_pts={len(index)} close_syms={len(close_m)}"
    )

    initial = 100_000.0
    print("replaying LTM on equity calendar...")
    ltm = ltm_replay(
        dates,
        close_m,
        universe,
        mode="A",
        initial_capital=initial,
        bps=RESEARCH_BPS,
        whole_shares=False,
    )
    print(
        f"  LTM trades={len(ltm['trades'])} cohorts={len(ltm['cohorts'])} "
        f"holdings={len(ltm['state'].holdings)}"
    )
    for c in ltm["cohorts"]:
        print(
            f"    {c['date']} selected={len(c['selected'])} "
            f"entries={len(c['entries'])} exits={len(c['exits'])}"
        )

    print("replaying 52W...")
    w52 = w52_replay(
        dates,
        high_m,
        low_m,
        close_m,
        vol_m,
        index,
        universe,
        initial_capital=initial,
        whole_shares=False,
    )
    from app.services.strategies.breakout52w.book_engine import snapshot_open_trades

    prices = {s: close_m.get(s, {}).get(dates[-1]) for s in universe}
    w52["open_trades"] = snapshot_open_trades(w52["state"], prices, dates[-1])
    print(
        f"  52W trades={len(w52['trades'])} open={len(w52['open_trades'])} "
        f"holdings={len(w52['state'].holdings)}"
    )

    from app.services.strategies.ltm.book_engine import snapshot_open_trades as ltm_open

    # LTM engine liquidates on last bar if not a rebalance; snapshot whatever remains.
    ltm["open_trades"] = ltm_open(ltm["state"], prices, dates[-1])

    rows = [
        book_stats("LTM", ltm, initial=initial),
        book_stats("52W", w52, initial=initial),
    ]
    rows.sort(key=lambda r: r["score"], reverse=True)
    print("\n=== RANKED COMPARISON (shared daily_ohlcv calendar) ===")
    print_table(rows)

    # NIFTY 500 buy-and-hold on same dates
    idx_vals = [index[d] for d in dates if d in index]
    if len(idx_vals) >= 2 and idx_vals[0]:
        bh = idx_vals[-1] / idx_vals[0] - 1.0
        print(f"\nNIFTY 500 buy-and-hold over {dates[0]} → {dates[-1]}: {bh*100:+.2f}%")

    out = Path(__file__).with_name("strategy_backtest_comparison.json")
    out.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    asyncio.run(main())
