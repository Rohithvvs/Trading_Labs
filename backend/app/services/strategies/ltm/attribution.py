"""Per-name 1Y book-trade returns and Top 5 / Least 5 boards."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .book_engine import Trade


def window_start(end: date, *, years: int = 1) -> date:
    try:
        return end.replace(year=end.year - years)
    except ValueError:
        return end - timedelta(days=365 * years)


def _overlaps_window(tr: Trade, start: date, end: date) -> bool:
    entry = tr.entry_date
    exit_d = tr.exit_date or end
    return entry <= end and exit_d >= start


def per_name_backtests(
    trades: list[Trade],
    *,
    asof: date,
    years: int = 1,
    history_valid: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    start = window_start(asof, years=years)
    by_sym: dict[str, list[Trade]] = {}
    for tr in trades:
        if history_valid is not None and tr.symbol not in history_valid:
            continue
        if not _overlaps_window(tr, start, asof):
            continue
        by_sym.setdefault(tr.symbol, []).append(tr)

    reports: dict[str, dict[str, Any]] = {}
    for sym, items in by_sym.items():
        closed = [t for t in items if not t.open]
        marked = [t for t in items if t.open]
        all_t = closed + marked
        rets = [t.pnl_pct for t in all_t if t.pnl_pct is not None]
        wins = [r for r in rets if r > 0]
        losses = [r for r in rets if r <= 0]
        net = 1.0
        for r in rets:
            net *= 1.0 + r
        net_return = net - 1.0
        win_rate = (len(wins) / len(rets)) if rets else 0.0
        profit_factor = None
        if losses:
            profit_factor = (sum(wins) / abs(sum(losses))) if wins else 0.0
        elif wins:
            profit_factor = float("inf")
        best = max(all_t, key=lambda t: t.pnl_pct or -999, default=None)
        worst = min(all_t, key=lambda t: t.pnl_pct or 999, default=None)
        reports[sym] = {
            "window_start": start.isoformat(),
            "window_end": asof.isoformat(),
            "trade_count": len(all_t),
            "net_return": net_return,
            "win_rate": win_rate,
            "max_drawdown": min((r for r in rets if r < 0), default=0.0),
            "profit_factor": profit_factor,
            "never_selected_in_window": False,
            "trades": all_t,
            "best_trade": best,
            "worst_trade": worst,
        }
    return reports


def empty_backtest(asof: date, *, years: int = 1) -> dict[str, Any]:
    return {
        "window_start": window_start(asof, years=years).isoformat(),
        "window_end": asof.isoformat(),
        "trade_count": 0,
        "net_return": None,
        "win_rate": None,
        "max_drawdown": None,
        "profit_factor": None,
        "never_selected_in_window": True,
        "trades": [],
        "best_trade": None,
        "worst_trade": None,
    }


def build_boards(
    reports: dict[str, dict[str, Any]],
    signals: dict[str, str],
    *,
    top_n: int = 5,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    qualified = [
        (sym, rep)
        for sym, rep in reports.items()
        if not rep.get("never_selected_in_window") and rep.get("trade_count", 0) > 0
    ]

    def to_row(rank: int, sym: str, rep: dict[str, Any]) -> dict[str, Any]:
        pf = rep.get("profit_factor")
        return {
            "rank": rank,
            "symbol": sym,
            "signal": signals.get(sym, "REJECT"),
            "return": rep["net_return"],
            "trades": rep["trade_count"],
            "win_rate": rep["win_rate"],
            "max_dd": rep.get("max_drawdown"),
            "profit_factor": pf if pf != float("inf") else None,
            "profit_factor_infinite": pf == float("inf"),
        }

    positive = [(s, r) for s, r in qualified if (r.get("net_return") or 0) > 0]
    positive.sort(key=lambda item: (-(item[1]["net_return"] or 0), item[0]))
    top5 = [to_row(i + 1, s, r) for i, (s, r) in enumerate(positive[:top_n])]

    all_q = list(qualified)
    all_q.sort(key=lambda item: ((item[1]["net_return"] if item[1]["net_return"] is not None else 0), item[0]))
    least5 = [to_row(i + 1, s, r) for i, (s, r) in enumerate(all_q[:top_n])]
    return top5, least5
