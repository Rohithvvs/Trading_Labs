"""Load latest LTM + 52W scan payloads and print a ranked comparison table."""
from __future__ import annotations

import asyncio
import json
import math
import sys
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import text
from app.db.session import AsyncSessionLocal


STRATEGIES = (
    ("17_long_term_mom", "LTM"),
    ("09_52w_breakout", "52W"),
)


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
    if v is None:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def summarize(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    blotter = payload.get("blotter") or []
    curve = payload.get("equity_curve") or []
    book = payload.get("book_metrics") or {}
    initial = float(payload.get("initial_capital") or book.get("initial_capital") or 100_000.0)

    closed = [t for t in blotter if not t.get("open") and t.get("pnl_pct") is not None]
    pnls = [float(t["pnl_pct"]) for t in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    trades = len(pnls)
    win_rate = (len(wins) / trades) if trades else None
    if losses and wins:
        pf = abs(sum(wins) / sum(losses))
    elif wins and not losses:
        pf = float("inf")
    else:
        pf = 0.0 if trades else None
    avg_trade = (sum(pnls) / trades) if trades else None
    best = max(pnls) if pnls else None
    worst = min(pnls) if pnls else None

    cashs = [_num(p.get("cash")) for p in curve]
    cashs = [c for c in cashs if c is not None]
    avg_cash = (sum(cashs) / len(cashs)) if cashs else None
    if cashs and curve:
        expos = []
        for p in curve:
            eq = _num(p.get("equity"))
            cash = _num(p.get("cash"))
            if eq and eq > 0 and cash is not None:
                expos.append(max(0.0, min(1.0, 1.0 - cash / eq)))
        avg_exposure = (sum(expos) / len(expos)) if expos else _num(book.get("exposure"))
    else:
        avg_exposure = _num(book.get("exposure"))

    total_return = _num(book.get("total_return"))
    cagr = _num(book.get("cagr"))
    max_dd = _num(book.get("max_dd"))
    calmar = _num(book.get("calmar"))
    if total_return is None and curve:
        first = _num(curve[0].get("equity")) or initial
        last = _num(curve[-1].get("equity"))
        if first and last is not None:
            total_return = last / first - 1.0
    if cagr is None and curve:
        d0 = _as_date(curve[0].get("date"))
        d1 = _as_date(curve[-1].get("date"))
        last = _num(curve[-1].get("equity"))
        first = _num(curve[0].get("equity")) or initial
        if d0 and d1 and first and last and last > 0:
            days = max((d1 - d0).days, 1)
            cagr = (last / first) ** (365.25 / days) - 1.0
    if max_dd is None and curve:
        peak = None
        max_dd = 0.0
        for p in curve:
            eq = _num(p.get("equity"))
            if eq is None:
                continue
            peak = eq if peak is None else max(peak, eq)
            if peak:
                max_dd = min(max_dd, eq / peak - 1.0)
    if calmar is None and cagr is not None and max_dd is not None and max_dd < 0:
        calmar = cagr / abs(max_dd)

    # Transparent 0-100 composite used only for ranking in this report.
    # CAGR 40% = 100, Calmar 2.0 = 100, PF 3.0 = 100, win 70% = 100,
    # |DD| 10% = 100 / 50% = 0, avg trade 8% = 100.
    def clip(x: float) -> float:
        return max(0.0, min(100.0, x))

    cagr_s = clip(((cagr or 0.0) / 0.40) * 100.0)
    calmar_s = clip(((calmar or 0.0) / 2.0) * 100.0)
    pf_val = 3.0 if pf == float("inf") else (pf or 0.0)
    pf_s = clip((pf_val / 3.0) * 100.0)
    wr_s = clip(((win_rate or 0.0) / 0.70) * 100.0)
    dd_s = clip((1.0 - (abs(max_dd or 0.0) - 0.10) / 0.40) * 100.0) if max_dd is not None else 0.0
    avg_s = clip((((avg_trade or 0.0) / 0.08) * 100.0))
    score = (
        0.25 * cagr_s
        + 0.20 * calmar_s
        + 0.20 * pf_s
        + 0.15 * wr_s
        + 0.15 * dd_s
        + 0.05 * avg_s
    )
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

    period = None
    if curve:
        period = f"{curve[0].get('date')} → {curve[-1].get('date')}"
    elif payload.get("evaluation_date"):
        period = str(payload.get("evaluation_date"))

    return {
        "strategy": name,
        "display": payload.get("display_name") or name,
        "status": payload.get("status"),
        "evaluation_date": payload.get("evaluation_date"),
        "period": period,
        "mode": payload.get("mode"),
        "score": round(score, 1),
        "grade": grade,
        "trades": trades,
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
        "ending_equity": _num(book.get("ending_equity")) or (_num(curve[-1].get("equity")) if curve else None),
        "initial": initial,
        "open_trades": sum(1 for t in blotter if t.get("open")),
        "blotter_rows": len(blotter),
        "curve_points": len(curve),
        "buy": (payload.get("summary") or {}).get("buy"),
        "watch": (payload.get("summary") or {}).get("watch"),
        "reject": (payload.get("summary") or {}).get("reject"),
        "data_source": payload.get("data_source"),
        "survivorship_biased": payload.get("survivorship_biased"),
        "excess_vs_nifty500": _num(book.get("excess_vs_nifty500")),
    }


async def load_latest() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT strategy_id, status, scan_id, started_at, computed_at, completed_at,
                           error_code, payload
                    FROM strategy_scan_latest
                    WHERE strategy_id = ANY(:ids)
                    """
                ),
                {"ids": [s[0] for s in STRATEGIES]},
            )
        ).mappings().all()
        for row in rows:
            payload = row["payload"] or {}
            if isinstance(payload, str):
                payload = json.loads(payload)
            payload = dict(payload)
            payload["_row_status"] = row["status"]
            payload["_scan_id"] = str(row["scan_id"]) if row["scan_id"] else None
            payload["_started_at"] = str(row["started_at"]) if row["started_at"] else None
            payload["_computed_at"] = str(row["computed_at"]) if row["computed_at"] else None
            payload["_completed_at"] = str(row["completed_at"]) if row["completed_at"] else None
            payload["_error_code"] = row["error_code"]
            out[row["strategy_id"]] = payload
    return out


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

    line = "─┼─".join("─" * w for w in widths)
    print(fmt_row(header))
    print(line)
    for row in table:
        print(fmt_row(row))


async def main() -> None:
    latest = await load_latest()
    print("=== RAW LATEST ROWS ===")
    if not latest:
        print("No strategy_scan_latest rows found.")
    for sid, short in STRATEGIES:
        p = latest.get(sid)
        if not p:
            print(f"{short} ({sid}): MISSING")
            continue
        print(
            f"{short} ({sid}): row_status={p.get('_row_status')} "
            f"payload_status={p.get('status')} scan_id={p.get('_scan_id')} "
            f"completed_at={p.get('_completed_at')} error={p.get('_error_code')} "
            f"eval={p.get('evaluation_date')} blotter={len(p.get('blotter') or [])} "
            f"curve={len(p.get('equity_curve') or [])} recs={len(p.get('recommendations') or [])}"
        )
        keys = sorted((p.get("book_metrics") or {}).keys())
        print(f"  book_metrics keys={keys}")

    summaries = []
    for sid, short in STRATEGIES:
        p = latest.get(sid)
        if not p or p.get("_row_status") != "completed" or not (p.get("blotter") or p.get("equity_curve")):
            continue
        summaries.append(summarize(short, p))
    summaries.sort(key=lambda r: r["score"], reverse=True)

    print("\n=== RANKED COMPARISON ===")
    if summaries:
        print_table(summaries)
        out_path = Path(__file__).with_name("strategy_backtest_comparison.json")
        out_path.write_text(json.dumps(summaries, indent=2, default=str), encoding="utf-8")
        print(f"\nWrote {out_path}")
    else:
        print("No completed backtest payloads with blotter/curve to rank.")


if __name__ == "__main__":
    asyncio.run(main())
